"""Durable acquisition task transitions, quota isolation and safe recovery."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from src.ingestion.m08_tasks import AcquisitionTaskStore, AuthorizationBlocked, CheckpointResult, TaskError
from src.raw_store.store import Store


PROJECT = "study-1"
ACTOR = "operator-1"
TAVILY = "tavily_credit"
BRAVE = "brave_request"
YOUTUBE = "youtube_quota_unit"


def checkpoint(key, kind, source_id, *, unit=None, units=1):
    result = {"key": key, "kind": kind, "source_id": source_id, "input": {"fixture": key}}
    if unit is not None:
        result.update(unit=unit, units=units)
    return result


def configuration():
    return {
        "mode": "synthetic", "study_id": PROJECT, "scope_id": "frozen-scope", "scope_version": "v2",
        "query_plan": {"version": "query-v1", "language": "en"},
        "sources": [
            {"source_id": "tavily", "adapter_version": "adapter-v1"},
            {"source_id": "brave", "adapter_version": "adapter-v1"},
            {"source_id": "youtube", "adapter_version": "adapter-v1"},
        ],
        "research_goal": "Validate the synthetic sampling chain",
        "window_start": "2026-01-01", "window_end": "2026-06-30",
        "sample_target": 120, "source_limits": {"youtube": 120}, "query_limit": 3, "page_limit": 3,
        "budgets": {
            TAVILY: {"authorized": 4, "available": 7},
            BRAVE: {"authorized": 9, "available": 1},
            YOUTUBE: {"authorized": 9, "available": 8},
        },
        "authorization": {"policy_ref": "synthetic-policy-v1", "account_ref": "fixture-only"},
        "checkpoints": [
            checkpoint("discover-t", "query", "tavily", unit=TAVILY, units=2),
            checkpoint("discover-b", "query", "brave", unit=BRAVE),
            checkpoint("read", "page", "youtube", unit=YOUTUBE, units=4),
            checkpoint("quality-check", "import", "youtube"),
            checkpoint("audit", "audit", "youtube"),
        ],
    }


class AcquisitionTaskTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory(prefix="voc-m08d-合成 ")))
        self.path = self.directory / "m08-sampling" / "tasks.sqlite3"
        self.ledger = AcquisitionTaskStore(self.path)
        self.authorization = Mock(return_value=True)
        self.worker = Mock(side_effect=self.result)

    @staticmethod
    def result(config, step, request_id):
        return CheckpointResult(
            {"fixture_receipt": request_id, "task_id": config["acquisition_task_id"]},
            used_units=step.get("units", 0),
        )

    def create(self, *, config=None, key="create-1"):
        return self.ledger.create(PROJECT, config or configuration(), actor=ACTOR, idempotency_key=key)

    def queue(self, *, config=None):
        task = self.create(config=config)
        self.action(task["acquisition_task_id"], "queue")
        return task["acquisition_task_id"]

    def action(self, task_id, action, *, ledger=None):
        return (ledger or self.ledger).action(PROJECT, task_id, action, actor=ACTOR, authorize=self.authorization)

    def step(self, task_id, *, key="step-1", ledger=None, worker=None, should_dispatch=None, recover=None):
        return (ledger or self.ledger).step(
            PROJECT, task_id, actor=ACTOR, authorize=self.authorization,
            worker=worker or self.worker, idempotency_key=key, should_dispatch=should_dispatch, recover=recover,
        )

    def test_frozen_binding_idempotent_create_and_per_project_access(self):
        config = configuration()
        created = self.create(config=config)
        task_id = created["acquisition_task_id"]
        config["scope_version"] = "v3"
        with self.assertRaisesRegex(TaskError, "idempotency_conflict"):
            self.create(config=config)
        self.assertEqual(self.create()["acquisition_task_id"], task_id)
        changed_budget = configuration()
        changed_budget["budgets"][TAVILY]["authorized"] = 200
        with self.assertRaisesRegex(TaskError, "duplicate_acquisition_plan"):
            self.create(config=changed_budget, key="create-different-key")
        self.assertEqual(self.ledger.get(PROJECT, task_id)["config"]["scope_version"], "v2")
        self.assertEqual(self.ledger.list("another-study"), [])
        with self.assertRaisesRegex(TaskError, "task_not_found"):
            self.ledger.get("another-study", task_id)
        self.assertEqual(len(self.ledger.list(PROJECT, limit=1)), 1)
        self.assertEqual(self.ledger.list(PROJECT, offset=1), [])
        with self.assertRaisesRegex(TaskError, "invalid_task_pagination"):
            self.ledger.list(PROJECT, limit=101)

    def test_formal_mode_project_mismatch_secret_and_bounds_fail_before_creation(self):
        cases = (
            ({"mode": "formal"}, "formal_collection_blocked"),
            ({"real_cost_budget_micros": 1}, "formal_collection_blocked"),
            ({"study_id": "different"}, "project_binding_mismatch"),
            ({"window_start": "2026-08-01"}, "invalid_window"),
            ({"query_limit": 1}, "query_limit_exceeded"),
            ({"page_limit": 0}, "page_limit_exceeded"),
            ({"authorization": {"api_key": "fixture-marker"}}, "invalid_task_config"),
            ({"query_plan": {"metadata": ({"token": "fixture-marker"},)}}, "invalid_task_config"),
        )
        for changes, reason in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(TaskError, reason):
                self.create(config={**configuration(), **changes})
        self.assertEqual(self.ledger.list(PROJECT), [])

    def test_page_limit_counts_grouped_accesses_independent_of_metering_units(self):
        config = configuration()
        config["checkpoints"][2]["request_count"] = 4
        with self.assertRaisesRegex(TaskError, "page_limit_exceeded"):
            self.create(config=config)
        config["page_limit"] = 4
        task_id = self.queue(config=config)
        self.step(task_id)
        self.step(task_id, key="step-2")
        accessed = self.step(task_id, key="step-3")
        self.assertEqual(accessed["attempts"][2]["checkpoint"]["request_count"], 4)

    def test_legal_transitions_distinct_metering_and_receipt_readback_across_restart(self):
        task_id = self.create()["acquisition_task_id"]
        self.assertEqual(self.ledger.get(PROJECT, task_id)["state"], "draft")
        with self.assertRaisesRegex(TaskError, "invalid_task_transition"):
            self.step(task_id)
        self.assertEqual(self.action(task_id, "queue")["state"], "queued")
        first = self.step(task_id)
        self.assertEqual(first["state"], "partial")
        self.assertIsNotNone(first["started_at"])
        self.assertEqual(self.action(task_id, "pause")["state"], "paused")
        with self.assertRaisesRegex(TaskError, "invalid_task_transition"):
            self.step(task_id, key="step-2")
        reopened = AcquisitionTaskStore(self.path)
        self.assertEqual(self.action(task_id, "resume", ledger=reopened)["state"], "queued")
        recovered = self.step(task_id, ledger=reopened)
        self.assertEqual(recovered["attempts"], first["attempts"])
        self.assertEqual(self.worker.call_count, 1)
        for number in range(2, 6):
            complete = self.step(task_id, key=f"step-{number}", ledger=reopened)
        self.assertEqual(complete["state"], "completed")
        self.assertIsNotNone(complete["completed_at"])
        self.assertEqual(complete["next_checkpoint"], 5)
        self.assertEqual({unit: entry["used"] for unit, entry in complete["usage"].items()},
                         {TAVILY: 2, BRAVE: 1, YOUTUBE: 4})
        self.assertTrue(all(entry["simulated"] for entry in complete["usage"].values()))
        self.assertEqual(complete["real_api_calls"], 0)
        self.assertEqual(complete["real_cost_micros"], 0)
        self.assertEqual(self.worker.call_count, 5)
        self.assertEqual([event["event"] for event in complete["history"]][-4:],
                         ["reserved", "receipt_received", "checkpoint_persisted", "usage_reconciled"])
        self.assertEqual(self.step(task_id, key="step-5", ledger=reopened)["state"], "completed")
        self.assertEqual(self.worker.call_count, 5)
        with self.assertRaisesRegex(TaskError, "invalid_task_transition"):
            self.action(task_id, "cancel")

    def test_current_authorization_is_required_for_resume_and_next_checkpoint(self):
        task_id = self.queue()
        self.step(task_id)
        self.action(task_id, "pause")
        self.authorization.side_effect = AuthorizationBlocked("source_permission_revoked")
        denied = self.action(task_id, "resume")
        self.assertEqual((denied["state"], denied["reason"]), ("permission_blocked", "source_permission_revoked"))
        self.assertEqual(self.worker.call_count, 1)
        self.authorization.side_effect = None
        self.action(task_id, "resume")
        self.authorization.return_value = False
        denied = self.step(task_id, key="step-2")
        self.assertEqual(denied["state"], "permission_blocked")
        self.assertEqual(denied["next_checkpoint"], 1)
        self.assertEqual(self.worker.call_count, 1)

    def test_unknown_or_exhausted_budget_blocks_without_cross_unit_spend(self):
        for remaining, reason in ((None, "budget_unknown"), (0, "budget_exhausted")):
            with self.subTest(remaining=remaining):
                config = configuration()
                config["checkpoints"][0]["input"]["fixture"] = f"fixture-{remaining}"
                config["budgets"][TAVILY]["available"] = remaining
                task_id = self.create(config=config, key=f"create-{remaining}")["acquisition_task_id"]
                self.action(task_id, "queue")
                blocked = self.step(task_id)
                self.assertEqual((blocked["state"], blocked["reason"]), ("budget_blocked", reason))
                self.assertEqual(blocked["attempts"], [])
                self.assertEqual(blocked["usage"][BRAVE]["available"], 1)
        self.worker.assert_not_called()

    def test_midflight_pause_and_competing_workers_use_one_reservation(self):
        task_id = self.queue()
        started = Event()
        release = Event()

        def slow_worker(config, step, request_id):
            started.set()
            if not release.wait(5):
                raise RuntimeError("test synchronization failed")
            return self.result(config, step, request_id)

        with ThreadPoolExecutor() as pool:
            future = pool.submit(self.step, task_id, worker=slow_worker)
            try:
                self.assertTrue(started.wait(5))
                competing = AcquisitionTaskStore(self.path)
                active = self.step(task_id, ledger=competing)
                self.assertEqual(active["attempts"][0]["state"], "reserved")
                self.assertEqual(active["usage"][TAVILY]["reserved"], 2)
                with self.assertRaisesRegex(TaskError, "request_reconciliation_required"):
                    self.step(task_id, key="competing-step", ledger=competing)
                self.assertEqual(self.action(task_id, "pause", ledger=competing)["state"], "paused")
                with self.assertRaisesRegex(TaskError, "request_reconciliation_required"):
                    self.action(task_id, "resume", ledger=competing)
            finally:
                release.set()
            paused = future.result(timeout=5)
        self.assertEqual((paused["state"], paused["next_checkpoint"]), ("paused", 1))
        self.assertEqual(paused["usage"][TAVILY]["used"], 2)
        self.assertEqual(paused["usage"][TAVILY]["reserved"], 0)
        self.worker.assert_not_called()

    def test_process_interruption_keeps_unknown_charge_and_blocks_recreation(self):
        task_id = self.queue()
        command = """
import os
from pathlib import Path
import sys
from src.ingestion.m08_tasks import AcquisitionTaskStore

ledger = AcquisitionTaskStore(Path(sys.argv[1]))
ledger.step(
    "study-1", sys.argv[2], actor="operator-1", authorize=lambda config: True,
    worker=lambda *args: os._exit(37), idempotency_key="step-1",
)
"""
        child = subprocess.run([sys.executable, "-c", command, str(self.path), task_id],
                               check=False, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 37, child.stderr.decode(errors="replace"))
        reopened = AcquisitionTaskStore(self.path)
        recovered = self.step(task_id, ledger=reopened)
        self.assertTrue(recovered["reconciliation_required"])
        self.assertEqual(recovered["usage"][TAVILY]["reserved"], 2)
        self.assertIsNone(recovered["attempts"][0]["used_units"])
        with self.assertRaisesRegex(TaskError, "request_reconciliation_required"):
            self.step(task_id, key="retry-with-fresh-key", ledger=reopened)
        self.assertEqual(self.action(task_id, "cancel", ledger=reopened)["state"], "cancelled")
        interrupting_plan = configuration()
        interrupting_plan["checkpoints"].pop()
        second_task_id = self.create(config=interrupting_plan, key="create-2")["acquisition_task_id"]
        self.action(second_task_id, "queue")
        with self.assertRaisesRegex(TaskError, "request_reconciliation_required"):
            self.step(second_task_id)
        self.worker.assert_not_called()

    def test_durable_received_receipt_can_be_settled_without_resending_after_restart(self):
        task_id = self.queue()
        with patch.object(self.ledger, "_settle", side_effect=SystemExit), self.assertRaises(SystemExit):
            self.step(task_id)
        reopened = AcquisitionTaskStore(self.path)
        received = reopened.get(PROJECT, task_id)
        self.assertEqual(received["attempts"][0]["state"], "received")
        self.assertTrue(received["attempts"][0]["receipt"]["fixture_receipt"])
        self.assertEqual(received["next_checkpoint"], 0)
        reconciled = self.step(task_id, ledger=reopened)
        self.assertEqual(reconciled["attempts"][0]["state"], "reconciled")
        self.assertEqual(reconciled["next_checkpoint"], 1)
        self.worker.assert_called_once()

    def test_new_recovery_key_cannot_dispatch_another_checkpoint_on_retry(self):
        task_id = self.queue()
        with patch.object(self.ledger, "_settle", side_effect=SystemExit), self.assertRaises(SystemExit):
            self.step(task_id)
        reopened = AcquisitionTaskStore(self.path)
        recovery = self.step(task_id, key="recovery-1", ledger=reopened)
        retry = self.step(task_id, key="recovery-1", ledger=reopened)
        self.assertEqual(recovery, retry)
        self.assertEqual(retry["next_checkpoint"], 1)
        self.assertEqual(retry["history"][-3]["event"], "receipt_recovered")
        self.worker.assert_called_once()

    def test_committed_import_is_recovered_after_interruption_without_dispatch(self):
        config = configuration()
        config["checkpoints"] = config["checkpoints"][3:]
        task_id = self.queue(config=config)
        with patch.object(self.ledger, "_receive", side_effect=SystemExit), self.assertRaises(SystemExit):
            self.step(task_id)
        reopened = AcquisitionTaskStore(self.path)
        reserved = reopened.get(PROJECT, task_id)["attempts"][0]
        self.assertEqual(reserved["state"], "reserved")
        lookup = Mock(side_effect=self.result)
        self.authorization.return_value = False
        with self.assertRaises(AuthorizationBlocked):
            self.step(task_id, key="recover-1", ledger=reopened, recover=lookup)
        lookup.assert_not_called()
        self.authorization.return_value = True
        recovered = self.step(task_id, key="recover-1", ledger=reopened, recover=lookup)
        lookup.assert_called_once_with({**config, "acquisition_task_id": task_id, "real_cost_budget_micros": 0},
                                       config["checkpoints"][0], reserved["request_id"])
        self.assertEqual(recovered["next_checkpoint"], 1)
        self.assertEqual(recovered["attempts"][0]["state"], "reconciled")
        self.assertEqual(self.step(task_id, key="recover-1", ledger=reopened, recover=lookup), recovered)
        self.worker.assert_called_once()

    def test_import_recovery_racing_original_receipt_records_one_settlement(self):
        config = configuration()
        config["checkpoints"] = config["checkpoints"][3:]
        task_id = self.queue(config=config)
        reading = Event()
        release = Event()

        def worker(config, checkpoint, request_id):
            reading.set()
            if not release.wait(5):
                raise RuntimeError("test synchronization failed")
            return self.result(config, checkpoint, request_id)

        with ThreadPoolExecutor() as pool:
            in_flight = pool.submit(self.step, task_id, worker=worker)
            try:
                self.assertTrue(reading.wait(5))
                competing = AcquisitionTaskStore(self.path)
                first = self.step(task_id, ledger=competing, recover=self.result)
                self.assertEqual(first["next_checkpoint"], 1)
            finally:
                release.set()
            self.assertEqual(in_flight.result(timeout=5), first)
        self.assertEqual([event["event"] for event in first["history"]].count("usage_reconciled"), 1)

    def test_reserved_metered_request_never_uses_import_recovery(self):
        task_id = self.queue()
        with patch.object(self.ledger, "_receive", side_effect=SystemExit), self.assertRaises(SystemExit):
            self.step(task_id)
        lookup = Mock(side_effect=self.result)
        with self.assertRaisesRegex(TaskError, "request_reconciliation_required"):
            self.step(task_id, key="new-key", recover=lookup)
        self.assertTrue(self.step(task_id, recover=lookup)["reconciliation_required"])
        lookup.assert_not_called()
        self.worker.assert_called_once()

    def test_overcharge_or_worker_error_preserve_unknown_use_without_leaking_error(self):
        task_id = self.queue()
        with self.assertRaisesRegex(TaskError, "request_reconciliation_required"):
            self.step(task_id, worker=Mock(return_value=CheckpointResult({"receipt": "test"}, used_units=3)))
        blocked = self.ledger.get(PROJECT, task_id)
        self.assertEqual((blocked["state"], blocked["reason"]), ("paused", "request_reconciliation_required"))
        self.assertTrue(blocked["reconciliation_required"])
        self.assertIsNone(blocked["attempts"][0]["receipt"])
        self.assertEqual(blocked["usage"][TAVILY]["reserved"], 2)

    def test_known_retriable_outcome_records_receipt_then_resumes_at_next_checkpoint(self):
        task_id = self.queue()
        result = CheckpointResult({"provider": "fixture", "error": "rate_limit"}, 1, "paused", "rate_limit")
        paused = self.step(task_id, worker=Mock(return_value=result))
        self.assertEqual((paused["state"], paused["reason"]), ("paused", "rate_limit"))
        self.assertEqual(paused["attempts"][0]["outcome"], "paused")
        self.assertEqual(paused["usage"][TAVILY]["used"], 1)
        self.action(task_id, "resume")
        switched = self.step(task_id, key="step-2")
        self.assertEqual(switched["attempts"][1]["unit"], BRAVE)
        self.assertEqual(switched["attempts"][0]["unit"], TAVILY)
        self.assertEqual(self.worker.call_count, 1)

    def test_fallback_skip_records_a_local_receipt_before_any_budget_check(self):
        config = configuration()
        config["budgets"][BRAVE]["available"] = None
        task_id = self.queue(config=config)
        first = self.step(task_id)

        def skip(config, step, attempts):
            self.assertEqual(config["acquisition_task_id"], task_id)
            self.assertEqual(step["key"], "discover-b")
            self.assertEqual(attempts, first["attempts"])
            return CheckpointResult(
                {"prior_request": attempts[0]["request_id"]}, outcome="skipped", reason="fallback_not_required",
            )

        skipped = self.step(task_id, key="step-2", should_dispatch=skip)
        self.assertEqual(skipped["next_checkpoint"], 2)
        attempt = skipped["attempts"][1]
        self.assertEqual((attempt["reserved_units"], attempt["used_units"], attempt["state"]), (0, 0, "reconciled"))
        self.assertEqual((attempt["outcome"], attempt["reason"]), ("skipped", "fallback_not_required"))
        self.assertEqual(skipped["history"][-4]["event"], "not_dispatched")
        self.assertEqual(self.worker.call_count, 1)

    def test_ledger_does_not_open_other_sqlite_as_its_schema_and_supports_backup(self):
        work = Store(self.directory / "work")
        with self.assertRaisesRegex(sqlite3.DatabaseError, "Unsupported acquisition ledger"):
            AcquisitionTaskStore(work.path)
        task_id = self.queue()
        original = self.step(task_id)
        backup = self.directory / "restored-ledger.sqlite3"
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            self.assertEqual(target.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(target.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(AcquisitionTaskStore(backup).get(PROJECT, task_id), original)
        self.assertEqual(work.one("PRAGMA user_version")["user_version"], 8)


if __name__ == "__main__":
    unittest.main()
