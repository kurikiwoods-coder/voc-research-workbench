"""Measure C5 from synthetic CSV to real M05/C3/SQLite reconciliation.

Run as `python -m scripts.benchmark_m06_denominators` from the repository root.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
from time import perf_counter, sleep
from unittest.mock import patch
from urllib.parse import quote
from uuid import UUID

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from src.ingestion.import_files import MAX_ROWS
from src.raw_store.corpus import (
    CANDIDATE, SOURCE_ROWS, STATISTICS_BATCH_ROWS, STATISTICS_SINGLE_ROW, CorpusStore,
)
from src.raw_store.denominators import SyntheticDecision, synthetic_database
from src.raw_store.mentions import (
    EvidenceInterval, MentionDraft, MentionStore, ProductProposal, ReviewDecision, SupportDraft,
)
from src.raw_store.relations import RelationGrant, RelationStore
from src.raw_store.store import Store, now


ORIGIN = "http://127.0.0.1:8765"
ACTOR = "synthetic-scale-reviewer"
BASIS = "local:synthetic-scale"
PRODUCTS = ("P-SYN-A", "P-SYN-B")
SOURCES = ("forum", "reddit")
MAIN_TASK = "TASK-SYN-PRIMARY"
SECONDARY_TASK = "TASK-SYN-SECONDARY"
INTENT = "INTENT-SYN"
ORPHAN = "INTENT-SYN-WAIT-PRIMARY"
VERSIONS = ("1.0.0", "2.0.0")
HEADERS = ("raw_text", "source_type", "source_url", "published_at", "access_policy", "privacy", "external_id",
           "product_category_id")
BUCKETS = ("published_classified", "none_unknown", "review_pending", "partial_or_schema_gap", "pending_parent", "other_pending")


def ok(response):
    assert response.is_success, (response.request.method, response.request.url.path, response.text)
    return response.json()


def insert(db, table, **values):
    columns = ", ".join(values)
    parameters = ", ".join("?" for _ in values)
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({parameters})", tuple(values.values()))


def command(db, identifier, study=None):
    insert(db, "m06_command", command_id=identifier, study_id=study,
           namespace=f"study:{study}" if study else "global", operation="fixture",
           idempotency_key=identifier, input_hash=sha256(identifier.encode()).hexdigest(),
           actor_ref=ACTOR, reason="synthetic benchmark design", created_at=now(), result_ref="{}")


def freeze_scopes(client):
    design = {"name": "C5 合成规模", "scope": {"mode": "cross_category", "topic": "合成范围一",
                                                "product_category_ids": list(PRODUCTS)}}
    created = ok(client.post("/api/studies", json=design | {"request_key": str(UUID(int=1))}))
    study = created["study_id"]
    first = created["scope"]["scope_id"]
    endpoint = f"/api/studies/{study}"
    frozen = ok(client.post(f"{endpoint}/scopes/{first}/freeze"))
    updated = ok(client.put(endpoint, json=design | {"revision": frozen["revision"],
        "change_note": "合成第二范围", "scope": design["scope"] | {"topic": "合成范围二"}}))
    second = updated["scope"]["scope_id"]
    ok(client.post(f"{endpoint}/scopes/{second}/freeze"))
    return study, (first, second)


def synthetic_row(group, slot):
    key = f"{group}-{slot}"
    source = SOURCES[slot % 2]
    text = f"合成发生 {group}：产品甲与产品乙都要离线工作。"
    if slot not in (0, 1, 2):
        text += f" 合成样本文本 {slot}。"
    return (text, source, f"https://{source}.synthetic.invalid/post/{key}",
            "2026-11-11" if slot % 2 == 0 else "2026-11-13", "合成许可夹具", "public", key,
            PRODUCTS[slot % 2])


def import_batch(client, store, study, scope, groups, slots, index):
    generated_at = perf_counter()
    labels = [(group, slot) for group in groups for slot in slots]
    data = StringIO(newline="")
    writer = csv.writer(data)
    writer.writerow(HEADERS)
    writer.writerows(synthetic_row(*label) for label in labels)
    payload = data.getvalue().encode()
    generation = perf_counter() - generated_at
    started = perf_counter()
    root = f"/api/imports/{study}"
    receipt = ok(client.post(f"{root}/scopes/{scope}/uploads", content=payload, headers={
        "Content-Type": "application/octet-stream", "X-VOC-Filename": quote(f"合成-{index}.csv"),
    }))
    url = f"{root}/uploads/{receipt['file_id']}"
    plan = {"sheet_index": 0, "mapping": ok(client.get(url))["suggested_mapping"], "privacy": "public"}
    preview = ok(client.post(url + "/preview", json=plan))
    saved = ok(client.post(url + "/confirm", json=plan | {"preview_token": preview["preview_token"]}))
    rows = store.rows("SELECT record_id, line_number, status FROM import_rows WHERE batch_id=? ORDER BY line_number",
                      (saved["batch_id"],))
    assert len(rows) == len(labels) and all(row["status"] in {"staged", "pending_review"} for row in rows)
    return {key: row["record_id"] for key, row in zip(labels, rows, strict=True)}, generation, perf_counter() - started


def import_fixture(client, store, study, scopes, group_count):
    records = {}
    generation = import_time = 0.0
    batches = 0
    for parity, scope in enumerate(scopes):
        for slots in ((0, 3, 4, 5, 6, 7, 8, 9), (1,), (2,)):
            groups = range(parity, group_count, len(scopes))
            width = MAX_ROWS // len(slots)
            for start in range(0, len(groups), width):
                new, generated, elapsed = import_batch(client, store, study, scope, groups[start:start + width], slots, batches)
                records.update(new)
                generation += generated
                import_time += elapsed
                batches += 1
    return records, batches, {"csv_generation_s": generation, "csv_import_s": import_time}


def record_review(corpus, study, record, retention, *, licensed=True):
    if not licensed:
        return corpus.review(study, record, "excluded", "user_quote", "合成复核：授权已撤销",
                             license_status="revoked")
    return corpus.review(study, record, "verified", "user_quote", "合成审核", "本机核对合成原文与许可",
                         retention, "authorized", BASIS + "-license")


def qualify_fixture(store, study, records):
    corpus = CorpusStore(store)
    current_day = datetime.now(UTC).date()
    retention = (current_day + timedelta(days=30)).isoformat()
    expired_day = (current_day - timedelta(days=1)).isoformat()
    def review_chunk(items, at, deadline):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for record in items:
                review_id = corpus._review_in_transaction(
                    db, at, study, record, "verified", "user_quote", "合成审核", "本机核对合成原文与许可",
                    deadline, "authorized", BASIS + "-license",
                )
                assert type(review_id) is int

    historical = [record for (_, slot), record in records.items() if slot == 9]
    current = [record for (_, slot), record in records.items() if slot < 8]
    for items, at, deadline in ((historical, expired_day + "T00:00:00Z", expired_day), (current, now(), retention)):
        for offset in range(0, len(items), 500):
            if offset % 10000 == 0:
                print(f"M05 processed {offset}/{len(items)} reviews through {deadline}", file=sys.stderr, flush=True)
            review_chunk(items[offset:offset + 500], at, deadline)
    return retention


def check_review_rollback(store, study, record, retention):
    corpus = CorpusStore(store)
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        at = now()
        review_id = corpus._review_in_transaction(
            db, at, study, record, "verified", "user_quote", "合成审核", "本机核对合成原文与许可",
            retention, "authorized", BASIS + "-license",
        )
        try:
            corpus._review_in_transaction(db, at, study, record, "invalid", "user_quote", "合成审核")
        except ValueError:
            db.rollback()
        else:
            raise AssertionError("M05 accepted an invalid decision")
        assert db.execute("SELECT 1 FROM corpus_snapshots WHERE record_id=?", (record,)).fetchone() is None
        assert db.execute("SELECT 1 FROM corpus_reviews WHERE review_id=?", (review_id,)).fetchone() is None
        assert db.execute("SELECT 1 FROM corpus_licenses WHERE review_id=?", (review_id,)).fetchone() is None
    assert not corpus.detail(study, record)["engineering_eligible"]


def install_registry(store, study, scopes, representatives):
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        for index, version in enumerate(VERSIONS):
            key = f"registry-{version}"
            command(db, key)
            insert(db, "m06_registry", registry_version=version, parent_version=VERSIONS[index - 1] if index else None,
                   created_at=now(), command_id=key, sealed=0)
            for product in PRODUCTS:
                insert(db, "m06_product", registry_version=version, product_category_id=product, name=product,
                       description="合成产品", parent_id=None, status="confirmed", version=version)
            for task in (MAIN_TASK, SECONDARY_TASK):
                insert(db, "m06_task", registry_version=version, category_id=task, name=task,
                       definition="合成任务", inclusion_criteria="合成纳入", exclusion_criteria="合成排除",
                       discovery="preset", lifecycle_status="confirmed", version=version)
            for intent, lifecycle, primary in ((INTENT, "confirmed", MAIN_TASK), (ORPHAN, "pending_parent", None)):
                insert(db, "m06_intent", registry_version=version, intent_id=intent, name=intent, definition="合成定义",
                       inclusion_criteria="合成纳入", exclusion_criteria="合成排除", lifecycle_status=lifecycle,
                       primary_category_id=primary, survey_validation_status="unvalidated", version=version)
            for task in (MAIN_TASK, SECONDARY_TASK):
                insert(db, "m06_intent_task", registry_version=version, intent_id=INTENT, category_id=task,
                       is_primary=int(task == MAIN_TASK))
            for entry in representatives:
                insert(db, "m06_representative", registry_version=version, intent_id=INTENT, study_id=study,
                       segment_revision=1, mention_id=entry["mention_id"], evidence_id=entry["evidence_ids"][0])
            db.execute("UPDATE m06_registry SET sealed=1 WHERE registry_version=?", (version,))
            for scope_index, scope in enumerate(scopes):
                key = f"mapping-{scope_index}-{index}"
                command(db, key, study)
                for product in PRODUCTS:
                    insert(db, "m06_scope_product", study_id=study, scope_id=scope, mapping_revision=index + 1,
                           registry_version=version, product_category_id=product)
                insert(db, "m06_scope_binding", study_id=study, scope_id=scope, mapping_revision=index + 1,
                       previous_revision=index or None, registry_version=version, mapping_status="mapped_product",
                       scope_reviewer_ref=ACTOR, catalog_reviewer_ref=ACTOR, basis_ref=BASIS, command_id=key)


PRIMARY_SLOTS = (0, 2, 3, 4, 5, 6)


def evidence_interval(group, slot, records):
    text = synthetic_row(group, slot)[0]
    return EvidenceInterval(records[(group, slot)], sha256(text.encode()).hexdigest(), 0, len(text))


def evidence_drafts(group, records):
    for slot in PRIMARY_SLOTS:
        original = evidence_interval(group, slot, records)
        supports = (SupportDraft(original, slot + 1, "independent", BASIS),)
        if slot == 0:
            repost = evidence_interval(group, 1, records)
            supports += (SupportDraft(repost, 2, "repost", BASIS, original=original),)
        yield MentionDraft(f"group-{group}-slot-{slot}", supports)


def proposal_products(draft):
    slot = int(draft.ref.rsplit("-", 1)[-1])
    for support in draft.supports:
        products = PRODUCTS if slot == 0 and support.identity == "independent" else (PRODUCTS[(support.segment_no - 1) % 2],)
        for product in products:
            yield support.interval, product


def database_sizes(store):
    return {"database_bytes": store.path.stat().st_size,
            "wal_bytes": Path(f"{store.path}-wal").stat().st_size if Path(f"{store.path}-wal").exists() else 0}


def checkpoint(db):
    status, _, _ = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    assert status == 0


def segment_fixture(store, study, scopes, records, group_count):
    mentions = MentionStore(store, authorize=lambda candidate, _: ACTOR if candidate == study else None)
    started = perf_counter()
    drafts = tuple(draft for group in range(group_count) for draft in evidence_drafts(group, records))
    draft_seconds = perf_counter() - started
    version_sizes = []
    with closing(store.connect()) as db:
        db.execute("PRAGMA wal_autocheckpoint=0")
        checkpoint(db)
        baseline = database_sizes(store)
        started = perf_counter()
        first = mentions.publish_revision(study, key="scale-segments-r1", expected_revision=0,
                                          rule_version="synthetic-scale-r1", members=drafts)
        first_seconds = perf_counter() - started
        first_wal = database_sizes(store)["wal_bytes"]
        checkpoint(db)
        version_sizes.append(dict(database_sizes(store), active_wal_bytes=first_wal, version="segments-1"))
        started = perf_counter()
        install_registry(store, study, scopes, tuple(first["members"][index] for index in (0, 1, 4)))
        registry_seconds = perf_counter() - started
        registry_wal = database_sizes(store)["wal_bytes"]
        checkpoint(db)
        version_sizes.append(dict(database_sizes(store), active_wal_bytes=registry_wal, version="registry-2"))
        started = perf_counter()
        proposals = tuple(ProductProposal(draft.ref, interval, 2, VERSIONS[1], product, BASIS, "synthetic-scale-products")
                          for draft in drafts for interval, product in proposal_products(draft))
        second = mentions.publish_revision(study, key="scale-segments-r2", expected_revision=1,
                                           rule_version="synthetic-scale-r2", members=drafts, proposals=proposals)
        second_seconds = perf_counter() - started
        second_wal = database_sizes(store)["wal_bytes"]
        checkpoint(db)
        version_sizes.append(dict(database_sizes(store), active_wal_bytes=second_wal, version="segments-2"))
        assert first["members"] == second["members"]
        started = perf_counter()
        reviews = []
        for draft, member in zip(drafts, second["members"], strict=True):
            identifiers = {support.interval: identifier
                           for support, identifier in zip(draft.supports, member["evidence_ids"], strict=True)}
            for interval, product in proposal_products(draft):
                reviews.append(ReviewDecision(member["mention_id"], identifiers[interval], 2, VERSIONS[1], product,
                                              1, "human_confirmed", BASIS))
        mentions.review_products(study, key="scale-review-products", expected_revision=2, decisions=reviews)
        review_seconds = perf_counter() - started
        review_wal = database_sizes(store)["wal_bytes"]
        checkpoint(db)
        version_sizes.append(dict(database_sizes(store), active_wal_bytes=review_wal, version="product-review"))
    return second["members"], {"draft_seconds": draft_seconds, "first_segment_seconds": first_seconds,
        "registry_and_scope_mapping_seconds": registry_seconds, "second_segment_and_proposals_seconds": second_seconds,
        "product_review_seconds": review_seconds, "pre_segments": baseline, "version_sizes": version_sizes}


def build_fixture(store, raw_rows):
    group_count = raw_rows // 10
    app = create_app(Settings(store.directory))
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 29205),
                    headers={"Origin": ORIGIN, "X-VOC-Action": "connectivity"}) as client:
        study, scopes = freeze_scopes(client)
        print(f"Importing {raw_rows} synthetic raw rows", file=sys.stderr, flush=True)
        records, batches, timings = import_fixture(client, store, study, scopes, group_count)
    assert len(records) == raw_rows
    print(f"Reviewing {raw_rows} synthetic raw rows through M05", file=sys.stderr, flush=True)
    started = perf_counter()
    retention = qualify_fixture(store, study, records)
    timings["m05_review_seconds"] = perf_counter() - started
    check_review_rollback(store, study, records[(0, 8)], retention)
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM import_rows").fetchone()[0] == raw_rows
        assert db.execute("SELECT COUNT(*) FROM corpus_reviews").fetchone()[0] == 9 * group_count
    print(f"Sealing {group_count * len(PRIMARY_SLOTS)} occurrences via C3", file=sys.stderr, flush=True)
    members, segment_timings = segment_fixture(store, study, scopes, records, group_count)
    return study, scopes, records, members, batches, timings | segment_timings


def install_decisions(scenario, members):
    record_reviews = scenario.store.rows("""SELECT e.evidence_id, MAX(r.review_id) AS review_id FROM m06_evidence e
        JOIN corpus_reviews r USING(record_id) GROUP BY e.evidence_id""")
    review_by_id = {row["evidence_id"]: row["review_id"] for row in record_reviews}
    decisions = {
        0: {"choice": INTENT, "noul": True, "disposition": "human_confirmed", "publication_status": "published"},
        2: {},
        3: {"choice": INTENT, "noul": True, "review_pending": True},
        4: {"choice": INTENT, "noul": True, "review_pending": True, "issues": ("schema_gap",)},
        5: {"choice": ORPHAN, "noul": True},
        6: {"attempted": False, "receipt_id": None},
    }
    for member in members:
        slot = int(member["ref"].rsplit("-", 1)[-1])
        grants = {key: review_by_id[key] for key in member["evidence_ids"]}
        current = SyntheticDecision(VERSIONS[1], 2, grants, **decisions[slot])
        scenario.decisions[member["mention_id"]] = (current, replace(current, registry_version=VERSIONS[0],
                                                                     segment_revision=1))


def relation_store(store, study):
    grant = RelationGrant(ACTOR, "project_reviewer", "synthetic-owner", BASIS,
                          "2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z",
                          frozenset({"read", "evidence"}), study)
    return RelationStore(store, grants=lambda: (grant,))


def timed_query(relations, study, scenario, *, batch=True, filters=None, revision=2, version=VERSIONS[1]):
    start = perf_counter()
    result = relations.denominators(study, registry_version=version, segment_revision=revision, filters=filters,
                                    mode="synthetic", synthetic=scenario, batch_qualification=batch)
    return {key: value for key, value in result.items() if key != "as_of_utc"}, perf_counter() - start


def check_counts(result, groups, revoked=0):
    counts = result["counts"]
    assert result["availability"] == "available", result["reasons"]
    assert result["reconciliation"]["balanced"]
    assert counts["N_extracted_mentions"] == 7 * groups, counts
    assert counts["N_eligible_dedup"] == 6 * groups - revoked, counts
    assert counts["N_excluded"] == groups + revoked, counts
    assert counts["N_published_classified"] == groups, counts
    expected = dict.fromkeys(BUCKETS, groups)
    expected["review_pending"] -= int(revoked > 0)
    expected["partial_or_schema_gap"] -= int(revoked > 1)
    assert counts["buckets"] == expected, (counts["buckets"], expected)
    assert result["by_primary_category"] == [{"category_id": MAIN_TASK, "name": MAIN_TASK, "count": groups, "ratio": 1.0}]
    ledger = result["excluded_by_reason"]
    reasons = {"DUPLICATE_OCCURRENCE": groups}
    if revoked:
        reasons["LICENSE_RESTRICTED"] = revoked
    assert ledger["primary"] == reasons, ledger
    assert ledger["excluded_unsegmented_records"] == {
        "count": 2 * groups, "by_reason": {"LICENSE_RESTRICTED": groups, "NO_LEGAL_SEGMENT": groups},
    }, ledger


def verify_qualification(store, study, records):
    corpus = CorpusStore(store)
    today = now()[:10]
    with store.db() as db:
        db.execute("BEGIN")
        def measure(batch):
            start = perf_counter()
            answer = list(corpus.statistics_inputs(db, study, records.values(), today=today, batch=batch))
            return {row["record_id"]: row for row in answer}, perf_counter() - start
        batched, batch_s = measure(True)
        individual, individual_s = measure(False)
    assert batched == individual and len(batched) == len(records)
    assert not batched[records[(0, 3)]]["engineering_eligible"]
    assert not batched[records[(0, 8)]]["engineering_eligible"]
    assert not batched[records[(0, 9)]]["engineering_eligible"]
    return {"batched_seconds": batch_s, "individual_seconds": individual_s, "matches": len(batched)}


def explain_plans(store, study, records):
    keys = sorted(set(records))[:500]
    legacy_keys = {f"record_{index}": key for index, key in enumerate(keys)}
    placeholders = ", ".join(f":{name}" for name in legacy_keys)
    legacy_sql = f"{SOURCE_ROWS} AND r.record_id IN ({placeholders}) AND {CANDIDATE}"
    params = {"study_id": study, "today": now()[:10]}
    with store.db() as db:
        supports_sql = """SELECT s.mention_id, e.record_id
            FROM m06_support s JOIN m06_evidence e USING(study_id,evidence_id)
            WHERE s.study_id=:study_id AND s.segment_revision=2 ORDER BY s.mention_id, s.evidence_id"""
        statements = {
            "single_qualification": (STATISTICS_SINGLE_ROW, {"record_id": keys[0]}),
            "legacy_batch_qualification": (legacy_sql, legacy_keys),
            "batch_qualification": (STATISTICS_BATCH_ROWS, {"record_ids": json.dumps(keys)}),
            "segment_supports": (supports_sql, {}),
        }
        return {kind: [row[3] for row in db.execute(f"EXPLAIN QUERY PLAN {query}", params | bindings)]
                for kind, (query, bindings) in statements.items()}


def count_query_statements(relations, study, scenario, batch, expected):
    counts = Counter()
    connect = scenario.store.connect

    def observe(statement):
        counts[statement.split(maxsplit=1)[0].strip(";").upper()] += 1

    def observed_connection():
        connection = connect()
        connection.set_trace_callback(observe)
        return connection

    with patch.object(scenario.store, "connect", observed_connection):
        assert timed_query(relations, study, scenario, batch=batch)[0] == expected
    return dict(counts)


def measure_reads(relations, study, scenario, groups, repeats):
    modes = {}
    canonical = None
    for batch in (True, False):
        times = []
        for _ in range(repeats + 1):
            result, elapsed = timed_query(relations, study, scenario, batch=batch)
            check_counts(result, groups, revoked=1)
            if canonical is None:
                canonical = result
            assert canonical == result
            times.append(elapsed)
        modes["batched" if batch else "individual"] = {
            "first_connection_seconds": times[0], "hot_seconds": times[1:],
            "hot_median_seconds": statistics.median(times[1:]), "hot_max_seconds": max(times[1:]),
            "hot_sample_p95_seconds": statistics.quantiles(times[1:], n=100, method="inclusive")[94]
            if repeats > 1 else times[1],
            "statements": count_query_statements(relations, study, scenario, batch, canonical),
        }
    return canonical, modes


def check_filtered(relations, study, scenario, groups):
    product = {"product_category_id": PRODUCTS[1], "source": "forum"}
    result, elapsed = timed_query(relations, study, scenario, filters=product)
    assert result["counts"]["N_eligible_dedup"] == groups, result["counts"]
    assert result["counts"]["N_published_classified"] == groups, result["counts"]
    combined = {"product_category_id": list(PRODUCTS)}
    union, union_elapsed = timed_query(relations, study, scenario, filters=combined)
    assert union["counts"]["N_eligible_dedup"] == 6 * groups - 1
    historical, historical_elapsed = timed_query(relations, study, scenario, revision=1, version=VERSIONS[0])
    check_counts(historical, groups, revoked=1)
    formal = relations.denominators(study, registry_version=VERSIONS[1], segment_revision=2, mode="formal")
    assert formal["counts"] is None and "G1_BLOCKED" in formal["reasons"]
    return {"joint_filter_seconds": elapsed, "product_union_seconds": union_elapsed,
            "historical_seconds": historical_elapsed, "joint_filter_distinct": groups, "formal_counts": None}


def measure_concurrent_revocation(relations, study, scenario, record):
    snapshot_read = Event()
    change_committed = Event()
    blocked_writer = Event()
    reads = []
    actual = relations.corpus.statistics_inputs

    def synchronized_read(*args, **kwargs):
        yield from actual(*args, **kwargs)
        reads.append(perf_counter())
        if len(reads) == 1:
            snapshot_read.set()
            assert change_committed.wait(20), "The concurrent M05 write did not commit"

    def writer():
        started = perf_counter()
        blocked_writer.set()
        result = record_review(CorpusStore(scenario.store), study, record, None, licensed=False)
        assert not result["engineering_eligible"] and result["source_permission_revoked"]
        return perf_counter() - started

    with patch.object(relations.corpus, "statistics_inputs", synchronized_read):
        with ThreadPoolExecutor(max_workers=2) as executor:
            read = executor.submit(timed_query, relations, study, scenario)
            try:
                assert snapshot_read.wait(600), "The statistics reader did not establish a snapshot"
                with scenario.store.db() as lock:
                    lock.execute("BEGIN IMMEDIATE")
                    writing = executor.submit(writer)
                    assert blocked_writer.wait(10)
                    held_since = perf_counter()
                    sleep(0.1)
                    assert not writing.done(), "The writer bypassed the active SQLite write lock"
                held_for = perf_counter() - held_since
                write_seconds = writing.result(timeout=20)
            finally:
                change_committed.set()
            result, elapsed = read.result(timeout=600)
    assert len(reads) >= 2, "The stale result was not discarded and retried"
    return result, {"lock_held_while_writer_pending_seconds": held_for, "writer_seconds": write_seconds,
                    "query_seconds": elapsed, "snapshots_read": len(reads)}


CRASH_MARKER = "synthetic-uncommitted-crash-marker"
CRASH_WRITER = """
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA foreign_keys=ON')
connection.execute('BEGIN IMMEDIATE')
connection.execute(
    'INSERT INTO m06_command SELECT ?, NULL, namespace, operation, ?, input_hash, actor_ref, reason, created_at, result_ref '
    'FROM m06_command WHERE command_id=?', (sys.argv[2], sys.argv[2], sys.argv[3]),
)
assert connection.total_changes == 1
print('transaction-open', flush=True)
sys.stdin.read()
"""


def kill_writer(store):
    with subprocess.Popen([sys.executable, "-c", CRASH_WRITER, str(store.path), CRASH_MARKER,
                           f"registry-{VERSIONS[0]}"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True) as child:
        try:
            assert child.stdout.readline().strip() == "transaction-open", child.poll()
        finally:
            if child.poll() is None:
                child.kill()
            exit_status = child.wait(timeout=20)
    assert exit_status != 0
    return exit_status


def validate_database(store, raw_rows):
    started = perf_counter()
    with store.db() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert [row[0] for row in db.execute("PRAGMA integrity_check")] == ["ok"]
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("SELECT COUNT(*) FROM import_rows").fetchone()[0] == raw_rows
        assert db.execute("SELECT 1 FROM m06_command WHERE command_id=?", (CRASH_MARKER,)).fetchone() is None
        assert db.execute("SELECT COUNT(*) FROM m06_evidence").fetchone()[0] == 7 * (raw_rows // 10)
        assert db.execute("SELECT COUNT(*) FROM m06_member").fetchone()[0] == 12 * (raw_rows // 10)
    return perf_counter() - started


def recover_snapshot(study, scenario, records, raw_rows, working_directory):
    live = scenario.store
    relations = relation_store(live, study)
    groups = raw_rows // 10
    with closing(live.connect()) as keeper:
        checkpoint(keeper)
        during, concurrency = measure_concurrent_revocation(relations, study, scenario, records[(0, 4)])
        check_counts(during, groups, revoked=2)
        active_sizes = database_sizes(live)
        assert active_sizes["wal_bytes"] > 0
        exit_status = kill_writer(live)
        reopened = Store(live.directory)
        assert reopened.one("SELECT 1 FROM m06_command WHERE command_id=?", (CRASH_MARKER,)) is None
        with synthetic_database(parent=working_directory) as restored:
            started = perf_counter()
            with closing(live.connect()) as source, closing(restored.store.connect()) as target:
                source.backup(target)
            backup_s = perf_counter() - started
            started = perf_counter()
            restored.store = Store(restored.store.directory)
            reopen_s = perf_counter() - started
            restored.decisions.update(scenario.decisions)
            integrity_s = validate_database(restored.store, raw_rows)
            restored_relations = relation_store(restored.store, study)
            result, restored_read_s = timed_query(restored_relations, study, restored)
            assert result == during
            historical, _ = timed_query(restored_relations, study, restored, revision=1, version=VERSIONS[0])
            check_counts(historical, groups, revoked=2)
            restored_sizes = database_sizes(restored.store)
    return {"live_before_backup": active_sizes, "restored": restored_sizes, "backup_seconds": backup_s,
            "reopen_seconds": reopen_s, "integrity_and_foreign_keys_seconds": integrity_s,
            "reconciled_read_seconds": restored_read_s, "post_recovery_counts": result["counts"],
            "process_exit_status": exit_status, "concurrency": concurrency,
            "live_integrity_and_foreign_keys_seconds": validate_database(live, raw_rows)}


def migration_check(working_directory):
    with TemporaryDirectory(prefix="m06-c5-v6-", dir=working_directory) as directory:
        path = Path(directory) / "connectivity.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            Store._migrate(db, 6)
            assert db.execute("PRAGMA user_version").fetchone()[0] == 6
        started = perf_counter()
        store = Store(directory)
        elapsed = perf_counter() - started
        validate_database(store, 0)
        with store.db() as db:
            db.execute("DROP INDEX corpus_review_excluded")
        started = perf_counter()
        reopened = Store(directory)
        v7_reopen_s = perf_counter() - started
        assert reopened.one("SELECT name FROM sqlite_schema WHERE name='corpus_review_excluded'")
        validate_database(reopened, 0)
        return {"empty_v6_to_v7_seconds": elapsed, "old_v7_index_reopen_seconds": v7_reopen_s}


def peak_working_set():
    if sys.platform == "win32":
        import os
        measured = subprocess.run(["powershell", "-NoProfile", "-Command",
                                   f"(Get-Process -Id {os.getpid()}).PeakWorkingSet64"],
                                  capture_output=True, text=True, check=False)
        return int(measured.stdout) if measured.returncode == 0 and measured.stdout.strip().isdigit() else None
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def measure_fixture(scenario, fixture, raw_rows, repeats, working_directory):
    study, scopes, records, members, batches, fixture_timings = fixture
    print(f"Comparing current M05 qualifications and denominator outputs at {raw_rows}", file=sys.stderr, flush=True)
    install_decisions(scenario, members)
    corpus = CorpusStore(scenario.store)
    revoked = record_review(corpus, study, records[(0, 3)], None, licensed=False)
    assert not revoked["engineering_eligible"] and revoked["source_permission_revoked"]
    qualification = verify_qualification(scenario.store, study, records)
    relations = relation_store(scenario.store, study)
    groups = raw_rows // 10
    result, queries = measure_reads(relations, study, scenario, groups, repeats)
    filtered = check_filtered(relations, study, scenario, groups)
    plans = explain_plans(scenario.store, study, records.values())
    print(f"Testing committed WAL, writer failure and independent recovery at {raw_rows}", file=sys.stderr, flush=True)
    recovery = recover_snapshot(study, scenario, records, raw_rows, working_directory)
    return {"raw_records": raw_rows, "frozen_scopes": len(scopes), "import_batches": batches,
            "extracted_occurrence_candidates": len(members), "evidence_support_candidates": 7 * groups,
            "counts": result["counts"], "excluded_by_reason": result["excluded_by_reason"],
            "build": fixture_timings, "qualification": qualification, "queries": queries, "filtered_queries": filtered,
            "query_plans": plans, "recovery": recovery, "peak_process_working_set_bytes": peak_working_set()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 100000])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--work-directory", type=Path)
    parser.add_argument("--report", type=Path, help="Write a JSON Lines copy to this file.")
    args = parser.parse_args()
    if args.repeats < 1 or any(size < 20 or size % 10 for size in args.sizes):
        parser.error("Use at least one hot repeat and raw sizes divisible by 10 and at least 20.")
    working_directory = args.work_directory
    if working_directory:
        working_directory.mkdir(parents=True, exist_ok=True)
    environment = {"platform": platform.platform(), "python": platform.python_version(),
                   "sqlite": sqlite3.sqlite_version, "schema": 7, "research_api_calls": 0,
                   "query_first_connection": "Fresh SQLite connection; OS file cache was not cleared"} | migration_check(working_directory)
    def emit(value):
        line = json.dumps(value, ensure_ascii=False)
        if args.report:
            with args.report.open("a", encoding="utf-8") as report_file:
                report_file.write(line + "\n")
        print(line, flush=True)

    if args.report:
        args.report.write_text("", encoding="utf-8")
    emit({"environment": environment})
    for size in args.sizes:
        with synthetic_database(parent=working_directory) as scenario:
            fixture = build_fixture(scenario.store, size)
            report = measure_fixture(scenario, fixture, size, args.repeats, working_directory)
            emit(report)


if __name__ == "__main__":
    main()
