"""Synthetic acquisition through the same local routes as the workbench."""

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from src.ingestion.m08_acquisition import OFFLINE_DOMAINS
from src.raw_store.corpus import CorpusStore
from src.raw_store.store import Conflict, Store
from test_studies import HEADERS, ORIGIN, draft


class SamplingIntegration(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory(prefix="voc-m08-采样 ")))
        self.denied = set()
        self.open_client()
        response = self.client.post("/api/studies", json=draft())
        self.assertEqual(response.status_code, 201, response.text)
        study = response.json()
        self.study = study["study_id"]
        self.scope = study["scope"]["scope_id"]
        response = self.client.post(f"/api/studies/{self.study}/scopes/{self.scope}/freeze")
        self.assertEqual(response.status_code, 200, response.text)
        self.root = f"/api/acquisition/{self.study}/tasks"
        self.payload = {
            "scope_id": self.scope, "scope_version": "v1", "allowed_domains": list(OFFLINE_DOMAINS),
            "mode": "merge", "providers": ["tavily", "brave"], "data_class": "synthetic",
            "request_key": str(uuid4()), "source_ids": ["m08-stackexchange", "m08-youtube"],
            "sample_target": 120, "per_source_limit": 80, "query_limit": 6, "page_limit": 60, "batch_count": 3,
        }
        self.enterContext(patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Fixture only")))

    def open_client(self):
        self.app = create_app(Settings(self.directory), acquisition_permission=lambda _, source: source not in self.denied)
        self.client = self.enterContext(TestClient(self.app, base_url=ORIGIN, client=("127.0.0.1", 23000),
                                                   headers=HEADERS))

    def create(self, **changes):
        response = self.client.post(self.root, json={**self.payload, **changes})
        self.assertEqual(response.status_code, 201, response.text)
        self.task = response.json()["acquisition_task_id"]
        return response.json()

    def action(self, action, **kwargs):
        response = self.client.post(f"{self.root}/{self.task}/{action}", **kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def step(self, key=None):
        return self.action("step", json={"request_key": key or str(uuid4())})

    def complete(self, row):
        for _ in range(row["checkpoint_count"] - row["next_checkpoint"]):
            row = self.step()
        self.assertEqual(row["state"], "completed", row)
        self.assertEqual(row["real_api_calls"], 0)
        return row

    def test_three_batches_120_segments_30_exact_readbacks_and_isolation(self):
        self.create()
        self.action("queue")
        key = str(uuid4())
        row = self.step(key)
        self.assertEqual(self.step(key)["next_checkpoint"], row["next_checkpoint"])
        self.assertEqual(set(row["engineering_funnel"].values()), {None})
        self.action("pause")
        self.open_client()
        result = self.complete(self.action("resume"))
        self.assertEqual(list(result["engineering_funnel"].values()), [60, 60, 120, None, None])
        self.assertEqual(set(result["formal_funnel"].values()), {None})
        attempts = result["attempts"]
        batches = [item["receipt"] for item in attempts if item["checkpoint"]["kind"] == "import"]
        self.assertEqual(len({batch["batch_id"] for batch in batches}), 3)
        repeated = [item for batch in batches for item in batch["evidence"]
                    if item["identity_status"] == "cross_source_review_pending"]
        self.assertTrue(repeated)
        self.assertEqual({item["source_id"] for item in repeated}, {"m08-stackexchange", "m08-youtube"})
        queries = [item["receipt"] for item in attempts if item["checkpoint"]["kind"] == "query"]
        self.assertEqual(sum(len(item["hits"]) for item in queries), 120)
        self.assertEqual(len({hit["canonical_url"] for item in queries for hit in item["hits"]}), 60)
        self.assertEqual({unit: budget["used"] for unit, budget in result["usage"].items()},
                         {"tavily_credit": 3, "brave_request": 3, "stackexchange_request": 30,
                          "youtube_quota_unit": 30})
        for index in range(0, 120, 4):
            response = self.client.get(f"{self.root}/{self.task}/evidence/{index}")
            self.assertEqual(response.status_code, 200, response.text)
            evidence = response.json()
            self.assertEqual(len(evidence["text"]), evidence["end_cp"] - evidence["start_cp"])
            self.assertTrue(evidence["published_at"].startswith("2026-03-01"))
            self.assertEqual(evidence["scope_id"], self.scope)
            self.assertEqual(evidence["role"], "synthetic")
            self.assertFalse(evidence["engineering_eligible"] or evidence["research_eligible"] or
                             evidence["outbound_allowed"])
        self.assertEqual(self.app.state.store.one("PRAGMA user_version")["user_version"], 9)
        self.assertEqual(self.app.state.store.one("SELECT count(*) AS n FROM import_batches")["n"], 0)
        db = Store(self.directory / "m08-sampling" / "tasks" / self.task)
        self.assertEqual(db.one("SELECT count(*) AS n FROM corpus_snapshots")["n"], 60)
        with self.assertRaises(Conflict):
            CorpusStore(db).qualified_record(self.study, batches[0]["evidence"][0]["record_id"])
        for path in (db.path, self.app.state.sampling.ledger.path):
            with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(path.with_suffix(".backup"))) as copy:
                source.backup(copy)
                self.assertEqual(copy.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertIsNone(copy.execute("PRAGMA foreign_key_check").fetchone())
                with closing(sqlite3.connect(path.with_suffix(".restored"))) as restored:
                    copy.backup(restored)
                    self.assertEqual(list(restored.iterdump()), list(source.iterdump()))

    def prepare_import(self, **changes):
        self.create(sample_target=4, batch_count=1, **changes)
        row = self.action("queue")
        for _ in range(row["checkpoint_count"] - 1):
            self.step()
        return self.app.state.sampling.ledger

    def test_committed_import_recovers_once_after_receipt_write_interruption(self):
        ledger = self.prepare_import(fixture_scenario="source_unavailable", fallback_format="xlsx")
        key = str(uuid4())
        with patch.object(ledger, "_receive", side_effect=OSError("simulated write interruption")):
            reply = self.client.post(f"{self.root}/{self.task}/step", json={"request_key": key})
        self.assertEqual(reply.status_code, 409, reply.text)
        self.open_client()
        view = self.client.get(f"{self.root}/{self.task}").json()
        self.assertTrue(view["local_recovery_available"])
        self.assertTrue(view["reconciliation_required"])
        recovered = self.step(key)
        self.assertEqual(self.step(key)["next_checkpoint"], recovered["checkpoint_count"])
        self.assertEqual(recovered["state"], "completed")
        db = Store(self.directory / "m08-sampling" / "tasks" / self.task)
        self.assertEqual(db.one("SELECT count(*) AS n FROM import_batches")["n"], 1)
        self.assertEqual(db.one("SELECT count(*) AS n FROM m08_import_receipts")["n"], 1)

    def test_import_and_review_share_rollback(self):
        self.prepare_import()
        review = CorpusStore._review_in_transaction
        calls = 0

        def interrupt(corpus, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated transaction interruption")
            return review(corpus, *args, **kwargs)

        with patch.object(CorpusStore, "_review_in_transaction", interrupt):
            response = self.client.post(f"{self.root}/{self.task}/step", json={"request_key": str(uuid4())})
        self.assertEqual(response.status_code, 409)
        view = self.client.get(f"{self.root}/{self.task}").json()
        self.assertFalse(view["local_recovery_available"])
        db = Store(self.directory / "m08-sampling" / "tasks" / self.task)
        self.assertEqual(db.one("SELECT count(*) AS n FROM import_batches")["n"], 0)
        self.assertEqual(db.one("SELECT count(*) AS n FROM corpus_snapshots")["n"], 0)

    def test_reconciled_empty_result_differs_from_incomplete_authority(self):
        self.create(sample_target=4, batch_count=1, mode="independent", providers=["tavily"])
        with patch("src.ingestion.m08_search._attempt") as attempt:
            attempt.return_value = {"provider": "tavily", "error": None, "sent": True, "hits": []}
            result = self.complete(self.action("queue"))
        self.assertEqual(list(result["engineering_funnel"].values()), [0, 0, 0, None, None])

    def test_source_revoke_blocks_historical_read_and_resume(self):
        self.create(sample_target=4, batch_count=1)
        self.action("queue")
        self.step()
        self.action("pause")
        self.denied.add("m08-stackexchange")
        self.assertEqual(self.client.get(f"{self.root}/{self.task}").status_code, 403)
        self.assertEqual(self.client.get(self.root).json()["tasks"], [])
        self.assertEqual(self.client.post(f"{self.root}/{self.task}/resume").status_code, 403)
        self.assertEqual(self.app.state.sampling.ledger.get(self.study, self.task)["state"], "permission_blocked")

    def test_verified_source_withdrawal_blocks_evidence_projection(self):
        self.create(sample_target=2, batch_count=1)
        result = self.complete(self.action("queue"))
        item = result["attempts"][-1]["receipt"]["evidence"][0]
        corpus = CorpusStore(Store(self.directory / "m08-sampling" / "tasks" / self.task))
        corpus.review(self.study, item["record_id"], "excluded", "synthetic", "来源许可已撤销",
                      license_status="revoked")
        self.assertEqual(self.client.get(f"{self.root}/{self.task}/evidence/0").status_code, 403)

    def test_fallback_search_uses_secondary_only_for_switchable_failure(self):
        self.create(sample_target=2, batch_count=1, mode="fallback", fixture_scenario="primary_unavailable")
        result = self.complete(self.action("queue"))
        secondary = result["attempts"][1]["receipt"]
        self.assertEqual(secondary["switch"]["from"], "tavily")
        self.assertEqual(secondary["switch"]["to"], "brave")
        self.assertEqual(result["usage"]["brave_request"]["used"], 1)

    def test_successful_primary_does_not_reserve_unneeded_secondary_budget(self):
        self.create(sample_target=2, batch_count=1, mode="fallback", budgets={"brave_request": 0})
        result = self.complete(self.action("queue"))
        self.assertEqual(result["attempts"][1]["reserved_units"], 0)
        self.assertEqual(result["usage"]["brave_request"]["used"], 0)

    def test_budget_blocks_before_source_work(self):
        self.create(sample_target=2, batch_count=1, budgets={"tavily_credit": 0})
        self.action("queue")
        result = self.step()
        self.assertEqual(result["state"], "budget_blocked")
        self.assertEqual(result["attempts"], [])

    def test_csv_and_excel_fallback_retain_unknown_access_and_formal_counts(self):
        for kind in ("csv", "xlsx"):
            self.create(request_key=str(uuid4()), sample_target=4, batch_count=1,
                        fixture_scenario="source_unavailable", fallback_format=kind)
            result = self.complete(self.action("queue"))
            receipt = result["attempts"][-1]["receipt"]
            self.assertTrue(receipt["fallback"])
            self.assertEqual(receipt["format"], kind)
            self.assertEqual(len(receipt["evidence"]), 4)
            self.assertTrue(all(item["method"] == "authorized_synthetic_file" for item in receipt["evidence"]))
            self.assertIsNone(result["engineering_funnel"]["N_accessible_pages"])
            self.assertEqual(set(result["formal_funnel"].values()), {None})

    def test_only_exact_frozen_project_accepts_requests(self):
        other = self.client.post("/api/studies", json=draft()).json()["study_id"]
        self.assertEqual(self.client.post(f"/api/acquisition/{other}/tasks", json=self.payload).status_code, 404)
        self.assertEqual(self.client.post(self.root, json={**self.payload, "scope_version": "v2"}).status_code, 422)
        self.assertEqual(self.client.post(self.root, json={**self.payload, "source_ids": ["m08-reddit"]}).status_code, 403)
        self.assertEqual(self.client.post(self.root, json={**self.payload, "actor": "owner"}).status_code, 422)
        self.assertEqual(self.client.post(self.root, json={**self.payload, "page_limit": 0}).status_code, 409)
        self.assertEqual(self.client.post(self.root, json=self.payload, headers={"Origin": "https://example.org"}).status_code, 403)
        self.assertEqual(self.client.post(f"/api/acquisition/{self.study}/collect").status_code, 403)
