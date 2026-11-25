"""Shared sealed intent definitions, version history, and engineering consumption."""

from collections import defaultdict

from src.raw_store.registry_contract import SURVEY_STATES
from src.raw_store.relation_queries import _registry_version, definitions


CHANGE_FIELDS = (
    "name", "definition", "inclusion_criteria", "exclusion_criteria",
    "primary_category_id", "secondary_category_ids", "lifecycle_status",
    "survey_validation_status", "approved_shared_examples", "version",
)
LINEAGE_STATUS = {"merge": "merged", "split": "split", "retire": "retired"}
ANCESTRY = """
    WITH RECURSIVE ancestry(registry_version, parent_version, created_at, depth) AS (
        SELECT registry_version, parent_version, created_at, 0
        FROM m06_registry WHERE registry_version=? AND sealed=1
        UNION ALL
        SELECT parent.registry_version, parent.parent_version, parent.created_at, child.depth + 1
        FROM ancestry child JOIN m06_registry parent ON parent.registry_version=child.parent_version
        WHERE parent.sealed=1
    )
"""


def _exact(db, version):
    if not isinstance(version, str) or not version.strip():
        raise ValueError("需要精确的注册表版本。")
    return _registry_version(db, version)


def _paging(limit, offset):
    if type(limit) is not int or type(offset) is not int or not 1 <= limit <= 100 or offset < 0:
        raise ValueError("分页参数无效。")


def _page(items, limit, offset):
    return {
        "items": items[offset:offset + limit],
        "next_offset": offset + limit if len(items) > offset + limit else None,
    }


def _history(db, version):
    return db.execute(ANCESTRY + """
        SELECT registry_version, parent_version, created_at FROM ancestry ORDER BY depth
    """, (version,)).fetchall()


def _lineage(db, version, *, through=None, intent_id=None):
    """Project versioned definition edges. Command and project data stay private."""
    rows = db.execute(ANCESTRY + """
        SELECT edge.registry_version, edge.from_version, edge.from_id, edge.to_id, edge.action
        FROM ancestry
        JOIN m06_change_edge edge ON edge.registry_version=ancestry.registry_version
        WHERE edge.kind='intent' AND (? IS NULL OR ? IN (edge.from_id, edge.to_id))
          AND (? IS NULL OR ancestry.depth < (
              SELECT depth FROM ancestry WHERE registry_version=?
          ))
        ORDER BY ancestry.depth DESC, edge.seq
    """, (version, intent_id, intent_id, through, through))
    return [dict(row) for row in rows]


def _lineage_by_intent(edges, *, by_version=False):
    grouped = defaultdict(list)
    for edge in edges:
        for intent_id in {edge["from_id"], edge["to_id"]} - {None}:
            key = (edge["registry_version"], intent_id) if by_version else intent_id
            grouped[key].append(edge)
    return grouped


def _snapshot(db, version, *, object_id=None, approved_only=False, **filters):
    items = definitions(db, "intent", registry_version=version, object_id=object_id, **filters)["items"]
    examples = defaultdict(list)
    if items:
        rows = db.execute("""
            SELECT intent_id, kind, example_text AS text, classification FROM m07_shared_example
            WHERE registry_version=? AND (? IS NULL OR intent_id=?)
              AND (?=0 OR classification='approved_shared')
            ORDER BY intent_id, seq
        """, (version, object_id, object_id, approved_only))
        for row in rows:
            examples[row["intent_id"]].append({key: row[key] for key in ("kind", "text", "classification")})
    for item in items:
        item["secondary_category_ids"] = [
            category for category in item["category_ids"] if category != item["primary_category_id"]
        ]
        item["approved_shared_examples"] = examples.get(item["intent_id"], [])
    return {item["intent_id"]: item for item in items}


def _attach_task_names(db, version, items):
    if not items:
        return
    tasks = {task["category_id"]: task["name"] for task in definitions(
        db, "task", registry_version=version,
    )["items"]}
    for item in items:
        item["task_categories"] = [
            {"category_id": category, "name": tasks[category],
             "role": "primary" if category == item["primary_category_id"] else "secondary"}
            for category in item["category_ids"]
        ]


def _changes(before, after):
    return [
        {"field": field, "before": before.get(field), "after": after.get(field)}
        for field in CHANGE_FIELDS if before.get(field) != after.get(field)
    ]


def _status(before, after, changes, lineage=()):
    for edge in reversed(lineage):
        if edge["action"] in LINEAGE_STATUS:
            return LINEAGE_STATUS[edge["action"]]
    if not before:
        return "added"
    if not after:
        return "removed"
    if before["lifecycle_status"] != after["lifecycle_status"]:
        if after["lifecycle_status"] in {"merged", "retired"}:
            return after["lifecycle_status"]
    return "modified" if changes else "unchanged"


def _recent_changes(db, history, items, *, approved_only=False):
    newer = {item["intent_id"]: item for item in items}
    recent = {}
    lineage = _lineage_by_intent(_lineage(db, history[0]["registry_version"]), by_version=True)
    for version in history:
        parent = version["parent_version"]
        older = _snapshot(db, parent, approved_only=approved_only) if parent is not None else {}
        for intent_id, item in newer.items():
            before = older.get(intent_id, {})
            changes = _changes(before, item)
            edges = lineage.get((version["registry_version"], intent_id), ())
            status = _status(before, item, changes, edges)
            if status != "unchanged":
                recent[intent_id] = {
                    "registry_version": version["registry_version"], "created_at": version["created_at"],
                    "status": status,
                    "fields": [change["field"] for change in changes],
                }
        newer = {intent_id: older[intent_id] for intent_id in newer if intent_id not in recent}
        if not newer:
            break
    return recent


class RegistryVersions:
    """Read the M06 sealed projection using one consistent snapshot per operation."""

    def __init__(self, relations):
        self.relations = relations

    def versions(self, *, limit=25, offset=0):
        _paging(limit, offset)
        with self.relations._transaction() as (db, _):
            current = _registry_version(db, None)
            return {"current_registry_version": current,
                    **_page([dict(row) for row in _history(db, current)], limit, offset)}

    def catalog(self, version=None, *, q=None, lifecycle_status=None, primary_category_id=None,
                survey_validation_status=None, limit=25, offset=0):
        _paging(limit, offset)
        if survey_validation_status is not None and survey_validation_status not in SURVEY_STATES:
            raise ValueError("问卷验证状态无效。")
        if q is not None and (not isinstance(q, str) or len(q) > 160):
            raise ValueError("搜索词无效。")
        with self.relations._transaction() as (db, _):
            resolved = _registry_version(db, None) if version is None else _exact(db, version)
            items = _snapshot(db, resolved, q=q, lifecycle_status=lifecycle_status)
            filtered = [
                item for item in items.values()
                if (primary_category_id is None or item["primary_category_id"] == primary_category_id)
                and (survey_validation_status is None or item["survey_validation_status"] == survey_validation_status)
            ]
            page = _page(filtered, limit, offset)
            recent = _recent_changes(db, _history(db, resolved), page["items"]) if page["items"] else {}
            _attach_task_names(db, resolved, page["items"])
            for item in page["items"]:
                item["recent_change"] = recent.get(item["intent_id"])
            return {"registry_version": resolved, **page}

    def detail(self, version, intent_id):
        with self.relations._transaction() as (db, _):
            version = _exact(db, version)
            item = _snapshot(db, version, object_id=intent_id)[intent_id]
            _attach_task_names(db, version, [item])
            lineage = _lineage(db, version, intent_id=intent_id)
            events = _lineage_by_intent(lineage, by_version=True)
            changes = []
            newer = item
            for revision in _history(db, version):
                parent = revision["parent_version"]
                if parent is None:
                    older = {}
                else:
                    try:
                        older = _snapshot(db, parent, object_id=intent_id)[intent_id]
                    except KeyError:
                        older = {}
                diff = _changes(older, newer)
                status = _status(older, newer, diff, events.get((revision["registry_version"], intent_id), ()))
                if (older or newer) and status != "unchanged":
                    changes.append({**dict(revision), "status": status, "changes": diff})
                newer = older
            return {**item, "change_log": changes, "lineage": lineage}

    def compare(self, from_version, to_version, *, limit=25, offset=0):
        _paging(limit, offset)
        with self.relations._transaction() as (db, _):
            from_version, to_version = _exact(db, from_version), _exact(db, to_version)
            before, after = _snapshot(db, from_version), _snapshot(db, to_version)
            ancestors = {row["registry_version"] for row in _history(db, to_version)}
            forward = from_version in ancestors
            tip, base = (to_version, from_version) if forward else (from_version, to_version)
            lineage_by_id = _lineage_by_intent(_lineage(db, tip, through=base))
            intermediates = {
                intent_id for intent_id, edges in lineage_by_id.items()
                if any(edge["action"] in LINEAGE_STATUS for edge in edges)
            }
            results = []
            for intent_id in sorted(before.keys() | after.keys() | intermediates):
                old, new = before.get(intent_id, {}), after.get(intent_id, {})
                changes = _changes(old, new)
                lineage = lineage_by_id[intent_id]
                events = lineage if forward or not (old or new) else ()
                results.append({"intent_id": intent_id, "status": _status(old, new, changes, events),
                                "changes": changes, "lineage": lineage})
            return {"from_version": from_version, "to_version": to_version, **_page(results, limit, offset)}

    def consumer(self, version, *, limit=25, offset=0):
        _paging(limit, offset)
        with self.relations._transaction() as (db, _):
            version = _exact(db, version)
            items = list(_snapshot(db, version, lifecycle_status="confirmed", approved_only=True).values())
            page = _page(items, limit, offset)
            recent = _recent_changes(db, _history(db, version), page["items"], approved_only=True) if page["items"] else {}
            _attach_task_names(db, version, page["items"])
            for item in page["items"]:
                item["recent_change"] = recent.get(item["intent_id"])
            return {"registry_version": version, "mode": "engineering", **page}
