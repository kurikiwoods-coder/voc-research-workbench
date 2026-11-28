"""Local immutable snapshots for the offline topic discovery stage."""

from collections import Counter
from contextlib import closing, contextmanager
from dataclasses import fields
import json
from math import isfinite
import re
import sqlite3
from uuid import uuid4

from src.discovery.embedding_inputs import Lineage
from src.edition_policy import Edition
from src.raw_store.store import Conflict, SQLITE_TIMEOUT, dump, now


SCHEMA_VERSION = 2
APPLICATION_IDS = {Edition.BUSINESS: 0x4D303943, Edition.PERSONAL: 0x4D303950}
CANDIDATE_OUTPUT_VERSION = "m09-d-candidates-v1"
CANDIDATE_DECISIONS = frozenset({"retained", "rejected"})
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_STATUSES = {"empty", "insufficient_samples", "empty_vocabulary", "no_clusters", "clustered"}
_LINEAGE_FIELDS = frozenset(field.name for field in fields(Lineage))
_REFERENCE_FIELDS = {
    "mention": {"kind", "segment_revision", "mention_id", "evidence_id", "original_language"},
    "sampling": {"kind", "task_id", "receipt_index", "original_language"},
}
_MEMBER_FIELDS = frozenset({
    "document_id", "topic_id", "reference", "lineage", "original_language", "original_excerpt_sha256",
    "model_input_sha256", "raw_topic_id", "hdbscan_cluster_id", "membership_probability",
    "outlier_score", "centroid_similarity", "postprocessing",
})

_SCHEMA = (
    """CREATE TABLE topic_runs (
        run_id TEXT PRIMARY KEY NOT NULL,
        study_id TEXT NOT NULL,
        scope_id TEXT NOT NULL,
        scope_version TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL CHECK(status IN ('empty','insufficient_samples','empty_vocabulary','no_clusters','clustered')),
        metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata) = 'object'),
        quality TEXT NOT NULL CHECK(json_valid(quality) AND json_type(quality) = 'object'),
        replay_of TEXT,
        UNIQUE(study_id, idempotency_key),
        UNIQUE(study_id, scope_id, scope_version, run_id),
        FOREIGN KEY(study_id, scope_id, scope_version, replay_of)
            REFERENCES topic_runs(study_id, scope_id, scope_version, run_id),
        CHECK(replay_of IS NULL OR replay_of <> run_id)
    ) STRICT""",
    """CREATE INDEX topic_runs_scope ON topic_runs(study_id, scope_id, scope_version, finished_at DESC, run_id)""",
    """CREATE TABLE topics (
        run_id TEXT NOT NULL REFERENCES topic_runs(run_id),
        topic_id INTEGER NOT NULL CHECK(topic_id >= -1),
        keywords TEXT NOT NULL CHECK(json_valid(keywords) AND json_type(keywords) = 'array'),
        CHECK(topic_id <> -1 OR json_array_length(keywords) = 0),
        PRIMARY KEY(run_id, topic_id)
    ) STRICT""",
    """CREATE TABLE topic_members (
        run_id TEXT NOT NULL,
        topic_id INTEGER NOT NULL,
        document_id TEXT NOT NULL,
        reference TEXT NOT NULL CHECK(json_valid(reference) AND json_type(reference) = 'object'),
        lineage TEXT NOT NULL CHECK(json_valid(lineage) AND json_type(lineage) = 'object'),
        original_language TEXT NOT NULL,
        original_excerpt_sha256 TEXT NOT NULL CHECK(length(original_excerpt_sha256) = 64),
        model_input_sha256 TEXT NOT NULL CHECK(length(model_input_sha256) = 64),
        raw_topic_id INTEGER CHECK(raw_topic_id >= -1 AND raw_topic_id = topic_id),
        hdbscan_cluster_id INTEGER CHECK(hdbscan_cluster_id >= -1),
        membership_probability REAL CHECK(membership_probability BETWEEN 0 AND 1),
        outlier_score REAL CHECK(outlier_score BETWEEN 0 AND 1),
        centroid_similarity REAL CHECK(centroid_similarity BETWEEN -1 AND 1),
        PRIMARY KEY(run_id, document_id),
        UNIQUE(run_id, topic_id, document_id),
        FOREIGN KEY(run_id, topic_id) REFERENCES topics(run_id, topic_id)
    ) STRICT""",
    """CREATE TABLE topic_postprocessing (
        run_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        decision TEXT NOT NULL CHECK(json_valid(decision) AND json_type(decision) = 'object'),
        PRIMARY KEY(run_id, document_id),
        FOREIGN KEY(run_id, document_id) REFERENCES topic_members(run_id, document_id)
    ) STRICT""",
    """CREATE TABLE topic_representatives (
        run_id TEXT NOT NULL,
        topic_id INTEGER NOT NULL CHECK(topic_id >= 0),
        document_id TEXT NOT NULL,
        position INTEGER NOT NULL CHECK(position >= 0),
        PRIMARY KEY(run_id, topic_id, position),
        UNIQUE(run_id, topic_id, document_id),
        FOREIGN KEY(run_id, topic_id, document_id) REFERENCES topic_members(run_id, topic_id, document_id)
    ) STRICT""",
    """CREATE TRIGGER topic_runs_insert BEFORE INSERT ON topic_runs
       WHEN NEW.finished_at IS NOT NULL
         OR EXISTS(SELECT 1 FROM topic_runs WHERE run_id = NEW.run_id
                    OR (study_id = NEW.study_id AND idempotency_key = NEW.idempotency_key))
         OR (NEW.replay_of IS NOT NULL AND NOT EXISTS(
            SELECT 1 FROM topic_runs WHERE run_id = NEW.replay_of AND finished_at IS NOT NULL))
       BEGIN SELECT RAISE(ABORT, 'invalid topic run insert'); END""",
    """CREATE TRIGGER topic_runs_update BEFORE UPDATE ON topic_runs
       WHEN OLD.finished_at IS NOT NULL OR NEW.finished_at IS NULL
            OR NEW.run_id IS NOT OLD.run_id OR NEW.study_id IS NOT OLD.study_id
            OR NEW.scope_id IS NOT OLD.scope_id OR NEW.scope_version IS NOT OLD.scope_version
            OR NEW.idempotency_key IS NOT OLD.idempotency_key OR NEW.request_sha256 IS NOT OLD.request_sha256
            OR NEW.started_at IS NOT OLD.started_at OR NEW.status IS NOT OLD.status
            OR NEW.metadata IS NOT OLD.metadata OR NEW.quality IS NOT OLD.quality
            OR NEW.replay_of IS NOT OLD.replay_of
            OR (OLD.status = 'clustered') <> EXISTS(SELECT 1 FROM topics WHERE run_id = OLD.run_id AND topic_id >= 0)
            OR (OLD.status = 'empty') <> NOT EXISTS(SELECT 1 FROM topics WHERE run_id = OLD.run_id)
            OR EXISTS(SELECT 1 FROM topics AS topic WHERE topic.run_id = OLD.run_id AND NOT EXISTS(
                SELECT 1 FROM topic_members AS member
                WHERE member.run_id = topic.run_id AND member.topic_id = topic.topic_id))
       BEGIN SELECT RAISE(ABORT, 'invalid topic run seal or immutable topic run'); END""",
    """CREATE TRIGGER topic_runs_delete BEFORE DELETE ON topic_runs
       BEGIN SELECT RAISE(ABORT, 'immutable topic run'); END""",
    """CREATE TRIGGER topic_members_scope BEFORE INSERT ON topic_members
       WHEN NOT EXISTS(SELECT 1 FROM topic_runs
                       WHERE run_id = NEW.run_id
                         AND study_id IS json_extract(NEW.lineage, '$.study_id')
                         AND scope_id IS json_extract(NEW.lineage, '$.scope_id')
                         AND scope_version IS json_extract(NEW.lineage, '$.scope_version'))
       BEGIN SELECT RAISE(ABORT, 'topic member scope mismatch'); END""",
)


_CANDIDATE_SCHEMA = (
    f"""ALTER TABLE topic_runs
        ADD COLUMN candidate_output_version TEXT NOT NULL DEFAULT '{CANDIDATE_OUTPUT_VERSION}'""",
    """CREATE TRIGGER topic_runs_candidate_output_version
       BEFORE UPDATE OF candidate_output_version ON topic_runs
       BEGIN SELECT RAISE(ABORT, 'immutable candidate output version'); END""",
    """CREATE TABLE topic_candidate_reviews (
        run_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        topic_id INTEGER NOT NULL CHECK(topic_id >= 0),
        request_id TEXT NOT NULL,
        actor_ref TEXT NOT NULL,
        decision TEXT NOT NULL CHECK(decision IN ('retained', 'rejected')),
        decided_at TEXT NOT NULL,
        PRIMARY KEY(run_id, revision),
        UNIQUE(run_id, request_id),
        FOREIGN KEY(run_id, topic_id) REFERENCES topics(run_id, topic_id)
    ) STRICT""",
    """CREATE TRIGGER topic_candidate_reviews_insert BEFORE INSERT ON topic_candidate_reviews
       WHEN NOT EXISTS(SELECT 1 FROM topic_runs WHERE run_id = NEW.run_id AND finished_at IS NOT NULL)
         OR NEW.revision <> (
            SELECT COALESCE(MAX(revision), 0) + 1 FROM topic_candidate_reviews WHERE run_id = NEW.run_id)
         OR EXISTS(SELECT 1 FROM topic_candidate_reviews
                   WHERE run_id = NEW.run_id AND request_id = NEW.request_id)
       BEGIN SELECT RAISE(ABORT, 'invalid candidate review append'); END""",
    """CREATE TRIGGER topic_candidate_reviews_update BEFORE UPDATE ON topic_candidate_reviews
       BEGIN SELECT RAISE(ABORT, 'immutable candidate review'); END""",
    """CREATE TRIGGER topic_candidate_reviews_delete BEFORE DELETE ON topic_candidate_reviews
       BEGIN SELECT RAISE(ABORT, 'immutable candidate review'); END""",
)


def _initialize(db, app_id):
    identity = db.execute("SELECT application_id, user_version FROM pragma_application_id(), pragma_user_version()")
    application, version = identity.fetchone()
    if (application, version) == (app_id, SCHEMA_VERSION):
        return
    if (application, version) == (app_id, 1):
        for statement in _CANDIDATE_SCHEMA:
            db.execute(statement)
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        return
    if (application, version) != (0, 0) or db.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone():
        raise sqlite3.DatabaseError("Unsupported topic run database")

    for statement in _SCHEMA:
        db.execute(statement)
    for statement in _CANDIDATE_SCHEMA:
        db.execute(statement)
    for table in ("topics", "topic_members", "topic_representatives", "topic_postprocessing"):
        db.execute(f"""CREATE TRIGGER {table}_insert BEFORE INSERT ON {table}
                       WHEN EXISTS(SELECT 1 FROM topic_runs WHERE run_id = NEW.run_id
                                   AND finished_at IS NOT NULL)
                       BEGIN SELECT RAISE(ABORT, 'immutable topic run'); END""")
        for action in ("update", "delete"):
            db.execute(f"""CREATE TRIGGER {table}_{action} BEFORE {action} ON {table}
                           BEGIN SELECT RAISE(ABORT, 'immutable topic run'); END""")
    db.execute(f"PRAGMA application_id={app_id}")
    db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def _digest(value):
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _valid_score(value, lower):
    return value is None or (type(value) in (int, float) and lower <= value <= 1 and isfinite(value))


def _member_values(member, scope):
    ref, lineage = member["reference"], member["lineage"]
    if member.keys() - _MEMBER_FIELDS or lineage.keys() != _LINEAGE_FIELDS:
        raise ValueError("m09_unexpected_member_fields")
    kind = ref.get("kind")
    if kind not in _REFERENCE_FIELDS or ref.keys() != _REFERENCE_FIELDS[kind]:
        raise ValueError("m09_invalid_evidence_reference")
    if (
        tuple(lineage.get(key) for key in ("study_id", "scope_id", "scope_version")) != scope
        or ref["original_language"] != member["original_language"]
        or type(lineage["start_cp"]) is not int or type(lineage["end_cp"]) is not int
        or not 0 <= lineage["start_cp"] < lineage["end_cp"]
        or Lineage(**lineage).document_id != member["document_id"]
        or not _digest(lineage.get("raw_sha256"))
        or not _digest(member["original_excerpt_sha256"])
        or not _digest(member["model_input_sha256"])
    ):
        raise ValueError("m09_invalid_member_lineage")
    if kind == "mention" and (
        not ref["mention_id"] or not ref["evidence_id"] or type(ref["segment_revision"]) is not int
        or ref["segment_revision"] < 1
        or any(ref[key] != lineage.get(key) for key in ("mention_id", "evidence_id", "segment_revision"))
        or lineage.get("acquisition_task_id") is not None
    ):
        raise ValueError("m09_invalid_mention_lineage")
    if kind == "sampling" and (
        not ref["task_id"] or ref["task_id"] != lineage.get("acquisition_task_id")
        or type(ref["receipt_index"]) is not int or ref["receipt_index"] < 0
        or any(lineage.get(key) is not None for key in ("mention_id", "evidence_id", "segment_revision"))
    ):
        raise ValueError("m09_invalid_sampling_lineage")
    if not all(_valid_score(member.get(key), lower) for key, lower in (
        ("membership_probability", 0), ("outlier_score", 0), ("centroid_similarity", -1),
    )):
        raise ValueError("m09_invalid_member_diagnostics")
    decision = member.get("postprocessing")
    if decision is not None and (
        not isinstance(decision, dict) or decision.keys() - {"status", "method", "reason", "topic_id"}
    ):
        raise ValueError("m09_invalid_postprocessing")
    return (
        member["topic_id"], member["document_id"], dump(ref), dump(lineage), member["original_language"],
        member["original_excerpt_sha256"], member["model_input_sha256"], member.get("raw_topic_id"),
        member.get("hdbscan_cluster_id"), member.get("membership_probability"), member.get("outlier_score"),
        member.get("centroid_similarity"),
    )


def _summary(row):
    result = dict(row)
    result.pop("candidate_output_version", None)
    for key in ("metadata", "quality"):
        result[key] = json.loads(result[key])
    return result


class TopicRunStore:
    """Transaction boundary for one workspace's offline topic database.

    Callers resolve project access and current evidence eligibility through the discovery service.
    """

    def __init__(self, workspace_store):
        if workspace_store.fixture or workspace_store.diagnostic:
            raise ValueError("m09_workspace_store_required")
        self.workspace_store = workspace_store
        workspace_path = workspace_store.path
        self.path = workspace_path.with_name(workspace_path.stem + "-m09-topics.sqlite3")
        with self._transaction(write=True) as db:
            _initialize(db, APPLICATION_IDS[Edition(workspace_store.edition)])

    @contextmanager
    def _transaction(self, *, write=False):
        if self.path.is_symlink():
            raise ValueError("m09_topic_database_symlink")
        with closing(sqlite3.connect(self.path, timeout=SQLITE_TIMEOUT)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db

    @staticmethod
    def _snapshot(db, row):
        result = _summary(row)
        run_id = row["run_id"]
        representatives = {}
        for item in db.execute(
            "SELECT topic_id, document_id FROM topic_representatives WHERE run_id=? ORDER BY topic_id, position",
            (run_id,),
        ):
            representatives.setdefault(item["topic_id"], []).append(item["document_id"])

        members = []
        for item in db.execute(
            """SELECT member.*, postprocessing.decision AS postprocessing
               FROM topic_members AS member
               LEFT JOIN topic_postprocessing AS postprocessing USING(run_id, document_id)
               WHERE member.run_id=? ORDER BY member.document_id""",
            (run_id,),
        ):
            member = dict(item)
            del member["run_id"]
            for key in ("reference", "lineage", "postprocessing"):
                if member[key] is not None:
                    member[key] = json.loads(member[key])
            members.append(member)

        counts = Counter(member["topic_id"] for member in members)
        result["topics"] = [
            {"topic_id": item["topic_id"], "keywords": json.loads(item["keywords"]),
             "member_count": counts[item["topic_id"]],
             "representative_document_ids": representatives.get(item["topic_id"], [])}
            for item in db.execute("SELECT topic_id, keywords FROM topics WHERE run_id=? ORDER BY topic_id", (run_id,))
        ]
        result["members"] = members
        return result

    @classmethod
    def _by_request(cls, db, study_id, idempotency_key, request_sha256):
        row = db.execute(
            "SELECT * FROM topic_runs WHERE study_id=? AND idempotency_key=? AND finished_at IS NOT NULL",
            (study_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != request_sha256:
            raise Conflict("m09_idempotency_conflict")
        return cls._snapshot(db, row)

    def by_request(self, study_id, idempotency_key, request_sha256):
        with self._transaction() as db:
            return self._by_request(db, study_id, idempotency_key, request_sha256)

    def get(self, study_id, run_id):
        with self._transaction() as db:
            row = db.execute(
                "SELECT * FROM topic_runs WHERE study_id=? AND run_id=? AND finished_at IS NOT NULL",
                (study_id, run_id),
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            return self._snapshot(db, row)

    def list_by_scope(self, study_id, scope_id, scope_version):
        with self._transaction() as db:
            return [
                _summary(row) for row in db.execute(
                    """SELECT * FROM topic_runs
                       WHERE study_id=? AND scope_id=? AND scope_version=? AND finished_at IS NOT NULL
                       ORDER BY finished_at DESC, run_id""",
                    (study_id, scope_id, scope_version),
                )
            ]

    def candidate_reviews(self, run_id, revision):
        with self._transaction() as db:
            version_row = db.execute(
                "SELECT candidate_output_version FROM topic_runs WHERE run_id=? AND finished_at IS NOT NULL",
                (run_id,),
            ).fetchone()
            if version_row is None:
                raise KeyError(run_id)
            latest = db.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM topic_candidate_reviews WHERE run_id=?", (run_id,),
            ).fetchone()[0]
            revision = latest if revision is None else revision
            if revision > latest:
                raise KeyError(revision)
            reviews = [
                dict(row) for row in db.execute(
                    """SELECT revision, topic_id, decision, actor_ref, decided_at FROM topic_candidate_reviews
                       WHERE run_id=? AND revision<=? ORDER BY revision""",
                    (run_id, revision),
                )
            ]
            return version_row["candidate_output_version"], latest, revision, reviews

    def review_candidate(self, run_id, topic_id, decision, expected_revision, request_id, actor_ref):
        with self._transaction(write=True) as db:
            existing = db.execute(
                """SELECT revision, topic_id, decision, actor_ref
                   FROM topic_candidate_reviews WHERE run_id=? AND request_id=?""",
                (run_id, request_id),
            ).fetchone()
            revision = expected_revision + 1
            if existing is not None:
                if tuple(existing) != (revision, topic_id, decision, actor_ref):
                    raise Conflict("m09_candidate_idempotency_conflict")
                return revision
            latest = db.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM topic_candidate_reviews WHERE run_id=?", (run_id,),
            ).fetchone()[0]
            if latest != expected_revision:
                raise Conflict("m09_candidate_revision_conflict")
            db.execute(
                """INSERT INTO topic_candidate_reviews(run_id, revision, topic_id, request_id, actor_ref,
                                                        decision, decided_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, revision, topic_id, request_id, actor_ref, decision, now()),
            )
            return revision

    def save(self, *, study_id, scope_id, scope_version, idempotency_key, request_sha256, started_at, status,
             metadata, topics, members, quality, replay_of=None):
        scope = study_id, scope_id, scope_version
        if not all(isinstance(value, str) and value for value in (*scope, idempotency_key, started_at)):
            raise ValueError("m09_invalid_topic_run_identity")
        if status not in _STATUSES or not _digest(request_sha256):
            raise ValueError("m09_invalid_topic_run_metadata")
        with self._transaction(write=True) as db:
            existing = self._by_request(db, study_id, idempotency_key, request_sha256)
            if existing is not None:
                return existing

            run_id = str(uuid4())
            db.execute(
                """INSERT INTO topic_runs(
                       run_id, study_id, scope_id, scope_version, idempotency_key, request_sha256,
                       started_at, status, metadata, quality, replay_of
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, *scope, idempotency_key, request_sha256, started_at, status,
                 dump(metadata), dump(quality), replay_of),
            )
            topics = tuple(topics)
            members = tuple(members)
            for topic in topics:
                if topic.keys() - {"topic_id", "keywords", "member_count", "representative_document_ids"}:
                    raise ValueError("m09_unexpected_topic_fields")
            db.executemany(
                "INSERT INTO topics(run_id, topic_id, keywords) VALUES (?, ?, ?)",
                [(run_id, topic["topic_id"], dump(topic["keywords"])) for topic in topics],
            )
            db.executemany(
                """INSERT INTO topic_members(
                       run_id, topic_id, document_id, reference, lineage, original_language, original_excerpt_sha256,
                       model_input_sha256, raw_topic_id, hdbscan_cluster_id, membership_probability, outlier_score,
                       centroid_similarity
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(run_id, *_member_values(member, scope)) for member in members],
            )
            db.executemany(
                "INSERT INTO topic_postprocessing(run_id, document_id, decision) VALUES (?, ?, ?)",
                [(run_id, member["document_id"], dump(member["postprocessing"]))
                 for member in members if member.get("postprocessing") is not None],
            )
            db.executemany(
                "INSERT INTO topic_representatives(run_id, topic_id, document_id, position) VALUES (?, ?, ?, ?)",
                [(run_id, topic["topic_id"], document_id, index)
                 for topic in topics for index, document_id in enumerate(topic.get("representative_document_ids", ()))],
            )
            db.execute("UPDATE topic_runs SET finished_at=? WHERE run_id=?", (now(), run_id))
            row = db.execute("SELECT * FROM topic_runs WHERE run_id=?", (run_id,)).fetchone()
            return self._snapshot(db, row)
