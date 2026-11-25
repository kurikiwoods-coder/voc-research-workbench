"""Current, project-scoped denominator accounting for the frozen M06-B-F.1 policy."""

from collections import Counter, defaultdict
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
import math
from tempfile import TemporaryDirectory

from src.raw_store import relation_queries as queries
from src.raw_store.mention_segments import validate_interval
from src.raw_store.mentions import SUPPORTS, _Support, _dependencies, _interval
from src.raw_store.store import Conflict, Store


POLICY = "M06-B-F.1"
BUCKETS = ("published_classified", "none_unknown", "review_pending",
           "partial_or_schema_gap", "pending_parent", "other_pending")
EXTRACTED = "N_extracted_mentions"
ELIGIBLE = "N_eligible_dedup"
PUBLISHED = "N_published_classified"
EXCLUDED = "N_excluded"
UNSEGMENTED = "excluded_unsegmented_records"
EARLY = ("N_discovered_urls", "N_accessible_pages")
LATE_FILTERS = ("intent_id", "category_id", "confidence_band", "index_version")
LICENSE = "LICENSE_RESTRICTED"
UNVERIFIABLE = "EVIDENCE_UNVERIFIABLE"
IDENTITY = "IDENTITY_PENDING"
DUPLICATE = "DUPLICATE_OCCURRENCE"


@dataclass(frozen=True)
class SyntheticDecision:
    registry_version: str
    segment_revision: int
    evidence_grants: dict
    index_version: str = "synthetic-index"
    model_id: str = "synthetic-model"
    question_set_version: str = "synthetic-questions"
    calibration_version: str = "synthetic-calibration"
    receipt_version: str = "synthetic-receipt-v1"
    receipt_id: str = "synthetic-receipt"
    attempted: bool = True
    issues: tuple = ()
    choice: str | None = None
    noul: bool | None = False
    review_pending: bool = False
    confidence_band: str | None = None
    disposition: str | None = None
    publication_status: str = "pending"
    probabilities: tuple | None = (0.8, 0.2)
    context_ids: tuple = ()


@dataclass
class _Synthetic:
    store: Store
    decisions: dict = field(default_factory=dict)


@contextmanager
def synthetic_database(parent=None):
    """Bind in-memory exercise decisions to a newly created, temporary SQLite store."""
    with TemporaryDirectory(prefix="m06-c5-synthetic-", dir=parent) as directory:
        yield _Synthetic(Store(directory))


def _empty(mode, filters, versions, at):
    return {"mode": mode, "availability": "unavailable", "reasons": [],
            "counts": None, "by_primary_category": None, "excluded_by_reason": None,
            "reconciliation": None, "coverage": {}, "anomaly_refs": [],
            "filter_echo": {**filters, **{key: versions[key] for key in
                                        ("study_id", "registry_version", "segment_revision",
                                         "counting_policy_version")}},
            "resolved_versions": versions, "as_of_utc": at, "counting_policy_version": POLICY}


def _dependencies_for(db, study, revision, mention, support, raws):
    if support.original_id is not None or support.context_ids:
        dependencies = _dependencies(db, study, revision, mention, support)
    else:
        dependencies = {support.evidence_id: (support.interval, support.scope_id)}
    failures, grants = set(), {}
    for key, (interval, scope) in dependencies.items():
        record = raws.get(interval.record_id)
        if record is None:
            failures.add(UNVERIFIABLE)
        elif not record["engineering_eligible"]:
            failures.add(_restriction(record))
        else:
            try:
                validate_interval(interval, record, study_id=study, scope_id=scope)
            except (Conflict, ValueError):
                failures.add(UNVERIFIABLE)
            else:
                grants[key] = record["review_id"]
    return grants, failures


def _restriction(record):
    if record["license_status"] in {"revoked", "expired", "denied", "unknown", "pending"}:
        return LICENSE
    if record["status"] in {"revoked", "retention_expired", "source_restricted", "policy_restricted"}:
        return LICENSE
    return UNVERIFIABLE


def _latest_reviews(db, study, revision):
    result = defaultdict(list)
    for row in db.execute(
        """SELECT * FROM m06_product_review r
           WHERE study_id=? AND segment_revision=? AND decision_seq=(
             SELECT MAX(x.decision_seq) FROM m06_product_review x
             WHERE (x.study_id, x.segment_revision, x.mention_id, x.evidence_id,
                    x.catalog_version, x.product_category_id) =
                   (r.study_id, r.segment_revision, r.mention_id, r.evidence_id,
                    r.catalog_version, r.product_category_id))""", (study, revision),
    ):
        result[row["mention_id"], row["evidence_id"]].append(row)
    return result


def _discovery(db, study, revision, version):
    rows = db.execute(
        """SELECT r.mention_id, r.intent_id, r.review_state, c.created_at, i.evidence_id, i.dependency_role
           FROM m06_discovery_review r
           JOIN m06_command c USING (study_id, command_id)
           LEFT JOIN m06_discovery_input i USING (study_id, segment_revision, mention_id, registry_version, seq)
           WHERE r.study_id=? AND r.segment_revision=? AND r.registry_version=? AND r.seq=(
             SELECT MAX(x.seq) FROM m06_discovery_review x
             WHERE (x.study_id, x.segment_revision, x.mention_id, x.registry_version)=
                   (r.study_id, r.segment_revision, r.mention_id, r.registry_version))""",
        (study, revision, version),
    )
    result = defaultdict(list)
    for row in rows:
        result[row["mention_id"]].append(row)
    return result


def _reviewed_after(db, review, at):
    row = db.execute(
        "SELECT julianday(reviewed_at)>julianday(?) FROM corpus_reviews WHERE review_id=?", (at, review),
    ).fetchone()
    return row is None or row[0] != 0


def _discovery_state(db, study, rows, access, refs, evidence, raws):
    if not rows or rows[0]["review_state"] in {"closed", "rejected"}:
        return None, False
    for row in rows:
        key = row["evidence_id"]
        event = evidence.get(key)
        if event is None:
            return None, False
        record = raws.get(event["record_id"])
        if record is None or not record["engineering_eligible"]:
            return None, False
        if row["dependency_role"] == "occurrence":
            if key not in refs or not access.permits("read", study, refs[key]):
                return None, False
        try:
            validate_interval(_interval(event), record, study_id=study, scope_id=event["scope_id"])
        except (Conflict, ValueError):
            return None, False
        if _reviewed_after(db, record["review_id"], row["created_at"]):
            return None, False
    if not any(row["dependency_role"] == "occurrence" for row in rows):
        return None, False
    return rows[0]["intent_id"], rows[0]["review_state"] == "open"


def _valid_probabilities(values):
    return (isinstance(values, (tuple, list)) and len(values) >= 2
            and all(type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1 for value in values)
            and math.isclose(sum(values), 1, abs_tol=1e-6))


def _publishable(decision, pending, intent, primary):
    return (decision and decision.attempted and not decision.issues
            and _valid_probabilities(decision.probabilities) and decision.noul is True
            and not pending and not decision.review_pending and decision.choice == intent
            and intent is not None and primary is not None and decision.publication_status == "published"
            and decision.disposition in {"auto", "human_confirmed"}
            and all((decision.receipt_id, decision.index_version, decision.model_id,
                     decision.question_set_version, decision.calibration_version, decision.receipt_version)))


def _bucket(decision, *, invalid, pending, intent, primary, candidate_missing_parent):
    if decision and decision.attempted:
        if (decision.issues or not _valid_probabilities(decision.probabilities)
                or type(decision.noul) is not bool):
            return "partial_or_schema_gap"
    if invalid and decision is None and intent is None and not pending:
        return "other_pending"
    if decision and decision.attempted and (decision.choice is None or decision.noul is False):
        return "none_unknown"
    if pending or (decision and decision.review_pending):
        return "review_pending"
    if candidate_missing_parent:
        return "pending_parent"
    if _publishable(decision, pending, intent, primary):
        return "published_classified"
    return "other_pending"


def reconcile(eligible, buckets, published, primary_counts):
    """Compare independently accumulated totals before giving a consumer a reconciliation."""
    eligible_delta = eligible - sum(buckets.values())
    primary_delta = published - sum(primary_counts.values())
    return {"eligible_difference": eligible_delta, "primary_difference": primary_delta,
            "balanced": eligible_delta == primary_delta == 0, "publication_allowed": False}


def _primary_tasks(db, version):
    return {row[0]: (row[1], row[2]) for row in db.execute(
        "SELECT category_id, name, lifecycle_status FROM m06_task WHERE registry_version=?", (version,),
    )}


def _primary_counts(assigned):
    return Counter(assigned.values())


def _note_filter_coverage(filters, window, time_filter, evidence, record, coverage, stages):
    if filters.get("source") and not evidence["source"]:
        for stage in stages:
            coverage[stage].add("SOURCE_FIELD_MISSING")
    if window and queries._matches(filters.get("source"), evidence["source"]):
        field = time_filter[0]
        stamp = record["metadata"].get(field) if field == "published_at" else record["trace"][field]
        try:
            missing = queries._utc(stamp) is None
        except (ValueError, TypeError):
            missing = True
        if missing:
            for stage in stages:
                coverage[stage].add("TIME_FIELD_MISSING")


def _late_match(filters, intent, categories, decision):
    return (queries._matches(filters.get("intent_id"), intent)
            and (not filters.get("category_id")
                 or set(queries._values(filters["category_id"])).intersection(categories))
            and queries._matches(filters.get("confidence_band"), decision.confidence_band if decision else None)
            and queries._matches(filters.get("index_version"), decision.index_version if decision else None))


def _decisions(synthetic, mention, version, revision, filters, supports, context_grants):
    current, invalid = [], False
    for attempt in synthetic.decisions.get(mention, ()) if synthetic else ():
        if (attempt.registry_version != version or attempt.segment_revision != revision
                or not queries._matches(filters.get("index_version"), attempt.index_version)):
            continue
        bindings = attempt.evidence_grants
        groups = [grants for key, grants in supports.items() if key in bindings]
        actual = {key: value for group in groups for key, value in group.items()}
        for key in attempt.context_ids:
            if key in context_grants:
                actual[key] = context_grants[key]
        if any(key not in actual for key in attempt.context_ids):
            invalid = True
            continue
        if groups and bindings == actual:
            current.append(attempt)
        else:
            invalid = True
    return current, invalid


def _rows_without_support(db, study, revision, filters):
    return [row[0] for row in db.execute(
        """SELECT r.record_id FROM import_rows r
           JOIN import_batches b USING(batch_id)
           JOIN corpus_snapshots snap ON snap.record_id=r.record_id AND snap.study_id=b.study_id
           WHERE b.study_id=? AND r.privacy='public' AND
             (? IS NULL OR b.scope_id=?) AND NOT EXISTS (
               SELECT 1 FROM m06_evidence e JOIN m06_support s USING(study_id, evidence_id)
               WHERE e.study_id=b.study_id AND e.scope_id=b.scope_id AND e.record_id=r.record_id
                 AND s.segment_revision=?
             )""", (study, filters.get("scope_id"), filters.get("scope_id"), revision),
    )]


def _snapshot(db, relations, access, study, mode, version, revision, filters, synthetic, batch):
    version = queries._registry_version(db, version)
    segment = queries._segment(db, study, revision)
    revision = segment["segment_revision"] if segment else None
    versions = {"study_id": study, "registry_version": version, "segment_revision": revision,
                "scope_id": filters.get("scope_id"), "scope_version": filters.get("scope_version"),
                "mapping_revision": filters.get("mapping_revision"), "catalog_version": filters.get("catalog_version"),
                "scope_mappings": [], "counting_policy_version": POLICY, "index_version": filters.get("index_version")}
    at = access.at.isoformat()
    result = _empty(mode, filters, versions, at)
    if revision is not None and not access.permits("read", study, entire_project=True):
        if not any(grant.study_id == study and grant.evidence_refs
                   and any(ref[0] == revision and access.permits("read", study, ref)
                           for ref in grant.evidence_refs)
                   for grant in access.grants):
            raise KeyError(revision)
    if mode == "formal":
        result["reasons"] = ["G1_BLOCKED", "RESEARCH_NOT_ADMITTED", "M12_RECEIPTS_MISSING"]
        return result
    if mode == "synthetic" and synthetic is None:
        result["reasons"] = ["SYNTHETIC_FIXTURE_REQUIRED"]
        return result
    if revision is None or version is None:
        result["reasons"] = [code for absent, code in (
            (revision is None, "SEGMENT_REVISION_UNAVAILABLE"), (version is None, "REGISTRY_UNAVAILABLE"),
        ) if absent]
        return result
    if not synthetic and (filters.get("confidence_band") or filters.get("index_version")):
        result["reasons"] = ["M12_RECEIPTS_MISSING"]
        return result
    if filters.get("catalog_version"):
        queries._registry_version(db, filters["catalog_version"])
    return _calculate(db, relations, access, study, result, segment, filters, synthetic, batch)


def _calculate(db, relations, access, study, result, segment, filters, synthetic, batch):
    versions = result["resolved_versions"]
    version, revision = versions["registry_version"], versions["segment_revision"]
    today = access.at.date().isoformat()
    wide = access.permits("read", study, entire_project=True)
    time_filter = queries._time_filter(filters)
    window = time_filter[1] is not None or time_filter[2] is not None
    scoped = filters.get("scope_id")
    product_filter = filters.get("product_category_id")
    late = any(filters.get(key) for key in LATE_FILTERS)
    details = queries._intent_details(db, version)
    tasks = _primary_tasks(db, version)
    reviews = _latest_reviews(db, study, revision)
    discovery = _discovery(db, study, revision, version)
    engineering = (queries._engineering_attestations(db, study, version, revision)
                   if not synthetic and (filters.get("intent_id") or filters.get("category_id")) else {})
    evidence = {}
    dependent_ids = set()
    if synthetic and wide:
        dependent_ids.update(key for decisions in synthetic.decisions.values()
                             for decision in decisions if decision.segment_revision == revision
                             for key in decision.context_ids)
    supports, refs, record_ids, scopes = [], {}, set(), set()
    states = {row["mention_id"]: row["identity_state"] for row in db.execute(
        "SELECT mention_id, identity_state FROM m06_member WHERE study_id=? AND segment_revision=?", (study, revision),
    )}
    for row in db.execute(SUPPORTS + " ORDER BY s.mention_id, s.evidence_id", (study, revision)):
        key, mention = row["evidence_id"], row["mention_id"]
        ref = (revision, mention, key)
        if not access.permits("read", study, ref):
            continue
        refs[key] = ref
        evidence[key] = row
        support = _Support.from_row(row)
        if not scoped or scoped == support.scope_id:
            supports.append((mention, states[mention], support))
            scopes.add(support.scope_id)
        record_ids.add(support.interval.record_id)
        dependent_ids.update(support.context_ids)
        if support.original_id:
            dependent_ids.add(support.original_id)
    for rows in discovery.values():
        if wide or any(row["dependency_role"] == "occurrence" and row["evidence_id"] in refs for row in rows):
            dependent_ids.update(row["evidence_id"] for row in rows if row["evidence_id"])
    for key in dependent_ids - evidence.keys():
        found = db.execute("SELECT * FROM m06_evidence WHERE study_id=? AND evidence_id=?", (study, key)).fetchone()
        if found is not None:
            evidence[key] = found
    record_ids.update(item["record_id"] for item in evidence.values())
    unsegmented = _rows_without_support(db, study, revision, filters) if wide else []
    record_ids.update(unsegmented)
    raws = {record["record_id"]: record for record in relations.corpus.statistics_inputs(
        db, study, record_ids, today=today, batch=batch,
    )}
    if wide and scoped:
        scopes.add(scoped)
    elif scoped and scoped not in scopes:
        raise KeyError(scoped)
    if scoped and filters.get("mapping_revision") is not None:
        queries._historical_mapping(db, study, segment, scoped, filters)
    coverage = defaultdict(set)
    for stage in EARLY:
        coverage[stage].add("M08_SAMPLING_LEDGER_MISSING")
    if late:
        for stage in (EXTRACTED, EXCLUDED, UNSEGMENTED):
            coverage[stage].add("DOWNSTREAM_FILTER_NOT_AVAILABLE_AT_STAGE")
    if not wide:
        coverage[UNSEGMENTED].add("EXACT_EVIDENCE_GRANT_ONLY")
    groups, eligible_dependencies = defaultdict(list), defaultdict(dict)
    exact_mappings = defaultdict(dict)
    excluded, secondary = Counter(), Counter()
    extracted = 0
    for mention, state, support in supports:
        key = support.evidence_id
        record = raws.get(support.interval.record_id)
        if record is None:
            for stage in (EXTRACTED, EXCLUDED):
                coverage[stage].add("INPUT_NOT_VISIBLE")
            continue
        if not queries._matches(filters.get("batch_id"), record["trace"]["batch_id"]):
            continue
        if not queries._matches(filters.get("scope_version"), record["trace"]["scope_version"]):
            raise KeyError(support.scope_id)
        if not record["engineering_eligible"] and (filters.get("source") or window or product_filter):
            for stage in (EXTRACTED, EXCLUDED):
                coverage[stage].add("RESTRICTED_INPUT_FILTER_UNKNOWN")
            continue
        evidence_ref = {"scope_id": support.scope_id, "scope_version": record["trace"]["scope_version"],
                        "batch_id": record["trace"]["batch_id"],
                        "source": record.get("metadata", {}).get("source_type")}
        if record["engineering_eligible"]:
            _note_filter_coverage(filters, window, time_filter, evidence_ref, record, coverage,
                                  (EXTRACTED, EXCLUDED, ELIGIBLE))
            if not queries._evidence_matches(filters, evidence_ref, record, time_filter):
                continue
        try:
            grants, failures = _dependencies_for(db, study, revision, mention, support, raws)
        except (Conflict, KeyError, ValueError):
            grants, failures = {}, {UNVERIFIABLE}
        edges = list(queries._product_edges(reviews[mention, key], evidence_ref, state, grants, filters))
        if not failures:
            for edge in edges:
                pin = edge["mapping_revision"], edge["catalog_version"]
                exact_mappings[support.scope_id][pin] = {
                    **{field: edge[field] for field in ("scope_id", "scope_version", "mapping_revision", "catalog_version")},
                    "mapping_status": "mapped_product",
                }
        if product_filter:
            if failures:
                for stage in (EXTRACTED, EXCLUDED):
                    coverage[stage].add("RESTRICTED_INPUT_FILTER_UNKNOWN")
                continue
            if not any(
                edge["effective"] and queries._matches(product_filter, edge["product_category_id"]) for edge in edges
            ):
                if state == "needs_review" or any(review["decision"] in {"proposed", "queued"}
                                                   for review in reviews[mention, key]):
                    for stage in (EXTRACTED, EXCLUDED, ELIGIBLE):
                        coverage[stage].add("PRODUCT_ATTRIBUTION_UNVERIFIED")
                continue
        extracted += 1
        reasons = set(failures)
        if state == "needs_review":
            reasons.add(IDENTITY)
        if reasons:
            first = next(code for code in (LICENSE, UNVERIFIABLE, IDENTITY) if code in reasons)
            excluded[first] += 1
            secondary.update(reasons - {first})
            continue
        groups[mention].append(key)
        eligible_dependencies[mention][key] = grants
    mappings = queries._catalog_mappings(db, study, segment, filters, scopes, {
        scope: list(pins.values()) for scope, pins in exact_mappings.items()
    }, project_wide=wide)
    versions["scope_mappings"] = mappings
    for field in ("mapping_revision", "catalog_version"):
        values = {item[field] for item in mappings}
        if len(values) == 1:
            versions[field] = next(iter(values))
    if product_filter and any(mapping["mapping_status"] == "unresolved" for mapping in mappings):
        result["reasons"] = ["SCOPE_MAPPING_UNRESOLVED"]
        result["coverage"] = {ELIGIBLE: ["SCOPE_MAPPING_UNRESOLVED"]}
        return result
    repeats = sum(len(keys) - 1 for keys in groups.values())
    if repeats:
        excluded[DUPLICATE] = repeats
    context_grants = {}
    if synthetic:
        for key in refs:
            row = evidence[key]
            mention = row["mention_id"]
            if mention not in groups or key in eligible_dependencies[mention]:
                continue
            try:
                grants, failures = _dependencies_for(db, study, revision, mention, _Support.from_row(row), raws)
            except (Conflict, KeyError, ValueError):
                continue
            if not failures:
                eligible_dependencies[mention][key] = grants
        for key in {key for attempts in synthetic.decisions.values() for attempt in attempts
                    if attempt.segment_revision == revision for key in attempt.context_ids}:
            if key not in evidence or (not wide and key not in refs):
                continue
            event = evidence[key]
            record = raws.get(event["record_id"])
            if record and record["engineering_eligible"]:
                try:
                    validate_interval(_interval(event), record, study_id=study, scope_id=event["scope_id"])
                except (Conflict, ValueError):
                    continue
                context_grants[key] = record["review_id"]

    buckets = Counter(dict.fromkeys(BUCKETS, 0))
    assigned, anomaly_counts = {}, Counter()
    eligible_total = 0
    published_mentions = set()
    anomalies, bindings = [], set()
    for mention, keys in groups.items():
        decisions, invalid = _decisions(synthetic, mention, version, revision, filters,
                                        eligible_dependencies[mention], context_grants)
        if len(decisions) > 1:
            result["reasons"] = ["COMPETING_CURRENT_DECISIONS"]
            return result
        decision = decisions[0] if decisions else None
        intent, pending = _discovery_state(db, study, discovery[mention], access, refs, evidence, raws)
        if decision is not None and decision.attempted:
            intent = decision.choice
        detail = details.get(intent, {})
        related = detail.get("category_ids", ())
        primary = detail.get("primary_category_id")
        lifecycle = detail.get("lifecycle_status")
        valid_parent = primary in related and tasks.get(primary, (None, None))[1] == "confirmed"
        candidate_missing_parent = lifecycle in {"candidate", "confirmed", "pending_parent"} and not valid_parent
        if lifecycle != "confirmed" or not valid_parent:
            primary = None
        if not _late_match(filters, intent, related, decision):
            if not any(
                grant == eligible_dependencies[mention][key] and definition in details
                and details[definition]["lifecycle_status"] == "confirmed"
                and _late_match(filters, definition, details[definition]["category_ids"], None)
                for key in keys for definition, grant in engineering.get((mention, key), ())
            ):
                continue
        if decision:
            bindings.add((decision.index_version, decision.model_id, decision.question_set_version,
                          decision.calibration_version, decision.receipt_version))
        eligible_total += 1
        if _publishable(decision, pending, intent, primary):
            published_mentions.add(mention)
        bucket = _bucket(decision, invalid=invalid, pending=pending, intent=intent, primary=primary,
                         candidate_missing_parent=candidate_missing_parent)
        buckets[bucket] += 1
        if bucket == "published_classified" and primary:
            assigned[mention] = primary
        elif anomaly_counts[bucket] < 5:
            key = next((key for key in keys if access.permits("evidence", study, refs[key])), None)
            if key is not None:
                anomalies.append({"mention_id": mention, "evidence_id": key, "segment_revision": revision,
                                  "reason": bucket})
                anomaly_counts[bucket] += 1

    unsegmented_reasons = Counter()
    for record_id in unsegmented:
        record = raws.get(record_id)
        if record is None:
            continue
        if not queries._matches(filters.get("batch_id"), record["trace"]["batch_id"]):
            continue
        if not record["engineering_eligible"]:
            if filters.get("source") or window or product_filter:
                coverage[UNSEGMENTED].add("RESTRICTED_INPUT_FILTER_UNKNOWN")
            else:
                unsegmented_reasons[_restriction(record)] += 1
            continue
        trace = record["trace"]
        evidence_ref = {**trace, "source": record["metadata"].get("source_type")}
        _note_filter_coverage(filters, window, time_filter, evidence_ref, record, coverage, (UNSEGMENTED,))
        if product_filter:
            coverage[UNSEGMENTED].add("UNSEGMENTED_PRODUCT_UNKNOWN")
        elif queries._evidence_matches(filters, evidence_ref, record, time_filter):
            unsegmented_reasons["NO_LEGAL_SEGMENT"] += 1
    if not synthetic:
        coverage[PUBLISHED].add("M12_RECEIPTS_MISSING")
    categories = _primary_counts(assigned)
    published_total = len(published_mentions)
    versions["coding_bindings"] = [dict(zip(
        ("index_version", "model_id", "question_set_version", "calibration_version", "receipt_version"), binding,
    )) for binding in sorted(bindings)]
    reconciliation = reconcile(eligible_total, buckets, published_total, categories)
    counts = {**dict.fromkeys(EARLY), EXTRACTED: None if late else extracted,
              ELIGIBLE: eligible_total, PUBLISHED: published_total if synthetic else None,
              EXCLUDED: None if late else sum(excluded.values()), "buckets": dict(buckets),
              "published_ratio": published_total / eligible_total if synthetic and eligible_total else None}
    ledger = {"primary": dict(sorted(excluded.items())), "secondary": dict(sorted(secondary.items())),
              UNSEGMENTED: {"count": sum(unsegmented_reasons.values()) if wide and not late else None,
                            "by_reason": dict(sorted(unsegmented_reasons.items())) if wide and not late else {}},
              "identity_review_rate": excluded[IDENTITY] / extracted if extracted and not late else None}
    return {**result, "availability": "available" if reconciliation["balanced"] else "unavailable",
            "reasons": [] if reconciliation["balanced"] else ["RECONCILIATION_MISMATCH"],
            "counts": counts, "by_primary_category": [
                {"category_id": key, "name": tasks[key][0], "count": count,
                 "ratio": count / published_total if published_total else None}
                for key, count in sorted(categories.items())
            ], "excluded_by_reason": None if late else ledger, "reconciliation": reconciliation,
            "coverage": {stage: sorted(reasons) for stage, reasons in coverage.items()}, "anomaly_refs": anomalies}


def denominators(relations, study, *, registry_version, segment_revision, filters, mode,
                 synthetic, batch_qualification):
    filters = queries._project_filters({**(filters or {}), "mode": mode})
    filters.pop("mode")
    if filters.pop("counting_policy_version", POLICY) != POLICY:
        raise ValueError("统计口径版本无效。")
    queries._time_filter(filters)
    if synthetic is not None and (mode != "synthetic" or not isinstance(synthetic, _Synthetic)
                                  or synthetic.store is not relations.store):
        raise ValueError("合成回执需要独立合成数据库。")
    for _ in range(3):
        access = relations._access()
        access.require("read", study)
        with closing(relations.store.connect()) as db:
            generation = db.execute("PRAGMA data_version").fetchone()[0]
            db.execute("BEGIN")
            try:
                if db.execute("SELECT 1 FROM study_projects WHERE study_id=?", (study,)).fetchone() is None:
                    raise KeyError(study)
                result = _snapshot(db, relations, access, study, mode, registry_version, segment_revision,
                                   filters, synthetic, batch_qualification)
            except Conflict:
                if access.at.date() != relations._access().at.date():
                    continue
                raise
            db.execute("ROLLBACK")
            fresh = relations._access()
            fresh.require("read", study)
            current_generation = db.execute("PRAGMA data_version").fetchone()[0]
            if (generation == current_generation and access.at.date() == fresh.at.date()
                    and access.same_as(fresh, study)):
                return result
    raise Conflict("统计期间资料已变化，请重新查询。")
