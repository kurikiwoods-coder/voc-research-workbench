"""C4 relation reads, candidate checks and atomic registry combinations."""

from collections import defaultdict
from contextlib import closing, contextmanager, nullcontext
from dataclasses import asdict, replace
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

from src.raw_store import relation_queries
from src.raw_store.denominators import denominators
from src.raw_store.corpus_policy import safe_source_url
from src.raw_store.mention_segments import validate_interval
from src.raw_store.mentions import MentionStore, _dependencies, _get_support, _grants, _head, _insert, _reference
from src.raw_store.relation_access import RelationAccess, RelationGrant
from src.raw_store.relation_registry import (
    IntentDefinition, PublishedProductRef, TaskDefinition, inherited_representatives,
    parent_violations, protect_published_products, registry_head, registry_version as check_registry_version, stage_registry,
    validate_definitions,
)
from src.raw_store.store import Conflict, dump, now


__all__ = ["IntentDefinition", "PublishedProductRef", "RelationGrant", "RelationStore", "TaskDefinition"]

ENGINEERING_ATTRIBUTION = relation_queries.ENGINEERING_ATTRIBUTION
COMBINATION = "c4_registry_combination"


def _references(refs, revision):
    if type(revision) is not int or revision < 1:
        raise ValueError("请指定有效的片段版本。")
    result = []
    for reference in refs:
        if isinstance(reference, dict):
            if reference.get("segment_revision", revision) != revision:
                raise Conflict("证据须属于指定片段版。")
            reference = (reference.get("mention_id"), reference.get("evidence_id"))
        if not isinstance(reference, (tuple, list)) or len(reference) != 2:
            raise ValueError("请提供准确的发生与证据引用。")
        result.append((revision, *(_reference(part) for part in reference)))
    if len(set(result)) != len(result):
        raise ValueError("请移除重复的证据引用。")
    return tuple(sorted(result))


def _command(db, study, key, operation, actor, payload):
    signature = sha256(dump([study, operation, actor, payload]).encode("utf-8")).hexdigest()
    prior = db.execute(
        """SELECT input_hash, result_ref FROM m06_command
           WHERE study_id=? AND namespace=? AND operation=? AND idempotency_key=?""",
        (study, f"study:{study}", operation, key),
    ).fetchone()
    if prior is None:
        return signature, None
    if prior["input_hash"] != signature:
        raise Conflict("这个命令键对应不同输入或授权身份。")
    return signature, json.loads(prior["result_ref"])


def _save(db, study, key, operation, actor, signature, result, timestamp, reason):
    _insert(db, "m06_command", command_id=result["command_id"], study_id=study,
            namespace=f"study:{study}", operation=operation, idempotency_key=key,
            input_hash=signature, actor_ref=actor, reason=reason, created_at=timestamp, result_ref=dump(result))


def _receipt(result):
    return {key: result[key] for key in ("command_id", "registry_version", "segment_revision", "intent_id")}


def _review_versions(db, dependencies):
    return [{"segment_revision": revision, "mention_id": mention, "evidence_id": evidence,
             "grants": _grants(db, group)} for (revision, mention, evidence), group in dependencies.items()]


def _protected_replay(result, dependencies, db):
    if result["supports"] != _review_versions(db, dependencies):
        raise Conflict("依赖原话的核验版本已变化，请重新审核。")
    return _receipt(result)


class RelationStore:
    """The server injects active grants for one trusted principal. Default access is definition-only."""

    def __init__(self, store, *, grants=None, published_refs=None):
        self.store = store
        self.mentions = MentionStore(store)
        self.corpus = self.mentions.corpus
        self.grants = grants
        self.published_refs = published_refs

    def _access(self):
        return RelationAccess(self.grants, now())

    def can_read_project(self, study_id):
        return self._access().permits("read", study_id)

    @contextmanager
    def _transaction(self, study=None, *, operation="read", write=False, publish=False):
        access = self._access() if study is not None else None
        if access is not None:
            access.require("read", study)
            access.require(operation, study)
            if publish:
                access.require("publish_registry", None)
        with closing(self.store.connect()) as db:
            snapshot = db.execute("PRAGMA data_version").fetchone()[0] if not write else None
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                if study is not None:
                    row = db.execute("SELECT status FROM study_projects WHERE study_id=?", (study,)).fetchone()
                    if row is None:
                        raise KeyError(study)
                    if write and row[0] == "archived":
                        raise Conflict("归档项目不能提交关系。")
                    self._check_access(access, study, write=write)
                yield db, access
                db.execute("COMMIT")
                if not write:
                    if access is not None:
                        self._check_access(access, study, write=False)
                        self.corpus._check_day(access.at.date().isoformat())
                    if db.execute("PRAGMA data_version").fetchone()[0] != snapshot:
                        raise Conflict("读取期间资料已变化，请重新查询。")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _check_access(self, access, study, *, write):
        if not access.same_as(self._access(), study):
            if write:
                raise PermissionError("项目授权已变化。")
            raise KeyError(study)

    def definitions(self, kind, *, registry_version=None, object_id=None, **filters):
        with self._transaction() as (db, _):
            return relation_queries.definitions(db, kind, registry_version=registry_version, object_id=object_id, **filters)

    def task_intent_edges(self, *, registry_version=None, task_id=None, intent_id=None, role="all", **filters):
        with self._transaction() as (db, _):
            return relation_queries.task_intent_edges(
                db, registry_version=registry_version, task_id=task_id, intent_id=intent_id, role=role, **filters,
            )

    def _project_query(self, query, study, mode, versions, filters, *, audit_tombstones=False, **selection):
        if mode not in {"formal", "engineering", "synthetic"}:
            raise ValueError("关系浏览模式无效。")
        with self._transaction(study) as (db, access):
            can_read = None
            if not access.permits("read", study, entire_project=True):
                can_read = lambda revision, mention, evidence: access.permits("read", study, (revision, mention, evidence))
            if audit_tombstones and access.permits("audit", study):
                def can_audit(revision, mention, evidence):
                    reference = (revision, mention, evidence)
                    return all(access.permits(operation, study, reference) for operation in ("read", "audit"))

                selection["can_audit"] = can_audit
            return query(db, self.mentions, study, **versions, **selection, filters={**(filters or {}), "mode": mode},
                         can_read=can_read, today=access.at.date().isoformat())

    def product_intent_edges(self, study_id, *, registry_version=None, segment_revision=None,
                             product_id=None, intent_id=None, filters=None, mode="engineering"):
        return self._project_query(
            relation_queries.product_intent_edges, study_id, mode,
            {"registry_version": registry_version, "segment_revision": segment_revision},
            filters, product_id=product_id, intent_id=intent_id,
        )

    def project_mentions(self, study_id, *, registry_version=None, segment_revision=None,
                         mention_id=None, filters=None, mode="engineering"):
        return self._project_query(
            relation_queries.project_mentions, study_id, mode,
            {"registry_version": registry_version, "segment_revision": segment_revision},
            filters, mention_id=mention_id, audit_tombstones=True,
        )

    def denominators(self, study_id, *, registry_version=None, segment_revision=None, filters=None,
                     mode, synthetic=None, batch_qualification=True):
        return denominators(self, study_id, registry_version=registry_version, segment_revision=segment_revision,
                            filters=filters, mode=mode, synthetic=synthetic, batch_qualification=batch_qualification)

    def read_evidence(self, study_id, revision, mention_id, evidence_id):
        with self._transaction(study_id, operation="evidence") as (db, access):
            reference = (revision, mention_id, evidence_id)
            for operation in ("read", "evidence"):
                access.require(operation, study_id, reference)
            segment = db.execute(
                "SELECT rule_version FROM m06_segment_rev WHERE study_id=? AND segment_revision=? AND sealed=1",
                (study_id, revision),
            ).fetchone()
            if segment is None:
                raise KeyError(revision)
            support = _get_support(db, study_id, revision, mention_id, evidence_id)
            (record, excerpt), _ = self.mentions._qualified_evidence(
                db, study_id, revision, mention_id, support, access.at.date().isoformat(), {},
            )
            trace = record["trace"]
            source_url = record["metadata"].get("source_url")
            duplicate = record["duplicate"]
            return {
                "study_id": study_id, "segment_revision": revision, "revision": revision, "mention_id": mention_id,
                "evidence_id": evidence_id, "excerpt": excerpt, **asdict(support.interval),
                "scope_id": support.scope_id, "scope_version": trace["scope_version"],
                "batch_id": trace["batch_id"], "line_number": trace["line_number"],
                "source_url": source_url if safe_source_url(source_url) else None,
                "rule_version": segment["rule_version"], "license_status": record["license_status"],
                "privacy": record["privacy"], "duplicate": {"group_id": duplicate["group_id"]} if duplicate else None,
                "research_eligible": False, "outbound_allowed": False,
            }

    @staticmethod
    def _expect_versions(db, study, version, revision):
        if (registry_head(db), _head(db, study)) != (version, revision):
            raise Conflict("注册表或片段版本已变化。")

    @staticmethod
    def _collect(db, access, study, refs, operation):
        dependencies = {}
        states = {}
        for reference in refs:
            revision, mention, evidence = reference
            for permission in ("read", "evidence", operation):
                access.require(permission, study, reference)
            row = db.execute(
                """SELECT member.identity_state FROM m06_member member JOIN m06_segment_rev segment
                   USING (study_id, segment_revision)
                   WHERE member.study_id=? AND member.segment_revision=? AND member.mention_id=? AND segment.sealed=1""",
                (study, revision, mention),
            ).fetchone()
            if row is None:
                raise KeyError(mention)
            support = _get_support(db, study, revision, mention, evidence)
            dependencies[reference] = _dependencies(db, study, revision, mention, support)
            anchor = support.event_anchor
            if support.original_id is not None:
                anchor = _get_support(db, study, revision, mention, support.original_id).event_anchor
            states[reference] = (row[0], anchor)
        return dependencies, states

    @contextmanager
    def _qualified_refs(self, db, study, dependencies):
        record_ids = [
            interval.record_id for group in dependencies.values() for interval, _ in group.values()
        ]
        checks = self.corpus.qualified_write_inputs(db, study, record_ids) if record_ids else nullcontext({})
        with checks as records:
            for group in dependencies.values():
                for interval, scope in group.values():
                    validate_interval(interval, records[interval.record_id], study_id=study, scope_id=scope)
            yield

    @staticmethod
    def _independent(states, refs):
        distinct = defaultdict(set)
        for reference in refs:
            state, anchor = states[reference]
            if state == "distinct":
                distinct[reference[1]].add(anchor or reference[1])
        anchors = set()
        for own_anchors in distinct.values():
            if anchors.isdisjoint(own_anchors):
                anchors.update(own_anchors)
            else:
                return 0
        return len(distinct)

    def validate(self, study_id, *, operation, candidate_intent_id, expected_registry_version, expected_segment_revision,
                 candidate_category_id=None, primary_category_id=None, secondary_ids=(), representative_refs=()):
        if operation not in {"confirm", "candidate"}:
            raise ValueError("预检操作无效。")
        _reference(candidate_intent_id)
        if candidate_category_id is not None:
            _reference(candidate_category_id)
        if expected_registry_version is not None:
            check_registry_version(expected_registry_version)
        refs = _references(representative_refs, expected_segment_revision)
        with self._transaction(study_id, operation="validate") as (db, access):
            self._expect_versions(db, study_id, expected_registry_version, expected_segment_revision)
            confirm = operation == "confirm"
            violations = parent_violations(
                db, expected_registry_version, primary_category_id, tuple(secondary_ids or ()), confirm=confirm,
            )
            _, states = self._collect(db, access, study_id, refs, "validate")
            cache = {}
            for revision, mention, evidence in refs:
                self.mentions._qualified_evidence(
                    db, study_id, revision, mention, _get_support(db, study_id, revision, mention, evidence),
                    access.at.date().isoformat(), cache,
                )
            if confirm and self._independent(states, refs) < 3:
                violations.append("REPRESENTATIVES_INSUFFICIENT")
            return {"valid": not violations, "violations": violations, "candidate_allowed": True,
                    "lifecycle_status": "pending_parent" if primary_category_id is None else "candidate",
                    "registry_version": expected_registry_version, "segment_revision": expected_segment_revision}

    def attribute(self, study_id, *, key, expected_registry_version, expected_segment_revision, intent_id, supports):
        """Register explicitly approved engineering inputs against an existing version."""
        _reference(key)
        _reference(intent_id)
        check_registry_version(expected_registry_version)
        references = _references(supports, expected_segment_revision)
        if not references:
            raise ValueError("工程关系需要直接证据。")
        with self._transaction(study_id, operation="attribute", write=True) as (db, access):
            payload = [expected_registry_version, intent_id, references]
            signature, prior = _command(db, study_id, key, ENGINEERING_ATTRIBUTION, access.actor, payload)
            if prior is None:
                self._expect_versions(db, study_id, expected_registry_version, expected_segment_revision)
            row = db.execute(
                """SELECT lifecycle_status FROM m06_intent JOIN m06_registry USING(registry_version)
                   WHERE registry_version=? AND intent_id=? AND sealed=1""",
                (expected_registry_version, intent_id),
            ).fetchone()
            if row is None:
                raise KeyError(intent_id)
            if row[0] != "confirmed":
                raise Conflict("工程归属需要已确认意图。")
            dependencies, states = self._collect(db, access, study_id, references, "attribute")
            if any(state != "distinct" for state, _ in states.values()):
                raise Conflict("工程归属需要已区分的发生。")
            with self._qualified_refs(db, study_id, dependencies):
                if prior is not None:
                    result = _protected_replay(prior, dependencies, db)
                else:
                    result = self._save_attribution(
                        db, study_id, key, intent_id, expected_registry_version, expected_segment_revision,
                        dependencies, signature, access.actor,
                    )
                self._check_access(access, study_id, write=True)
            return result

    @staticmethod
    def _save_attribution(db, study, key, intent, version, revision, dependencies, signature, actor):
        result = {"command_id": str(uuid4()), "registry_version": version, "segment_revision": revision,
                  "intent_id": intent, "supports": _review_versions(db, dependencies)}
        _save(db, study, key, ENGINEERING_ATTRIBUTION, actor, signature, result, now(), ENGINEERING_ATTRIBUTION)
        return _receipt(result)

    def publish_combination(self, study_id, *, key, expected_registry_version, expected_segment_revision,
                            registry_version, intent, tasks=(), primary_category_id=None, secondary_ids=(),
                            representative_refs=(), approval_ref, attribution_refs=()):
        """Seal a complete registry snapshot and project result in the caller's one write transaction."""
        key, approval_ref = _reference(key), _reference(approval_ref)
        version = check_registry_version(registry_version)
        if expected_registry_version is not None:
            check_registry_version(expected_registry_version)
        tasks = tuple(sorted(tasks, key=lambda task: task.category_id))
        secondaries = tuple(sorted(secondary_ids))
        refs = _references(representative_refs, expected_segment_revision)
        attribution = _references(attribution_refs, expected_segment_revision)
        validate_definitions(intent, tasks)
        if primary_category_id is None and intent.lifecycle_status == "candidate":
            intent = replace(intent, lifecycle_status="pending_parent")
        confirm = intent.lifecycle_status == "confirmed"
        if attribution and not confirm:
            raise ValueError("工程归属需要已确认意图。")
        payload = [expected_registry_version, expected_segment_revision, version, asdict(intent),
                   [asdict(task) for task in tasks], primary_category_id, secondaries, refs, approval_ref, attribution]
        with self._transaction(study_id, operation="validate", write=True, publish=True) as (db, access):
            for reference in attribution:
                access.require("attribute", study_id, reference)
            signature, prior = _command(db, study_id, key, COMBINATION, access.actor, payload)
            if prior is None:
                self._expect_versions(db, study_id, expected_registry_version, expected_segment_revision)
            inherited = inherited_representatives(db, expected_registry_version, study_id, intent.intent_id)
            inherited_keys = [(row["segment_revision"], row["mention_id"], row["evidence_id"]) for row in inherited]
            dependencies, states = self._collect(
                db, access, study_id, sorted(set((*inherited_keys, *refs, *attribution))), "validate",
            )
            if parent_violations(db, expected_registry_version, primary_category_id, secondaries, confirm=confirm, tasks=tasks):
                raise ValueError("主任务或次任务未通过版次和状态检查。")
            if confirm and self._independent(states, refs) < 3:
                raise ValueError("确认意图至少需要三次可核独立发生。")
            if any(states[reference][0] != "distinct" for reference in attribution):
                raise Conflict("工程归属需要已区分的发生。")
            with self._qualified_refs(db, study_id, dependencies):
                if prior is not None:
                    result = _protected_replay(prior, dependencies, db)
                else:
                    result = self._publish(
                        db, study_id, key, signature, access.actor, approval_ref, version, expected_registry_version,
                        expected_segment_revision, intent, tasks, primary_category_id, secondaries, inherited, refs,
                        attribution, dependencies,
                    )
                self._check_access(access, study_id, write=True)
            return result

    def _publish(self, db, study, key, signature, actor, approval, version, parent, revision,
                 intent, tasks, primary, secondaries, inherited, refs, attribution, dependencies):
        timestamp = now()
        result = {"command_id": str(uuid4()), "registry_version": version, "segment_revision": revision,
                  "intent_id": intent.intent_id, "supports": _review_versions(db, dependencies)}
        _save(db, study, key, COMBINATION, actor, signature, result, timestamp, approval)
        stage_registry(db, version, parent, result["command_id"], timestamp, intent, tasks, primary, secondaries,
                       inherited, [(mention, evidence) for _, mention, evidence in refs], study, revision)
        if self.published_refs is not None:
            protect_published_products(db, version, self.published_refs())
        db.execute("UPDATE m06_registry SET sealed=1 WHERE registry_version=?", (version,))
        if attribution:
            attest = {reference: dependencies[reference] for reference in attribution}
            self._save_attribution(db, study, f"combination:{result['command_id']}", intent.intent_id, version,
                                   revision, attest, signature, actor)
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.IntegrityError("关系发行包含未满足的外键。")
        return _receipt(result)
