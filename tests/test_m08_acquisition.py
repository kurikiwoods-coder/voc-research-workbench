"""Frozen scope binding and the local-only M08 routes."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from src.ingestion.m08_acquisition import OFFLINE_DOMAINS, permitted
from test_studies import HEADERS, ORIGIN, draft


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(TemporaryDirectory(prefix="voc-m08-合成 ")))
        self.app = create_app(Settings(self.path))
        self.client = self.enterContext(TestClient(
            self.app, base_url=ORIGIN, client=("127.0.0.1", 23000), headers=HEADERS,
        ))

    def project(self, category="fixtures-storage", *, freeze=True):
        response = self.client.post("/api/studies", json=draft(
            mode="single_category", product_category_ids=[category],
        ))
        self.assertEqual(response.status_code, 201, response.text)
        project = response.json()
        scope = project["scope"]
        if freeze:
            response = self.client.post(f"/api/studies/{project['study_id']}/scopes/{scope['scope_id']}/freeze")
            self.assertEqual(response.status_code, 200, response.text)
        return project["study_id"], {
            "scope_id": scope["scope_id"], "scope_version": scope["scope_version"], "product_category_id": category,
            "research_object": "Fictional objects", "research_goal": "Evaluate a fictional interaction",
            "keywords": ["synthetic storage"], "language": "en", "country": "US",
            "allowed_domains": list(OFFLINE_DOMAINS), "mode": "merge", "providers": ["tavily", "brave"],
            "data_class": "synthetic",
        }

    def send(self, project, payload, route="preview", **kwargs):
        return self.client.post(f"/api/acquisition/{project}/{route}", json=payload, **kwargs)

    @property
    def ledger(self):
        return self.path / "m08-offline" / "acquisition.sqlite3"

    def test_preview_preserves_distinct_frozen_products_and_scope_versions(self):
        for category in ("fixtures-storage", "fixtures-education"):
            study, payload = self.project(category)
            response = self.send(study, payload)
            self.assertEqual(response.status_code, 200, response.text)
            plan = response.json()["plan"]
            self.assertEqual((plan["study_id"], plan["scope_id"], plan["scope_version"]),
                             (study, payload["scope_id"], "v1"))
            self.assertEqual(plan["product_category_id"], category)
            self.assertEqual(plan["date_from"], "2026-03-01")
            self.assertEqual(plan["budget"]["real_requests"], 0)
        self.assertFalse(self.ledger.exists())

    def test_wrong_project_version_category_domain_and_window_fail_closed(self):
        first, payload = self.project()
        second, _ = self.project("another-category")
        self.assertEqual(self.send(second, payload).status_code, 404)
        for changes in (
            {"scope_version": "v2"}, {"product_category_id": "another-category"},
            {"allowed_domains": ["example.com"]}, {"date_to": "2026-08-02"},
            {"date_from": "2026-03-00"}, {"data_class": "internal_cx"},
            {"keywords": ["synthetic " + "@".join(("test", "example.com"))]}, {"limit": True},
        ):
            self.assertEqual(self.send(first, {**payload, **changes}).status_code, 422, changes)
        draft_study, draft_payload = self.project(freeze=False)
        self.assertEqual(self.send(draft_study, draft_payload).status_code, 422)
        self.assertFalse(self.ledger.exists())

    def test_demo_preserves_discoveries_without_writing_research_records(self):
        project, payload = self.project()
        rejected = self.send(project, payload, "demo")
        self.assertEqual(rejected.status_code, 422)
        payload = {key: value for key, value in payload.items() if key not in ("research_object", "research_goal", "keywords")}
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network")):
            response = self.send(project, payload, "demo")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["mode"], "offline_fixture")
        self.assertEqual(result["real_api_calls"], 0)
        self.assertEqual(len(result["discoveries"]), 3)
        self.assertEqual(sorted(item["discovery_count"] for item in result["urls"]), [1, 2])
        duplicates = [item for item in result["discoveries"] if item["canonical_url"] == result["urls"][0]["canonical_url"]]
        self.assertEqual({item["provider"] for item in duplicates}, {"tavily", "brave"})
        self.assertEqual(len({item["original_url"] for item in duplicates}), 2)
        self.assertEqual({item["status"] for item in result["pages"]}, {"accessible", "inaccessible"})
        self.assertTrue(next(item for item in result["pages"] if item["accessible"])["published_at"].startswith("2026-03-01"))
        self.assertTrue(all(item["quote"] is None for item in result["pages"]))
        self.assertTrue(all(value is None for value in result["formal_funnel"].values()))
        self.assertEqual(result["engineering_funnel"]["N_discovered_urls"], 2)
        self.assertEqual(result["engineering_funnel"]["N_accessible_pages"], 1)
        self.assertIsNone(result["engineering_funnel"]["N_extracted_mentions"])
        self.assertEqual([item["usage"]["unit"] for item in result["attempts"]], ["credit", "request"])
        self.assertTrue(all(item["usage"]["actual_cost"] is None for item in result["attempts"]))
        self.assertEqual(self.app.state.store.one("PRAGMA user_version")["user_version"], 8)
        self.assertEqual(self.app.state.store.one("SELECT count(*) AS n FROM corpus_snapshots")["n"], 0)
        with closing(sqlite3.connect(self.ledger)) as db:
            row = db.execute("SELECT study_id, scope_id, scope_version, payload FROM receipts").fetchone()
            self.assertEqual(row[:3], (project, payload["scope_id"], "v1"))
            self.assertEqual(json.loads(row[3]), result)
            self.assertNotIn("Fictional objects", row[3])
            self.assertNotIn("公开社区论坛", row[3])
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertIsNone(db.execute("PRAGMA foreign_key_check").fetchone())

    def test_source_permissions_remain_independent_and_default_closed(self):
        response = self.client.get("/api/acquisition/sources")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        result = response.json()
        self.assertFalse(result["formal_collection"]["enabled"])
        self.assertEqual(len(result["sources"]), 3)
        for source in result["sources"]:
            self.assertEqual(len(source["permissions"]), 5)
            self.assertTrue(all(not permitted(source["permissions"], action) for action in source["permissions"]))
        permissions = {"access": "approved", "store": "unknown", "research": "revoked"}
        self.assertTrue(permitted(permissions, "access"))
        self.assertTrue(all(not permitted(permissions, action) for action in ("store", "research", "transmit")))

    def test_archived_study_can_preview_but_cannot_create_a_demo_receipt(self):
        project, payload = self.project()
        revision = self.client.get(f"/api/studies/{project}").json()["revision"]
        response = self.client.delete(f"/api/studies/{project}", params={"revision": revision})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.send(project, payload).status_code, 200)
        selectors = {key: value for key, value in payload.items() if key not in ("research_object", "research_goal", "keywords")}
        self.assertEqual(self.send(project, selectors, "demo").status_code, 422)
        self.assertFalse(self.ledger.exists())

    def test_incomplete_fixture_is_unknown_and_successfully_empty_fixture_is_zero(self):
        project, payload = self.project()
        selectors = {key: value for key, value in payload.items() if key not in ("research_object", "research_goal", "keywords")}
        from src.execution.transport import Response
        for status, expected in ((503, None), (200, 0)):
            with patch("src.ingestion.m08_acquisition._search_fixture", return_value=Response(status, {"results": []})):
                response = self.send(project, {**selectors, "mode": "independent", "providers": ["tavily"]}, "demo")
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            for key in ("N_discovered_urls", "N_accessible_pages"):
                self.assertEqual(result["engineering_funnel"][key], expected)
                self.assertIsNone(result["formal_funnel"][key])

    def test_local_controls_and_formal_collection_gate(self):
        project, payload = self.project()
        blocked = self.send(project, payload, "collect")
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.headers["cache-control"], "no-store")
        wrong = self.send(project, payload, headers={"Origin": "https://example.com"})
        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(wrong.headers["cache-control"], "no-store")
        self.assertEqual(self.send(project, payload, headers={"X-VOC-Action": "other"}).status_code, 403)
        self.assertEqual(self.client.get("/api/acquisition/sources", headers={"Host": "example.com"}).status_code, 403)
        remote = TestClient(self.app, base_url=ORIGIN, client=("192.0.2.4", 23000), headers=HEADERS)
        self.assertEqual(remote.get("/api/acquisition/sources").status_code, 403)
        self.assertFalse(self.ledger.exists())
