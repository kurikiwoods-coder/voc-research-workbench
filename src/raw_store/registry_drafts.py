"""Project-scoped registry proposals for the future M11 review workflow."""

from contextlib import contextmanager
from hashlib import sha256
import json
from uuid import uuid4

from src.raw_store.mentions import _head, _insert
from src.raw_store.registry_contract import definition_fields, identifier, missing_definition
from src.raw_store.relation_registry import parent_violations, registry_head, registry_version
from src.raw_store.store import Conflict, dump, now


KINDS = ("candidate", "amend", "merge", "split", "retire", "restore")
DEFINITION_KEYS = ("primary_category_id", "secondary_category_ids", "source_intent_ids")
CURRENT = """SELECT d.*, r.state, r.lifecycle_status, r.definition_json, r.source_refs_json,
                   r.target_ids_json, r.reason, r.actor_ref, r.created_at AS updated_at
              FROM m07_draft d JOIN m07_draft_revision r USING (study_id, draft_id)
             WHERE d.study_id=?"""


def _ids(values):
    if not isinstance(values, (list, tuple)) or len(values) > 100:
        raise ValueError("任务或意图列表无效。")
    ids = sorted(identifier(value) for value in values)
    if len(ids) != len(set(ids)):
        raise ValueError("请移除重复标识。")
    return ids


def _definition(values):
    result = definition_fields(values)
    result.update({key: _ids(values.get(key, ())) for key in DEFINITION_KEYS[1:]})
    primary = values.get("primary_category_id")
    result["primary_category_id"] = identifier(primary) if primary is not None else None
    if primary is not None and primary in result["secondary_category_ids"]:
        raise ValueError("主任务不能同时列为次任务。")
    return result


def _refs(values):
    if not isinstance(values, (list, tuple)) or len(values) > 100:
        raise ValueError("证据引用列表无效。")
    result = set()
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("请指定准确证据引用。")
        revision = item.get("segment_revision")
        if type(revision) is not int or not 0 < revision < 2**53:
            raise ValueError("片段版本无效。")
        key = (revision, identifier(item.get("mention_id")), identifier(item.get("evidence_id")))
        if key in result:
            raise ValueError("请移除重复证据引用。")
        result.add(key)
    return [dict(segment_revision=revision, mention_id=mention, evidence_id=evidence)
            for revision, mention, evidence in sorted(result)]


def _intent(db, version, intent_id):
    row = db.execute(
        """SELECT intent.* FROM m06_intent intent JOIN m06_registry registry USING (registry_version)
           WHERE registry.sealed=1 AND registry_version=? AND intent_id=?""", (version, intent_id),
    ).fetchone()
    if row is None:
        raise KeyError(intent_id)
    return row


def _version_definition(db, version, intent_id):
    row = _intent(db, version, intent_id)
    secondaries = [item[0] for item in db.execute(
        """SELECT category_id FROM m06_intent_task
           WHERE registry_version=? AND intent_id=? AND is_primary=0 ORDER BY category_id""", (version, intent_id),
    )]
    return _definition(dict(row) | {"secondary_category_ids": secondaries})


def _edges(kind, intent, definition, targets):
    if kind == "merge":
        return [(source, intent) for source in definition["source_intent_ids"]]
    if kind == "split":
        return [(intent, target) for target in targets]
    return []


def _check_lineage(db, study, draft, proposed):
    if not proposed:
        return
    graph = {}
    for source, target in db.execute(
        """SELECT from_id, to_id FROM m06_change_edge JOIN m06_registry USING (registry_version)
           WHERE sealed=1 AND kind='intent' AND action IN ('merge', 'split')""",
    ):
        graph.setdefault(source, set()).add(target)
    for row in db.execute(
        CURRENT + " AND d.revision=r.revision AND r.state='submitted' AND d.draft_id<>?", (study, draft),
    ):
        for source, target in _edges(row["kind"], row["intent_id"],
                                     json.loads(row["definition_json"]), json.loads(row["target_ids_json"])):
            graph.setdefault(source, set()).add(target)
    for source, target in proposed:
        pending = [target]
        seen = set()
        while pending:
            item = pending.pop()
            if item == source:
                raise ValueError("合并或拆分谱系不得循环。")
            if item not in seen:
                seen.add(item)
                pending.extend(graph.get(item, ()))
        graph.setdefault(source, set()).add(target)


def _unused(db, study, draft, intent):
    if db.execute("SELECT 1 FROM m06_intent WHERE intent_id=? LIMIT 1", (intent,)).fetchone():
        raise Conflict("所选意图标识已存在。")
    for row in db.execute(CURRENT + " AND d.revision=r.revision AND r.state<>'withdrawn' AND d.draft_id<>?",
                          (study, draft)):
        if row["intent_id"] == intent or intent in json.loads(row["target_ids_json"]):
            raise Conflict("所选意图标识已有待处理提案。")


class RegistryDrafts:
    def __init__(self, relations):
        self.relations = relations

    @staticmethod
    def permitted(access, study):
        return all(access.permits(operation, study, entire_project=True)
                   for operation in ("read", "validate", "registry_draft"))

    @contextmanager
    def _transaction(self, study, *, write=False):
        access = self.relations._access()
        if not self.permitted(access, study):
            raise PermissionError("当前项目未获意图草稿授权。") if write else KeyError(study)
        with self.relations._transaction(study, operation="registry_draft", write=write) as (db, current):
            if not access.same_as(current, study):
                raise PermissionError("项目授权已变化。") if write else KeyError(study)
            yield db, access
            if write:
                self.relations._check_access(access, study, write=True)

    @staticmethod
    def _row(db, study, draft, revision=None):
        row = db.execute(CURRENT + " AND d.draft_id=? AND r.revision=COALESCE(?,d.revision)",
                         (study, identifier(draft), revision)).fetchone()
        if row is None:
            raise KeyError(draft)
        return row

    def _visible_refs(self, access, study, refs, *, require=False):
        visible = []
        for ref in refs:
            exact = (ref["segment_revision"], ref["mention_id"], ref["evidence_id"])
            try:
                for operation in ("read", "evidence", "validate"):
                    access.require(operation, study, exact)
                self.relations.read_evidence(study, *exact)
            except (KeyError, Conflict):
                if require:
                    raise
            else:
                visible.append(ref)
        return visible

    def _item(self, db, access, row, *, with_refs=False, revision=None):
        definition = json.loads(row["definition_json"])
        targets = json.loads(row["target_ids_json"])
        study = row["study_id"]
        return {
            **{key: row[key] for key in ("draft_id", "kind", "intent_id", "base_registry_version",
                                         "origin_registry_version", "lifecycle_status", "state",
                                         "study_id", "created_at", "updated_at", "reason", "actor_ref")},
            "revision": revision if revision is not None else row["revision"],
            "first_discovered_at": row["created_at"][:10] if row["kind"] == "candidate" else None,
            "definition": definition, "survey_validation_status": "unvalidated",
            "missing_fields": self._missing(db, row["base_registry_version"], definition),
            "target_ids": targets,
            "source_refs": self._visible_refs(access, study, json.loads(row["source_refs_json"])) if with_refs else [],
        }

    @staticmethod
    def _missing(db, base, definition):
        return [*missing_definition(definition), *parent_violations(
            db, base, definition["primary_category_id"], definition["secondary_category_ids"], confirm=True,
        )]

    def projects(self):
        with self.relations._transaction() as (db, _):
            access = self.relations._access()
            rows = db.execute("SELECT study_id, name FROM study_projects WHERE status<>'archived' ORDER BY name, study_id")
            items = [dict(row) for row in rows if self.permitted(access, row["study_id"])]
            if any(not access.same_as(self.relations._access(), item["study_id"]) for item in items):
                raise Conflict("项目授权已变化。")
            return items

    def list(self, study, *, limit=25, offset=0):
        with self._transaction(study) as (db, access):
            rows = list(db.execute(CURRENT + """
                AND d.revision=r.revision ORDER BY r.created_at DESC,d.draft_id LIMIT ? OFFSET ?""",
                (study, limit + 1, offset)))
            return {"items": [self._item(db, access, row) for row in rows[:limit]],
                    "next_offset": offset + limit if len(rows) > limit else None}

    def detail(self, study, draft):
        with self._transaction(study) as (db, access):
            return self._item(db, access, self._row(db, study, draft), with_refs=True)

    def history(self, study, draft, *, limit=25, offset=0):
        with self._transaction(study) as (db, access):
            self._row(db, study, draft)
            rows = list(db.execute(CURRENT.replace("SELECT d.*,", "SELECT d.*, r.revision AS historical_revision,")
                                   + " AND d.draft_id=? ORDER BY r.revision DESC LIMIT ? OFFSET ?",
                                   (study, draft, limit + 1, offset)))
            return {"items": [self._item(db, access, row, revision=row["historical_revision"]) for row in rows[:limit]],
                    "next_offset": offset + limit if len(rows) > limit else None}

    def preflight(self, study, draft, revision, expected_segment_revision=None):
        with self._transaction(study) as (db, access):
            row = self._row(db, study, draft)
            self._expect(row, revision, registry_head(db))
            definition = json.loads(row["definition_json"])
            refs = self._visible_refs(access, study, json.loads(row["source_refs_json"]), require=True)
            segment = _head(db, study)
            if expected_segment_revision is not None and segment != expected_segment_revision:
                raise Conflict("片段版本已变化。")
            base = row["base_registry_version"]
            violations = self._missing(db, base, definition)
            if segment:
                result = self.relations.validate(
                    study, operation="confirm", candidate_intent_id=row["intent_id"],
                    expected_registry_version=base, expected_segment_revision=segment,
                    primary_category_id=definition["primary_category_id"],
                    secondary_ids=definition["secondary_category_ids"], representative_refs=refs,
                )
                violations.extend(result["violations"])
            else:
                violations.append("REPRESENTATIVES_INSUFFICIENT")
            violations = list(dict.fromkeys(violations))
            return {"valid": not violations, "violations": violations, "formal_issuance": False,
                    "candidate_allowed": True, "lifecycle_status": row["lifecycle_status"],
                    "registry_version": base, "segment_revision": segment or None}

    @staticmethod
    def _expect(row, revision, base):
        if type(revision) is not int or row["revision"] != revision or row["base_registry_version"] != base:
            raise Conflict("草稿或注册表版本已变化。")

    def command(self, study, operation, *, request_key, expected_registry_version, reason,
                draft_id=None, expected_revision=None, kind=None, intent_id=None, definition=None,
                origin_registry_version=None, source_refs=None, target_ids=None):
        if operation not in {"create", "edit", "submit", "withdraw"}:
            raise ValueError("草稿操作无效。")
        identifier(request_key)
        if not isinstance(reason, str) or not 0 < len(reason.strip()) <= 2000:
            raise ValueError("请填写变更理由。")
        if expected_registry_version is not None:
            registry_version(expected_registry_version)
        if origin_registry_version is not None:
            registry_version(origin_registry_version)
        values = _definition(definition) if definition is not None else None
        refs = _refs(source_refs) if source_refs is not None else None
        targets = _ids(target_ids) if target_ids is not None else None
        if operation != "create" and (kind is not None or intent_id is not None or origin_registry_version is not None):
            raise ValueError("草稿身份及来源版本固定。")
        if operation in {"submit", "withdraw"} and any(item is not None for item in (values, refs, targets)):
            raise ValueError("请先保存草稿内容。")
        with self._transaction(study, write=True) as (db, access):
            signature = sha256(dump([
                access.actor, operation, draft_id, expected_revision, expected_registry_version,
                kind, intent_id, values, origin_registry_version, refs, targets, reason.strip(),
            ]).encode()).hexdigest()
            prior = db.execute("SELECT * FROM m07_draft_command WHERE study_id=? AND request_key=?",
                               (study, request_key)).fetchone()
            if prior is not None:
                if prior["input_hash"] != signature:
                    raise Conflict("这个命令键对应不同输入或授权身份。")
                return self._item(db, access, self._row(db, study, prior["draft_id"], prior["revision"]),
                                  revision=prior["revision"], with_refs=True)
            if registry_head(db) != expected_registry_version:
                raise Conflict("注册表版本已变化。")
            timestamp = now()
            if operation == "create":
                if draft_id is not None or expected_revision is not None or kind not in KINDS:
                    raise ValueError("创建草稿格式无效。")
                intent_id = identifier(intent_id) if intent_id is not None else "INT-" + uuid4().hex
                draft_id = str(uuid4())
                revision, state = 1, "draft"
                if kind == "candidate":
                    _unused(db, study, draft_id, intent_id)
                    if origin_registry_version is not None:
                        raise ValueError("新候选没有历史版本。")
                else:
                    origin = origin_registry_version if kind == "restore" else expected_registry_version
                    if kind == "restore" and (origin is None or origin == expected_registry_version
                                              or refs or values is not None or targets):
                        raise ValueError("恢复须从历史定义起草。")
                    if kind != "restore" and origin_registry_version is not None:
                        raise ValueError("当前版本提案不能指定来源版本。")
                    values = values if values is not None else _version_definition(db, origin, intent_id)
                    _intent(db, origin, intent_id)
                    if kind == "restore":
                        values = self._restore_tasks(db, expected_registry_version, values)
                _insert(db, "m07_draft", study_id=study, draft_id=draft_id, kind=kind, intent_id=intent_id,
                        base_registry_version=expected_registry_version, origin_registry_version=origin_registry_version,
                        created_at=timestamp, revision=revision)
            else:
                row = self._row(db, study, draft_id)
                base = row["base_registry_version"] if operation == "withdraw" else expected_registry_version
                self._expect(row, expected_revision, base)
                if row["state"] == "withdrawn" or (row["state"] != "draft" and operation != "withdraw"):
                    raise Conflict("草稿当前状态不允许该操作。")
                kind, intent_id = row["kind"], row["intent_id"]
                revision = row["revision"] + 1
                state = {"edit": "draft", "submit": "submitted", "withdraw": "withdrawn"}[operation]
                values = values if values is not None else json.loads(row["definition_json"])
                targets = targets if targets is not None else json.loads(row["target_ids_json"])
                if refs is None:
                    refs = json.loads(row["source_refs_json"])
                db.execute("UPDATE m07_draft SET revision=? WHERE study_id=? AND draft_id=?",
                           (revision, study, draft_id))
            values = values if values is not None else _definition({})
            refs = refs or []
            targets = targets or []
            if operation != "withdraw":
                self._check_proposal(db, study, draft_id, expected_registry_version, kind, intent_id, values, targets)
                self._visible_refs(access, study, refs, require=True)
            if state == "submitted" and missing_definition(values):
                raise ValueError("提交审核前请补齐定义及纳入排除标准。")
            _insert(db, "m07_draft_revision", study_id=study, draft_id=draft_id, revision=revision, state=state,
                    lifecycle_status="candidate" if values["primary_category_id"] else "pending_parent",
                    definition_json=dump(values), source_refs_json=dump(refs), target_ids_json=dump(targets),
                    reason=reason.strip(), actor_ref=access.actor, created_at=timestamp)
            _insert(db, "m07_draft_command", study_id=study, request_key=request_key, input_hash=signature,
                    draft_id=draft_id, revision=revision)
            return self._item(db, access, self._row(db, study, draft_id), with_refs=True)

    @staticmethod
    def _restore_tasks(db, base, definition):
        primary = definition["primary_category_id"]
        retained = {row["category_id"] for row in db.execute(
            "SELECT category_id FROM m06_task WHERE registry_version=? AND lifecycle_status='confirmed'", (base,),
        )}
        return definition | {
            "primary_category_id": primary if primary in retained else None,
            "secondary_category_ids": [category for category in definition["secondary_category_ids"]
                                       if category in retained],
        }

    @staticmethod
    def _check_proposal(db, study, draft, base, kind, intent, definition, targets):
        issues = parent_violations(db, base, definition["primary_category_id"],
                                  definition["secondary_category_ids"], confirm=False)
        if issues:
            raise ValueError("草稿引用的任务须在基础版本中有效。")
        sources = definition["source_intent_ids"]
        if (kind == "split" and len(targets) < 2) or (kind != "split" and targets):
            raise ValueError("拆分至少需要两个后继意图标识。")
        if (kind == "merge" and not sources) or (kind != "merge" and sources):
            raise ValueError("合并须指定前序意图。")
        for source in sources:
            _intent(db, base, source)
        for target in targets:
            _unused(db, study, draft, target)
        _check_lineage(db, study, draft, _edges(kind, intent, definition, targets))
