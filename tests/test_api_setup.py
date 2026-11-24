"""Offline API setup and diagnostic regressions. Provider fixtures cannot enter the formal ledger."""

from base64 import b64encode
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from src.config import MODEL, Settings
from src.dashboard.api_setup import KeyInput
from src.dashboard.app import balance, create_app
from src.execution.checks import run_checks
from src.execution.provider_diagnostics import run_probe
from src.execution.transport import Response, brave_monthly_quota
from src.raw_store.credentials import CredentialVault
from src.raw_store.store import Conflict, Store
from test_connectivity import response_for

ORIGIN = "http://localhost"
AUTH = {"X-VOC-Action": "connectivity", "Origin": ORIGIN}
FIRST = "offline-fixture-credential-first"
ROTATED = "offline-fixture-credential-rotated"


def review_pair(provider, *, valid=True):
    proof = b"Local engineering evidence fixture. Must not leave the workspace."
    document = {
        "provider": provider,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": "Test operator",
        "region": "Test",
        "terms_reference": "Isolated engineering fixture",
        "evidence_file": "../never-read-path-from-upload",
        "evidence_sha256": sha256(proof).hexdigest() if valid else "mismatch",
        "public_text_approved": True,
        "zdr_enabled": True,
        "retention_reviewed": True,
        "subprocessors_reviewed": True,
    }
    return {
        "record": b64encode(json.dumps(document).encode()).decode(),
        "attachment": b64encode(proof).decode(),
    }


class SetupAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = Settings(self.root)

    def client(self, base=None, peer="127.0.0.1"):
        return TestClient(
            create_app(base or self.base), base_url=ORIGIN, client=(peer, 31001), headers=AUTH
        )

    def read(self, client):
        response = client.get("/api/workspace")
        self.assertEqual(response.headers["cache-control"], "no-store")
        for marker in (FIRST, ROTATED, "NeverRepeatThisInput", "never-read-path-from-upload"):
            self.assertNotIn(marker, response.text)
        payload = response.json()
        return payload, {p["id"]: p for p in payload["setup"]["providers"]}

    def test_empty_workspace_planned_connectors_and_wizard(self):
        with self.client() as client:
            workspace, providers = self.read(client)
            self.assertEqual(workspace["history"], [])
            self.assertFalse(workspace["setup"]["wizard_seen"])
            self.assertEqual({p["status"] for p in providers.values()}, {"NOT_CONFIGURED"})
            self.assertEqual(
                {p["id"]: p["status"] for p in workspace["setup"]["future"]},
                {"youtube": "PLANNED", "forms": "PLANNED"},
            )
            for name in ("youtube", "forms"):
                self.assertEqual(client.put(f"/api/setup/{name}/key", json={"key": FIRST}).status_code, 404)
                self.assertEqual(client.post(f"/api/setup/{name}/diagnostics", json={"request_key": str(uuid4())}).status_code, 404)
            self.assertEqual(client.post("/api/setup/wizard").status_code, 200)
        with self.client() as client:
            self.assertTrue(self.read(client)[0]["setup"]["wizard_seen"])

    def test_rotation_is_immediate_and_survives_service_restart_without_echo(self):
        path = "/api/setup/jevmodel/key"
        with self.client() as client:
            self.assertEqual(client.put(path, json={"key": FIRST}).json(), {"configured": True})
            workspace, providers = self.read(client)
            self.assertTrue(workspace["token"]["key_configured"])
            self.assertEqual(providers["jevmodel"]["credential_source"], "local")
            self.assertEqual(providers["jevmodel"]["status"], "REVIEW_REQUIRED")
            self.assertTrue(client.put(path, json={"key": ROTATED}).is_success)
        with patch.object(Settings, "load_base", return_value=self.base):
            self.assertEqual(Settings.load().keys["jevmodel"], ROTATED)
        with self.client() as client:
            self.assertTrue(self.read(client)[0]["token"]["key_configured"])
            self.assertEqual(client.delete(path).json(), {"configured": False})
        with self.client() as client:
            self.assertEqual(self.read(client)[1]["jevmodel"]["status"], "NOT_CONFIGURED")
            self.assertFalse(CredentialVault(self.root).read()["keys"])

    def test_environment_keys_can_be_replaced_and_locally_disabled(self):
        base = replace(self.base, keys={"tavily": FIRST})
        with self.client(base) as client:
            self.assertEqual(self.read(client)[1]["tavily"]["credential_source"], "environment")
            self.assertTrue(client.put("/api/setup/tavily/key", json={"key": ROTATED}).is_success)
            self.assertTrue(client.delete("/api/setup/tavily/key").is_success)
        with self.client(base) as client:
            result = self.read(client)[1]["tavily"]
            self.assertFalse(result["configured"])
            self.assertEqual(result["credential_source"], "disabled")
            self.assertEqual(base.keys["tavily"], FIRST)

    def test_loopback_host_and_same_origin_required_for_mutations(self):
        path = "/api/setup/brave/key"
        with self.client() as client:
            for headers in (
                {"Origin": "https://example.invalid"},
                {"Origin": ""},
                {"Host": "example.invalid"},
                {"X-VOC-Action": ""},
            ):
                response = client.put(path, headers=headers, json={"key": FIRST})
                self.assertIn(response.status_code, (400, 403))
                self.assertNotIn(FIRST, response.text)
            self.assertEqual(self.read(client)[1]["brave"]["status"], "NOT_CONFIGURED")
        with self.client(peer="192.0.2.4") as client:
            self.assertEqual(client.put(path, json={"key": FIRST}).status_code, 403)
        self.assertFalse(CredentialVault(self.root).path.exists())

    def test_invalid_and_oversized_secret_requests_are_never_echoed_or_saved(self):
        path = "/api/setup/typesafe/key"
        with self.client() as client:
            for invalid in ({"key": {"NeverRepeatThisInput": ROTATED}}, {"key": FIRST, "extra": ROTATED},
                            {"key": "NeverRepeatThisInput\nInjected"}, {"key": "x" * 513}):
                response = client.put(path, json=invalid)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("NeverRepeatThisInput", response.text)
                self.assertNotIn(ROTATED, response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
            large = client.put(path, json={"key": ROTATED * 1024})
            self.assertEqual(large.status_code, 413)
            self.assertNotIn(ROTATED, large.text)
        self.assertFalse(CredentialVault(self.root).path.exists())

    def test_private_storage_and_failed_atomic_replacement(self):
        vault = CredentialVault(self.root)
        with self.client() as client:
            self.assertTrue(client.put("/api/setup/brave/key", json={"key": FIRST}).is_success)
            self.assertNotIn(FIRST, repr(KeyInput(key=FIRST)))
            if os.name == "nt":
                self.assertNotIn(FIRST.encode(), vault.path.read_bytes())
            else:
                self.assertEqual(vault.directory.stat().st_mode & 0o777, 0o700)
                self.assertEqual(vault.path.stat().st_mode & 0o777, 0o600)
            with patch("src.raw_store.credentials.os.replace", side_effect=OSError):
                self.assertEqual(client.put("/api/setup/brave/key", json={"key": ROTATED}).status_code, 503)
            self.assertEqual(vault.read()["keys"]["brave"], FIRST)
            self.assertEqual(list(vault.directory.iterdir()), [vault.path])

    def test_unreadable_vault_preserves_offline_access_and_fails_closed(self):
        with self.client(replace(self.base, keys={"jevmodel": FIRST})) as client:
            self.assertTrue(client.put("/api/setup/brave/key", json={"key": ROTATED}).is_success)
            vault = CredentialVault(self.root)
            vault.path.write_bytes(b"unreadable")
            workspace, _ = self.read(client)
            self.assertTrue(workspace["setup"]["error"])
            self.assertFalse(workspace["token"]["key_configured"])
            self.assertEqual(client.put("/api/setup/brave/key", json={"key": FIRST}).status_code, 503)
            self.assertEqual(client.post("/api/runs", json={"request_key": str(uuid4())}).status_code, 503)

    def test_reviews_and_active_provider_are_independent_and_persistent(self):
        with self.client() as client:
            path = "/api/setup/typesafe/review"
            self.assertEqual(client.put(path, json=review_pair("jevmodel")).status_code, 422)
            self.assertEqual(client.put(path, json=review_pair("typesafe", valid=False)).status_code, 422)
            self.assertTrue(client.put(path, json=review_pair("typesafe")).json()["approved"])
            self.assertTrue(client.put("/api/setup/jev/typesafe").is_success)
            self.assertTrue(client.put("/api/setup/typesafe/key", json={"key": FIRST}).is_success)
        with self.client() as client:
            workspace, providers = self.read(client)
            self.assertEqual(workspace["token"]["provider"], "typesafe")
            self.assertTrue(providers["typesafe"]["review"]["approved"])
            self.assertEqual(providers["typesafe"]["status"], "NOT_TESTED")
            self.assertFalse(providers["jevmodel"]["review"]["approved"])

    def test_preflight_records_without_http_are_idempotent_and_stay_out_of_formal_gate(self):
        key = str(uuid4())
        body = {"request_key": key}
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No egress expected")):
            with self.client() as client:
                first = client.post("/api/setup/tavily/diagnostics", json=body).json()
                self.assertEqual(first["status"], "NOT_CONFIGURED")
                self.assertIsNone(first["http_status"])
                self.assertTrue(client.put("/api/setup/jevmodel/key", json={"key": FIRST}).is_success)
                review = client.post("/api/setup/jevmodel/diagnostics", json={"request_key": str(uuid4())}).json()
                self.assertEqual(review["status"], "REVIEW_REQUIRED")
                self.assertIsNone(review["http_status"])
            with self.client() as restarted:
                later = restarted.post("/api/setup/tavily/diagnostics", json=body).json()
                self.assertEqual(later, first)
                work, providers = self.read(restarted)
                self.assertEqual(providers["tavily"]["recent_tests"][0]["evidence_id"], first["evidence_id"])
                self.assertEqual(work["history"], [])
                self.assertEqual(work["config"]["acceptance"], "NOT_TESTED")


class ProbeFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = Settings(
            self.root,
            keys={name: FIRST for name in ("jevmodel", "typesafe", "tavily", "brave")},
            local_reviews={"jevmodel": review_pair("jevmodel"), "typesafe": review_pair("typesafe")},
        )
        self.db = Store(self.root, diagnostic=True, fixture=True)

    def test_jev_fixed_version_fields_usage_and_same_key_only_send_one_pair(self):
        sent = []

        def sender(method, url, payload, headers):
            sent.append((url, payload, headers["Idempotency-Key"]))
            body = response_for(payload)
            body[FIRST] = FIRST
            body["request_debug"] = {"x-api-key": FIRST}
            return Response(200, body, 0, FIRST)

        result = run_probe(self.cfg, self.db, "jevmodel", "synthetic-11", sender)
        self.assertEqual(run_probe(self.cfg, self.db, "jevmodel", "synthetic-11", sender), result)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["scope"], "engineering_fixture")
        self.assertEqual([len(p["questions"]) for _, p, _ in sent], [8, 3])
        self.assertEqual({p["model"] for _, p, _ in sent}, {MODEL})
        self.assertEqual(len({k for _, _, k in sent}), 2)
        self.assertEqual([s["input_tokens"] for s in result["shards"]], [17, 17])
        self.assertEqual(result["shards"][-1]["remaining_tokens"], 0)
        self.assertEqual(balance(Store(self.root), self.cfg, self.db)["input_tokens"], 34)
        self.assertEqual(Store(self.root).history(), [])
        self.assertNotIn(FIRST, json.dumps(self.db.audit(result["run_id"])))

    def test_missing_probability_and_alias_stay_blocked(self):
        def missing(method, url, payload, headers):
            data = response_for(payload)
            if "friction" in data["answers"]:
                del data["answers"]["friction"]["probabilities"]
            return Response(200, data)

        def alias(method, url, payload, headers):
            return Response(200, {**response_for(payload), "model": "jev-latest"})

        gaps = run_probe(self.cfg, self.db, "jevmodel", "missing", missing)
        wrong = run_probe(self.cfg, self.db, "typesafe", "alias", alias)
        rejected = run_probe(self.cfg, self.db, "jevmodel", "rejected", lambda *a: Response(422, {}))
        self.assertEqual(gaps["status"], "CAPABILITY_BLOCKED")
        self.assertIn("friction.probabilities", gaps["schema_gap"])
        self.assertNotIn("probabilities", gaps["shards"][0]["response_fields"]["friction"])
        self.assertEqual(wrong["status"], "CAPABILITY_BLOCKED")
        self.assertEqual([s["response_model"] for s in wrong["shards"]], ["jev-latest"])
        self.assertEqual(rejected["status"], "CAPABILITY_BLOCKED")
        self.assertEqual(rejected["http_status"], 422)
        self.assertIn("fixed_model_or_request_contract", rejected["schema_gap"])

    def test_diagnostics_cannot_retry_unrecorded_or_ambiguous_requests(self):
        self.db.begin("in-flight", self.cfg)
        with self.assertRaises(Conflict):
            run_probe(self.cfg, self.db, "jevmodel", "in-flight", lambda *args: self.fail("No resend"))
        issued = []

        def fail(method, url, body, headers):
            issued.append(headers["Idempotency-Key"])
            return Response(None, {})

        first = run_probe(self.cfg, self.db, "jevmodel", "aborted", fail)
        later = run_probe(self.cfg, self.db, "jevmodel", "aborted", fail)
        self.assertEqual(first, later)
        self.assertEqual(first["error_code"], "offline")
        self.assertEqual(len(issued), 1)
        self.assertIsNone(first["shards"][0]["input_tokens"])
        with self.assertRaises(Conflict):
            run_probe(self.cfg, self.db, "typesafe", "aborted", fail)
        with self.assertRaises(ValueError):
            run_checks(self.cfg, Store(self.root, diagnostic=True), "not-a-formal-run")

    def test_search_checks_provider_then_canonical_source_and_ignores_snippets(self):
        sent = []
        original = "https://cooking.stackexchange.com/q/123"

        def sender(method, url, payload, headers):
            sent.append((url, headers))
            if "api.tavily.com" in url:
                self.assertTrue(payload["include_usage"])
                return Response(200, {"results": [{"url": original, "content": FIRST}], "usage": {"credits": 1}})
            return Response(200, {
                "items": [{
                    "question_id": 123, "link": original, "content_license": "CC BY-SA 4.0",
                    "creation_date": 1724000000, "owner": {"display_name": "Example participant"},
                    "body": "<p>I need a better way to clean a sticky measuring cup.</p>",
                }],
            })

        good = run_probe(self.cfg, self.db, "tavily", "search", sender)
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0][1]["Authorization"], "Bearer " + FIRST)
        self.assertNotIn("Authorization", sent[1][1])
        self.assertTrue(good["source"]["excerpt_verified"])
        self.assertEqual(good["source"]["source_http"], [200])
        self.assertEqual(good["credits"], 1)
        self.assertNotIn(FIRST, json.dumps(self.db.audit(good["run_id"])))

        def no_license(method, url, payload, headers):
            if "api.tavily.com" in url:
                return Response(200, {"results": [{"url": original, "content": "Search text only."}]})
            return Response(200, {"items": [{"question_id": 123, "link": original, "body": "No approval."}]})

        weak = run_probe(self.cfg, self.db, "tavily", "no-license", no_license)
        self.assertEqual(weak["status"], "CONNECTED")
        self.assertTrue(weak["source"]["original_fetched"])
        self.assertFalse(weak["source"]["license_verified"])
        self.assertFalse(weak["source"]["excerpt_verified"])

    def test_provider_error_outcomes_and_budget_are_based_on_observed_fields(self):
        for status, reason in ((401, "invalid_key"), (402, "insufficient_balance"), (403, "permission_denied"),
                               (429, "rate_limited"), (503, "upstream_error")):
            result = run_probe(self.cfg, self.db, "brave", f"error-{status}", lambda *a: Response(status, {}))
            self.assertEqual((result["http_status"], result["error_code"]), (status, reason))
            self.assertIsNone(result["monthly_remaining"])
        self.assertEqual(brave_monthly_quota({"X-RateLimit-Remaining": "1"}), (None, None))
        self.assertEqual(brave_monthly_quota({
            "X-RateLimit-Limit": "1, 1000", "X-RateLimit-Remaining": "1, 0",
            "X-RateLimit-Policy": "1;w=1, 1000;w=2592000",
        }), (0, 1000))
