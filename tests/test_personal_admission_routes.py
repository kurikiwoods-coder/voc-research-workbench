"""Trusted HTTP and ledger integration for Personal acceptance batch controls."""

from base64 import b64encode
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from src.dashboard.personal_governance import governance_decision
from src.dashboard.personal_workspace import provision
from src.edition_policy import Deployment, Domain, Edition, LocalOwner, Permission
from src.raw_store.personal_validation import BatchContext, Budget, OperationGrant, ValidationLedger
from test_edition_policy import fixture_root, owner_environment
from test_imports import HEADERS, ORIGIN


SYNTHETIC_REVISION = "local:private-fixture-credential-revision"
SYNTHETIC_PAYLOAD = "17" * 32
LIMIT = 2**63 - 1


class PersonalAdmissionRouteTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(fixture_root("voc-personal-admission-http-")))
        self.directory = root / "personal"
        self.scope = provision(self.directory, "合成验收项目", "合成验收研究问题", uuid4())
        self.other = provision(self.directory, "第二合成验收项目", "第二个合成问题", uuid4())
        self.environment, self.proof = owner_environment(self.scope)
        self.endpoint = f"/api/personal/pre-admission/{self.scope['study_id']}"
        self.target = {key: self.scope[key] for key in ("scope_id", "scope_version")}
        self.now = datetime.now(UTC)
        self.start = (self.now - timedelta(minutes=5)).isoformat()
        self.end = (self.now + timedelta(hours=1)).isoformat()
        self.budget = Budget(3, 2, 0, 0, 0, LIMIT)
        transport = self.enterContext(patch(
            "src.execution.transport.build_opener", side_effect=AssertionError("Unexpected supplier HTTP"),
        ))
        self.addCleanup(transport.assert_not_called)

    def connect(self, *, environment=None, edition=Edition.PERSONAL, deployment=Deployment.LOCAL,
                authenticated=True, client_host="127.0.0.1"):
        owner = None
        if edition == Edition.PERSONAL and deployment == Deployment.LOCAL:
            owner = LocalOwner.from_environment(environment or self.environment)
        settings = Settings(self.directory if owner else self.directory.parent / "business",
                            edition=edition, deployment=deployment, personal_owner=owner)
        app = create_app(settings)
        headers = HEADERS.copy()
        if authenticated:
            headers["Authorization"] = "Basic " + b64encode(f"owner:{self.proof}".encode()).decode()
        client = TestClient(app, base_url=ORIGIN, client=(client_host, 29204), headers=headers)
        return self.enterContext(client), app

    def ledger_context(self, app, scope=None):
        scope = self.scope if scope is None else scope
        policy = app.state.edition_policy
        decision = policy.decide(Permission.READ_PERSONAL_APPROVALS, Domain.LOCAL_WORKSPACE,
                                 study_id=scope["study_id"], proof=self.proof, current_scope=lambda _: True)
        self.assertTrue(decision.allowed)
        decision = governance_decision(decision, policy.owner)
        return BatchContext(decision.scope.study_id, decision.scope.scope_id, decision.scope.scope_version,
                            decision.actor_ref, decision.owner_ref, decision.evidence_refs[0], decision.policy_version)

    @staticmethod
    def allow(db, batch, grant):
        return True

    def draft(self, app, scope=None):
        ledger = ValidationLedger(app.state.store, engineering_fixture=True)
        context = self.ledger_context(app, scope)
        batch = ledger.draft(context, self.start, self.end, self.budget, "USD", 6, LIMIT, "local:fixture",
                             self.allow)
        return ledger, context, batch["batch_id"]

    def post(self, client, batch_id, action, body=None, **kwargs):
        return client.post(f"{self.endpoint}/{batch_id}/{action}", json=self.target if body is None else body,
                           **kwargs)

    def test_projection_preserves_budget_integer_and_hides_immutable_secrets(self):
        client, app = self.connect()
        ledger, context, batch_id = self.draft(app)
        ledger.bind_credential(context, "search", "tavily", "fixture-account", "fixture-channel",
                               SYNTHETIC_REVISION, "local:fixture-anchor", self.allow)
        grant = OperationGrant(
            "search", "tavily", "fixture-account", "fixture-channel", SYNTHETIC_REVISION, "", None,
            "local:risk", "local:source", "18" * 32, SYNTHETIC_PAYLOAD, "", self.start, self.end,
            self.budget, "local:fixture-approval",
        )
        authorized = ledger.authorize(batch_id, context, grant, self.allow)
        request = ledger.reserve(batch_id, context, authorized["grant_id"], 1, SYNTHETIC_PAYLOAD,
                                 Budget(1, 1, 0, 0, 0, 2**53 + 1), self.allow)
        ledger.add_evidence(batch_id, context, "C0-1", "synthetic_fixture", "local:fixture-review",
                            "19" * 32, "local:private-review-detail", self.allow)
        response = client.get(self.endpoint, params=self.target)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        summary = response.json()
        self.assertEqual((summary["mode"], summary["formal_gate"]), ("synthetic_only", "NOT_EVALUATED"))
        item, = summary["batches"]
        self.assertEqual(item["batch_id"], batch_id)
        self.assertEqual(item["status"], "approved")
        self.assertEqual(item["reason"], "operation_authorized")
        self.assertTrue(item["can_pause"])
        self.assertTrue(item["can_revoke"])
        self.assertEqual((item["budget"]["units"], item["used"]["units"]), (str(LIMIT), str(2**53 + 1)))
        self.assertEqual(item["authorizations"], [{
            "grant_id": authorized["grant_id"], "operation": "search", "provider": "tavily",
            "channel_ref": "fixture-channel", "account_ref": "fixture-account",
            "status": "requires_execution_recheck", "credential_current": True,
        }])
        self.assertEqual(item["requests"], [{
            "request_id": request["request_id"], "operation": "search", "status": "reserved",
            "reconciliation_status": "not_applicable", "estimated_units": str(2**53 + 1), "actual_units": None,
        }])
        self.assertEqual(item["evidence"], [{
            "check_id": "C0-1", "kind": "synthetic_fixture", "evidence_ref": "local:fixture-review",
            "status": "ENGINEERING_EVIDENCE",
        }])
        for private in (SYNTHETIC_REVISION, SYNTHETIC_PAYLOAD, "local:private-review-detail", self.proof,
                        "local:fixture-approval", "local:fixture-anchor", "19" * 32):
            with self.subTest(private_type=type(private)):
                self.assertNotIn(private, response.text)
        ledger.bind_credential(context, "search", "tavily", "fixture-account", "fixture-channel",
                               "local:rotated-fixture-anchor", "local:fixture-anchor", self.allow)
        authorization, = client.get(self.endpoint, params=self.target).json()["batches"][0]["authorizations"]
        self.assertEqual((authorization["credential_current"], authorization["status"]), (False, "inactive"))

    def test_stop_actions_use_the_acceptance_batch_and_preserve_append_only_history(self):
        client, app = self.connect()
        _, _, batch_id = self.draft(app)
        for action, expected in (("pause", "paused"), ("pause", "paused"), ("revoke", "revoked"),
                                 ("revoke", "revoked")):
            with self.subTest(action=action, expected=expected):
                response = self.post(client, batch_id, action)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), {"batch_id": batch_id, "status": expected})
        self.assertEqual(self.post(client, batch_id, "pause").status_code, 409)
        latest, = client.get(self.endpoint, params=self.target).json()["batches"]
        self.assertEqual((latest["status"], latest["reason"]), ("revoked", "owner_revoked"))
        self.assertFalse(latest["can_pause"])
        self.assertFalse(latest["can_revoke"])
        with app.state.store.db() as db:
            states = db.execute("SELECT state FROM personal_validation_batch_events WHERE batch_id=? ORDER BY sequence",
                                (batch_id,))
            self.assertEqual([row["state"] for row in states], ["draft", "paused", "revoked"])

    def test_scope_permissions_same_origin_and_request_redaction(self):
        client, app = self.connect()
        _, _, batch_id = self.draft(app)
        self.assertEqual(client.get(self.endpoint, params=self.target | {"scope_version": "v99"}).status_code, 404)
        self.assertEqual(client.get(self.endpoint, params=[*self.target.items(), ("scope_version", "v99")]).status_code, 422)
        self.assertEqual(self.post(client, batch_id, "pause", self.target | {"scope_id": str(uuid4())}).status_code, 404)
        self.assertEqual(self.post(client, uuid4(), "pause").status_code, 404)
        denied = client.get(f"/api/personal/pre-admission/{self.other['study_id']}", params=self.target)
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn(self.other["study_id"], denied.text)
        auth_denied = client.get(self.endpoint, params=self.target, headers={"X-VOC-Owner": self.proof})
        self.assertEqual(auth_denied.status_code, 403)
        self.assertNotIn(self.proof, auth_denied.text)
        malformed = self.post(client, batch_id, "pause", self.target | {"credential_revision": SYNTHETIC_REVISION})
        self.assertEqual(malformed.status_code, 422)
        self.assertNotIn(SYNTHETIC_REVISION, malformed.text)
        cross_origin = self.post(client, batch_id, "pause", headers={"Origin": "http://untrusted.invalid"})
        self.assertEqual(cross_origin.status_code, 403)
        unauthenticated, _ = self.connect(authenticated=False)
        self.assertEqual(unauthenticated.get(self.endpoint, params=self.target).status_code, 401)
        nonlocal_client, _ = self.connect(client_host="192.0.2.20")
        self.assertEqual(nonlocal_client.get(self.endpoint, params=self.target).status_code, 403)

    def test_write_permission_and_recheck_before_commit(self):
        client, app = self.connect()
        _, _, batch_id = self.draft(app)
        reader_env, _ = owner_environment(self.scope, self.proof, permissions=[Permission.READ_PERSONAL_APPROVALS])
        reader, reader_app = self.connect(environment=reader_env)
        _, _, reader_batch_id = self.draft(reader_app)
        item, = reader.get(self.endpoint, params=self.target).json()["batches"]
        self.assertEqual(item["batch_id"], reader_batch_id)
        self.assertFalse(item["can_pause"])
        self.assertFalse(item["can_revoke"])
        malformed = reader.post(f"{self.endpoint}/{reader_batch_id}/pause", content='{"synthetic-invalid-json"')
        self.assertEqual(malformed.status_code, 403)

        original = app.state.edition_policy
        grant = original.owner.grants[0]
        changed = replace(original, owner=replace(original.owner, grants=(
            replace(grant, expires_at=grant.expires_at + timedelta(minutes=1)),
        )))
        append = ValidationLedger._batch_event

        def change_exact_authorization_after_append(ledger, db, batch, state, reason):
            append(ledger, db, batch, state, reason)
            app.state.edition_policy = changed

        try:
            with patch.object(ValidationLedger, "_batch_event", change_exact_authorization_after_append):
                self.assertEqual(self.post(client, batch_id, "pause").status_code, 403)
        finally:
            app.state.edition_policy = original
        batch, = client.get(self.endpoint, params=self.target).json()["batches"]
        self.assertEqual(batch["status"], "draft")

    def test_business_and_cloud_reject_before_body_validation(self):
        for edition, deployment in ((Edition.BUSINESS, Deployment.LOCAL), (Edition.BUSINESS, Deployment.CLOUD),
                                    (Edition.PERSONAL, Deployment.CLOUD)):
            with self.subTest(edition=edition, deployment=deployment):
                client, _ = self.connect(edition=edition, deployment=deployment)
                self.assertEqual(client.get(self.endpoint, params=self.target).status_code, 403)
                response = client.post(self.endpoint + "/invalid-id/revoke", content='{"synthetic-invalid-json"')
                self.assertEqual(response.status_code, 403)
