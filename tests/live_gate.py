"""Explicit live suite. Runs one authorized batch; unavailable external proofs are reported as skipped."""

from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import Settings
from src.execution.checks import run_checks
from src.raw_store.store import Store


class LiveGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = Settings.load()
        cls.db = Store(settings.directory)
        cls.batch_id = run_checks(settings, cls.db, str(uuid.uuid4()))
        cls.results = {r["requirement_id"]: r for r in cls.db.results(cls.batch_id)}
        print("Live batch", cls.batch_id, "·", settings.provider)

    def verify(self, id):
        row = self.results[id]
        self.assertTrue(row["evidence"])
        if row["status"] == "BLOCKED":
            self.skipTest("BLOCKED · " + row["blocker"])
        self.assertEqual(row["status"], "PASS", row["blocker"])

    def test_live_model_and_shards(self):
        self.verify("C0-1")

    def test_live_answer_contract(self):
        self.verify("C0-2")

    def test_live_discovery_and_quote(self):
        self.verify("C0-3")

    def test_live_ledger_readback(self):
        self.verify("C0-4")

    def test_isolation_drill(self):
        self.verify("C0-5")

    def test_cross_category_recall(self):
        self.verify("C0-6")

    def test_gate_requires_all_six(self):
        self.verify("G-1")


if __name__ == "__main__":
    suite = unittest.main(verbosity=2, exit=False)
    if not suite.result.wasSuccessful():
        sys.exit(1)
    if LiveGate.results["G-1"]["status"] != "PASS":
        print("G-1 BLOCKED · 阶段验收暂缓")
        sys.exit(2)
