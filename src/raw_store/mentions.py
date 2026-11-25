"""Publish C3 occurrence revisions and qualify their evidence on use."""

from collections import defaultdict
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
import sqlite3
from uuid import uuid4

from src.raw_store.corpus import CorpusStore
from src.raw_store.corpus_policy import safe_source_url
from src.raw_store.mention_identity import event_anchor, validate_identity
from src.raw_store.mention_products import (
    ProductProposal, ReviewDecision, prepare_product_proposal, prepare_product_review, scope_mapping,
)
from src.raw_store.mention_segments import (
    EvidenceInterval, MentionDraft, Replacement, SupportDraft, require_replacement_lineage,
    validate_interval, validate_replacements,
)
from src.raw_store.store import Conflict, dump, now

__all__ = [
    "EvidenceInterval", "MentionDraft", "MentionStore", "ProductProposal",
    "Replacement", "ReviewDecision", "SupportDraft",
]

SUPPORTS = """SELECT s.*, e.scope_id, e.record_id, e.raw_sha256, e.start_cp, e.end_cp
    FROM m06_support s JOIN m06_evidence e USING (study_id, evidence_id)
    WHERE s.study_id=? AND s.segment_revision=?"""

EDGE_KEY = ("mention_id", "evidence_id", "catalog_version", "product_category_id")
REVIEW_FIELDS = (*EDGE_KEY, "decision_seq", "decision", "basis_ref", "mode", "proposal_provenance")


@dataclass(frozen=True)
class _Support:
    evidence_id: str
    interval: EvidenceInterval
    scope_id: str
    identity: str
    context_ids: tuple[str, ...]
    original_id: str | None
    event_anchor: str | None

    @classmethod
    def from_row(cls, row):
        basis = json.loads(row["occurrence_basis"])
        return cls(
            row["evidence_id"], _interval(row), row["scope_id"], basis["identity"],
            tuple(basis["contexts"]), basis["original"], basis.get("event_anchor"),
        )


def _interval(row):
    return EvidenceInterval(row["record_id"], row["raw_sha256"], row["start_cp"], row["end_cp"])


def _reference(value):
    # Caller references are opaque tokens, not descriptions or excerpts.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value):
        raise ValueError("请使用受控标识引用操作、规则或审核依据。")
    return value


def _insert(db, table, **values):
    db.execute(
        f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
        tuple(values.values()),
    )


def _head(db, study_id):
    return db.execute(
        "SELECT COALESCE(MAX(segment_revision), 0) FROM m06_segment_rev WHERE study_id=? AND sealed=1",
        (study_id,),
    ).fetchone()[0]


def _expect_head(db, study_id, expected):
    if _head(db, study_id) != expected:
        raise Conflict("片段版已变化，请重新读取并核对当前版本。")


def _supports(db, study_id, revision):
    return db.execute(SUPPORTS + " ORDER BY s.segment_no, s.evidence_id", (study_id, revision)).fetchall()


def _get_support(db, study_id, revision, mention_id, evidence_id):
    row = db.execute(
        SUPPORTS + " AND s.mention_id=? AND s.evidence_id=?",
        (study_id, revision, mention_id, evidence_id),
    ).fetchone()
    if row is None:
        raise KeyError(evidence_id)
    return _Support.from_row(row)


def _require_distinct(db, study_id, revision, mention_id):
    state = db.execute(
        "SELECT identity_state FROM m06_member WHERE study_id=? AND segment_revision=? AND mention_id=?",
        (study_id, revision, mention_id),
    ).fetchone()
    if state is None or state["identity_state"] != "distinct":
        raise Conflict("需求发生的身份尚未核定。")


def _evidence(db, study_id, interval, scope_id):
    values = (study_id, interval.record_id, interval.raw_sha256, interval.start_cp, interval.end_cp)
    stored = db.execute(
        """SELECT evidence_id FROM m06_evidence
           WHERE study_id=? AND record_id=? AND raw_sha256=? AND start_cp=? AND end_cp=?""",
        values,
    ).fetchone()
    if stored is not None:
        return stored["evidence_id"]
    evidence_id = str(uuid4())
    _insert(
        db, "m06_evidence", study_id=study_id, evidence_id=evidence_id, scope_id=scope_id,
        record_id=interval.record_id, raw_sha256=interval.raw_sha256,
        start_cp=interval.start_cp, end_cp=interval.end_cp,
    )
    return evidence_id


def _dependencies(db, study_id, revision, mention_id, support):
    """Resolve the stored direct, context and explicit original evidence IDs."""
    result = {support.evidence_id: (support.interval, support.scope_id)}
    required_ids = support.context_ids
    if support.original_id is not None:
        original = _get_support(db, study_id, revision, mention_id, support.original_id)
        if original.identity != "independent":
            raise Conflict("转载依赖的原帖身份无法核对。")
        required_ids += (original.evidence_id, *original.context_ids)
    for evidence_id in required_ids:
        if evidence_id in result:
            continue
        row = db.execute(
            "SELECT * FROM m06_evidence WHERE study_id=? AND evidence_id=?", (study_id, evidence_id),
        ).fetchone()
        if row is None or row["scope_id"] != support.scope_id:
            raise Conflict("证据的上下文引用无法核对。")
        result[evidence_id] = (_interval(row), row["scope_id"])
    return result


def _grants(db, dependencies):
    # Bind confirmed decisions to the M05 review versions actually used.
    return {
        evidence_id: db.execute(
            "SELECT MAX(review_id) FROM corpus_reviews WHERE record_id=?", (interval.record_id,),
        ).fetchone()[0]
        for evidence_id, (interval, _) in dependencies.items()
    }


def _latest_reviews(db, study_id, revision, mention_id):
    return db.execute(
        """SELECT * FROM m06_product_review r
           WHERE study_id=? AND segment_revision=? AND mention_id=? AND decision_seq=(
               SELECT MAX(x.decision_seq) FROM m06_product_review x
               WHERE (x.study_id, x.segment_revision, x.mention_id, x.evidence_id,
                      x.catalog_version, x.product_category_id)=
                     (r.study_id, r.segment_revision, r.mention_id, r.evidence_id,
                      r.catalog_version, r.product_category_id)
           ) ORDER BY catalog_version, product_category_id, evidence_id""",
        (study_id, revision, mention_id),
    )


def _save_review(db, study_id, revision, command_id, actor, at, values):
    _insert(
        db, "m06_product_review", study_id=study_id, segment_revision=revision,
        command_id=command_id, actor_ref=actor, decided_at=at,
        **{field: values[field] for field in REVIEW_FIELDS},
    )


class MentionStore:
    """Local C3 service. The application supplies a trusted project authorizer."""

    def __init__(self, store, *, authorize=None):
        self.store = store
        self.corpus = CorpusStore(store)
        self.authorize = authorize

    def _actors(self, study_id, permissions):
        actors = {}
        for permission in permissions:
            actor = self.authorize(study_id, permission) if self.authorize is not None else None
            if not isinstance(actor, str) or not actor.strip():
                if permission == "read":
                    raise KeyError(study_id)
                raise PermissionError("项目未授予此次操作所需权限。")
            actors[permission] = _reference(actor)
        return actors

    @contextmanager
    def _transaction(self, study_id, permissions, *, write=False):
        actors = self._actors(study_id, permissions)
        with closing(self.store.connect()) as db:
            data_version = None if write else db.execute("PRAGMA data_version").fetchone()[0]
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                project = db.execute("SELECT status FROM study_projects WHERE study_id=?", (study_id,)).fetchone()
                if project is None:
                    raise KeyError(study_id)
                if write and project["status"] == "archived":
                    raise Conflict("归档项目不能发布或审核片段。")
                if self._actors(study_id, permissions) != actors:
                    raise PermissionError("项目授权已变化。")
                yield db, actors
                db.execute("COMMIT")
                if not write:
                    if self._actors(study_id, permissions) != actors:
                        raise KeyError(study_id)
                    if db.execute("PRAGMA data_version").fetchone()[0] != data_version:
                        raise Conflict("读取期间研究库已变化，请重新取得当前证据。")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    @staticmethod
    def _command(db, study_id, key, operation, actors, payload):
        namespace = f"study:{study_id}"
        input_hash = sha256(dump([namespace, operation, actors, payload]).encode("utf-8")).hexdigest()
        prior = db.execute(
            "SELECT input_hash, result_ref FROM m06_command WHERE namespace=? AND operation=? AND idempotency_key=?",
            (namespace, operation, key),
        ).fetchone()
        if prior is not None:
            if prior["input_hash"] != input_hash:
                raise Conflict("此幂等键已用于其他输入或审核身份。")
            return input_hash, json.loads(prior["result_ref"])
        return input_hash, None

    @staticmethod
    def _save_command(db, study_id, key, operation, input_hash, actor, result, at):
        command_id = str(uuid4())
        _insert(
            db, "m06_command", command_id=command_id, study_id=study_id, namespace=f"study:{study_id}",
            operation=operation, idempotency_key=key, input_hash=input_hash, actor_ref=actor,
            reason=operation, created_at=at, result_ref=dump(result),
        )
        return command_id

    def publish_revision(self, study_id, *, key, expected_revision, rule_version, members, replacements=(), proposals=()):
        """Atomically publish the complete C3 membership for one project revision."""
        _reference(key)
        _reference(rule_version)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("缺少有效的父片段版。")
        members, replacements, proposals = tuple(members), tuple(replacements), tuple(proposals)
        if not members:
            raise ValueError("发布片段版至少需要一个有原话支持的发生。")
        seen = set()
        refs = set()
        for member in members:
            _reference(member.ref)
            if member.ref in refs or not member.supports:
                raise ValueError("发生引用须唯一，且至少有一个直接证据区间。")
            refs.add(member.ref)
            if member.mention_id is not None:
                _reference(member.mention_id)
            for support in member.supports:
                _reference(support.basis_ref)
                if type(support.segment_no) is not int or support.segment_no < 1 or support.interval in seen:
                    raise ValueError("证据区间须唯一，段序须为正整数。")
                if support.interval in support.contexts or len(set(support.contexts)) != len(support.contexts):
                    raise ValueError("上下文不能重复或自指。")
                seen.add(support.interval)
        for replacement in replacements:
            _reference(replacement.reason)
        for proposal in proposals:
            _reference(proposal.basis_ref)
            _reference(proposal.rule_version)
        membership = {member.ref: member.supports for member in members}
        if any(not any(s.interval == p.interval for s in membership.get(p.member_ref, ())) for p in proposals):
            raise ValueError("产品提议须绑定当前版成员的直接证据。")
        intervals = tuple(dict.fromkeys(
            interval for member in members for support in member.supports
            for interval in (support.interval, *support.contexts, support.original) if interval is not None
        ))
        payload = [expected_revision, rule_version, [asdict(m) for m in members],
                   [asdict(r) for r in replacements], [asdict(p) for p in proposals]]
        permissions = ("segment", "identity")
        with self._transaction(study_id, permissions, write=True) as (db, actors):
            input_hash, replay = self._command(db, study_id, key, "publish_revision", actors, payload)
            if replay is None:
                _expect_head(db, study_id, expected_revision)
            record_ids = (interval.record_id for interval in intervals)
            with self.corpus.qualified_write_inputs(db, study_id, record_ids) as records:
                if replay is None:
                    replay = self._publish(
                        db, study_id, key, expected_revision, rule_version, members, replacements,
                        proposals, intervals, records, actors, input_hash,
                    )
                if self._actors(study_id, permissions) != actors:
                    raise PermissionError("项目授权已变化。")
            return replay

    @staticmethod
    def _member_ids(db, study_id, parent, members, replacements, event_anchors):
        history = {}
        source_events = {}
        parent_support = defaultdict(list)
        previous = db.execute(
            """SELECT s.*, e.scope_id, e.record_id, e.raw_sha256, e.start_cp, e.end_cp
               FROM m06_support s JOIN m06_evidence e USING (study_id, evidence_id)
               WHERE s.study_id=? ORDER BY s.segment_revision DESC""",
            (study_id,),
        )
        for row in previous:
            support = _Support.from_row(row)
            if support.identity != "repost":
                mention_id = row["mention_id"]
                history.setdefault(support.interval, mention_id)
                if support.event_anchor:
                    source_events.setdefault(support.event_anchor, mention_id)
                if row["segment_revision"] == parent:
                    parent_support[mention_id].append(support)
        retired = {row[0] for row in db.execute(
            "SELECT DISTINCT old_mention_id FROM m06_replacement WHERE study_id=?", (study_id,),
        )}
        targets = {edge.to_ref for edge in replacements}
        result = {}
        anchors = {}
        fresh = set()
        current_events = set()
        for member in members:
            intervals = [s.interval for s in member.supports if s.identity != "repost"]
            anchors[member.ref] = intervals
            events = {event_anchors[interval] for interval in intervals if event_anchors[interval]}
            if events & current_events:
                raise Conflict("同一来源事件和原文区间不能登记两次发生。")
            current_events.update(events)
            prior_ids = {history[interval] for interval in intervals if interval in history}
            prior_ids.update(source_events[event] for event in events if event in source_events)
            if len(prior_ids) > 1:
                raise Conflict("多个原帖区间引用不同的既有发生，须先完成带谱系的复核。")
            prior = next(iter(prior_ids), None)
            if member.ref in targets:
                if member.mention_id is not None:
                    raise Conflict("拆并后继须新建发生 ID。")
                # Exact anchors owned by a surviving parent cannot move to a different occurrence.
                if prior in parent_support and not any(
                    edge.to_ref == member.ref and edge.from_mention_id == prior for edge in replacements
                ):
                    raise Conflict("拆并后继引用了未被替换的原版发生。")
                mention_id = None
            else:
                mention_id = member.mention_id or prior
                if mention_id in retired:
                    raise Conflict("已被拆并替换的发生不能重新激活。")
                if member.mention_id is not None and mention_id != prior:
                    # Corrections keep an overlapping range on the same immutable record.
                    if prior is not None or not any(
                        s.interval.record_id == interval.record_id
                        and s.interval.raw_sha256 == interval.raw_sha256
                        and max(s.interval.start_cp, interval.start_cp) < min(s.interval.end_cp, interval.end_cp)
                        for s in parent_support.get(mention_id, ()) for interval in intervals
                    ):
                        raise Conflict("当前证据无法核对所引用的既有发生。")
            if mention_id is None:
                mention_id = str(uuid4())
                fresh.add(mention_id)
            result[member.ref] = mention_id
        retained = set(result.values())
        if len(retained) != len(result):
            raise Conflict("同版应仅保留每个稳定发生一次。")
        validate_replacements(replacements, parent_support, result, fresh)
        require_replacement_lineage(
            ((ident, support.interval) for ident, supports in parent_support.items() if ident not in retained
             for support in supports),
            ((ref, interval) for ref, ident in result.items() if ident in fresh for interval in anchors[ref]),
            replacements,
        )
        return result, fresh

    def _publish(
        self, db, study_id, key, parent, rule_version, members, replacements, proposals, intervals,
        records, actors, input_hash,
    ):
        scopes = {interval: records[interval.record_id]["trace"]["scope_id"] for interval in intervals}
        excerpts = {
            interval: validate_interval(interval, records[interval.record_id], study_id=study_id, scope_id=scopes[interval])
            for interval in intervals
        }
        identity_anchors = {
            interval: event_anchor(records[interval.record_id], interval) for interval in intervals
        }
        states = {}
        for member in members:
            for support in member.supports:
                if any(scopes[other] != scopes[support.interval] for other in (*support.contexts, support.original)
                       if other is not None):
                    raise Conflict("直接证据及其上下文、原帖须绑定同一冻结范围。")
            states[member.ref] = validate_identity(member.supports, records, identity_anchors)
        event_anchors = {
            support.interval: identity_anchors[support.interval] if support.identity == "independent" else None
            for member in members for support in member.supports
        }
        member_ids, fresh = self._member_ids(db, study_id, parent, members, replacements, event_anchors)
        evidence_ids = {interval: _evidence(db, study_id, interval, scopes[interval]) for interval in intervals}
        revision = parent + 1
        result = {"revision": revision, "members": [
            {"ref": member.ref, "mention_id": member_ids[member.ref],
             "evidence_ids": [evidence_ids[s.interval] for s in member.supports]} for member in members
        ]}
        at = now()
        command_id = self._save_command(
            db, study_id, key, "publish_revision", input_hash, actors["segment"], result, at,
        )
        _insert(
            db, "m06_segment_rev", study_id=study_id, segment_revision=revision, parent_rev=parent or None,
            rule_version=rule_version, created_at=at, command_id=command_id,
        )
        for mention_id in fresh:
            _insert(db, "m06_mention", study_id=study_id, mention_id=mention_id, created_at=at)
        for member in members:
            mention_id = member_ids[member.ref]
            _insert(db, "m06_member", study_id=study_id, segment_revision=revision,
                    mention_id=mention_id, identity_state=states[member.ref])
            for support in member.supports:
                _insert(
                    db, "m06_support", study_id=study_id, segment_revision=revision, mention_id=mention_id,
                    evidence_id=evidence_ids[support.interval], segment_no=support.segment_no,
                    review_ref=support.basis_ref, occurrence_basis=dump({
                        "identity": support.identity, "reviewer": actors["identity"],
                        "original": evidence_ids.get(support.original),
                        "contexts": [evidence_ids[context] for context in support.contexts],
                        "event_anchor": event_anchors.get(support.interval),
                    }),
                )
        for edge in replacements:
            _insert(db, "m06_replacement", study_id=study_id, segment_revision=revision, old_rev=parent,
                    old_mention_id=edge.from_mention_id, new_mention_id=member_ids[edge.to_ref], reason=edge.reason)
        edge_keys = set()
        for proposal in proposals:
            values = prepare_product_proposal(
                db, study_id, scopes[proposal.interval], proposal, mention_id=member_ids[proposal.member_ref],
                evidence_id=evidence_ids[proposal.interval], excerpt=excerpts[proposal.interval],
            )
            edge = {field: values[field] for field in EDGE_KEY}
            if tuple(edge.values()) in edge_keys:
                raise ValueError("同一产品提议不能在片段版重复登记。")
            edge_keys.add(tuple(edge.values()))
            _insert(db, "m06_mention_product", study_id=study_id, segment_revision=revision,
                    command_id=command_id, link_type=values["link_type"], **edge)
            _save_review(db, study_id, revision, command_id, actors["segment"], at, values)
        db.execute(
            "UPDATE m06_segment_rev SET sealed=1 WHERE study_id=? AND segment_revision=?", (study_id, revision),
        )
        # SQLite 3.45 can lose a deferred violation when sealing a self-referencing revision.
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.IntegrityError("片段封版未通过数据库外键检查。")
        return result

    def review_products(self, study_id, *, key, expected_revision, decisions):
        """Append mode A decisions in one C2-qualified transaction."""
        _reference(key)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("产品审核需要有效的片段版。")
        decisions = tuple(decisions)
        if not decisions:
            raise ValueError("请提供至少一条产品审核。")
        keys = set()
        for decision in decisions:
            _reference(decision.basis_ref)
            edge = tuple(getattr(decision, field) for field in EDGE_KEY)
            if edge in keys:
                raise ValueError("不能在同一审核命令重复提交产品边。")
            keys.add(edge)
        payload = [expected_revision, [asdict(d) for d in decisions]]
        with self._transaction(study_id, ("product_review",), write=True) as (db, actors):
            actor = actors["product_review"]
            input_hash, replay = self._command(db, study_id, key, "review_products", actors, payload)
            if replay is None:
                _expect_head(db, study_id, expected_revision)
            supports = [
                _get_support(db, study_id, expected_revision, decision.mention_id, decision.evidence_id)
                for decision in decisions
            ]
            dependencies = [
                _dependencies(db, study_id, expected_revision, decision.mention_id, support)
                for decision, support in zip(decisions, supports, strict=True)
            ]
            ids = (interval.record_id for group in dependencies for interval, _ in group.values())
            with self.corpus.qualified_write_inputs(db, study_id, ids) as records:
                if replay is None:
                    replay = self._review(
                        db, study_id, key, expected_revision, decisions, supports, dependencies, records, actor, input_hash,
                    )
                if self._actors(study_id, ("product_review",)) != actors:
                    raise PermissionError("项目授权已变化。")
            return replay

    def _review(self, db, study_id, key, revision, decisions, supports, dependencies, records, actor, input_hash):
        reviews = []
        for decision, support, group in zip(decisions, supports, dependencies, strict=True):
            if decision.decision == "human_confirmed":
                _require_distinct(db, study_id, revision, decision.mention_id)
            excerpts = {
                evidence_id: validate_interval(interval, records[interval.record_id], study_id=study_id, scope_id=scope)
                for evidence_id, (interval, scope) in group.items()
            }
            values = prepare_product_review(
                db, study_id, revision, decision, excerpt=excerpts[support.evidence_id], actor_ref=actor,
                grants=_grants(db, group),
            )
            reviews.append(values)
        result = {"revision": revision, "decisions": [
            {field: values[field] for field in (*EDGE_KEY, "decision_seq")} for values in reviews
        ]}
        at = now()
        command_id = self._save_command(db, study_id, key, "review_products", input_hash, actor, result, at)
        for values in reviews:
            _save_review(db, study_id, revision, command_id, actor, at, values)
        return result

    def _qualified_evidence(self, db, study_id, revision, mention_id, support, today, cache):
        records = {}
        dependencies = _dependencies(db, study_id, revision, mention_id, support)
        for evidence_id, (interval, scope) in dependencies.items():
            if interval.record_id not in cache:
                try:
                    cache[interval.record_id] = self.corpus.qualified_record_in_transaction(
                        db, study_id, interval.record_id, today=today,
                    )
                except (Conflict, KeyError):
                    self.corpus._check_day(today)
                    cache[interval.record_id] = None
            record = cache[interval.record_id]
            if record is None:
                raise Conflict("证据或其依赖原话当前失格。")
            excerpt = validate_interval(interval, record, study_id=study_id, scope_id=scope)
            records[evidence_id] = (record, excerpt)
        return records[support.evidence_id], dependencies

    def read_evidence(self, study_id, revision, mention_id, evidence_id):
        """Read the exact support, using current M05 qualification for every dependency."""
        with self._transaction(study_id, ("read",)) as (db, _):
            row = db.execute(
                "SELECT rule_version FROM m06_segment_rev WHERE study_id=? AND segment_revision=? AND sealed=1",
                (study_id, revision),
            ).fetchone()
            if row is None:
                raise KeyError(revision)
            support = _get_support(db, study_id, revision, mention_id, evidence_id)
            today = now()[:10]
            (record, excerpt), _ = self._qualified_evidence(db, study_id, revision, mention_id, support, today, {})
            self.corpus._check_day(today)
            source_url = record["metadata"].get("source_url")
            return {
                "study_id": study_id, "revision": revision, "mention_id": mention_id,
                "evidence_id": evidence_id, "excerpt": excerpt, **asdict(support.interval),
                "scope_id": support.scope_id, "scope_version": record["trace"]["scope_version"],
                "batch_id": record["trace"]["batch_id"], "rule_version": row["rule_version"],
                "source_url": source_url if safe_source_url(source_url) else None,
                "license_status": record["license_status"], "privacy": record["privacy"],
                "duplicate": record["duplicate"], "contexts": list(support.context_ids),
                "original_evidence_id": support.original_id,
                "research_eligible": False, "outbound_allowed": False,
            }

    def read_revision(self, study_id, revision=None):
        """Return a sealed revision with the current project-local evidence projection."""
        with self._transaction(study_id, ("read",)) as (db, _):
            revision = _head(db, study_id) if revision is None else revision
            header = db.execute(
                """SELECT parent_rev, rule_version FROM m06_segment_rev
                   WHERE study_id=? AND segment_revision=? AND sealed=1""",
                (study_id, revision),
            ).fetchone()
            if header is None:
                raise KeyError(revision)
            today = now()[:10]
            records = {}
            visible = defaultdict(dict)
            for row in _supports(db, study_id, revision):
                support = _Support.from_row(row)
                try:
                    _, dependencies = self._qualified_evidence(
                        db, study_id, revision, row["mention_id"], support, today, records,
                    )
                except Conflict:
                    continue
                visible[row["mention_id"]][support.evidence_id] = dependencies
            members = []
            for row in db.execute(
                "SELECT mention_id, identity_state FROM m06_member WHERE study_id=? AND segment_revision=? ORDER BY mention_id",
                (study_id, revision),
            ):
                mention_id, state = row
                evidence = visible.get(mention_id)
                if not evidence:
                    continue
                products = []
                for review in _latest_reviews(db, study_id, revision, mention_id):
                    group = evidence.get(review["evidence_id"])
                    if group is None:
                        continue
                    provenance = json.loads(review["proposal_provenance"])
                    active = (state == "distinct" and review["decision"] == "human_confirmed"
                              and review["mode"] == "A" and provenance.get("grants") == _grants(db, group))
                    products.append({
                        **{field: review[field] for field in EDGE_KEY[1:]},
                        "decision": review["decision"], "decision_seq": review["decision_seq"],
                        "mapping_revision": provenance["mapping_revision"], "rule_version": provenance["rule_version"],
                        "scope_id": provenance["scope_id"], "effective": active,
                    })
                members.append({"mention_id": mention_id, "identity_state": state,
                                "evidence_ids": list(evidence), "products": products})
            previous_visible = set()
            if header["parent_rev"] is not None:
                for row in _supports(db, study_id, header["parent_rev"]):
                    old_id = row["mention_id"]
                    if old_id not in previous_visible:
                        try:
                            self._qualified_evidence(
                                db, study_id, header["parent_rev"], old_id, _Support.from_row(row), today, records,
                            )
                        except Conflict:
                            continue
                        previous_visible.add(old_id)
            replacements = [
                {"parent_revision": row["old_rev"], "from_mention_id": row["old_mention_id"],
                 "to_mention_id": row["new_mention_id"]}
                for row in db.execute(
                    """SELECT old_rev, old_mention_id, new_mention_id FROM m06_replacement
                       WHERE study_id=? AND segment_revision=? ORDER BY old_mention_id, new_mention_id""",
                    (study_id, revision),
                ) if row["old_mention_id"] in previous_visible and row["new_mention_id"] in visible
            ]
            self.corpus._check_day(today)
            return {"revision": revision, "parent_revision": header["parent_rev"], "rule_version": header["rule_version"],
                    "members": members, "replacements": replacements}

    def read_scope_mapping(self, study_id, scope_id, *, mapping_revision=None, catalog_version=None):
        with self._transaction(study_id, ("read",)) as (db, _):
            return scope_mapping(db, study_id, scope_id, mapping_revision, catalog_version)
