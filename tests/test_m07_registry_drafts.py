"""Exercise governed proposals with real SQLite and synthetic supports."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
from sqlite3 import IntegrityError
from threading import Barrier
import unittest

from fastapi.testclient import TestClient

import test_m06_relations_queries as fixtures
from test_m06_constraints import registry, seal_registry
from src.dashboard.app import create_app
from src.raw_store.registry_contract import legacy_candidates
from src.raw_store.registry_drafts import RegistryDrafts
from src.raw_store.registry_versions import RegistryVersions
from src.raw_store.store import Conflict


VERSION = fixtures.VERSION
DEFINITION = {
    "name": "合成离线操作", "definition": "设备断网后仍可操作。",
    "inclusion_criteria": "描述断网操作。", "exclusion_criteria": "仅讨论连接设置。",
}


class RegistryDraftTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RelationQueryTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.project = self.fixture.study
        self.rows = self.fixture.fixture.db.rows
        supports = self.fixture.publish([])
        self.fixture.seal_definitions(supports, parent=None)
        self.fixture.grants = [self.fixture.grant("registry_reviewer", "read", "validate", "registry_draft", "evidence")]
        self.service = RegistryDrafts(self.fixture.relations)
        self.refs = [self.fixture.ref(item) | {"segment_revision": 1} for item in supports]

    def create(self, **changes):
        return self.service.command(self.project, "create", **({
            "request_key": "test-create", "reason": "合成草稿", "expected_registry_version": VERSION,
            "kind": "candidate", "definition": DEFINITION,
        } | changes))

    def update(self, draft, operation="edit", **changes):
        return self.service.command(self.project, operation, **({
            "request_key": f"test-{operation}", "reason": "补充合成定义",
            "expected_registry_version": VERSION, "draft_id": draft["draft_id"],
            "expected_revision": draft["revision"],
        } | changes))

    def test_legacy_sample_is_only_pending_and_never_copies_private_material(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "sample-intent-registry.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        pending = legacy_candidates(doc)
        self.assertEqual(len(pending), 3)
        for item in pending:
            self.assertEqual(item["lifecycle_status"], "pending_parent")
            self.assertIsNone(item["primary_category_id"])
            self.assertEqual(item["entity_version"], "1.0.0")
            self.assertEqual(item["approved_shared_examples"], [])
            self.assertNotIn("representative_quotes", item)
        doc["intents"].append(doc["intents"][0])
        with self.assertRaises(ValueError):
            legacy_candidates(doc)

    def test_same_name_has_distinct_stable_ids_and_duplicate_id_is_rejected(self):
        first = self.create(intent_id="INT-DISTINCT-1")
        second = self.create(intent_id="INT-DISTINCT-2", request_key="test-create-2")
        self.assertNotEqual(first["intent_id"], second["intent_id"])
        self.assertEqual(first["definition"]["name"], second["definition"]["name"])
        with self.assertRaises(Conflict):
            self.create(intent_id=first["intent_id"], request_key="test-create-3")
        self.assertEqual(len(self.service.list(self.project)["items"]), 2)

    def test_missing_parent_can_be_retained_but_fails_confirmation_preflight(self):
        draft = self.create()
        result = self.service.preflight(self.project, draft["draft_id"], 1)
        self.assertEqual(draft["lifecycle_status"], "pending_parent")
        self.assertIn("PRIMARY_REQUIRED", result["violations"])
        self.assertFalse(result["formal_issuance"])
        self.assertFalse(result["valid"])
        for changes in ({"primary_category_id": "T-unknown"}, {
            "primary_category_id": fixtures.PRIMARY, "secondary_category_ids": [fixtures.PRIMARY],
        }, {"secondary_category_ids": [fixtures.SECONDARY, fixtures.SECONDARY]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.update(draft, definition=DEFINITION | changes)
        self.assertEqual(len(self.rows("SELECT * FROM m07_draft_revision")), 1)

    def test_revision_and_idempotent_replay_preserve_history_and_allow_withdrawal(self):
        original = self.create()
        self.assertEqual(self.create(), original)
        edited = self.update(original, definition=DEFINITION | {"name": "新名称"})
        self.assertEqual(edited["revision"], 2)
        self.assertEqual(self.update(original, definition=DEFINITION | {"name": "新名称"}), edited)
        with self.assertRaises(Conflict):
            self.update(original, definition=DEFINITION | {"name": "另一个名称"})
        self.assertEqual(self.create()["revision"], 1)
        submitted = self.update(edited, "submit")
        self.assertEqual(submitted["state"], "submitted")
        with self.assertRaises(Conflict):
            self.update(submitted, request_key="edit-submitted")
        withdrawn = self.update(submitted, "withdraw")
        self.assertEqual(withdrawn["state"], "withdrawn")
        history = self.service.history(self.project, original["draft_id"])["items"]
        self.assertEqual([item["revision"] for item in history], [4, 3, 2, 1])
        self.assertEqual(history[-1]["definition"]["name"], DEFINITION["name"])
        self.assertEqual(history[-1]["survey_validation_status"], "unvalidated")
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM m06_intent")[0]["n"], 2)
        with self.assertRaises(IntegrityError), self.fixture.fixture.db.db() as db:
            db.execute("INSERT OR REPLACE INTO m07_draft_revision SELECT * FROM m07_draft_revision WHERE revision=1")

    def test_concurrent_edit_accepts_one_expected_revision(self):
        original = self.create()
        barrier = Barrier(2)

        def edit(index):
            barrier.wait(timeout=10)
            try:
                return self.update(original, request_key=f"race-{index}",
                                   definition=DEFINITION | {"name": f"编辑 {index}"})["revision"]
            except Conflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(edit, range(2))), [2, "conflict"])
        self.assertEqual(len(self.rows("SELECT * FROM m07_draft_revision")), 2)

    def test_preflight_reuses_exact_eligibility_and_never_publishes(self):
        data = DEFINITION | {"primary_category_id": fixtures.PRIMARY}
        draft = self.create(definition=data, source_refs=self.refs)
        result = self.service.preflight(self.project, draft["draft_id"], 1)
        self.assertTrue(result["valid"])
        self.assertFalse(result["formal_issuance"])
        one = self.update(draft, source_refs=self.refs[:1])
        self.assertIn("REPRESENTATIVES_INSUFFICIENT",
                      self.service.preflight(self.project, one["draft_id"], 2)["violations"])
        self.assertEqual(len(self.rows("SELECT * FROM m06_registry")), 1)
        self.assertEqual(len(self.rows("SELECT * FROM m06_intent")), 2)

    def test_project_and_exact_permissions_are_independent_and_rechecked(self):
        draft = self.create(reason="私有变更理由", source_refs=self.refs)
        self.assertCountEqual(self.service.detail(self.project, draft["draft_id"])["source_refs"], self.refs)
        registry = RegistryVersions(self.fixture.relations)
        self.assertNotIn("私有变更理由", json.dumps(registry.catalog(VERSION), ensure_ascii=False))
        broad = self.fixture.grant("registry_reviewer", "read", "validate", "registry_draft")
        exact = self.fixture.grant("registry_reviewer", "evidence", evidence=frozenset({
            (1, self.refs[0]["mention_id"], self.refs[0]["evidence_id"]),
        }))
        self.fixture.grants = [broad, exact]
        self.assertEqual(self.service.detail(self.project, draft["draft_id"])["source_refs"], self.refs[:1])
        with self.assertRaises(KeyError):
            self.service.preflight(self.project, draft["draft_id"], 1)
        self.fixture.grants = [replace(broad, evidence_refs=exact.evidence_refs)]
        with self.assertRaises(KeyError):
            self.service.detail(self.project, draft["draft_id"])
        with self.assertRaises(PermissionError):
            self.create()
        self.fixture.grants = [broad]
        self.assertEqual(self.service.detail(self.project, draft["draft_id"])["source_refs"], [])

    def test_merge_cycle_and_version_conflict_roll_back(self):
        target, source = fixtures.INTENT, fixtures.PENDING
        first = self.create(kind="merge", intent_id=target,
                            definition=DEFINITION | {"source_intent_ids": [source]})
        self.update(first, "submit")
        with self.assertRaises(ValueError):
            self.create(kind="merge", request_key="reverse-edge", intent_id=source,
                        definition=DEFINITION | {"source_intent_ids": [target]})
        with self.assertRaises(ValueError):
            self.create(kind="merge", request_key="self-edge", intent_id=source,
                        definition=DEFINITION | {"source_intent_ids": [source]})
        self.assertEqual(len(self.rows("SELECT * FROM m07_draft")), 1)
        with self.fixture.fixture.db.db() as db:
            db.execute("BEGIN IMMEDIATE")
            registry(db, "4.0.0", VERSION)
            seal_registry(db, "4.0.0")
        with self.assertRaises(Conflict):
            self.update(first, request_key="stale-version")
        self.assertEqual(len(self.rows("SELECT * FROM m07_draft_revision")), 2)
        latest = self.service.detail(self.project, first["draft_id"])
        withdrawn = self.update(latest, "withdraw", expected_registry_version="4.0.0")
        self.assertEqual(withdrawn["base_registry_version"], VERSION)
        self.assertEqual(withdrawn["state"], "withdrawn")

    def test_history_recovery_does_not_move_the_head_or_copy_private_references(self):
        with self.fixture.fixture.db.db() as db:
            db.execute("BEGIN IMMEDIATE")
            registry(db, "4.0.0", VERSION)
            seal_registry(db, "4.0.0")
        restored = self.create(kind="restore", intent_id=fixtures.PENDING, expected_registry_version="4.0.0",
                               origin_registry_version=VERSION, definition=None)
        self.assertEqual(restored["definition"]["name"], fixtures.PENDING)
        self.assertEqual(restored["source_refs"], [])
        self.assertEqual(restored["survey_validation_status"], "unvalidated")
        self.assertEqual(RegistryVersions(self.fixture.relations).versions()["current_registry_version"], "4.0.0")
        self.assertEqual(RegistryVersions(self.fixture.relations).detail(VERSION, fixtures.PENDING)["name"],
                         fixtures.PENDING)
        second = self.create(kind="restore", request_key="restore-confirmed", intent_id=fixtures.INTENT,
                             expected_registry_version="4.0.0", origin_registry_version=VERSION, definition=None)
        self.assertIsNone(second["definition"]["primary_category_id"])
        self.assertIn("PRIMARY_REQUIRED", second["missing_fields"])

    def test_http_boundaries_hide_projects_and_publish_endpoint(self):
        app = create_app(self.fixture.fixture.case.settings, relation_grants=lambda: self.fixture.grants)
        base = "http://127.0.0.1:8765"
        current = f"/api/studies/{self.project}/registry/drafts"
        headers = {"origin": base, "X-VOC-Action": "connectivity"}
        payload = {"request_key": "api-new", "expected_registry_version": VERSION, "reason": "合成",
                   "kind": "candidate", "definition": DEFINITION}
        with TestClient(app, base_url=base, client=("127.0.0.1", 43100)) as client:
            self.assertEqual(client.get("/api/registry/versions").status_code, 200)
            self.assertEqual(client.get("/api/registry/intents", params={"registry_version": VERSION}).status_code, 200)
            self.assertEqual(client.get("/api/registry/intents", headers={"origin": "https://example.invalid"}).status_code, 403)
            self.assertEqual(client.post(current, json=payload).status_code, 403)
            self.assertEqual(client.post(current, headers=headers, json=payload | {"role": "owner"}).status_code, 422)
            result = client.post(current, headers=headers, json=payload)
            self.assertEqual(result.status_code, 201, result.text)
            self.assertEqual(result.headers["cache-control"], "no-store")
            self.assertEqual(client.post(current + "/publish", headers=headers, json={}).status_code, 405)
            draft_id = result.json()["draft_id"]
            self.fixture.grants.clear()
            self.assertEqual(client.get(current + "/" + draft_id).status_code, 404)
            self.assertEqual(client.get("/api/registry/projects").json(), {"items": []})
            self.assertEqual(client.post(current, headers=headers, json=payload).status_code, 403)
        with TestClient(app, base_url=base, client=("192.0.2.10", 43100)) as client:
            self.assertEqual(client.get("/api/registry/versions").status_code, 403)
