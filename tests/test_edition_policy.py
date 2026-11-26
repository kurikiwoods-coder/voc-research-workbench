"""B-phase regressions using only private temporary databases and synthetic inputs."""

from base64 import b64encode
from contextlib import closing, redirect_stdout
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote
from uuid import uuid4

from fastapi.testclient import TestClient

from src.config import PACKYCODE_LIVE_BLOCK, Settings
from src.dashboard.app import create_app
from src.dashboard.personal_workspace import provision
from src.dashboard.study_api import ProjectInput
from src.edition_policy import Deployment, Domain, Edition, EditionPolicy, LocalOwner, Permission
from src.execution import packycode_preflight
from src.execution.checks import CODES, run_checks
from src.execution.jev import call_shards
from src.execution.provider_diagnostics import run_probe
from src.execution.transport import Denied, network, outbound
from src.ingestion.public_source import discover
from src.outputs.audit_receipt import export, verify_public_source
from src.outputs.recover_source_batch import restore_public_source_batch
from src.raw_store.store import Conflict, Store
from src.raw_store.studies import StudyStore
from test_corpus import QUOTE, ROW
from test_imports import HEADERS, ORIGIN, make_csv


def fixture_root(prefix):
    return TemporaryDirectory(prefix=prefix, dir=os.getenv("LOCALAPPDATA") if os.name == "nt" else None)


def owner_environment(binding=None, proof=None, **overrides):
    proof = proof or token_urlsafe(32)
    current = datetime.now(UTC)
    grant = None
    if binding is not None:
        grant = {key: binding[key] for key in ("study_id", "scope_id", "scope_version")}
        grant.update(purpose="personal_research", permissions=[p.value for p in Permission],
                     evidence_ref="local:synthetic-owner-grant", starts_at=(current - timedelta(days=1)).isoformat(),
                     expires_at=(current + timedelta(days=1)).isoformat())
        grant.update(overrides)
    environment = {
        "VOC_PERSONAL_OPERATOR_REF": "local-operator",
        "VOC_PERSONAL_OWNER_REF": "project-owner",
        "VOC_PERSONAL_OWNER_SHA256": sha256(proof.encode()).hexdigest(),
        "VOC_PERSONAL_PROJECT_GRANTS": json.dumps([grant] if binding else []),
    }
    return environment, proof


class EditionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(fixture_root("voc-edition-中文 ")))
        self.directory = self.root / "personal"
        self.binding = provision(self.directory, "合成图书馆课题", "研究合成输入", uuid4())
        self.sid, self.scope = self.binding["study_id"], self.binding["scope_id"]
        self.other = provision(self.directory, "第二合成项目", "不同范围", uuid4())
        self.env, self.proof = owner_environment(self.binding)
        self.auth = ("owner", self.proof)
        self.settings = self.personal_settings(self.env)
        self.imports = f"/api/imports/{self.sid}"
        self.corpus = f"/api/corpus/{self.sid}"
        self.opener = self.enterContext(patch("src.execution.transport.build_opener",
                                             side_effect=AssertionError("Unexpected supplier HTTP")))
        self.addCleanup(self.opener.assert_not_called)

    def personal_settings(self, environment):
        return Settings(self.directory, edition=Edition.PERSONAL, personal_owner=LocalOwner.from_environment(environment))

    def open_client(self, settings=None, *, auth=True, peer="127.0.0.1"):
        app = create_app(settings or self.settings)
        headers = dict(HEADERS)
        if auth:
            encoded = b64encode(f"owner:{self.proof}".encode()).decode()
            headers["Authorization"] = "Basic " + encoded
        client = TestClient(app, base_url=ORIGIN, client=(peer, 29204), headers=headers)
        return client, app

    def upload(self, client, study=None, scope=None, *, rows=None):
        return client.post(f"/api/imports/{study or self.sid}/scopes/{scope or self.scope}/uploads",
                           content=make_csv(rows=rows or [ROW]), headers={
                               "Content-Type": "application/octet-stream", "X-VOC-Filename": quote("合成样本.csv"),
                           })

    def imported(self, client, *, study=None, scope=None, rows=None):
        root = f"/api/imports/{study or self.sid}"
        response = self.upload(client, study, scope, rows=rows)
        response.raise_for_status()
        url = root + "/uploads/" + response.json()["file_id"]
        plan = {"sheet_index": 0, "mapping": client.get(url).raise_for_status().json()["suggested_mapping"]}
        preview = client.post(url + "/preview", json=plan).raise_for_status().json()
        plan["preview_token"] = preview["preview_token"]
        receipt = client.post(url + "/confirm", json=plan).raise_for_status().json()
        return url, plan, receipt["batch_id"]

    def review(self, client, record, **updates):
        return client.post(f"{self.corpus}/records/{record}/review", json={
            "decision": "verified", "role": "user_quote", "reason": "人工复核合成夹具",
            "basis": "合成来源许可", "license_status": "authorized", "license_evidence_ref": "local:fixture-authority",
            "retention_until": (datetime.now(UTC).date() + timedelta(days=30)).isoformat(),
        } | updates)

    def test_default_install_keeps_business_health_gate_and_setup(self):
        with patch.dict(os.environ, {"VOC_DATA_DIR": str(self.root / "business")}, clear=True):
            settings = Settings.load_base()
        self.assertEqual((settings.edition, settings.deployment), (Edition.BUSINESS, Deployment.LOCAL))
        client, _ = self.open_client(settings, auth=False)
        with client:
            status = client.get("/api/edition").raise_for_status().json()
            self.assertEqual(status["gates"]["business"]["status"], "BLOCKED")
            self.assertEqual(status["gates"]["personal"]["status"], "NOT_EVALUATED")
            self.assertTrue(status["operations"]["legacy_connectivity"])
            self.assertFalse(status["operations"]["personal_formal_research"])
            self.assertEqual(client.get("/api/workspace").status_code, 200)
            self.assertEqual(client.get("/api/edition/projects").status_code, 403)
            probe = client.post("/api/setup/packycode/diagnostics", json={"request_key": str(uuid4())})
            self.assertEqual(probe.status_code, 409)
            self.assertIn(PACKYCODE_LIVE_BLOCK, probe.text)

    def test_business_status_requires_current_review_and_same_finished_attempt_evidence(self):
        directory = self.root / "business"
        cfg = Settings(directory, keys={"jevmodel": "local-synthetic-credential"})
        review = {"approved": True, "checked_at": "2026-11-25T00:00:00+00:00", "review_hash": "reference-1"}
        client, app = self.open_client(cfg, auth=False)
        with client, patch.object(Settings, "review_status", return_value=review):
            store = app.state.store
            run, attempt = store.begin(str(uuid4()), cfg)
            for code in CODES:
                store.result(attempt, code, "PASS", "synthetic status-projection fixture", [])
            proof = store.record(attempt, "stage_gate", "local_gate", {}, {
                "statuses": dict.fromkeys(CODES, "PASS"), "provider_review": review,
            })
            store.result(attempt, "G-1", "PASS", "synthetic status-projection fixture", [proof])
            self.assertEqual(client.get("/api/edition").json()["gates"]["business"]["status"], "BLOCKED")
            store.finish(run, attempt, passed=True)
            self.assertEqual(client.get("/api/edition").json()["gates"]["business"]["status"], "PASS")
            with patch.object(Settings, "review_status", return_value=review | {"review_hash": "other-review"}):
                self.assertEqual(client.get("/api/edition").json()["gates"]["business"]["status"], "BLOCKED")
        with self.open_client()[0] as personal:
            status = personal.get("/api/edition").json()
            self.assertEqual(status["gates"]["personal"]["status"], "NOT_EVALUATED")
            self.assertEqual(status["gates"]["business"]["status"], "BLOCKED")

    def test_trusted_environment_accepts_each_valid_pair_only(self):
        for edition, deployment in ((e, d) for e in Edition for d in Deployment):
            with self.subTest(edition=edition, deployment=deployment), patch.dict(os.environ, {
                **self.env, "VOC_DATA_DIR": str(self.directory), "VOC_EDITION": edition, "VOC_DEPLOYMENT": deployment,
                "JEVMODEL_API_KEY": "fixture-local-secret",
            }, clear=True):
                cfg = Settings.load_base()
                self.assertEqual((cfg.edition, cfg.deployment), (edition, deployment))
                legacy = edition == Edition.BUSINESS and deployment == Deployment.LOCAL
                self.assertEqual(bool(cfg.keys), legacy)
                self.assertEqual(cfg.personal_owner is not None, edition == Edition.PERSONAL and deployment == Deployment.LOCAL)
        for setting, bad in (("VOC_EDITION", "personal"), ("VOC_EDITION", ""), ("VOC_DEPLOYMENT", "remote")):
            with patch.dict(os.environ, {setting: bad}, clear=True), self.assertRaises(ValueError):
                Settings.load_base()

    def test_invalid_owner_startup_and_grant_shapes_fail_closed(self):
        for changes in ({"VOC_PERSONAL_OWNER_SHA256": "test"},
                        {"VOC_PERSONAL_PROJECT_GRANTS": '{"status":"PASS"}'},
                        {"VOC_PERSONAL_PROJECT_GRANTS": "[" * 3000}):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ValueError):
                self.personal_settings(self.env | changes)
        without_dir = self.env | {"VOC_EDITION": "PERSONAL"}
        with patch.dict(os.environ, without_dir, clear=True), self.assertRaises(ValueError):
            Settings.load_base()
        with self.assertRaises(ValueError):
            Settings(self.directory, edition=Edition.PERSONAL)

    def test_cloud_is_status_only_and_opens_no_directory(self):
        for edition in Edition:
            directory = self.root / ("cloud-" + edition)
            client, app = self.open_client(Settings(directory, edition=edition, deployment=Deployment.CLOUD))
            with client:
                self.assertEqual(client.get("/api/health").json()["schema_version"], None)
                self.assertEqual(client.get("/api/edition").json()["workspace"], "STATUS_ONLY")
                for path in ("/api/workspace", "/api/studies", "/api/edition/projects", "/api/acquisition/sources"):
                    self.assertEqual(client.get(path).status_code, 403)
                self.assertEqual(client.post("/api/runs", json={}).status_code, 403)
                self.assertFalse(hasattr(app.state, "vault"))
                self.assertFalse(directory.exists())

    def test_owner_identity_is_trusted_and_only_exposes_typed_projection(self):
        client, _ = self.open_client()
        with client:
            response = client.get(f"/api/edition/projects/{self.sid}")
            payload = response.raise_for_status().json()
            self.assertEqual(payload["actor_ref"], "local-operator")
            self.assertEqual(payload["owner_ref"], "project-owner")
            self.assertEqual(payload["scope"], {key: self.binding[key] for key in ("study_id", "scope_id", "scope_version")})
            self.assertEqual(payload["evidence_refs"], ["local:synthetic-owner-grant"])
            self.assertEqual(payload["gate"], "G-1-PERSONAL")
            self.assertEqual(payload["purpose"], "personal_research")
            self.assertTrue(payload["allowed"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            for secret in (self.proof, self.env["VOC_PERSONAL_OWNER_SHA256"], QUOTE):
                self.assertNotIn(secret, response.text)
            self.assertTrue(client.get("/api/edition/projects").json()["projects"])

    def test_http_cannot_claim_owner_edition_grant_or_gate(self):
        path = f"/api/edition/projects/{self.sid}"
        client, _ = self.open_client(auth=False)
        with client:
            self.assertEqual(client.get("/api/edition").status_code, 200)
            for claimed in ({"X-VOC-Role": "owner"}, {"X-VOC-Edition": "BUSINESS"}, {"X-VOC-Actor": "project-owner"}):
                self.assertEqual(client.get(path, headers=claimed).status_code, 403)
            self.assertEqual(client.get(path, params={"edition": "BUSINESS"}).status_code, 403)
            self.assertEqual(client.get(path, params={"owner": "true"}).status_code, 403)
            for auth in (None, ("owner", "fake-proof"), ("different", self.proof)):
                self.assertEqual(client.get(path, auth=auth).status_code, 401)
            self.assertEqual(client.get(path, headers={"Authorization": "Basic !!!!"}).status_code, 401)
            injected = client.post("/api/runs", json={"edition": "BUSINESS", "owner": True, "gate_status": "PASS"})
            self.assertEqual(injected.status_code, 401)
        with self.open_client()[0] as trusted:
            url, plan, _ = self.imported(trusted)
            invalid = trusted.post(url + "/confirm", json=plan | {"edition": "BUSINESS"})
            self.assertEqual(invalid.status_code, 422)
            self.assertNotIn("BUSINESS", invalid.text)
            self.assertEqual(trusted.post("/api/runs", json={"gate_status": "PASS"}).status_code, 403)

    def test_nonloopback_and_foreign_origin_are_denied_even_with_proof(self):
        with self.open_client(peer="192.0.2.8")[0] as other:
            self.assertEqual(other.get("/api/edition/projects").status_code, 403)
        with self.open_client()[0] as trusted:
            self.assertEqual(trusted.get("/api/edition/projects", headers={"Origin": "https://origin.invalid"}).status_code, 403)
            self.assertEqual(trusted.get("/api/edition/projects", headers={"Host": "origin.invalid", "Origin": "http://origin.invalid"}).status_code, 400)

    def test_unbound_and_nonexistent_project_are_indistinguishable(self):
        with self.open_client()[0] as client:
            forbidden = client.get(f"/api/edition/projects/{self.other['study_id']}")
            missing = client.get(f"/api/edition/projects/{uuid4()}")
            self.assertEqual((forbidden.status_code, forbidden.json()), (404, missing.json()))
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(client.get(f"/api/edition/projects/{self.sid.upper()}").status_code, 200)
        env, _ = owner_environment(proof=self.proof)
        with self.open_client(self.personal_settings(env))[0] as unbound:
            self.assertEqual(unbound.get("/api/edition/projects").json(), {"projects": []})
            self.assertEqual(unbound.get(f"/api/edition/projects/{self.sid}").status_code, 404)

    def test_expired_wrong_version_and_archived_project_fail_authorization(self):
        for changes in ({"scope_version": "v2"}, {"scope_id": self.other["scope_id"]},
                        {"starts_at": "2020-01-01T00:00:00+00:00", "expires_at": "2021-01-01T00:00:00+00:00"}):
            env, _ = owner_environment(self.binding, self.proof, **changes)
            with self.open_client(self.personal_settings(env))[0] as client:
                self.assertEqual(client.get(f"/api/edition/projects/{self.sid}").status_code, 404)
        studies = StudyStore(Store(self.directory, edition=Edition.PERSONAL))
        studies.archive(self.sid, studies.get(self.sid)["revision"])
        with self.open_client()[0] as client:
            self.assertEqual(client.get(f"/api/studies/{self.sid}/scopes/{self.scope}").status_code, 404)

    def test_permissions_and_frozen_scope_are_enforced_for_imports(self):
        env, _ = owner_environment(self.binding, self.proof, permissions=["read_scope"])
        with self.open_client(self.personal_settings(env))[0] as client:
            self.assertEqual(client.get(f"/api/studies/{self.sid}/scopes/{self.scope}").status_code, 200)
            self.assertEqual(self.upload(client).status_code, 403)
            self.assertEqual(client.get(self.imports + "/batches").status_code, 403)
        with self.open_client()[0] as client:
            denied = self.upload(client, self.sid, self.other["scope_id"])
            self.assertEqual(denied.status_code, 404)
            denied = self.upload(client, self.other["study_id"], self.other["scope_id"])
            self.assertEqual(denied.status_code, 404)
            self.assertEqual(client.get(self.imports + "/batches").json()["batches"], [])

    def test_import_review_replay_revocation_and_formal_status(self):
        client, app = self.open_client()
        with client:
            url, plan, batch = self.imported(client)
            detail = client.get(self.corpus + "/batches/" + batch).raise_for_status().json()
            record = detail["records"][0]["record_id"]
            record_url = self.corpus + "/records/" + record
            self.assertEqual(client.get(record_url + "/eligible").status_code, 409)
            accepted = self.review(client, record).raise_for_status().json()
            self.assertEqual(accepted["raw_text"], QUOTE)
            qualification = client.get(record_url + "/eligible").raise_for_status().json()
            self.assertTrue(qualification["engineering_eligible"])
            self.assertFalse(qualification["research_eligible"])
            self.assertFalse(qualification["outbound_allowed"])
            self.assertEqual(qualification["trace"]["scope_id"], self.scope)
            statuses = f"/api/studies/{self.sid}/denominators"
            result = client.get(statuses, params={"mode": "formal"}).raise_for_status().json()
            self.assertEqual((result["availability"], result["counts"]), ("unavailable", None))
            self.assertIsNone(result["reconciliation"])
            self.assertIsNone(result["by_primary_category"])
            self.assertIn("G1_PERSONAL_NOT_EVALUATED", result["reasons"])
            self.assertEqual(result["counting_policy_version"], "M06-B-F.1")
            self.assertEqual(client.get(statuses, params={"mode": "synthetic"}).status_code, 403)
            self.assertEqual(client.get(statuses, params={"mode": "formal", "scope_id": self.other["scope_id"]}).status_code, 404)
            imported = client.post(url + "/confirm", json=plan).raise_for_status().json()
            self.assertEqual(imported["batch_id"], batch)
            client.post(self.imports + "/batches/" + batch + "/revoke").raise_for_status()
            self.assertNotIn(QUOTE, client.get(record_url).text)
            self.assertEqual(client.get(record_url + "/eligible").status_code, 409)
            self.assertNotIn(QUOTE, client.get(self.imports + "/batches/" + batch).text)
            self.assertNotIn(QUOTE, client.get(self.imports + "/batches/" + batch + "/errors.csv").raise_for_status().text)
            self.assertEqual(app.state.store.one("SELECT count(*) AS n FROM runs")["n"], 0)

    def test_historical_scope_cannot_return_other_scope_rows_or_duplicate_counts(self):
        studies = StudyStore(Store(self.directory, edition=Edition.PERSONAL))
        initial = studies.get(self.sid)
        newer = ProjectInput(name="合成图书馆课题", scope={"mode": "open", "topic": "另一个冻结范围"})
        other_scope = studies.update(self.sid, initial["revision"], newer.metadata(), newer.snapshot(), "")["scope"]
        studies.freeze(self.sid, other_scope["scope_id"])
        env, _ = owner_environment(other_scope, self.proof)
        with self.open_client(self.personal_settings(env))[0] as second_version:
            _, _, hidden = self.imported(second_version, scope=other_scope["scope_id"],
                                         rows=[[ROW[0], ROW[1], "https://source-b.invalid/post/2", *ROW[3:]]])
            hidden_record = second_version.get(self.corpus + "/batches/" + hidden).json()["records"][0]["record_id"]
            self.review(second_version, hidden_record).raise_for_status()
        with self.open_client()[0] as client:
            _, _, visible = self.imported(client)
            record = client.get(self.corpus + "/batches/" + visible).json()["records"][0]["record_id"]
            self.review(client, record).raise_for_status()
            reply = client.get(self.corpus + "/records/" + record).raise_for_status()
            self.assertEqual(reply.json()["duplicate"]["record_count"], 1)
            self.assertEqual(reply.json()["duplicate"]["canonical_record_id"], record)
            self.assertNotIn(hidden_record, reply.text)
            self.assertEqual(client.get(self.corpus + "/records/" + hidden_record).status_code, 404)
            self.assertEqual(client.get(self.imports + "/batches/" + hidden).status_code, 404)
            self.assertEqual(client.get(self.imports + "/batches/" + hidden + "/errors.csv").status_code, 404)
            self.assertEqual(client.get(self.corpus + "/batches/" + hidden).status_code, 404)
            self.assertEqual([row["batch_id"] for row in client.get(self.corpus + "/batches").json()["batches"]], [visible])
            self.assertEqual([row["batch_id"] for row in client.get(self.imports + "/batches").json()["batches"]], [visible])

    def test_import_and_review_permissions_do_not_read_verified_corpus(self):
        with self.open_client()[0] as client:
            _, _, batch = self.imported(client)
            record = client.get(self.corpus + "/batches/" + batch).json()["records"][0]["record_id"]
            self.review(client, record).raise_for_status()
        env, _ = owner_environment(self.binding, self.proof, permissions=["import_local", "review_corpus"])
        with self.open_client(self.personal_settings(env))[0] as client:
            saved = client.get(f"{self.imports}/batches/{batch}").raise_for_status().json()
            self.assertEqual(saved["rows"][0]["raw_text"], None)
            self.assertEqual(saved["rows"][0]["fields"], {})
            self.assertTrue(saved["rows"][0]["content_restricted"])
            self.assertEqual(client.get(self.corpus + "/records/" + record).status_code, 403)
            denied = self.review(client, record)
            self.assertEqual(denied.status_code, 403)
            self.assertNotIn(QUOTE, denied.text)

    def test_deny_without_permissions_does_not_disclose_object_existence(self):
        with self.open_client()[0] as client:
            _, _, batch = self.imported(client)
            record = client.get(self.corpus + "/batches/" + batch).json()["records"][0]["record_id"]
        env, _ = owner_environment(self.binding, self.proof, permissions=["read_scope"])
        with self.open_client(self.personal_settings(env))[0] as client:
            for existing, unknown in ((f"{self.imports}/batches/{batch}", f"{self.imports}/batches/{uuid4()}"),
                                      (f"{self.corpus}/records/{record}", f"{self.corpus}/records/{uuid4()}:2")):
                denied, missing = client.get(existing), client.get(unknown)
                self.assertEqual((denied.status_code, denied.json()), (403, missing.json()))
                self.assertEqual(missing.status_code, 403)

    def test_protected_read_rechecks_current_scope_inside_its_snapshot(self):
        with self.open_client()[0] as client:
            _, _, batch = self.imported(client)
            record = client.get(self.corpus + "/batches/" + batch).json()["records"][0]["record_id"]
            self.review(client, record).raise_for_status()
            for target in (f"{self.corpus}/records/{record}", f"{self.corpus}/records/{record}/eligible",
                           f"{self.imports}/batches/{batch}", f"{self.imports}/batches/{batch}/errors.csv"):
                self.assertEqual(client.get(target).status_code, 200)
                with patch("src.dashboard.edition_access.has_scope", side_effect=[True, False]):
                    denied = client.get(target)
                    self.assertEqual(denied.status_code, 403)
                    self.assertNotIn(QUOTE, denied.text)

    def test_upload_neither_counts_nor_deletes_other_projects_drafts(self):
        env, _ = owner_environment(self.other, self.proof)
        with self.open_client(self.personal_settings(env))[0] as other:
            for index in range(8):
                row = [f"Other synthetic fixture {index}", *ROW[1:]]
                self.upload(other, self.other["study_id"], self.other["scope_id"], rows=[row]).raise_for_status()
        old = provision(self.directory, "第三合成项目", "无权批次", uuid4())
        env, _ = owner_environment(old, self.proof)
        with self.open_client(self.personal_settings(env))[0] as other:
            with patch("src.raw_store.imports.now", return_value="2020-01-01T00:00:00+00:00"):
                draft = self.upload(other, old["study_id"], old["scope_id"]).raise_for_status().json()["file_id"]
        client, app = self.open_client()
        with client:
            self.assertEqual(self.upload(client).status_code, 201)
            self.assertEqual(app.state.store.one("SELECT file_id FROM import_files WHERE file_id=?", (draft,))["file_id"], draft)
            self.assertEqual(len(client.get(self.imports + "/batches").json()["drafts"]), 1)

    def test_local_mutation_rechecks_inside_write_transaction_and_can_retry(self):
        client, app = self.open_client()
        with client:
            with patch("src.dashboard.edition_access.has_scope", side_effect=[True, False]):
                self.assertEqual(self.upload(client).status_code, 403)
            self.assertEqual(app.state.store.one("SELECT count(*) AS n FROM import_files")["n"], 0)
            self.assertEqual(self.upload(client).status_code, 201)

    def test_personal_research_admission_and_engineering_domains_cannot_promote_each_other(self):
        policy = EditionPolicy(Edition.PERSONAL, Deployment.LOCAL, self.settings.personal_owner)
        for domain in Domain:
            decision = policy.decide(Permission.READ_SCOPE, domain, proof=self.proof, study_id=self.sid,
                                     current_scope=lambda scope: scope.scope_id == self.scope)
            self.assertEqual(decision.allowed, domain == Domain.LOCAL_WORKSPACE)
            self.assertEqual(decision.gate_status, "NOT_EVALUATED")
        for capability in ("approve", "validate_live", "publish", "collect", "reserve_budget", "replay"):
            self.assertFalse(policy.decide(capability, Domain.LOCAL_WORKSPACE, proof=self.proof,
                                          study_id=self.sid, current_scope=lambda _: True).allowed)

    def test_closed_live_routes_do_not_create_tasks_runs_or_vendor_requests(self):
        client, app = self.open_client()
        with client:
            for method, path in (
                ("POST", "/api/runs"), ("GET", f"/api/runs/{uuid4()}/evidence"),
                ("POST", f"/api/runs/{uuid4()}/resume"), ("POST", "/api/setup/jevmodel/diagnostics"),
                ("PUT", "/api/setup/jevmodel/review"), ("PUT", "/api/setup/packycode/key"),
                ("POST", f"/api/acquisition/{self.sid}/collect"), ("POST", f"/api/acquisition/{self.sid}/tasks"),
                ("POST", f"/api/acquisition/{self.sid}/tasks/{uuid4()}/step"),
                ("GET", f"/api/acquisition/{self.sid}/tasks"), ("GET", "/api/registry/versions"),
            ):
                with self.subTest(path=path):
                    self.assertEqual(client.request(method, path).status_code, 403)
            self.assertFalse(hasattr(app.state, "sampling"))
            self.assertFalse(hasattr(app.state, "diagnostics"))
        # Opening the same workspace again cannot resume the rejected operations.
        with self.open_client()[0] as reopened:
            self.assertEqual(reopened.post("/api/runs").status_code, 403)
            self.assertEqual(app.state.store.one("SELECT count(*) AS n FROM runs")["n"], 0)

    def test_legacy_services_refuse_personal_config_or_personal_store(self):
        formal = Store(self.root / "legacy")
        diagnostic = Store(self.root / "legacy", diagnostic=True)
        personal = Store(self.directory, edition=Edition.PERSONAL)
        for cfg, database in ((self.settings, formal), (Settings(self.root / "legacy"), personal),
                              (Settings(self.root / "cloud", deployment=Deployment.CLOUD), formal)):
            with self.assertRaises(Conflict):
                run_checks(cfg, database, str(uuid4()))
            with self.assertRaises(Denied):
                discover(cfg, database, None)
            self.assertEqual(call_shards(cfg, database, None, None, None)[:3], ([], [], []))
        result = run_probe(self.settings, diagnostic, "tavily", str(uuid4()))
        self.assertEqual(result["status"], "LIVE_TEST_BLOCKED")
        self.assertIsNone(result["http_status"])
        self.assertEqual(result["research_denominator"], 0)
        self.assertEqual(formal.history(), [])
        self.assertEqual(diagnostic.history(), [])
        self.assertEqual(personal.history(), [])
        with patch("src.outputs.audit_receipt.Settings.load_base", return_value=self.settings):
            self.assertEqual(verify_public_source(self.root)["status"], "BLOCKED")

    def test_archive_commands_and_resume_stop_before_store_or_transport(self):
        target = self.root / "must-not-create"
        environment = os.environ | {"VOC_EDITION": "PERSONAL", "VOC_DEPLOYMENT": "CLOUD", "VOC_DATA_DIR": str(target)}
        for args in (["src.outputs.audit_receipt", "--run", str(uuid4()), str(target)],
                     ["src.outputs.recover_source_batch"]):
            with self.subTest(command=args[0]):
                result = subprocess.run([sys.executable, "-m", *args], env=environment, capture_output=True,
                                        check=False, text=True, encoding="utf-8", timeout=25)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(target.exists())
                self.assertNotIn("Traceback", result.stderr)
        with self.assertRaises(ValueError):
            export(Store(self.directory, edition=Edition.PERSONAL), str(uuid4()), target)
        legacy = Store(self.root / "legacy-fixture", fixture=True)
        fixture = Mock()
        with self.assertRaises(ValueError):
            restore_public_source_batch(self.settings, legacy, folder=target, transport=fixture)
        fixture.assert_not_called()
        self.assertIsNone(legacy.one("SELECT id FROM runs"))

    def test_denied_privileged_route_never_parses_or_echoes_body(self):
        with self.open_client()[0] as client:
            malformed = b'{"request_key":"private-body-marker"'
            response = client.post("/api/runs", content=malformed, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("private-body-marker", response.text)
        with self.open_client(auth=False)[0] as client:
            response = client.post("/api/runs", content=malformed, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("private-body-marker", response.text)

    def test_transport_protects_configuration_independent_of_http_layer(self):
        for configuration in ({"VOC_EDITION": "PERSONAL"}, {"VOC_DEPLOYMENT": "CLOUD"}, {"VOC_EDITION": "unknown"}):
            with patch.dict(os.environ, configuration, clear=True), self.assertRaises(Denied):
                outbound("tavily", labels={"public_approved"})
        for channel in ("typesafe", "jevmodel", "tavily"):
            transport = Mock()
            with self.assertRaises(Denied):
                outbound(channel, labels={"internal_cx"}, transport=transport)
            transport.assert_not_called()
        with self.assertRaises(Denied):
            outbound("packycode", labels={"public_approved"}, method="POST")

    def test_no_claim_or_directory_can_restore_consumed_preflight(self):
        fresh = self.root / "fresh-preflight"
        for flags in ("--execute", "--resume-second"):
            with patch("sys.argv", ["preflight", flags, "--account-evidence", "never-read.json"]), \
                 patch.object(packycode_preflight, "PROBE_DIRECTORY", fresh), redirect_stdout(StringIO()) as output:
                self.assertEqual(packycode_preflight.main(), 2)
                self.assertIn("授权已耗尽", output.getvalue())
        diagnostics = Store(self.root / "preflight-ledger", diagnostic=True)
        with self.assertRaisesRegex(Denied, "授权已耗尽"):
            packycode_preflight.run_preflight(diagnostics, "fixture", fresh, vault_revision="fixture", transport=network)
        self.assertFalse(fresh.exists())
        self.assertEqual(diagnostics.history(), [])

    def test_databases_keep_edition_tag_even_if_copied(self):
        business = Store(self.root / "old-business")
        personal = Store(self.directory, edition=Edition.PERSONAL)
        if os.name != "nt":
            business.directory.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "独立空目录"):
            Store(business.directory, edition=Edition.PERSONAL)
        with self.assertRaisesRegex(ValueError, "个人工作区"):
            Store(personal.directory)
        with self.assertRaisesRegex(ValueError, "嵌套"):
            Store(personal.directory / "other")
        with self.assertRaisesRegex(ValueError, "嵌套"):
            Store(personal.directory / "other", edition=Edition.PERSONAL)
        target = self.root / "copied"
        target.mkdir()
        with personal.db() as source, closing(sqlite3.connect(target / business.path.name)) as copied:
            source.backup(copied)
        with self.assertRaisesRegex(ValueError, "产品版本"):
            Store(target)
        for store, version in ((business, 9), (personal, 10)):
            self.assertEqual(store.one("PRAGMA user_version")["user_version"], version)
            self.assertEqual(store.one("PRAGMA integrity_check")["integrity_check"], "ok")
            self.assertEqual(store.rows("PRAGMA foreign_key_check"), [])

    def test_platform_runtime_rejects_outside_owner_boundary(self):
        shared = self.root / "shared"
        if os.name == "nt":
            profile = self.root / "separate-local-profile"
            profile.mkdir()
            with patch.dict(os.environ, {"LOCALAPPDATA": str(profile)}), self.assertRaisesRegex(ValueError, "LOCALAPPDATA"):
                Store(shared, edition=Edition.PERSONAL)
            self.assertFalse(shared.exists())
        else:
            shared.mkdir()
            shared.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "仅限该用户"):
                Store(shared, edition=Edition.PERSONAL)


if __name__ == "__main__":
    unittest.main()
