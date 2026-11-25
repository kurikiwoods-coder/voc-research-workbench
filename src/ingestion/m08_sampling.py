"""Bind synthetic sampling checkpoints to M03, M04, M05 and exact M06 intervals."""

from collections import Counter
from contextlib import closing
import csv
from datetime import date, timedelta
from io import BytesIO, StringIO
import json
import sqlite3
from types import SimpleNamespace

from openpyxl import Workbook

from src.execution.transport import ENDPOINTS, Response
from src.ingestion.import_files import ImportProblem, list_sheets, read_sheet
from src.ingestion.import_mapping import evaluate
from src.ingestion.m08_acquisition import DEMO_QUERY, FIXTURE_KEYS, OFFLINE_DOMAINS, STAGES, PlanError, build_plan, source_catalog
from src.ingestion.m08_platforms import ADAPTER_VERSION, FIXTURE_SOURCES, STACK, YOUTUBE, platform_catalog, retrieve_fixture
from src.ingestion.m08_retrieval import normalize_url
from src.ingestion.m08_search import FALLBACK_ERRORS, preview_queries, search
from src.ingestion.m08_tasks import AcquisitionTaskStore, AuthorizationBlocked, CheckpointResult
from src.raw_store.corpus import CorpusStore
from src.raw_store.denominators import EARLY, EXTRACTED
from src.raw_store.imports import ImportStore
from src.raw_store.mention_segments import EvidenceInterval, validate_interval
from src.raw_store.store import SQLITE_TIMEOUT, Conflict, Store, dump, now


ACTOR = "local-workspace"
POLICY = "m08-synthetic-sampling-v1"
UNITS = {
    "tavily": "tavily_credit", "brave": "brave_request",
    STACK: "stackexchange_request", YOUTUBE: "youtube_quota_unit",
}
FIELDS = ("raw_text", "source_type", "source_url", "published_at", "lang", "external_id", "content_role")
IMPORT_RECEIPTS = """CREATE TABLE IF NOT EXISTS m08_import_receipts (
    request_id TEXT PRIMARY KEY NOT NULL,
    batch_id TEXT NOT NULL UNIQUE REFERENCES import_batches(batch_id),
    payload TEXT NOT NULL CHECK(json_valid(payload))
) STRICT"""


def sampling_config(studies, study_id, form):
    options = {key: form[key] for key in (
        "source_ids", "sample_target", "per_source_limit", "query_limit", "page_limit",
        "batch_count", "budgets", "fixture_scenario", "fallback_format",
    )}
    data = {key: value for key, value in form.items() if key not in options and key != "request_key"}
    catalog = {row["source_id"]: row for row in (*source_catalog({})["sources"], *platform_catalog())}
    source_ids = options["source_ids"]
    if not set(source_ids) <= FIXTURE_SOURCES:
        raise AuthorizationBlocked("current_authorization_required")
    domains = sorted({domain for key in source_ids for domain in catalog[key]["allowed_domains"]})
    if not set(data["allowed_domains"]) <= {*domains, *OFFLINE_DOMAINS}:
        raise PlanError("来源域名须在选定适配器的白名单中。")
    plan = build_plan(studies, study_id, {**data, **DEMO_QUERY, "allowed_domains": list(OFFLINE_DOMAINS)})
    ends = plan["date_from"], plan["date_to"]
    start = ends[0] or ends[1] or "2023-11-14"
    end = ends[1] or ends[0] or start
    providers = plan["providers"]
    if options["fallback_format"] != "none" and options["fixture_scenario"] != "source_unavailable":
        raise PlanError("文件兜底只用于来源中断演练。")
    if options["fixture_scenario"] == "primary_unavailable" and plan["mode"] != "fallback":
        raise PlanError("搜索故障演练需要选择备用搜索策略。")
    plan.update(allowed_domains=domains, limit=20, date_from=start, date_to=end)
    allocations = _allocation(options)
    sources = [{"source_id": key, "adapter_version": catalog[key]["adapter_version"]}
               for key in [*(f"m08-{provider}" for provider in providers), *source_ids]]
    checkpoints = []
    for batch, sizes in enumerate(allocations, start=1):
        for rank, provider in enumerate(providers):
            checkpoints.append({
                "key": f"query-{batch}-{rank}", "kind": "query", "source_id": f"m08-{provider}",
                "unit": UNITS[provider], "units": 1, "input": {"batch": batch, "rank": rank, "sizes": sizes},
            })
        for source, size in sizes.items():
            checkpoints.append({
                "key": f"page-{batch}-{source}", "kind": "page", "source_id": source,
                "unit": UNITS[source], "units": (size + 1) // 2, "request_count": (size + 1) // 2,
                "input": {"batch": batch, "size": size},
            })
        checkpoints.append({
            "key": f"import-{batch}", "kind": "import", "source_id": next(iter(sizes)),
            "input": {"batch": batch, "sizes": sizes},
        })
    return {
        **options, "study_id": study_id, "scope_id": plan["scope_id"], "scope_version": plan["scope_version"],
        "mode": "synthetic", "window_start": start, "window_end": end, "frozen_at": plan["frozen_at"],
        "research_goal": DEMO_QUERY["research_goal"], "query_plan": {
            "version": POLICY, "inputs": plan, "queries": preview_queries(plan, providers=providers, limit=20),
        },
        "authorization": {"policy": POLICY, "principal": ACTOR},
        "sources": sources, "source_limits": dict.fromkeys(source_ids, options["per_source_limit"]),
        "checkpoints": checkpoints, "budgets": {
            UNITS[key]: {"authorized": options["budgets"].get(UNITS[key], 200), "available": 200}
            for key in (*providers, *source_ids)
        },
    }


def _allocation(options):
    sources, batches = options["source_ids"], options["batch_count"]
    target = options["sample_target"]
    available = dict.fromkeys(sources, options["per_source_limit"])
    allocations = []
    for index in range(batches):
        desired, extra = divmod(target, batches)
        size = desired + (index < extra)
        if not 1 <= size <= 40:
            raise PlanError("每个合成批次可分配 1 至 40 条片段。")
        remaining = size
        allocation = Counter()
        while remaining:
            ordered = sources[index % len(sources):] + sources[:index % len(sources)]
            eligible = [source for source in ordered if available[source]]
            if not eligible:
                raise PlanError("单来源上限不足以覆盖样本目标。")
            for source in eligible[:remaining]:
                allocation[source] += 1
                available[source] -= 1
                remaining -= 1
        if sum((count + 1) // 2 for count in allocation.values()) > 20:
            raise PlanError("请调整单批目标，使取证对象数处于 20 个以内。")
        allocations.append(dict(allocation))
    return allocations


def _fixture_records(config, batch, source, segments):
    return retrieve_fixture(source, batch_no=batch, limit=(segments + 1) // 2,
                            published_date=config["window_start"])


def _same_batch(attempts, checkpoint, kind):
    return [item["receipt"] for item in attempts
            if item["receipt"] is not None and item["checkpoint"]["kind"] == kind
            and item["checkpoint"]["input"]["batch"] == checkpoint["input"]["batch"]]


def should_dispatch(config, checkpoint, attempts):
    if (checkpoint["kind"] == "query" and checkpoint["input"]["rank"] == 1
            and config["query_plan"]["inputs"]["mode"] == "fallback"):
        prior = _same_batch(attempts, checkpoint, "query")
        return bool(prior and prior[0].get("error") in FALLBACK_ERRORS)
    return True


def _completed(attempts, kind):
    return [item for item in attempts if item["checkpoint"]["kind"] == kind and item["state"] == "reconciled"]


def _queries_complete(checkpoints, queries):
    if len(queries) != sum(checkpoint["kind"] == "query" for checkpoint in checkpoints):
        return False
    switches = {(item["checkpoint"]["input"]["batch"], item["receipt"]["switch"]["from"])
                for item in queries if item["receipt"].get("switch") and not item["receipt"]["error"]}
    return all(not item["receipt"].get("error")
               or (item["checkpoint"]["input"]["batch"], item["receipt"]["provider"]) in switches
               for item in queries)


def _query(config, checkpoint, attempts):
    plan = config["query_plan"]["inputs"]
    batch, sizes = (checkpoint["input"][key] for key in ("batch", "sizes"))
    provider = checkpoint["source_id"][4:]
    previous = _same_batch(attempts, checkpoint, "query")
    if not should_dispatch(config, checkpoint, attempts):
        return CheckpointResult({"status": "skipped_by_fallback_policy"})
    urls = [record["canonical_url"] for source, size in sizes.items()
            for record in _fixture_records(config, batch, source, size)]

    def transport(method, url, request, headers):
        if config["fixture_scenario"] == "primary_unavailable" and not checkpoint["input"]["rank"]:
            return Response(503, {})
        hits = [{"url": value} for value in urls]
        if method == "POST" and url == ENDPOINTS["tavily"]:
            return Response(200, {"results": hits, "usage": {"credits": 1}})
        if method == "GET" and url.startswith(ENDPOINTS["brave"] + "?"):
            return Response(200, {"web": {"results": hits}})
        raise ValueError("Unknown synthetic search request")

    attempt = search(SimpleNamespace(keys=FIXTURE_KEYS), plan, mode="independent", providers=[provider],
                     labels={"public_approved"}, limit=20, transport=transport)["attempts"][0]
    for hit in attempt["hits"]:
        hit["canonical_url"] = normalize_url(hit["url"], plan["allowed_domains"])
    if previous and plan["mode"] == "fallback":
        attempt["switch"] = {"from": previous[0]["provider"], "to": provider, "reason": previous[0]["error"]}
    advance = (not attempt["error"] or plan["mode"] == "merge"
               or (plan["mode"] == "fallback" and not previous and attempt["error"] in FALLBACK_ERRORS))
    return CheckpointResult(attempt, int(attempt["sent"]), "completed" if advance else "paused",
                            None if advance else "search_failed")


def _page(config, checkpoint, attempts):
    source = checkpoint["source_id"]
    batch, size = (checkpoint["input"][key] for key in ("batch", "size"))
    if config["fixture_scenario"] == "source_unavailable":
        outcome = "completed" if config["fallback_format"] != "none" else "paused"
        return CheckpointResult({"status": "source_unavailable", "records": []}, 1, outcome,
                                None if outcome == "completed" else "source_unavailable")
    discovered = {hit["canonical_url"] for receipt in _same_batch(attempts, checkpoint, "query")
                  for hit in receipt.get("hits", [])}
    records = [record for record in _fixture_records(config, batch, source, size)
               if record["canonical_url"] in discovered]
    remaining = size
    for record in records:
        record["segments"] = record["segments"][:remaining]
        remaining -= len(record["segments"])
    return CheckpointResult({"status": "accessed" if records else "no_discovery", "records": records},
                            len(records))


def _isolated_directory(directory, task_id):
    return directory / "m08-sampling" / "tasks" / task_id


def _isolated_store(directory, task_id):
    return Store(_isolated_directory(directory, task_id))


def _bind_project(db, studies, config):
    study_id, scope_id = config["study_id"], config["scope_id"]
    project, scope = studies.get(study_id), studies.get_scope(study_id, scope_id)
    content = {key: scope[key] for key in ("date_window", "product_category_ids", "product_ids")}

    with db.db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM study_scope_freezes WHERE study_id=? AND scope_id=?",
                              (study_id, scope_id)).fetchone():
            return
        connection.execute("""INSERT INTO study_projects
            (study_id, request_key, request_digest, name, description, background, objective, subject,
             status, revision, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) ON CONFLICT(study_id) DO NOTHING""",
                           (study_id, study_id, POLICY, "M08 合成项目", "", "", "", "",
                            "active", project["created_at"], project["created_at"]))
        connection.execute("""INSERT INTO study_scopes
            (study_id, scope_id, version_no, content_json, changed_fields_json, change_note, created_at)
            VALUES (?, ?, ?, ?, '[]', '', ?)""",
                           (study_id, scope_id, int(scope["scope_version"][1:]), dump(content), scope["created_at"]))
        connection.execute("INSERT INTO study_scope_freezes VALUES (?, ?, ?)",
                           (study_id, scope_id, scope["frozen_at"]))


def _workbook(records, kind, language):
    values = [FIELDS, *((
        record["body"], "youtube" if record["source_id"] == YOUTUBE else "forum",
        record["source_locator"], record["published_at"], language, record["source_object_id"], "synthetic",
    ) for record in records)]
    if kind == "csv":
        stream = StringIO(newline="")
        csv.writer(stream).writerows(values)
        return stream.getvalue().encode("utf-8-sig")
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("M08 Synthetic")
    for row in values:
        sheet.append(row)
    binary = BytesIO()
    workbook.save(binary)
    return binary.getvalue()


def _import(config, checkpoint, attempts, request_id, *, directory, studies, authorize):
    pages = _same_batch(attempts, checkpoint, "page")
    records = [record for page in pages for record in page["records"] if record["segments"]]
    batch, sizes = (checkpoint["input"][key] for key in ("batch", "sizes"))
    fallback = not records and config["fallback_format"] != "none"
    if fallback:
        for source, size in sizes.items():
            fixtures = _fixture_records(config, batch + 100, source, size)
            for index, record in enumerate(fixtures):
                record["segments"] = record["segments"][:size - index * 2]
                record.update(method="authorized_synthetic_file", fetched_at=None)
            records.extend(fixtures)
    if not records:
        planned = [item for item in config["checkpoints"] if item["input"]["batch"] == batch]
        queries = [item for item in _completed(attempts, "query") if item["checkpoint"]["input"]["batch"] == batch]
        if (pages and all(page["status"] == "no_discovery" for page in pages)
                and _queries_complete(planned, queries) and all(not item["receipt"].get("hits") for item in queries)):
            return CheckpointResult({"status": "empty", "evidence": []})
        return CheckpointResult({"status": "no_extractable_records", "evidence": []}, outcome="failed",
                                reason="no_extractable_records")
    kind = config["fallback_format"] if fallback else "csv"
    plan = config["query_plan"]["inputs"]
    db = _isolated_store(directory, config["acquisition_task_id"])
    _bind_project(db, studies, config)
    study_id, scope_id = config["study_id"], config["scope_id"]
    imports, corpus = ImportStore(db), CorpusStore(db)
    data = _workbook(records, kind, plan["language"] or "")
    file = imports.upload(study_id, scope_id, f"m08-synthetic-{batch}.{kind}", kind, data, list_sheets(data, kind))
    scope = imports.check_target(study_id, scope_id)
    sheet = read_sheet(data, kind, 0)
    mapping = {field: index for index, field in enumerate(FIELDS)}
    rows, summary, _ = evaluate(sheet, mapping, scope, "unknown")
    if len(rows) != len(records) or any(row["status"] in {"duplicate", "rejected"} for row in rows):
        raise ImportProblem("合成采样批次未通过 M04 质量校验。")
    repeated = Counter(record["raw_sha256"] for record in records)
    prior = {item["raw_sha256"] for attempt in attempts if attempt["state"] == "reconciled"
             for item in (attempt["receipt"] or {}).get("evidence", ())}
    authorize(config)
    evidence = []
    with imports.write() as connection:
        connection.execute(IMPORT_RECEIPTS)
        receipt = imports.commit_in_transaction(connection, file, sheet, 0, mapping, "unknown",
                                                request_id, rows, summary)
        stamp = now()
        retention = (date.fromisoformat(stamp[:10]) + timedelta(days=30)).isoformat()
        for row, source in zip(rows, records, strict=True):
            ident = f"{receipt['batch_id']}:{row['line_number']}"
            corpus._review_in_transaction(
                connection, stamp, study_id, ident, "verified", "synthetic", "固定合成夹具",
                "本地 M08 工程测试授权", retention, "authorized", "local:m08-synthetic-sampling-v1",
            )
            record = corpus.describe(connection, corpus.source_row(connection, study_id, ident, stamp[:10]), stamp[:10])
            for segment in source["segments"]:
                interval = EvidenceInterval(ident, source["raw_sha256"], segment["start"], segment["end"])
                text = validate_interval(interval, record, study_id=study_id, scope_id=scope_id)
                if text != segment["text"]:
                    raise Conflict("合成片段与当前原文不一致。")
                evidence.append({
                    "study_id": study_id, "scope_id": scope_id, "scope_version": config["scope_version"],
                    "batch_id": receipt["batch_id"], "record_id": ident, "source_id": source["source_id"],
                    "source_object_id": source["source_object_id"], "object_kind": source["object_kind"],
                    "source_locator": source["source_locator"], "published_at": source["published_at"],
                    "method": source["method"], "role": "synthetic", "raw_sha256": interval.raw_sha256,
                    "collected_at": source["fetched_at"], "modified_at": source["modified_at"],
                    "license_reference": source["license_reference"], "attribution": source["attribution"],
                    "response_body_sha256": source["response_body_sha256"],
                    "start_cp": interval.start_cp, "end_cp": interval.end_cp,
                    "extraction_version": segment["extraction_version"],
                    "identity_status": ("cross_source_review_pending" if repeated[interval.raw_sha256] > 1
                                        or interval.raw_sha256 in prior else "distinct_source_object"),
                    "mention_id": None, "evidence_id": None, "segment_revision": None, "registry_version": None,
                })
        authorize(config)
        payload = {"status": "imported", "batch_id": receipt["batch_id"], "format": kind,
                   "fallback": fallback, "summary": summary, "evidence": evidence}
        connection.execute("INSERT INTO m08_import_receipts VALUES (?, ?, ?)",
                           (request_id, receipt["batch_id"], dump(payload)))
    return CheckpointResult(payload)


class SamplingTasks:
    def __init__(self, directory, studies, permission=None):
        self.directory = directory
        self.studies = studies
        self.permission = permission
        self.ledger = AcquisitionTaskStore(directory / "m08-sampling" / "ledger.sqlite3")

    def authorize_project(self, study_id):
        project = self.studies.get(study_id)
        if self.permission is not None and self.permission(study_id, None) is not True:
            raise AuthorizationBlocked("project_permission_required")
        return project

    def authorize(self, config):
        study_id = config["study_id"]
        project = self.authorize_project(study_id)
        scope = self.studies.get_scope(study_id, config["scope_id"])
        if (project["status"] == "archived" or scope["scope_version"] != config["scope_version"]
                or scope["frozen_at"] != config["frozen_at"]
                or config["authorization"] != {"policy": POLICY, "principal": ACTOR}):
            raise AuthorizationBlocked("scope_permission_changed")
        versions = {row["source_id"]: row["adapter_version"]
                    for row in (*source_catalog({})["sources"], *platform_catalog())
                    if row["enabled_status"] == "offline_fixture"}
        for source in config["sources"]:
            ident = source["source_id"]
            if (versions.get(ident) != source["adapter_version"]
                    or (self.permission is not None and self.permission(study_id, ident) is not True)):
                raise AuthorizationBlocked("source_permission_changed")
        return True

    def work(self, config, checkpoint, request_id):
        self.authorize(config)
        task = self.ledger.get(config["study_id"], config["acquisition_task_id"])
        attempts = task["attempts"]
        kind = checkpoint["kind"]
        if kind == "query":
            return _query(config, checkpoint, attempts)
        if kind == "page":
            return _page(config, checkpoint, attempts)
        if kind == "import":
            return _import(config, checkpoint, attempts, request_id, directory=self.directory, studies=self.studies,
                           authorize=self.authorize)
        raise ValueError("Unknown sampling checkpoint")

    def recover(self, config, checkpoint, request_id):
        path = _isolated_directory(self.directory, config["acquisition_task_id"]) / "connectivity.sqlite3"
        if not path.is_file():
            return None
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=SQLITE_TIMEOUT)) as db:
            db.execute("BEGIN")
            if not db.execute("SELECT 1 FROM sqlite_schema WHERE name='m08_import_receipts' AND type='table'").fetchone():
                return None
            row = db.execute("SELECT payload FROM m08_import_receipts WHERE request_id=?", (request_id,)).fetchone()
        return CheckpointResult(json.loads(row[0])) if row else None

    def project_view(self, task):
        config = task["config"]
        self.authorize(config)
        engineering = dict.fromkeys(STAGES)
        attempts = task["attempts"]
        queries = _completed(attempts, "query")
        pages = [item["receipt"] for item in _completed(attempts, "page")]
        imports = [item["receipt"] for item in _completed(attempts, "import")]
        if _queries_complete(config["checkpoints"], queries):
            engineering[EARLY[0]] = len({hit["canonical_url"] for item in queries
                                         for hit in item["receipt"].get("hits", [])})
            if (len(pages) == sum(item["kind"] == "page" for item in config["checkpoints"])
                    and all(item["status"] in {"accessed", "no_discovery"} for item in pages)):
                engineering[EARLY[1]] = len({record["canonical_url"] for item in pages
                                            for record in item["records"] if record["accessible"]})
        if len(imports) == config["batch_count"] and all(item["status"] in {"imported", "empty"} for item in imports):
            engineering[EXTRACTED] = sum(len(item["evidence"]) for item in imports)
        for item in attempts:
            if item["checkpoint"]["kind"] != "page" or not item["receipt"]:
                continue
            for record in item["receipt"]["records"]:
                record.pop("body", None)
                for segment in record["segments"]:
                    segment.pop("text", None)
        return {
            **task, "source_ids": task["config"]["source_ids"], "engineering_funnel": engineering,
            "local_recovery_available": any(
                item["state"] == "reserved" and item["checkpoint"]["kind"] == "import"
                and self.recover({**task["config"], "acquisition_task_id": task["acquisition_task_id"]},
                                 item["checkpoint"], item["request_id"]) is not None
                for item in attempts
            ),
            "formal_funnel": dict.fromkeys(STAGES), "failure_count": sum(
                bool(item["outcome"] != "skipped" and item["receipt"] and (item["reason"] or item["receipt"].get("error")
                     or item["receipt"].get("status") == "source_unavailable")) for item in attempts
            ),
        }

    def evidence(self, config, item):
        self.authorize(config)
        corpus = CorpusStore(_isolated_store(self.directory, config["acquisition_task_id"]))
        record = corpus.detail(config["study_id"], item["record_id"])
        if (record["status"] != "verified" or record["license_status"] != "authorized"
                or record["role"] != "synthetic" or record["trace"]["scope_version"] != config["scope_version"]
                or record["trace"]["batch_id"] != item["batch_id"]):
            raise AuthorizationBlocked("current_evidence_permission_required")
        interval = EvidenceInterval(item["record_id"], item["raw_sha256"], item["start_cp"], item["end_cp"])
        text = validate_interval(interval, record, study_id=config["study_id"], scope_id=config["scope_id"])
        self.authorize(config)
        return {**item, "text": text, "engineering_eligible": record["engineering_eligible"],
                "research_eligible": record["research_eligible"], "outbound_allowed": record["outbound_allowed"]}
