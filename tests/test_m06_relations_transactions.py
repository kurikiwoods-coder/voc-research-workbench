"""C4 fault and race coverage using synthetic M04/M05/C3 inputs and real SQLite."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3
from threading import Barrier
import unittest
from unittest.mock import patch

import test_m06_mentions as fixtures
from src.raw_store.corpus import CorpusStore
from src.raw_store.relations import IntentDefinition, RelationGrant, RelationStore, TaskDefinition
from src.raw_store.store import Conflict


ACTOR = "synthetic-registry-reviewer"
APPROVAL = "local:approved-synthetic-definition"
REGISTRY = "1.0.0"
PRIMARY = "TASK-PRIMARY"
SECONDARY = "TASK-SECONDARY"
INTENT = IntentDefinition("INTENT-OFFLINE", "离线使用", "断开网络后使用", "断网操作", "仅更改联网设置")
MAIN_TASK = TaskDefinition(PRIMARY, "离线操作", "离线完成操作", "无需网络", "仅网络设置")
OTHER_TASK = TaskDefinition(SECONDARY, "连续使用", "不中断操作", "保持运行", "恢复出厂设置")
TABLES = (
    "m06_command",
    "m06_registry",
    "m06_task",
    "m06_intent",
    "m06_intent_task",
    "m06_representative",
)


class ObservedConnection:
    def __init__(self, db, trace, *, before_commit=None, after_statement=None):
        self.db = db
        self.db.set_trace_callback(trace.append)
        self.before_commit = before_commit
        self.after_statement = after_statement

    def execute(self, sql, parameters=()):
        if sql.strip().upper() == "COMMIT" and self.before_commit is not None:
            self.before_commit(self.db)
        result = self.db.execute(sql, parameters)
        if self.after_statement is not None:
            self.after_statement(sql)
        return result

    def commit(self):
        if self.before_commit is not None:
            self.before_commit(self.db)
        return self.db.commit()

    def __getattr__(self, name):
        return getattr(self.db, name)


class RelationTransactionTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.MentionTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.db = self.case.db
        self.study = self.case.study
        self.context_batch, context = self.case.add_quote("c4-context", "合成上下文，说明这里是离线操作。")
        self.context_record = context.record_id
        self.intervals = tuple(
            self.case.add_quote(f"c4-representative-{i}", f"断网时仍然需要操作。合成发生 {i}。")[1]
            for i in range(3)
        )
        self.drafts = tuple(
            self.case.member(
                f"occurrence-{i}", interval, segment_no=i + 1, contexts=(context,) if i == 0 else (),
            )
            for i, interval in enumerate(self.intervals)
        )
        published = self.case.publish(self.drafts)
        self.representative_refs = tuple(
            (member["mention_id"], member["evidence_ids"][0]) for member in published["members"]
        )
        grant = RelationGrant(
            ACTOR, "registry_reviewer", "synthetic-owner", "local:fixture-permission",
            "2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z", frozenset({"publish_registry"}),
        )
        self.grants = [
            grant,
            replace(grant, study_id=self.study, operations=frozenset({"validate", "evidence", "read"})),
        ]
        self.store = RelationStore(self.db, grants=lambda: tuple(self.grants))

    def publish(self, **changes):
        args = {
            "key": "c4-fault-injection",
            "expected_registry_version": None,
            "expected_segment_revision": 1,
            "registry_version": REGISTRY,
            "intent": INTENT,
            "tasks": (MAIN_TASK, OTHER_TASK),
            "primary_category_id": PRIMARY,
            "secondary_ids": (SECONDARY,),
            "representative_refs": self.representative_refs,
            "approval_ref": APPROVAL,
        }
        return self.store.publish_combination(self.study, **(args | changes))

    def snapshot(self):
        return {table: self.case.rows(f"SELECT * FROM {table} ORDER BY rowid") for table in TABLES}

    def assert_published(self, version=REGISTRY):
        self.assertEqual(
            self.case.rows("SELECT sealed FROM m06_registry WHERE registry_version=?", (version,)), [(1,)],
        )
        self.assertEqual(
            self.case.rows(
                """SELECT category_id, is_primary FROM m06_intent_task
                   WHERE registry_version=? AND intent_id=? ORDER BY is_primary DESC""",
                (version, INTENT.intent_id),
            ),
            [(PRIMARY, 1), (SECONDARY, 0)],
        )
        self.assertEqual(
            self.case.rows("SELECT count(*) FROM m06_representative WHERE registry_version=?", (version,)), [(3,)],
        )

    def observe(self, trace, **hooks):
        connect = self.db.connect
        return patch.object(self.db, "connect", side_effect=lambda: ObservedConnection(connect(), trace, **hooks))

    def test_combination_passes_all_dependencies_through_one_locked_connection(self):
        connect = self.db.connect
        qualify = CorpusStore.qualified_write_inputs
        connections = []
        qualified = []
        trace = []

        def observe_connect():
            connection = ObservedConnection(connect(), trace)
            connections.append(connection)
            return connection

        @contextmanager
        def observe_qualification(corpus, db, study_id, record_ids):
            required = set(record_ids)
            with qualify(corpus, db, study_id, required) as records:
                qualified.append((db, study_id, required, set(records)))
                yield records

        with (
            patch.object(self.db, "connect", side_effect=observe_connect),
            patch.object(CorpusStore, "qualified_write_inputs", observe_qualification),
        ):
            self.publish()
        required = {self.context_record, *(interval.record_id for interval in self.intervals)}
        self.assertEqual(len(connections), 1)
        self.assertEqual(qualified, [(connections[0], self.study, required, required)])
        self.assertEqual(trace.count("BEGIN IMMEDIATE"), 1)
        self.assertEqual(trace.count("COMMIT"), 1)
        self.assert_published()

    def test_final_sqlite_commit_failure_rolls_back_and_leaves_key_retryable(self):
        with self.db.db() as db:
            db.executescript("""
                CREATE TABLE c4_commit_parent (id INTEGER PRIMARY KEY);
                CREATE TABLE c4_commit_child (parent_id INTEGER REFERENCES c4_commit_parent(id)
                    DEFERRABLE INITIALLY DEFERRED);
            """)
        before = self.snapshot()
        trace = []
        reached_commit = []

        def defer_violation(db):
            reached_commit.append(db.execute(
                "SELECT sealed FROM m06_registry WHERE registry_version=?", (REGISTRY,),
            ).fetchone()[0])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            db.execute("INSERT INTO c4_commit_child VALUES (17)")

        with self.observe(trace, before_commit=defer_violation), self.assertRaises((sqlite3.IntegrityError, Conflict)) as failure:
            self.publish()
        error = failure.exception
        if isinstance(error, Conflict):
            error = error.__cause__
        self.assertIsInstance(error, sqlite3.IntegrityError)
        self.assertEqual(error.sqlite_errorcode, sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY)
        self.assertEqual(reached_commit, [1])
        self.assertIn("COMMIT", trace)
        self.assertIn("ROLLBACK", trace[trace.index("COMMIT") + 1:])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.case.rows("SELECT count(*) FROM c4_commit_child"), [(0,)])
        self.publish()
        self.assert_published()

    def test_aborted_half_issuance_leaves_no_definition_command_or_edge(self):
        with self.db.db() as db:
            db.execute("""
                CREATE TRIGGER abort_c4_edge AFTER INSERT ON m06_intent_task BEGIN
                    SELECT RAISE(ABORT, 'synthetic half-issuance failure');
                END
            """)
        before = self.snapshot()
        trace = []
        with self.observe(trace), self.assertRaises((sqlite3.IntegrityError, Conflict)):
            self.publish()
        self.assertTrue(any("INSERT INTO m06_intent_task" in sql for sql in trace))
        self.assertIn("ROLLBACK", trace)
        self.assertNotIn("COMMIT", trace)
        self.assertEqual(self.snapshot(), before)
        with self.db.db() as db:
            db.execute("DROP TRIGGER abort_c4_edge")
        self.publish()
        self.assert_published()

    def test_context_revocation_inside_the_write_rolls_back_the_entire_command(self):
        with self.db.db() as db:
            db.execute(f"""
                CREATE TRIGGER revoke_c4_context AFTER INSERT ON m06_representative BEGIN
                    UPDATE import_batches SET revoked_at='2026-11-25T01:02:03+00:00'
                    WHERE batch_id='{self.context_batch}';
                END
            """)
        before = self.snapshot()
        with self.assertRaises(Conflict):
            self.publish()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            self.case.rows("SELECT revoked_at FROM import_batches WHERE batch_id=?", (self.context_batch,)),
            [(None,)],
        )
        with self.db.db() as db:
            db.execute("DROP TRIGGER revoke_c4_context")
        self.publish()
        self.assert_published()

    def test_utc_rollover_discards_all_staged_writes(self):
        today = datetime.now(timezone.utc).date()
        before_midnight = f"{today}T23:59:59.999+00:00"
        after_midnight = f"{today + timedelta(days=1)}T00:00:00.000+00:00"
        clock = [before_midnight]
        qualify = CorpusStore.qualified_write_inputs

        @contextmanager
        def cross_midnight(corpus, db, study_id, record_ids):
            with qualify(corpus, db, study_id, record_ids) as records:
                yield records
                self.assertIsNotNone(db.execute(
                    "SELECT 1 FROM m06_registry WHERE registry_version=? AND sealed=1", (REGISTRY,),
                ).fetchone())
                clock[0] = after_midnight

        before = self.snapshot()
        with (
            patch.object(CorpusStore, "qualified_write_inputs", cross_midnight),
            patch("src.raw_store.corpus.now", side_effect=lambda: clock[0]),
            self.assertRaises(Conflict),
        ):
            self.publish()
        self.assertEqual(self.snapshot(), before)
        self.publish()
        self.assert_published()

    def test_old_wal_snapshot_cannot_requalify_then_fresh_command_rejects_withdrawal(self):
        before = self.snapshot()
        with closing(self.db.connect()) as stale:
            stale.execute("BEGIN")
            self.assertEqual(stale.execute(
                "SELECT revoked_at FROM import_batches WHERE batch_id=?", (self.context_batch,),
            ).fetchone()[0], None)
            self.case.revoke_batch(self.context_batch)
            with self.assertRaises(sqlite3.OperationalError) as failure:
                with self.case.corpus.qualified_write_inputs(stale, self.study, [self.intervals[0].record_id]):
                    self.fail("The old read transaction acquired a write lock")
            self.assertEqual(failure.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY_SNAPSHOT)
            stale.execute("ROLLBACK")
        with self.assertRaises(Conflict):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_lost_response_replay_changed_payload_and_revoked_sources(self):
        created = self.publish()
        committed = self.snapshot()
        replay = self.publish(
            tasks=(OTHER_TASK, MAIN_TASK), representative_refs=tuple(reversed(self.representative_refs)),
        )
        self.assertEqual(replay["command_id"], created["command_id"])
        self.assertEqual(replay["registry_version"], created["registry_version"])
        self.assertEqual(self.snapshot(), committed)
        with self.assertRaises(Conflict):
            self.publish(intent=replace(INTENT, definition="已变更的合成定义"))
        self.assertEqual(self.snapshot(), committed)
        self.case.revoke_batch(self.context_batch)
        with self.assertRaises(Conflict):
            self.publish()
        self.assertEqual(self.snapshot(), committed)

    def test_successor_checks_inherited_historical_dependencies_and_preserves_its_parent(self):
        old = self.publish()
        new_drafts = []
        for index in range(3):
            _, interval = self.case.add_quote(f"c4-new-occur-{index}", f"合成新的离线操作发生 {index}。")
            new_drafts.append(self.case.member(f"new-{index}", interval, segment_no=index + 1))
        revision = self.case.publish(new_drafts, key="successor-segment", expected=1)
        new_refs = tuple(
            (member["mention_id"], member["evidence_ids"][0]) for member in revision["members"]
        )
        before = self.snapshot()
        self.case.revoke_batch(self.context_batch)
        with self.assertRaises(Conflict):
            self.publish(
                key="c4-new-intent", expected_registry_version=REGISTRY, expected_segment_revision=2,
                registry_version="1.1.0", intent=replace(INTENT, intent_id="INTENT-NEW"), representative_refs=new_refs,
            )
        self.assertEqual(self.snapshot(), before)
        self.assert_published(old["registry_version"])

    def test_two_writers_competing_for_the_same_parent_leave_one_sealed_version(self):
        self.publish()
        barrier = Barrier(2, timeout=10)

        def race(version):
            barrier.wait()
            try:
                return self.publish(key=f"c4-race-{version}", expected_registry_version=REGISTRY, registry_version=version)
            except Conflict as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(race, ("1.1.0", "1.2.0")))
        winners = [result for result in results if isinstance(result, dict)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(sum(isinstance(result, Conflict) for result in results), 1)
        winner = winners[0]["registry_version"]
        self.assert_published(winner)
        self.assertEqual(
            self.case.rows("SELECT registry_version FROM m06_registry WHERE parent_version=?", (REGISTRY,)),
            [(winner,)],
        )
        self.assertEqual(self.case.rows(
            "SELECT count(*) FROM m06_command WHERE idempotency_key LIKE 'c4-race-%'",
        ), [(1,)])
        before = self.snapshot()
        with self.assertRaises(Conflict):
            self.publish(key="c4-old-parent", expected_registry_version=REGISTRY, registry_version="2.0.0")
        self.assertEqual(self.snapshot(), before)

    def test_stale_segment_revision_preserves_registry_and_command_history(self):
        self.case.publish(self.drafts, key="new-segment", expected=1)
        before = self.snapshot()
        with self.assertRaises(Conflict):
            self.publish()
        self.assertEqual(self.snapshot(), before)
        self.publish(expected_segment_revision=2)
        self.assert_published()

    def test_grant_withdrawal_during_write_and_old_receipt_require_current_authorization(self):
        trace = []
        project_grant = self.grants[1]

        def withdraw_project_grant(sql):
            if "UPDATE M06_REGISTRY" in sql.upper():
                self.grants[1] = replace(project_grant, revoked_at="2000-01-02T00:00:00Z")

        before = self.snapshot()
        with self.observe(trace, after_statement=withdraw_project_grant), self.assertRaises((KeyError, PermissionError)):
            self.publish()
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("COMMIT", trace)
        self.grants[1] = project_grant
        self.publish()
        self.assert_published()
        committed = self.snapshot()
        self.grants[1] = replace(project_grant, revoked_at="2000-01-02T00:00:00Z")
        with self.assertRaises((KeyError, PermissionError)):
            self.publish()
        self.assertEqual(self.snapshot(), committed)

    def test_combination_attribution_requires_exact_project_permission_and_rechecks_replay(self):
        first, second, _ = self.representative_refs
        before = self.snapshot()
        with self.assertRaises(PermissionError):
            self.publish(attribution_refs=(first,))
        self.assertEqual(self.snapshot(), before)

        self.grants.append(replace(
            self.grants[1], role="project_reviewer", operations=frozenset({"attribute"}),
            evidence_refs=frozenset({(1, *first)}),
        ))
        with self.assertRaises(PermissionError):
            self.publish(attribution_refs=(second,))
        self.assertEqual(self.snapshot(), before)

        self.publish(attribution_refs=(first,))
        self.assert_published()
        self.assertEqual(self.case.rows(
            "SELECT count(*) FROM m06_command WHERE operation='engineering_attribution'",
        ), [(1,)])
        committed = self.snapshot()
        self.grants.pop()
        with self.assertRaises(PermissionError):
            self.publish(attribution_refs=(first,))
        self.assertEqual(self.snapshot(), committed)


if __name__ == "__main__":
    unittest.main()
