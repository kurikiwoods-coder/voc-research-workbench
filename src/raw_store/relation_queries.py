"""Project C4 definitions and evidence-backed relations from a caller-owned snapshot."""

from collections import defaultdict
from datetime import datetime, timezone
import json

from src.raw_store.mention_products import scope_mapping
from src.raw_store.mentions import _Support, _grants, _latest_reviews, _supports
from src.raw_store.store import Conflict


ENGINEERING_ATTRIBUTION = "engineering_attribution"

# These columns belong to approved shared definitions. Project audit tables
# and private command fields have no role in the shared search or projection.
DEFINITIONS = {
    "product": ("product_category_id", "name, description, parent_id, status, version"),
    "task": ("category_id", "name, definition, inclusion_criteria, exclusion_criteria, discovery, lifecycle_status, version"),
    "intent": ("intent_id", "name, definition, inclusion_criteria, exclusion_criteria, lifecycle_status, "
                          "survey_validation_status, primary_category_id, version"),
}
STATUSES = {
    "product": {"candidate", "confirmed", "merged", "retired"},
    "task": {"candidate", "confirmed", "rejected", "merged", "retired"},
    "intent": {"candidate", "pending_parent", "confirmed", "rejected", "merged", "retired"},
}


def _registry_version(db, version):
    if version is None:
        row = db.execute("SELECT registry_version FROM m06_registry_head").fetchone()
        return row[0] if row else None
    if not db.execute("SELECT 1 FROM m06_registry WHERE registry_version=? AND sealed=1", (version,)).fetchone():
        raise KeyError(version)
    return version


def _segment(db, study_id, revision, access):
    if revision is None:
        row = db.execute("SELECT segment_revision FROM m06_segment_head WHERE study_id=?", (study_id,)).fetchone()
        revision = row[0] if row else None
    access.require_revision(study_id, revision)
    if revision is None:
        return None
    row = db.execute(
        """SELECT segment_revision, parent_rev, rule_version, created_at FROM m06_segment_rev
           WHERE study_id=? AND segment_revision=? AND sealed=1""",
        (study_id, revision),
    ).fetchone()
    if row is None:
        raise KeyError(revision)
    return row


def _values(value):
    if value is None:
        return ()
    return tuple(value) if isinstance(value, (tuple, list, set, frozenset)) else (value,)


def _matches(expected, value):
    return not expected or value in _values(expected)


def _result(items, resolved, *, reasons=()):
    result = {"items": items, "resolved_versions": resolved, "availability": "unavailable" if reasons else "available",
              "reasons": list(reasons)}
    if reasons:
        result["counts"] = None
    return result


def _task_ids(db, registry_version):
    edges = defaultdict(list)
    for row in db.execute(
        """SELECT intent_id, category_id FROM m06_intent_task WHERE registry_version=?
           ORDER BY intent_id, is_primary DESC, category_id""",
        (registry_version,),
    ):
        edges[row["intent_id"]].append(row["category_id"])
    return edges


def definitions(db, kind, *, registry_version=None, object_id=None, **filters):
    """Read only sealed public fields and search within the same projection."""
    registry_version = _registry_version(db, registry_version)
    id_column, fields = DEFINITIONS[kind]
    status_column = "status" if kind == "product" else "lifecycle_status"
    status = filters.get(status_column)
    if set(_values(status)) - STATUSES[kind]:
        raise ValueError("定义生命周期无效。")
    rows = db.execute(
        f"""SELECT registry_version, {id_column}, {fields} FROM m06_{kind}
            WHERE registry_version=? AND (? IS NULL OR {id_column}=?) ORDER BY {id_column}""",
        (registry_version, object_id, object_id),
    ).fetchall()
    if object_id is not None and not rows:
        raise KeyError(object_id)
    task_ids = _task_ids(db, registry_version) if kind == "intent" else {}
    query = (filters.get("q") or "").casefold()
    items = []
    for row in rows:
        item = dict(row)
        if kind == "intent":
            item["category_ids"] = task_ids.get(row[id_column], [])
        if not _matches(status, row[status_column]):
            continue
        if kind == "product" and not _matches(filters.get("parent_id"), row["parent_id"]):
            continue
        if kind == "intent" and filters.get("category_id"):
            if not set(item["category_ids"]).intersection(_values(filters["category_id"])):
                continue
        if query and not any(query in value.casefold() for value in item.values() if isinstance(value, str)):
            continue
        items.append(item)
    return _result(items, {"registry_version": registry_version})


def task_intent_edges(db, *, registry_version=None, task_id=None, intent_id=None, role="all", **filters):
    """Use the same versioned edges and intent filter for either direction."""
    registry_version = _registry_version(db, registry_version)
    if role not in {"all", "primary", "secondary"}:
        raise ValueError("任务关系角色无效。")
    status = filters.get("lifecycle_status")
    if set(_values(status)) - STATUSES["intent"]:
        raise ValueError("意图生命周期无效。")
    if task_id is not None:
        definitions(db, "task", registry_version=registry_version, object_id=task_id)
    if intent_id is not None:
        definitions(db, "intent", registry_version=registry_version, object_id=intent_id)
    rows = db.execute(
        """SELECT edge.registry_version, edge.category_id, edge.intent_id, task.name AS category_name,
                  intent.name AS intent_name, intent.lifecycle_status,
                  CASE edge.is_primary WHEN 1 THEN 'primary' ELSE 'secondary' END AS role
           FROM m06_intent_task edge
           JOIN m06_task task USING (registry_version, category_id)
           JOIN m06_intent intent USING (registry_version, intent_id)
           WHERE edge.registry_version=? AND (? IS NULL OR edge.category_id=?)
                 AND (? IS NULL OR edge.intent_id=?)
           ORDER BY edge.intent_id, edge.is_primary DESC, edge.category_id""",
        (registry_version, task_id, task_id, intent_id, intent_id),
    )
    items = [dict(row) for row in rows
             if (role == "all" or row["role"] == role) and _matches(status, row["lifecycle_status"])]
    return _result(items, {"registry_version": registry_version})


def _utc(value):
    if not value:
        return None
    if len(value) == 10:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError("时间窗需要明确的 UTC 偏移。")
    return instant.astimezone(timezone.utc)


def _time_filter(filters):
    field = filters.get("time_field") or "published_at"
    if field not in {"published_at", "collected_at"}:
        raise ValueError("时间字段无效。")
    start, end = _utc(filters.get("from")), _utc(filters.get("to"))
    if start is not None and end is not None and start >= end:
        raise ValueError("时间窗起点须早于终点。")
    return field, start, end


def _evidence_matches(filters, evidence, record, time_filter):
    if any(not _matches(filters.get(key), evidence[key]) for key in ("scope_id", "scope_version", "batch_id", "source")):
        return False
    field, start, end = time_filter
    if start is None and end is None:
        return True
    stamp = record["metadata"].get(field) if field == "published_at" else record["trace"].get(field)
    try:
        instant = _utc(stamp)
    except (TypeError, ValueError):
        return False
    return instant is not None and (start is None or start <= instant) and (end is None or instant < end)


def _intent_details(db, version):
    categories = _task_ids(db, version)
    rows = db.execute(
        """SELECT intent_id, name AS intent_name, lifecycle_status, primary_category_id
           FROM m06_intent WHERE registry_version=? ORDER BY intent_id""",
        (version,),
    )
    return {row["intent_id"]: {**dict(row), "category_ids": categories.get(row["intent_id"], [])} for row in rows}


def _engineering_attestations(db, study_id, version, revision):
    """Only project-scoped, explicitly recorded C4 input may support a result."""
    refs = defaultdict(list)
    rows = db.execute(
        """SELECT result_ref FROM m06_command WHERE study_id=? AND operation=?
           AND json_extract(result_ref, '$.registry_version')=?
           AND json_extract(result_ref, '$.segment_revision')=?
           ORDER BY command_id""",
        (study_id, ENGINEERING_ATTRIBUTION, version, revision),
    )
    for row in rows:
        result = json.loads(row["result_ref"])
        for support in result["supports"]:
            refs[support["mention_id"], support["evidence_id"]].append((result["intent_id"], support["grants"]))
    return refs


def _historical_mapping(db, study_id, segment, scope_id, filters):
    mapping = filters.get("mapping_revision")
    catalog = filters.get("catalog_version")
    if mapping is None:
        latest = db.execute(
            """SELECT binding.mapping_revision FROM m06_scope_binding binding
               JOIN m06_command command USING (study_id, command_id)
               WHERE binding.study_id=? AND binding.scope_id=?
                     AND (? IS NULL OR julianday(command.created_at)<=julianday(?))
                     AND (? IS NULL OR binding.registry_version=?)
               ORDER BY binding.mapping_revision DESC LIMIT 1""",
            (study_id, scope_id, segment["created_at"] if segment else None,
             segment["created_at"] if segment else None, catalog, catalog),
        ).fetchone()
        mapping = latest[0] if latest is not None else None
    if mapping is not None:
        return scope_mapping(db, study_id, scope_id, mapping, catalog)
    row = db.execute(
        """SELECT scope.version_no FROM study_scope_freezes freeze
           JOIN study_scopes scope USING (study_id, scope_id)
           WHERE freeze.study_id=? AND freeze.scope_id=?""",
        (study_id, scope_id),
    ).fetchone()
    if row is None:
        raise KeyError(scope_id)
    return {"scope_id": scope_id, "scope_version": f"v{row[0]}",
            "mapping_revision": None, "catalog_version": None, "mapping_status": "unresolved"}


def _catalog_mappings(db, study_id, segment, filters, visible_scopes, exact, *, project_wide):
    """Preserve edge pins and resolve scoped empty views at their historical R."""
    requested = filters.get("scope_id")
    if requested is not None and project_wide:
        visible_scopes.add(requested)
    for scope_id in sorted(visible_scopes):
        if scope_id not in exact:
            exact[scope_id] = [_historical_mapping(db, study_id, segment, scope_id, filters)]
        if requested == scope_id and exact[scope_id][0]["scope_version"] != filters["scope_version"]:
            raise KeyError(scope_id)
    mappings = []
    for scope_id in sorted(exact):
        for mapping in sorted(exact[scope_id], key=lambda row: row["mapping_revision"] or 0):
            mappings.append({field: mapping[field] for field in
                             ("scope_id", "scope_version", "mapping_revision", "catalog_version", "mapping_status")})
    return mappings


def _product_edges(reviews, evidence, state, grants, filters):
    for review in reviews:
        provenance = json.loads(review["proposal_provenance"])
        if not _matches(filters.get("catalog_version"), review["catalog_version"]):
            continue
        if not _matches(filters.get("mapping_revision"), provenance["mapping_revision"]):
            continue
        yield {**evidence, "product_category_id": review["product_category_id"],
               "catalog_version": review["catalog_version"], "mapping_revision": provenance["mapping_revision"],
               "rule_version": provenance["rule_version"], "decision_seq": review["decision_seq"],
               "decision": review["decision"],
               "effective": state == "distinct" and review["decision"] == "human_confirmed"
                            and review["mode"] == "A" and provenance.get("grants") == grants}


def _project_snapshot(db, mentions, study_id, *, registry_version, segment_revision, filters,
                      access, can_read, today, require_registry=False):
    version = _registry_version(db, registry_version)
    segment = _segment(db, study_id, segment_revision, access)
    revision = segment["segment_revision"] if segment is not None else None
    resolved = {"registry_version": version, "segment_revision": revision,
                "catalog_version": filters.get("catalog_version"), "scope_mappings": []}
    if filters.get("mode") == "formal":
        return resolved, {}, [], ("G1_BLOCKED", "RESEARCH_NOT_ADMITTED", "M12_RECEIPTS_MISSING")
    missing = []
    if version is None and require_registry:
        missing.append("REGISTRY_UNAVAILABLE")
    if revision is None:
        missing.append("SEGMENT_REVISION_UNAVAILABLE")
    if resolved["catalog_version"] is not None:
        try:
            _registry_version(db, resolved["catalog_version"])
        except KeyError:
            missing.append("CATALOG_VERSION_UNAVAILABLE")
    if missing:
        return resolved, {}, [], tuple(missing)

    time_filter = _time_filter(filters)
    details = _intent_details(db, version)
    attestations = _engineering_attestations(db, study_id, version, revision)
    states = {row["mention_id"]: row["identity_state"] for row in db.execute(
        "SELECT mention_id, identity_state FROM m06_member WHERE study_id=? AND segment_revision=?",
        (study_id, revision),
    )}
    scoped = set()
    records, reviews, members = {}, {}, {}
    exact_mappings, relations = defaultdict(dict), []
    for row in _supports(db, study_id, revision):
        mention_id = row["mention_id"]
        support = _Support.from_row(row)
        if can_read is not None and not can_read(revision, mention_id, support.evidence_id):
            continue
        try:
            (record, _), dependencies = mentions._qualified_evidence(
                db, study_id, revision, mention_id, support, today, records,
            )
        except Conflict:
            continue
        evidence = {
            "study_id": study_id, "segment_revision": revision, "mention_id": mention_id,
            "evidence_id": support.evidence_id, "scope_id": support.scope_id,
            "scope_version": record["trace"]["scope_version"], "batch_id": record["trace"]["batch_id"],
            "source": record["metadata"].get("source_type"),
        }
        if not _matches(filters.get("scope_id"), support.scope_id):
            continue
        if not _matches(filters.get("scope_version"), evidence["scope_version"]):
            raise KeyError(support.scope_id)
        if not _evidence_matches(filters, evidence, record, time_filter):
            continue
        scoped.add(support.scope_id)
        grants = _grants(db, dependencies)
        state = states[mention_id]
        intents = {
            intent_id: details[intent_id] for intent_id, token in attestations[mention_id, support.evidence_id]
            if token == grants and state == "distinct" and intent_id in details
            and details[intent_id]["lifecycle_status"] == "confirmed"
        }
        intents = {intent_id: intent for intent_id, intent in intents.items()
                   if _matches(filters.get("intent_id"), intent_id)
                   and (not filters.get("category_id")
                        or set(intent["category_ids"]).intersection(_values(filters["category_id"])))}
        if mention_id not in reviews:
            reviews[mention_id] = defaultdict(list)
            for review in _latest_reviews(db, study_id, revision, mention_id):
                reviews[mention_id][review["evidence_id"]].append(review)
        products = []
        for product in _product_edges(reviews[mention_id][support.evidence_id], evidence, state, grants, filters):
            key = (product["mapping_revision"], product["catalog_version"])
            exact_mappings[support.scope_id][key] = {
                **{field: product[field] for field in ("scope_id", "scope_version", "mapping_revision", "catalog_version")},
                "mapping_status": "mapped_product",
            }
            if _matches(filters.get("product_category_id"), product["product_category_id"]):
                products.append(product)
        if (filters.get("intent_id") or filters.get("category_id")) and not intents:
            continue
        if filters.get("product_category_id") and not any(edge["effective"] for edge in products):
            continue
        entry = members.setdefault(mention_id, {"mention_id": mention_id, "identity_state": state,
                                                "evidence_refs": [], "products": [], "intents": {},
                                                "product_intent_edges": []})
        entry["evidence_refs"].append(evidence)
        entry["products"].extend(products)
        for intent_id, intent in intents.items():
            entry["intents"].setdefault(intent_id, {**intent, "evidence_ids": []})["evidence_ids"].append(support.evidence_id)
        for product in products:
            if product["effective"]:
                entry["product_intent_edges"].extend({"intent_id": key, **product} for key in intents)
                relations.extend((intent, product) for intent in intents.values())
    mentions.corpus._check_day(today)
    resolved["scope_mappings"] = _catalog_mappings(
        db, study_id, segment, filters, scoped, {key: list(mappings.values()) for key, mappings in exact_mappings.items()},
        project_wide=can_read is None,
    )
    catalogs = {scope["catalog_version"] for scope in resolved["scope_mappings"] if scope["catalog_version"]}
    if resolved["catalog_version"] is None and len(catalogs) == 1:
        resolved["catalog_version"] = next(iter(catalogs))
    return resolved, members, relations, ()


def _project_filters(filters):
    filters = dict(filters or {})
    if (filters.get("scope_id") is None) != (filters.get("scope_version") is None):
        raise ValueError("冻结范围 ID 和版本须同时指定。")
    if filters.get("mapping_revision") is not None and filters.get("scope_id") is None:
        raise ValueError("冻结映射版号需要指定冻结范围。")
    if filters.get("mode", "engineering") not in {"engineering", "synthetic", "formal"}:
        raise ValueError("查询模式无效。")
    return filters


def _replacement_links(db, mentions, study_id, revision, members, can_read, today):
    """Only show lineage when both ends still have readable evidence."""
    links = defaultdict(list)
    rows = db.execute(
        """SELECT old_rev, old_mention_id, segment_revision, new_mention_id, reason
           FROM m06_replacement WHERE study_id=? AND (segment_revision=? OR old_rev=?)
           ORDER BY old_rev, old_mention_id, segment_revision, new_mention_id""",
        (study_id, revision, revision),
    ).fetchall()
    visible, records = {}, {}
    for row in rows:
        incoming = row["segment_revision"] == revision
        member = row["new_mention_id"] if incoming else row["old_mention_id"]
        if member not in members:
            continue
        other_revision = row["old_rev"] if incoming else row["segment_revision"]
        other_member = row["old_mention_id"] if incoming else row["new_mention_id"]
        if other_revision not in visible:
            visible[other_revision] = set()
            for support_row in _supports(db, study_id, other_revision):
                mention_id = support_row["mention_id"]
                support = _Support.from_row(support_row)
                if mention_id in visible[other_revision]:
                    continue
                if can_read is not None and not can_read(other_revision, mention_id, support.evidence_id):
                    continue
                try:
                    mentions._qualified_evidence(db, study_id, other_revision, mention_id, support, today, records)
                except Conflict:
                    continue
                visible[other_revision].add(mention_id)
        if other_member in visible[other_revision]:
            links[member].append({
                "from_revision": row["old_rev"], "from_mention_id": row["old_mention_id"],
                "to_revision": row["segment_revision"], "to_mention_id": row["new_mention_id"], "reason": row["reason"],
            })
    return links


def _tombstones(db, mentions, study_id, revision, mention_id, can_audit, today):
    """Resolve restricted occurrences in the same snapshot as the live projection."""
    from src.raw_store.corpus_access import qualification
    from src.raw_store.mentions import _dependencies

    members = defaultdict(list)
    for row in _supports(db, study_id, revision):
        if mention_id is None or row["mention_id"] == mention_id:
            members[row["mention_id"]].append(_Support.from_row(row))

    records, restricted, tombstones = {}, {}, {}
    for member, supports in members.items():
        allowed = [support for support in supports if can_audit(revision, member, support.evidence_id)]
        if not allowed:
            continue
        for support in supports:
            try:
                mentions._qualified_evidence(db, study_id, revision, member, support, today, records)
            except Conflict:
                continue
            break
        else:
            for support in allowed:
                dependencies = _dependencies(db, study_id, revision, member, support)
                for interval, _ in dependencies.values():
                    if interval.record_id not in restricted:
                        row = mentions.corpus.source_row(db, study_id, interval.record_id, today)
                        access = qualification(row, today)
                        restricted[interval.record_id] = access["status"] in {
                            "revoked", "retention_expired", "policy_restricted", "source_restricted", "excluded",
                        }
                if any(restricted[interval.record_id] for interval, _ in dependencies.values()):
                    tombstones[member] = {"mention_id": member, "segment_revision": revision,
                                          "tombstone": True, "reason": "EVIDENCE_UNAVAILABLE"}
                    break
    return tombstones


def project_mentions(db, mentions, study_id, *, registry_version=None, segment_revision=None,
                     mention_id=None, filters=None, access, can_read=None, can_audit=None, today):
    """Return project-only mention status and visible eligible evidence references."""
    filters = _project_filters(filters)
    resolved, members, _, reasons = _project_snapshot(
        db, mentions, study_id, registry_version=registry_version, segment_revision=segment_revision,
        filters=filters, access=access, can_read=can_read, today=today,
    )
    if reasons:
        return _result([], resolved, reasons=reasons)
    revision = resolved["segment_revision"]
    if mention_id is not None:
        members = {key: member for key, member in members.items() if key == mention_id}
    tombstones = {}
    # Removed evidence cannot establish membership in a filtered slice.
    if can_audit is not None and revision is not None and not filters.keys() - {"mode", "time_field"}:
        tombstones = _tombstones(db, mentions, study_id, revision, mention_id, can_audit, today)
    if mention_id is not None and not members and not tombstones:
        raise KeyError(mention_id)
    replacements = _replacement_links(db, mentions, study_id, revision, members, can_read, today)
    items = []
    for ref in sorted(members):
        item = members[ref]
        item["intents"] = [item["intents"][key] for key in sorted(item["intents"])]
        item["replacements"] = replacements[ref]
        items.append(item)
    items.extend(tombstones.values())
    return _result(sorted(items, key=lambda item: item["mention_id"]), resolved)


def product_intent_edges(db, mentions, study_id, *, registry_version=None, segment_revision=None,
                         product_id=None, intent_id=None, filters=None, access, can_read=None, today):
    """Group both orientations from the same qualifying (S, V, R, M, E, P, A) witness."""
    filters = _project_filters(filters)
    if product_id is not None:
        filters["product_category_id"] = (product_id,)
    if intent_id is not None:
        filters["intent_id"] = (intent_id,)
    resolved, _, relations, reasons = _project_snapshot(
        db, mentions, study_id, registry_version=registry_version, segment_revision=segment_revision,
        filters=filters, access=access, can_read=can_read, today=today, require_registry=True,
    )
    if reasons:
        return _result([], resolved, reasons=reasons)
    catalog = filters.get("catalog_version")
    if any(scope["mapping_status"] == "unresolved" for scope in resolved["scope_mappings"]):
        return _result([], resolved, reasons=("SCOPE_MAPPING_UNRESOLVED",))
    version = resolved["registry_version"]
    if intent_id is not None:
        definitions(db, "intent", registry_version=version, object_id=intent_id)
    if product_id is not None:
        if not db.execute(
            """SELECT 1 FROM m06_product product JOIN m06_registry registry USING (registry_version)
               WHERE product.product_category_id=? AND registry.sealed=1
                     AND (? IS NULL OR product.registry_version=?) LIMIT 1""",
            (product_id, catalog, catalog),
        ).fetchone():
            raise KeyError(product_id)
    items = {}
    for intent, edge in relations:
        if product_id is not None and edge["product_category_id"] != product_id:
            continue
        if intent_id is not None and intent["intent_id"] != intent_id:
            continue
        if product_id is not None:
            key, fields = (intent["intent_id"],), intent
        else:
            key = (edge["product_category_id"], edge["catalog_version"])
            if key not in items:
                product = definitions(db, "product", registry_version=key[1], object_id=key[0])["items"][0]
                fields = {"product_category_id": key[0], "catalog_version": key[1], "product_name": product["name"]}
            else:
                fields = {}
        item = items.setdefault(key, {**fields, "evidence_refs": {}, "mentions": set(),
                                      "sources": defaultdict(set)})
        member, evidence = edge["mention_id"], edge["evidence_id"]
        item["mentions"].add(member)
        if edge["source"] is not None:
            item["sources"][edge["source"]].add(member)
        witness = (member, evidence, edge["catalog_version"], edge["product_category_id"])
        item["evidence_refs"][witness] = edge
    rows = []
    for key in sorted(items):
        item = items[key]
        item["distinct_mention_n"] = len(item.pop("mentions"))
        item["source_breakdown"] = {source: len(members) for source, members in sorted(item.pop("sources").items())}
        refs = item["evidence_refs"]
        item["evidence_refs"] = [refs[key] for key in sorted(refs)]
        rows.append(item)
    return _result(rows, resolved)
