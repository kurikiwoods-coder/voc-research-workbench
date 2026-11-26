"""Run Personal governance requests against isolated synthetic workspaces."""

from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard import personal_governance
from src.dashboard.app import create_app
from src.dashboard.edition_access import has_scope
from src.dashboard.personal_workspace import provision
from src.dashboard.study_api import ProjectInput
from src.edition_policy import Deployment, Domain, Edition, LocalOwner, Permission
from src.raw_store.credentials import VaultError
from src.raw_store.personal_approval_evidence import REGISTRY_NAME, REQUIRED_EVIDENCE
from src.raw_store.personal_credentials import PersonalCredentials
from src.raw_store.personal_validation import BatchContext
from src.raw_store.personal_validation_credentials import put_validation_credential, validation_binding
from src.raw_store.studies import StudyStore
from test_edition_policy import fixture_root, owner_environment
from test_imports import HEADERS, ORIGIN
from test_personal_credentials import BINDING, FIRST, ROTATED, synthetic_protection


class PersonalGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(fixture_root("voc-personal-governance-"))) / "personal"
        self.scope = provision(self.directory, "合成审批项目", "合成研究问题", uuid4())
        self.environment, self.proof = owner_environment(self.scope)
        self.approvals = self.governance(self.scope) + "/approvals"
        self.credential = self.governance(self.scope) + "/credential"
        self.identity = dict(zip(("provider", "channel_ref", "account_ref"), BINDING))
        self.model = "jev-1.14.0"
        self.now = datetime.now(UTC)
        self.expiry = self.now + timedelta(hours=4)
        self.enterContext(patch("src.raw_store.personal_credentials._protect", synthetic_protection))
        transport = self.enterContext(patch(
            "src.execution.transport.build_opener", side_effect=AssertionError("Unexpected supplier HTTP"),
        ))
        self.addCleanup(transport.assert_not_called)

    @staticmethod
    def governance(scope):
        return f"/api/personal/governance/{scope['study_id']}"

    def open_client(self, *, environment=None, settings=None, auth=True):
        if settings is None:
            settings = Settings(
                self.directory, edition=Edition.PERSONAL,
                personal_owner=LocalOwner.from_environment(environment or self.environment),
            )
        app = create_app(settings)
        headers = dict(HEADERS)
        if auth:
            headers["Authorization"] = "Basic " + b64encode(f"owner:{self.proof}".encode()).decode()
        return TestClient(
            app, base_url=ORIGIN, client=("127.0.0.1", 29204), headers=headers,
        ), app

    def check_response(self, response, status, detail=None):
        for private in (FIRST, ROTATED, self.proof):
            self.assertFalse(private in response.text, "Response disclosed a synthetic credential marker")
        self.assertEqual(response.status_code, status, response.text)
        body = response.json()
        if detail is not None:
            self.assertEqual(body, {"detail": detail})
        return body

    def configure(self, client, key=FIRST, *, scope=None):
        scope = scope or self.scope
        configured = self.check_response(client.put(
            self.governance(scope) + "/credential", json=self.identity | {"api_key": key},
        ), 200)
        self.assertEqual(configured, self.identity | {"configured": True})
        with client.app.state.store.db() as db:
            anchor = db.execute(
                "SELECT credential_revision FROM personal_credential_binding WHERE study_id=? AND scope_id=?",
                (scope["study_id"], scope["scope_id"]),
            ).fetchone()
        self.assertIsNotNone(anchor)
        revision = anchor["credential_revision"]
        self.assertEqual(self.vault(scope).read(revision)["credential_revision"], revision)
        return revision

    def vault(self, scope):
        return PersonalCredentials(self.directory, study_id=scope["study_id"], scope_id=scope["scope_id"])

    def development_evidence(self, revision, scope=None):
        scope = scope or self.scope
        return [
            {field: scope[field] for field in ("study_id", "scope_id", "scope_version")}
            | self.identity | {
                "purpose": "personal_research", "model": self.model, "credential_revision": revision,
                "evidence_ref": f"local:synthetic-evidence-{index}", "kind": kind,
                "status": "VERIFIED", "sha256": sha256(kind.encode()).hexdigest(), "terms_version": "fixture-1",
                "verified_at": (self.now - timedelta(hours=1)).isoformat(),
                "expires_at": (self.now + timedelta(hours=8)).isoformat(),
                "budget_unit": "TOKENS", "budget_limit": 1000,
            }
            for index, kind in enumerate(REQUIRED_EVIDENCE)
        ]

    def write_evidence(self, records):
        path = self.directory / REGISTRY_NAME
        path.write_text(json.dumps(records), encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o600)

    def application(self, records, **updates):
        return self.identity | {
            "model": self.model, "expires_at": self.expiry.isoformat(), "budget_unit": "TOKENS",
            "budget_limit": 100, "evidence_refs": [row["evidence_ref"] for row in records],
            "risks": [], "request_key": str(uuid4()),
        } | updates

    def submit(self, client, records, **updates):
        return self.check_response(client.post(self.approvals, json=self.application(records, **updates)), 201)

    @staticmethod
    def transition(client, approvals, event, action, request_key=None):
        return client.post(
            f"{approvals}/{event['event_id']}/{action}",
            json={"request_key": request_key or str(uuid4())},
        )

    def approve(self, client, pending):
        return self.check_response(self.transition(client, self.approvals, pending, "approve"), 201)

    def status(self, client):
        return self.check_response(client.get(self.approvals), 200)

    def test_active_governance_preserves_both_gates_and_no_provider_dispatch(self):
        client, _ = self.open_client()
        with client:
            revision = self.configure(client)
            records = self.development_evidence(revision)
            self.write_evidence(records)
            pending = self.submit(client, records, risks=[{
                "kind": "ENTERPRISE_DPA", "reason": "Synthetic optional item is unavailable.",
                "impact": "This fixture exercises approval only.",
                "safeguards": "Use isolated workspace and no supplier dispatch.",
                "responsible_ref": "project-owner", "review_basis": "local:synthetic-risk-review",
                "expires_at": self.expiry.isoformat(),
            }])
            self.assertEqual((pending["status"], pending["reasons"]), ("PENDING", []))
            self.assertFalse(self.status(client)["readiness"]["ready"])
            active = self.approve(client, pending)
            self.assertEqual((active["status"], active["reasons"]), ("ACTIVE", []))
            self.assertEqual(active["scope_id"], self.scope["scope_id"])
            self.assertEqual(active["scope_version"], self.scope["scope_version"])
            self.assertEqual((active["budget_unit"], active["budget_limit"]), ("TOKENS", 100))

            status = self.status(client)
            self.assertEqual(status["readiness"], {"ready": True, "reasons": []})
            self.assertEqual([item["status"] for item in status["approvals"]], ["ACTIVE", "SUPERSEDED"])
            self.assertNotIn(revision, json.dumps(status))
            self.assertEqual({row["kind"] for row in status["evidence"]}, set(REQUIRED_EVIDENCE))

            edition = self.check_response(client.get("/api/edition"), 200)
            self.assertEqual(edition["gates"]["business"]["status"], "BLOCKED")
            self.assertEqual(edition["gates"]["personal"]["status"], "NOT_EVALUATED")
            self.assertFalse(edition["operations"]["personal_pre_admission"])
            self.assertFalse(edition["operations"]["personal_formal_research"])
            for url in ("/api/runs", "/api/setup/packycode/diagnostics"):
                self.check_response(client.post(url, json={"request_key": str(uuid4())}), 403)

    def test_missing_evidence_and_unverified_evidence_cannot_approve(self):
        client, _ = self.open_client()
        with client:
            records = self.development_evidence(self.configure(client))
            missing = records[:-1]
            self.write_evidence(missing)
            pending = self.submit(client, missing)
            self.assertIn("MISSING_PROJECT_AUTHORIZATION", pending["reasons"])
            self.check_response(self.transition(client, self.approvals, pending, "approve"),
                                409, "MISSING_PROJECT_AUTHORIZATION")

            for state in ("UNKNOWN", "REVOKED", "PROHIBITED"):
                with self.subTest(state=state):
                    check = [records[0] | {"status": state}, *records[1:]]
                    self.write_evidence(check)
                    pending = self.submit(client, check)
                    reason = "PURPOSE_PROHIBITED" if state == "PROHIBITED" else "EVIDENCE_NOT_CURRENT"
                    self.assertEqual(pending["reasons"], [reason])
                    self.check_response(self.transition(client, self.approvals, pending, "approve"), 409, reason)

            unknown = self.application(records, evidence_refs=["local:never-verified"])
            self.check_response(client.post(self.approvals, json=unknown), 409, "EVIDENCE_NOT_CURRENT")
            self.assertFalse(self.status(client)["readiness"]["ready"])

    def test_prohibition_and_mandatory_risks_cannot_be_bypassed(self):
        client, _ = self.open_client()
        with client:
            records = self.development_evidence(self.configure(client))
            prohibited = records[0] | {"evidence_ref": "local:prohibited", "status": "PROHIBITED"}
            self.write_evidence([*records, prohibited])
            pending = self.submit(client, records)
            self.check_response(self.transition(client, self.approvals, pending, "approve"),
                                409, "PURPOSE_PROHIBITED")

            required_risk = [records[0] | {"mandatory_risks": ["ZDR"]}, *records[1:]]
            self.write_evidence(required_risk)
            pending = self.submit(client, required_risk, risks=[{
                "kind": "ZDR", "reason": "Synthetic optional unknown claim.",
                "impact": "This fixture exercises approval only.", "safeguards": "Isolate all synthetic data.",
                "responsible_ref": "project-owner", "review_basis": "local:synthetic-risk-review",
                "expires_at": self.expiry.isoformat(),
            }])
            self.check_response(self.transition(client, self.approvals, pending, "approve"),
                                409, "MANDATORY_RISK_REQUIRES_EVIDENCE")

    def test_budget_and_expiration_are_enforced(self):
        client, _ = self.open_client()
        with client:
            records = self.development_evidence(self.configure(client))
            self.write_evidence(records)
            self.check_response(client.post(
                self.approvals, json=self.application(records, budget_limit=0),
            ), 422, "INVALID_APPROVAL_REQUEST")
            pending = self.submit(client, records, budget_limit=1001)
            self.check_response(self.transition(client, self.approvals, pending, "approve"),
                                409, "BUDGET_OUTSIDE_VERIFIED_LIMIT")
            expired = self.application(records, expires_at=(self.now - timedelta(seconds=1)).isoformat())
            self.check_response(client.post(self.approvals, json=expired), 409, "APPROVAL_EXPIRED")

            short_lived = [records[0] | {"expires_at": (self.now + timedelta(hours=1)).isoformat()},
                           *records[1:]]
            self.write_evidence(short_lived)
            pending = self.submit(client, short_lived)
            self.check_response(self.transition(client, self.approvals, pending, "approve"),
                                409, "EVIDENCE_NOT_CURRENT")

            self.write_evidence(records)
            active = self.approve(client, self.submit(client, records, budget_limit=1000))
            with patch.object(personal_governance, "datetime", wraps=datetime) as clock:
                clock.now.return_value = self.expiry
                status = self.status(client)
            expired = next(item for item in status["approvals"] if item["event_id"] == active["event_id"])
            self.assertEqual((expired["status"], expired["reasons"]), ("EXPIRED", ["APPROVAL_EXPIRED"]))
            self.assertFalse(status["readiness"]["ready"])

    def test_changed_evidence_invalidates_active_approval(self):
        client, _ = self.open_client()
        with client:
            records = self.development_evidence(self.configure(client))
            self.write_evidence(records)
            self.approve(client, self.submit(client, records))
            changed = [records[0] | {"sha256": "c" * 64}, *records[1:]]
            self.write_evidence(changed)
            invalid = self.status(client)["approvals"][0]
            self.assertEqual((invalid["status"], invalid["reasons"]), ("INVALIDATED", ["EVIDENCE_CHANGED"]))

    def test_revocation_rotation_and_deletion(self):
        client, _ = self.open_client()
        with client:
            first_revision = self.configure(client)
            records = self.development_evidence(first_revision)
            self.write_evidence(records)
            active = self.approve(client, self.submit(client, records))
            revoked = self.check_response(self.transition(client, self.approvals, active, "revoke"), 201)
            self.assertEqual(revoked["status"], "REVOKED")
            self.assertEqual([event["status"] for event in self.status(client)["approvals"]],
                             ["REVOKED", "REVOKED", "SUPERSEDED"])
            self.check_response(self.transition(client, self.approvals, active, "revoke"),
                                409, "EVENT_VERSION_CHANGED")

            active = self.approve(client, self.submit(client, records))
            rotated = self.configure(client, ROTATED)
            self.assertNotEqual(first_revision, rotated)
            invalid = self.status(client)["approvals"][0]
            self.assertEqual((invalid["status"], invalid["reasons"]), ("INVALIDATED", ["CREDENTIAL_CHANGED"]))
            self.check_response(client.post(self.approvals, json=self.application(records)),
                                409, "EVIDENCE_NOT_CURRENT")

            records = self.development_evidence(rotated)
            self.write_evidence(records)
            pending = self.submit(client, records)
            self.check_response(self.transition(client, self.approvals, pending, "approve"),
                                409, "REVOKE_PRIOR_APPROVAL_FIRST")
            self.check_response(self.transition(client, self.approvals, active, "revoke"), 201)
            self.approve(client, pending)
            deleted = self.check_response(client.delete(self.credential), 200)
            self.assertEqual(deleted, {"configured": False, **dict.fromkeys(self.identity)})
            status = self.status(client)
            self.assertFalse(status["readiness"]["ready"])
            invalid = status["approvals"][0]
            self.assertEqual((invalid["status"], invalid["reasons"]), ("INVALIDATED", ["CREDENTIAL_CHANGED"]))

    def test_c_cleanup_503_preserves_new_anchor_and_blocks_d_replay(self):
        self.identity["channel_ref"] = "typesafe-officially"
        client, app = self.open_client()
        with client:
            first = self.configure(client)
            records = self.development_evidence(first)
            self.write_evidence(records)
            active = self.approve(client, self.submit(client, records))
            policy = app.state.edition_policy
            store = app.state.store

            def authorize(db):
                return policy.decide(
                    Permission.MANAGE_PERSONAL_CREDENTIALS, Domain.LOCAL_WORKSPACE, proof=self.proof,
                    study_id=self.scope["study_id"], current_scope=lambda scope: has_scope(db, scope),
                )

            with store.db() as db:
                decision = authorize(db)
            context = BatchContext(
                decision.scope.study_id, decision.scope.scope_id, decision.scope.scope_version, decision.actor_ref,
                decision.owner_ref, decision.evidence_refs[0], decision.policy_version,
            )
            grant = put_validation_credential(
                store, authorize=authorize, operation="model", **self.identity,
                api_key=None, evidence_ref="local:fixture-model-binding",
            )
            with store.db() as db:
                self.assertEqual(validation_binding(store, db, context, grant), FIRST)
            retained = self.vault(self.scope)._revision_path(first)
            with patch.object(PersonalCredentials, "discard_unbound", side_effect=OSError):
                self.check_response(
                    client.put(self.credential, json=self.identity | {"api_key": ROTATED}),
                    503, "PERSONAL_CREDENTIAL_CLEANUP_UNAVAILABLE",
                )
            self.assertTrue(retained.exists())
            invalid = self.status(client)["approvals"][0]
            self.assertEqual((invalid["event_id"], invalid["status"], invalid["reasons"]),
                             (active["event_id"], "INVALIDATED", ["CREDENTIAL_CHANGED"]))
            self.check_response(client.post(self.approvals, json=self.application(records)),
                                409, "EVIDENCE_NOT_CURRENT")
            with store.db() as db:
                self.assertNotEqual(personal_governance.binding_revision(db, decision), first)
                with self.assertRaises(VaultError):
                    validation_binding(store, db, context, grant)
                for table in ("runs", "shards", "personal_validation_requests"):
                    self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_concurrent_retries_and_competing_decisions_append_one_event(self):
        client, app = self.open_client()
        with client, ThreadPoolExecutor(max_workers=2) as requests:
            records = self.development_evidence(self.configure(client))
            self.write_evidence(records)
            body = self.application(records)

            def race(*operations):
                barrier = Barrier(len(operations))

                def request(operation):
                    barrier.wait(timeout=5)
                    return operation()

                futures = [requests.submit(request, operation) for operation in operations]
                return [future.result(timeout=15) for future in futures]

            def submit_request():
                return client.post(self.approvals, json=body)

            replies = race(submit_request, submit_request)
            pending, duplicate = (self.check_response(reply, 201) for reply in replies)
            self.assertEqual(pending["event_id"], duplicate["event_id"])
            self.check_response(client.post(self.approvals, json=body | {"budget_limit": 101}),
                                409, "IDEMPOTENCY_CONFLICT")

            keys = ("local:approve-first", "local:approve-second")
            replies = race(*(lambda key=key: self.transition(client, self.approvals, pending, "approve", key)
                             for key in keys))
            self.assertEqual(sorted(reply.status_code for reply in replies), [201, 409])
            for key, reply in zip(keys, replies):
                if reply.status_code == 201:
                    approved = self.check_response(reply, 201)
                    replay = self.check_response(self.transition(client, self.approvals, pending, "approve", key), 201)
                    self.assertEqual(approved["event_id"], replay["event_id"])
                else:
                    self.check_response(reply, 409, "EVENT_VERSION_CHANGED")
            competing = self.submit(client, records)
            self.check_response(self.transition(client, self.approvals, competing, "approve"),
                                409, "REVOKE_PRIOR_APPROVAL_FIRST")
            with app.state.store.db() as db:
                kinds = db.execute("SELECT kind FROM personal_provider_approval_events ORDER BY rowid")
                self.assertEqual([row["kind"] for row in kinds], ["submitted", "approved", "submitted"])

    def test_event_and_credential_changes_require_valid_authorization_at_commit(self):
        client, app = self.open_client()
        with client:
            revision = self.configure(client)
            records = self.development_evidence(revision)
            self.write_evidence(records)
            body = self.application(records)
            policy = app.state.edition_policy
            revoked, _ = owner_environment(None, self.proof)
            revoked_policy = replace(policy, owner=LocalOwner.from_environment(revoked))
            write_event = personal_governance.write_event

            def write_after_revocation(*args, **kwargs):
                result = write_event(*args, **kwargs)
                app.state.edition_policy = revoked_policy
                return result

            try:
                with patch.object(personal_governance, "write_event", side_effect=write_after_revocation):
                    self.check_response(client.post(self.approvals, json=body), 403)
            finally:
                app.state.edition_policy = policy
            self.assertEqual(self.status(client)["approvals"], [])
            self.check_response(client.post(self.approvals, json=body), 201)

            def protect_after_revocation(data, *, encrypt):
                if encrypt:
                    app.state.edition_policy = revoked_policy
                return synthetic_protection(data, encrypt=encrypt)

            try:
                with patch("src.raw_store.personal_credentials._protect", protect_after_revocation):
                    self.check_response(client.put(
                        self.credential, json=self.identity | {"api_key": ROTATED},
                    ), 403)
            finally:
                app.state.edition_policy = policy
            self.assertIs(self.status(client)["credential"]["configured"], True)
            self.assertEqual(self.status(client)["approvals"][0]["reasons"], [])

    def test_project_and_frozen_scope_isolate_events_and_credentials(self):
        other = provision(self.directory, "第二合成治理项目", "另一个合成研究问题", uuid4())
        client, app = self.open_client()
        with client:
            records = self.development_evidence(self.configure(client))
            self.write_evidence(records)
            pending = self.submit(client, records, request_key="local:scoped-request")
            other_api = self.governance(other) + "/approvals"
            denial = client.get(other_api)
            self.check_response(denial, 404)
            self.assertNotIn(other["study_id"], denial.text)

            other_env, _ = owner_environment(other, self.proof)
            with self.open_client(environment=other_env)[0] as other_client:
                status = self.check_response(other_client.get(other_api), 200)
                self.assertEqual((status["approvals"], status["evidence"]), ([], []))
                self.assertIs(status["credential"]["configured"], False)
                self.check_response(self.transition(other_client, other_api, pending, "approve"), 404)

            studies = StudyStore(app.state.store)
            form = ProjectInput(name="合成审批项目", scope={"mode": "open", "topic": "新范围"})
            current = studies.get(self.scope["study_id"])
            updated = studies.update(self.scope["study_id"], current["revision"], form.metadata(),
                                     form.snapshot(), form.change_note)
            new_scope = studies.freeze(self.scope["study_id"], updated["scope"]["scope_id"])["scope"]
            self.assertNotEqual(new_scope["scope_version"], self.scope["scope_version"])
            new_env, _ = owner_environment(new_scope, self.proof)
            with self.open_client(environment=new_env)[0] as new_scope_client:
                status = self.status(new_scope_client)
                self.assertEqual((status["approvals"], status["evidence"]), ([], []))
                self.assertIs(status["credential"]["configured"], False)
                self.check_response(self.transition(new_scope_client, self.approvals, pending, "approve"), 404)
                new_revision = self.configure(new_scope_client, scope=new_scope)
                new_records = self.development_evidence(new_revision, new_scope)
                self.write_evidence([*records, *new_records])
                new_pending = self.submit(new_scope_client, new_records, request_key="local:scoped-request")
                self.assertNotEqual(new_pending["event_id"], pending["event_id"])
            self.assertEqual(self.status(client)["approvals"][0]["event_id"], pending["event_id"])

    def test_denied_editions_permissions_and_forged_identity_hide_credentials(self):
        client, _ = self.open_client(auth=False)
        with client:
            self.check_response(client.get(self.approvals), 401)
            self.check_response(client.get(self.approvals, auth=("owner", "forged-proof")), 401)
            self.check_response(client.get(self.approvals, headers={"X-VOC-Owner": "project-owner"}), 403)
            self.check_response(client.put(self.credential, json=self.identity | {"api_key": FIRST}), 401)

        environment, _ = owner_environment(self.scope, self.proof, permissions=[Permission.READ_PERSONAL_APPROVALS])
        with self.open_client(environment=environment)[0] as reader:
            self.check_response(reader.get(self.approvals), 200)
            self.check_response(reader.post(self.approvals, json=self.application([])), 403)
            self.check_response(reader.put(self.credential, json=self.identity | {"api_key": FIRST}), 403)
            self.check_response(reader.delete(self.credential), 403)

        with self.open_client()[0] as owner:
            self.check_response(owner.put(self.credential, json=[FIRST]), 422, "INVALID_GOVERNANCE_REQUEST")
            self.check_response(owner.put(self.credential, json=self.identity | {
                "api_key": FIRST, "owner_ref": FIRST,
            }), 422, "INVALID_CREDENTIAL_REQUEST")
            self.check_response(owner.post(self.approvals, content=f'{{"api_key":"{FIRST}"'),
                                422, "INVALID_GOVERNANCE_REQUEST")
            self.check_response(owner.post(self.approvals, json=self.application([]) | {"api_key": FIRST}),
                                422, "INVALID_APPROVAL_REQUEST")

        for edition, deployment in ((Edition.BUSINESS, Deployment.LOCAL),
                                    (Edition.BUSINESS, Deployment.CLOUD), (Edition.PERSONAL, Deployment.CLOUD)):
            with self.subTest(edition=edition, deployment=deployment):
                directory = self.directory.parent / f"{edition}-{deployment}"
                settings = Settings(directory, edition=edition, deployment=deployment)
                isolated, app = self.open_client(settings=settings)
                with isolated:
                    self.check_response(isolated.get(self.approvals), 403)
                    self.check_response(isolated.post(self.approvals, json=self.application([])), 403)
                    self.check_response(isolated.put(self.credential, json=[FIRST]), 403)
                    self.check_response(isolated.delete(self.credential), 403)
                    self.assertFalse(hasattr(app.state, "personal_credentials"))
                    if deployment == Deployment.CLOUD:
                        self.assertFalse(directory.exists())
