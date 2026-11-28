from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from threading import Barrier
import unittest
from unittest.mock import patch
from urllib.error import URLError

from test_personal_admission import OPTIONS, QUOTE, SEARCH, URL
from test_personal_credentials import synthetic_protection
import test_personal_governance
from test_personal_live_evidence import FormalMatrixTests, _answers
from test_personal_live_transport import BUILD_OPENER, Reply

from src.config import MODEL
from src.dashboard.edition_access import has_scope
from src.edition_policy import Domain, Permission
from src.execution.personal_admission import digest, model_payloads, search_payload
from src.execution.personal_live_admission import LiveAdmission, MATERIAL
from src.execution.transport import ENDPOINTS
from src.ingestion.public_source import DOMAIN
from src.raw_store.credentials import VaultError
from src.raw_store.personal_live_authority import AuthorityError
from src.raw_store.personal_validation import Budget, ValidationLedger
from src.raw_store.personal_validation_credentials import put_validation_credential
from src.raw_store.store import Conflict


BATCH_BUDGET = Budget(4, 1, 1600, 800, 2400, 100)
SHARED_ACCOUNT_BUDGET = Budget(4, 4, 1600, 800, 2400, 100)
MODEL_ACCOUNT_BUDGET = Budget(2, 0, 1600, 800, 2400, 80)
LIMITS = {"search": Budget(1, 1, 0, 0, 0, 20), "source": Budget(1, 0, 0, 0, 0, 0),
          "model": Budget(1, 0, 800, 400, 1200, 40)}
MODEL_FIELDS = {"choices": [[key, value] for key, value in OPTIONS.items()], "text": QUOTE,
                "model_input_sha256": digest(QUOTE)}
V2_TEXT = "The synthetic label explains how to measure the syrup."
V2_USAGE = {1: (120, 60), 2: (90, 30)}


class PersonalLiveAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_personal_governance.PersonalGovernanceTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.identity["channel_ref"] = "typesafe-officially"
        self.client, app = self.fixture.open_client()
        self.enterContext(self.client)
        self.store = app.state.store
        self.policy = app.state.edition_policy
        self.enterContext(patch("src.raw_store.personal_live_authority._protect", synthetic_protection))
        self.opener = self.enterContext(patch(BUILD_OPENER)).return_value.open
        self.opener.side_effect = self.reply
        self.authority_path = self.fixture.directory.parent / "authority"
        self.authority_path.mkdir(mode=0o700)
        self.engine = self.open_engine()
        self.context = self.engine.context
        self.deployment = {
            **{field: getattr(self.context, field) for field in ("owner_ref", "study_id", "scope_id", "scope_version")},
            "evidence_ref": "fixture-deployment-approval",
        }
        self.engine.provision(self.deployment)
        now = datetime.now(UTC)
        self.start, self.expiry = (now - timedelta(minutes=1)).isoformat(), (now + timedelta(minutes=30)).isoformat()
        self.bindings = {
            operation: put_validation_credential(
                self.store, authorize=self.credential_permission, operation=operation, provider=provider,
                channel_ref=channel, account_ref=account, api_key=key, evidence_ref="fixture-binding",
            )
            for operation, provider, channel, account, key in (
                ("search", "tavily", "basic", "fixture-tavily-account", "fixture-tavily-credential"),
                ("source", "stackexchange", "public-api", "fixture-source-account", None),
            )
        }
        self.batch = self.draft_batch()

    def batch_packet(self, evidence_ref="fixture-batch-approval"):
        return {
            **{field: getattr(self.context, field) for field in ("owner_ref", "study_id", "scope_id", "scope_version")},
            "starts_at": self.start, "expires_at": self.expiry, "budget": asdict(BATCH_BUDGET), "currency": "USD",
            "decimals": 6, "single_cost": 40, "evidence_ref": evidence_ref,
        }

    def draft_batch(self, evidence_ref="fixture-batch-approval"):
        return self.engine.draft(self.batch_packet(evidence_ref))

    def open_engine(self):
        return LiveAdmission(
            self.store, self.policy, self.fixture.scope["study_id"], self.fixture.proof, self.authority_path,
        )

    def credential_permission(self, db):
        return self.policy.decide(
            Permission.MANAGE_PERSONAL_CREDENTIALS, Domain.LOCAL_WORKSPACE, proof=self.fixture.proof,
            study_id=self.fixture.scope["study_id"], current_scope=lambda scope: has_scope(db, scope),
        )

    def reply(self, request, *, timeout):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
        if request.full_url == ENDPOINTS["tavily"]:
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(json.loads(request.data), search_payload(SEARCH))
            response = {"request_id": "fixture-search-id", "results": [{"url": URL}], "usage": {"credits": 1}}
        else:
            self.assertEqual(request.full_url, ENDPOINTS["stackexchange"] + "8452?site=cooking&filter=withbody")
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.get_header("Authorization"))
            response = {"items": [{
                "question_id": 8452, "link": URL, "content_license": "CC BY-SA 4.0", "body": f"<p>{QUOTE}</p>",
                "owner": {"display_name": "Fixture author"}, "creation_date": 1630000000,
            }]}
        return Reply(json.dumps(response).encode())

    def packet(self, operation, *, slot=1, parent=None, batch=None, account_budget=BATCH_BUDGET):
        fields = {}
        keys = MATERIAL
        if operation != "search":
            keys |= {"source_permission", "retention", "attribution"}
            fields = {"source_ref": "fixture-source", "license": "CC BY-SA 4.0"}
        if operation == "search":
            target, payload = DOMAIN, search_payload(SEARCH)
            fields["query"] = SEARCH
        elif operation == "source":
            target, payload = URL, {"url": URL, "site": "cooking", "filter": "withbody"}
        else:
            target, payload = URL, model_payloads(QUOTE, OPTIONS)[slot - 1]
            fields |= MODEL_FIELDS
        binding = self.bindings.get(operation, {
            "provider": "packycode", "account_ref": "fixture-model-account",
            "channel_ref": "typesafe-officially", "credential_revision": "fixture-model-credential",
        })
        if parent is not None:
            fields |= {"depends_on": parent["request_id"], "depends_on_sha256": parent["response_sha256"]}
        return fields | {
            "batch_id": self.batch if batch is None else batch,
            "owner_ref": self.context.owner_ref, "operation": operation, "slot": slot,
            "target": target, "payload_sha256": digest(payload), "valid_from": self.start, "expires_at": self.expiry,
            "limit": asdict(LIMITS[operation]), "account_limit": asdict(account_budget),
            "material": {kind: "fixture-" + kind for kind in keys}, "evidence_ref": "fixture-operation-approval",
        } | {key: binding[key] for key in ("provider", "account_ref", "channel_ref", "credential_revision")}

    def execute_search(self, *, batch=None, account_budget=BATCH_BUDGET):
        packet = self.packet("search", batch=batch, account_budget=account_budget)
        grant = self.engine.authorize(packet["batch_id"], packet)
        result = self.engine.execute(packet["batch_id"], grant, packet)
        return packet, grant, result

    def receipt(self, request_id):
        return self.store.one("SELECT * FROM personal_validation_receipts WHERE request_id=?", (request_id,))

    def view(self, batch=None):
        return self.engine.ledger.view(self.batch if batch is None else batch, self.context, self.engine._owner)

    def search_bill(self, result):
        return {"request_id": result["request_id"], "provider": "tavily", "account_ref": "fixture-tavily-account",
                "provider_request_id": "fixture-search-id", "currency": "USD", "actual_units": 12,
                "bill_ref": "fixture-provider-bill"}

    def v2_batch_packet(self):
        revision = self.fixture.configure(self.client)
        records = [row | {"budget_limit": BATCH_BUDGET.total_tokens}
                   for row in self.fixture.development_evidence(revision)]
        self.fixture.write_evidence(records)
        pending = self.fixture.submit(self.client, records, budget_limit=BATCH_BUDGET.total_tokens)
        self.approval = self.fixture.approve(self.client, pending)
        self.bindings["model"] = put_validation_credential(
            self.store, authorize=self.credential_permission, operation="model", **self.fixture.identity,
            api_key=None, evidence_ref="local:fixture-model-binding",
        )
        slots = {}
        for operation, slot in (("search", 1), ("source", 1), ("model", 1), ("model", 2)):
            binding = self.bindings[operation]
            account_budget = MODEL_ACCOUNT_BUDGET if operation == "model" else BATCH_BUDGET
            slots[f"{operation}/{slot}"] = {
                key: binding[key] for key in ("provider", "account_ref", "channel_ref", "credential_revision")
            } | {"limit": asdict(LIMITS[operation]), "account_limit": asdict(account_budget)}
        return self.batch_packet("fixture-v2-batch-approval") | {"v2": {
            "slots": slots, "search_payload_sha256": digest(search_payload(SEARCH)), "systemone": {
                "approval_event_id": self.approval["event_id"], "dedicated_token_ref": "local:fixture-dedicated-token",
                "billing_rules_ref": "local:fixture-billing-rules", "allowance_ref": "local:fixture-allowance",
                "risk_acceptance_ref": "local:fixture-risk-acceptance", "rate_basis_tokens": 1_000_000,
                "input_rate_units": 25_000, "output_rate_units": 0, "additional_units_per_request": 1,
                "allowance_units": 100, "residual_risk_units": 20,
                "overdraft": False, "auto_recharge": False, "unbounded_charges": False,
            },
        }}

    def v2_packet(self, operation, *, slot=1):
        account_budget = MODEL_ACCOUNT_BUDGET if operation == "model" else BATCH_BUDGET
        packet = self.packet(operation, slot=slot, account_budget=account_budget)
        if operation != "search":
            packet["source_expires_at"] = self.expiry
        if operation == "model":
            payload = model_payloads(V2_TEXT, OPTIONS)[slot - 1]
            packet |= {"text": V2_TEXT, "model_input_sha256": digest(V2_TEXT), "payload_sha256": digest(payload),
                       "approval_event_id": self.approval["event_id"]}
        return packet

    def v2_reply(self, request, *, timeout):
        if request.full_url != ENDPOINTS["packycode"]:
            return self.reply(request, timeout=timeout)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
        payload = json.loads(request.data)
        slot = {8: 1, 3: 2}[len(payload["questions"])]
        self.assertEqual(payload, model_payloads(V2_TEXT, OPTIONS)[slot - 1])
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + test_personal_governance.FIRST)
        self.assertEqual(timeout, 12)
        input_tokens, output_tokens = V2_USAGE[slot]
        response = {"model": MODEL, "answers": _answers(payload["questions"]),
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}}
        return Reply(json.dumps(response).encode(), headers={"X-Request-Id": f"fixture-model-{slot}"})

    def v2_source(self):
        self.batch = self.engine.draft(self.v2_batch_packet())
        self.opener.side_effect = self.v2_reply
        search_packet = self.v2_packet("search")
        search_grant = self.engine.authorize(self.batch, search_packet)
        search = self.engine.execute(self.batch, search_grant, search_packet)
        self.assertTrue(search["eligible"])
        source_packet = self.v2_packet("source")
        with self.assertRaises(Conflict):
            self.engine.authorize(self.batch, source_packet)
        self.assertEqual(self.engine.reconcile(self.batch, self.search_bill(search))["actual_units"], 12)
        self.engine.resume(self.batch)
        source_grant = self.engine.authorize(self.batch, source_packet)
        source = self.engine.execute(self.batch, source_grant, source_packet)
        self.assertTrue(source["eligible"])
        return source

    def v2_review(self, source, **changes):
        proof = {"source_request_id": source["request_id"], "source_quote_sha256": digest(QUOTE),
                 "model_input_sha256": digest(V2_TEXT), "redaction_ref": "local:fixture-redaction",
                 "question_version": "personal-d-live-v1." + digest([MODEL_FIELDS["choices"],
                                                                       model_payloads(V2_TEXT, OPTIONS)])}
        return self.engine.review(self.batch, "C0-2", proof | changes)

    def v2_model_bill(self, result, slot):
        return {"request_id": result["request_id"], "provider": "packycode",
                "account_ref": self.fixture.identity["account_ref"], "provider_request_id": f"fixture-model-{slot}",
                "currency": "USD", "actual_units": 4, "bill_ref": f"local:fixture-model-bill-{slot}"}

    def test_v2_four_slots_settle_in_order_and_replay_stays_offline(self):
        source = self.v2_source()
        self.v2_review(source)
        completed = []
        for slot, usage in V2_USAGE.items():
            packet = self.v2_packet("model", slot=slot)
            grant = self.engine.authorize(self.batch, packet)
            result = self.engine.execute(self.batch, grant, packet)
            self.assertTrue(result["eligible"])
            receipt = self.receipt(result["request_id"])
            self.assertEqual(tuple(receipt[key] for key in ("input_tokens", "output_tokens", "total_tokens")),
                             (*usage, sum(usage)))
            self.assertEqual(receipt["model"], MODEL)
            self.assertEqual(receipt["quote_sha256"], digest(V2_TEXT))
            self.assertIsNone(receipt["actual_units"])
            self.assertEqual(receipt["estimated_units"], LIMITS["model"].units)
            self.assertEqual(self.view()["requests"][-1]["state"], "reconciliation")
            if slot == 1:
                with self.assertRaises(Conflict):
                    self.engine.authorize(self.batch, self.v2_packet("model", slot=2))
            else:
                with self.assertRaisesRegex(Conflict, "VALIDATION_FORMAL_REVIEW_REQUIRED"):
                    self.engine.complete(self.batch)
            proof = self.v2_model_bill(result, slot)
            self.assertEqual(self.engine.reconcile(self.batch, proof)["actual_units"], proof["actual_units"])
            self.engine = self.open_engine()
            self.assertEqual(self.engine.reconcile(self.batch, proof)["actual_units"], proof["actual_units"])
            self.engine.resume(self.batch)
            completed.append((packet, grant))

        for packet, grant in completed:
            self.assertFalse(self.engine.execute(self.batch, grant, packet)["dispatched"])
        view = self.view()
        self.assertEqual([(row["operation"], row["slot"], row["state"]) for row in view["requests"]],
                         [("search", 1, "settled"), ("source", 1, "settled"), ("model", 1, "settled"),
                          ("model", 2, "settled")])
        self.assertEqual(len(view["reconciliations"]), 3)
        self.assertEqual(view["spent"], asdict(Budget(4, 1, 210, 90, 300, 20)))
        self.assertEqual(view["research_denominator"], 0)
        for table in ("runs", "shards"):
            self.assertEqual(self.store.one(f"SELECT COUNT(*) AS count FROM {table}")["count"], 0)
        self.assertEqual(self.opener.call_count, 4)

        self.assertEqual(view["batch"]["state"], "approved")
        with self.assertRaisesRegex(Conflict, "VALIDATION_FORMAL_REVIEW_REQUIRED"):
            self.engine.complete(self.batch)
        evidence_fixtures = FormalMatrixTests()
        evidence_fixtures.setUp()
        for requirement in ("C0-5", "C0-6"):
            proof = evidence_fixtures.archive[f"{requirement}-proof"].copy()
            proof.pop("batch_id")
            self.engine.review(self.batch, requirement, proof)
        charges = {row["request_id"]: {"actual_units": row["actual_units"], "bill_ref": row["subject_ref"]}
                   for row in view["reconciliations"]}
        for receipt in view["receipts"]:
            request_id = receipt["request_id"]
            if receipt["provider"] == "stackexchange":
                charges[request_id] = {"actual_units": 0, "bill_ref": receipt["evidence_ref"]}
            charges[request_id].update({key: receipt[key] for key in ("provider_request_id", "provider", "account_ref")})
        with self.store.db() as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_violations = len(db.execute("PRAGMA foreign_key_check").fetchall())
        self.engine.review(self.batch, "C0-4", {
            "sqlite_reopened": True, "restart_readback": True, "idempotent_readback": True,
            "duplicate_charge_prevented": True, "currency": "USD", "integrity_check": integrity,
            "foreign_key_violations": foreign_key_violations, "charges": charges,
        })
        matrix = self.engine.matrix(self.batch)
        self.assertEqual({item["status"] for item in matrix.values()}, {"PASS"}, matrix)
        self.assertEqual(self.engine.complete(self.batch), "complete")
        self.assertEqual(self.open_engine().complete(self.batch), "complete")
        self.assertEqual(self.opener.call_count, 4)

    def test_v2_rejects_allowance_and_risk_mismatches_at_draft(self):
        approved = self.v2_batch_packet()
        for changes in ({"allowance_units": 99}, {"input_rate_units": 50_000}, {"auto_recharge": True},
                        {"overdraft": True}, {"unbounded_charges": True}, {"rate_basis_tokens": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                invalid = deepcopy(approved)
                invalid["v2"]["systemone"].update(changes)
                self.engine.draft(invalid)
        self.opener.assert_not_called()

    def test_v2_invalid_review_grant_and_rotated_model_credential_stop_before_send(self):
        source = self.v2_source()
        packet = self.v2_packet("model")
        with self.assertRaises(Conflict):
            self.engine.authorize(self.batch, packet)
        with self.assertRaises(Conflict):
            self.v2_review(source, source_quote_sha256=digest("Another synthetic quote"))
        self.v2_review(source)
        for changes in (
            {"account_ref": "fixture-other-account"}, {"source_expires_at": self.start},
            {"depends_on": source["request_id"], "depends_on_sha256": digest("different synthetic receipt")},
            {"limit": asdict(Budget(1, 0, 800, 400, 1200, 39))},
        ):
            with self.subTest(changes=changes), self.assertRaises(Conflict):
                self.engine.authorize(self.batch, packet | changes)
        grant = self.engine.authorize(self.batch, packet)
        self.fixture.configure(self.client, key=test_personal_governance.ROTATED)
        with self.assertRaises((Conflict, VaultError)):
            self.engine.execute(self.batch, grant, packet)
        self.assertEqual(len(self.view()["requests"]), 2)
        self.assertEqual(self.opener.call_count, 2)

    def test_v2_model_usage_overage_is_preserved_and_stops_remaining_slot(self):
        source = self.v2_source()
        self.v2_review(source)
        packet = self.v2_packet("model")
        grant = self.engine.authorize(self.batch, packet)

        def overage(request, *, timeout):
            with self.v2_reply(request, timeout=timeout) as reply:
                response = json.loads(reply.read())
                response["usage"]["output_tokens"] = LIMITS["model"].output_tokens + 1
                return Reply(json.dumps(response).encode(), headers=reply.headers)

        self.opener.side_effect = overage
        result = self.engine.execute(self.batch, grant, packet)
        self.assertFalse(result["eligible"])
        receipt = self.receipt(result["request_id"])
        self.assertEqual(receipt["output_tokens"], 401)
        self.assertEqual(receipt["reason"], "usage_over_budget")
        self.assertIsNone(receipt["actual_units"])
        self.assertEqual(self.view()["requests"][-1]["state"], "reconciliation")
        self.engine.reconcile(self.batch, self.v2_model_bill(result, 1))
        self.engine = self.open_engine()
        with self.assertRaises(Conflict):
            self.engine.resume(self.batch)
        with self.assertRaises(Conflict):
            self.engine.authorize(self.batch, self.v2_packet("model", slot=2))
        self.assertEqual(self.opener.call_count, 3)

    def test_search_reconciliation_and_reopen_permit_only_the_approved_hit(self):
        packet, grant, search = self.execute_search()
        self.assertTrue(search["dispatched"])
        self.assertTrue(search["eligible"])
        self.assertEqual(self.view()["requests"][0]["state"], "reconciliation")
        self.assertFalse(self.engine.execute(self.batch, grant, packet)["dispatched"])
        receipt = self.receipt(search["request_id"])
        with self.assertRaises(Conflict):
            self.engine.authorize(self.batch, self.packet("source", parent=receipt))
        with self.assertRaises(Conflict):
            self.engine.reconcile(self.batch, self.search_bill(search) | {"provider_request_id": "wrong-bill-id"})
        self.assertEqual(self.engine.reconcile(self.batch, self.search_bill(search))["actual_units"], 12)
        self.engine = self.open_engine()
        self.engine.resume(self.batch)
        wrong_url = f"https://{DOMAIN}/questions/9999"
        wrong = self.packet("source", parent=receipt) | {
            "target": wrong_url, "payload_sha256": digest({"url": wrong_url, "site": "cooking", "filter": "withbody"}),
        }
        with self.assertRaisesRegex(Conflict, "LIVE_SOURCE_NOT_IN_APPROVED_SEARCH"):
            self.engine.authorize(self.batch, wrong)
        source = self.packet("source", parent=receipt)
        source_grant = self.engine.authorize(self.batch, source)
        result = self.engine.execute(self.batch, source_grant, source)
        self.assertTrue(result["eligible"])
        self.assertEqual(self.receipt(result["request_id"])["quote_sha256"], digest(QUOTE))
        self.assertEqual(self.view()["research_denominator"], 0)
        self.assertEqual(self.opener.call_count, 2)

    def test_changed_payload_and_unverified_model_budget_do_not_reserve_or_send(self):
        packet = self.packet("search")
        grant = self.engine.authorize(self.batch, packet)
        changed = packet | {"query": {**SEARCH, "keywords": ["alternate synthetic query"]}}
        with self.assertRaisesRegex(Conflict, "LIVE_PAYLOAD_DIGEST_MISMATCH"):
            self.engine.execute(self.batch, grant, changed)
        with self.assertRaisesRegex(Conflict, "LIVE_OPERATION_APPROVAL_MISMATCH"):
            self.engine.execute(self.batch, grant, packet | {"evidence_ref": "different-approval"})
        for slot in (1, 2):
            with self.subTest(slot=slot), self.assertRaisesRegex(ValueError, "HARD_BUDGET_UNVERIFIED"):
                self.engine.authorize(self.batch, self.packet("model", slot=slot))
        self.assertEqual(self.view()["requests"], [])
        self.opener.assert_not_called()

    def test_credential_rotation_after_authorization_blocks_before_send(self):
        packet = self.packet("search")
        grant = self.engine.authorize(self.batch, packet)
        put_validation_credential(
            self.store, authorize=self.credential_permission, operation="search", provider="tavily",
            channel_ref="basic", account_ref="fixture-tavily-account", api_key="fixture-rotated",
            evidence_ref="fixture-rotation",
        )
        with self.assertRaisesRegex(VaultError, "CREDENTIAL_CHANGED"):
            self.engine.execute(self.batch, grant, packet)
        self.assertEqual(self.view()["requests"], [])
        self.opener.assert_not_called()

    def test_unknown_send_retains_reservation_and_prevents_automatic_retry(self):
        self.opener.side_effect = URLError("fixture disconnect")
        packet, grant, result = self.execute_search()
        request = self.view()["requests"][0]
        self.assertEqual(request["state"], "reconciliation")
        self.assertEqual(request["units"], LIMITS["search"].units)
        self.assertIsNone(self.receipt(result["request_id"])["actual_units"])
        self.assertFalse(self.engine.execute(self.batch, grant, packet)["dispatched"])
        self.opener.assert_called_once()

    def test_revocation_after_send_preserves_the_ineligible_receipt(self):
        def revoke_during_send(request, *, timeout):
            self.engine.stop(self.batch, "revoked")
            return self.reply(request, timeout=timeout)

        self.opener.side_effect = revoke_during_send
        packet, grant, result = self.execute_search()
        self.assertFalse(result["eligible"])
        self.assertEqual(self.receipt(result["request_id"])["eligible"], 0)
        proof = self.search_bill(result)
        self.assertEqual(self.view()["batch"]["state"], "revoked")
        self.assertEqual(self.engine.reconcile(self.batch, proof)["actual_units"], proof["actual_units"])
        self.engine = self.open_engine()
        self.assertEqual(self.engine.reconcile(self.batch, proof)["actual_units"], proof["actual_units"])
        state = self.view()
        self.assertEqual(state["batch"]["state"], "revoked")
        self.assertEqual(state["requests"][0]["state"], "settled")
        self.assertEqual(state["receipts"][0]["eligible"], 0)
        self.assertEqual(len(state["reconciliations"]), 1)
        with self.assertRaisesRegex(Conflict, "VALIDATION_RECONCILIATION_CONFLICT"):
            self.engine.reconcile(self.batch, proof | {"actual_units": 13})
        with self.assertRaises(Conflict):
            self.engine.resume(self.batch)
        with self.assertRaises(Conflict):
            self.engine.execute(self.batch, grant, packet)
        self.opener.assert_called_once()

    def test_receipt_database_failure_keeps_send_claim_and_stops_replay(self):
        with patch.object(self.engine.ledger, "receipt", side_effect=sqlite3.OperationalError):
            packet, grant, result = self.execute_search()
        self.assertEqual(result["state"], "reconciliation")
        self.assertFalse(self.engine.execute(self.batch, grant, packet)["dispatched"])
        self.assertIsNone(self.receipt(result["request_id"]))
        self.opener.assert_called_once()

    def test_provider_charge_over_reservation_blocks_resume_after_reopen(self):
        _, _, result = self.execute_search()
        amount = LIMITS["search"].units + 1
        proof = self.search_bill(result) | {"actual_units": amount}
        self.assertEqual(self.engine.reconcile(self.batch, proof)["actual_units"], amount)
        self.engine = self.open_engine()
        self.assertEqual(self.view()["batch"]["state"], "blocked")
        with self.assertRaisesRegex(Conflict, "VALIDATION_USAGE_OVER_BUDGET"):
            self.engine.resume(self.batch)
        self.assertEqual(self.view()["batch"]["state"], "blocked")
        self.opener.assert_called_once()

    def test_reconciliation_write_failure_preserves_charge_proof_and_pending_reservation(self):
        self.opener.side_effect = URLError("fixture disconnect")
        _, _, result = self.execute_search(account_budget=SHARED_ACCOUNT_BUDGET)
        second_batch = self.draft_batch("fixture-second-batch")
        _, _, second = self.execute_search(batch=second_batch, account_budget=SHARED_ACCOUNT_BUDGET)
        proof = self.search_bill(result)
        with patch.object(self.engine.authority, "archive_charge", side_effect=AuthorityError):
            with self.assertRaises(AuthorityError):
                self.engine.reconcile(self.batch, proof)
        self.assertEqual(self.view()["reconciliations"], [])
        with patch.object(self.engine.ledger, "_request_event", side_effect=sqlite3.OperationalError):
            with self.assertRaises(sqlite3.OperationalError):
                self.engine.reconcile(self.batch, proof)
        state = self.view()
        self.assertEqual(state["requests"][0]["state"], "reconciliation")
        self.assertEqual(state["spent"]["units"], LIMITS["search"].units)
        self.assertEqual(state["reconciliations"], [])
        self.engine = self.open_engine()
        with self.assertRaisesRegex(AuthorityError, "LIVE_AUTHORITY_CHARGE_CONFLICT"):
            self.engine.reconcile(self.batch, proof | {"actual_units": 13})
        with self.assertRaisesRegex(Conflict, "LIVE_RECONCILIATION_PROVIDER_REQUEST_CONFLICT"):
            self.engine.reconcile(second_batch, self.search_bill(second))
        self.assertEqual(self.view(second_batch)["reconciliations"], [])
        self.assertEqual(self.engine.reconcile(self.batch, proof)["actual_units"], proof["actual_units"])
        self.assertEqual(len(self.view()["reconciliations"]), 1)
        self.assertEqual(self.opener.call_count, 2)

    def test_reconciliation_cannot_reuse_provider_id_from_another_receipt(self):
        _, _, original = self.execute_search(account_budget=SHARED_ACCOUNT_BUDGET)
        self.assertTrue(original["eligible"])
        self.opener.side_effect = URLError("fixture disconnect")
        second_batch = self.draft_batch("fixture-second-batch")
        _, _, second = self.execute_search(batch=second_batch, account_budget=SHARED_ACCOUNT_BUDGET)
        with self.assertRaisesRegex(Conflict, "LIVE_RECONCILIATION_PROVIDER_REQUEST_CONFLICT"):
            self.engine.reconcile(second_batch, self.search_bill(second))
        self.assertEqual(self.view(second_batch)["requests"][0]["state"], "reconciliation")
        self.assertEqual(self.view(second_batch)["reconciliations"], [])
        self.assertEqual(self.opener.call_count, 2)

    def test_reconciliation_fails_closed_when_another_charge_archive_is_missing(self):
        self.opener.side_effect = URLError("fixture disconnect")
        second_batch = self.draft_batch("fixture-second-batch")
        with patch.object(self.engine.ledger, "receipt", side_effect=sqlite3.OperationalError):
            _, _, first = self.execute_search(account_budget=SHARED_ACCOUNT_BUDGET)
            _, _, second = self.execute_search(batch=second_batch, account_budget=SHARED_ACCOUNT_BUDGET)
        self.assertIsNone(self.receipt(first["request_id"]))
        self.assertIsNone(self.receipt(second["request_id"]))
        first_proof, second_proof = self.search_bill(first), self.search_bill(second)
        first_result = self.engine.reconcile(self.batch, first_proof)
        charge_path = self.authority_path / f"live-charge-{first['request_id']}.dpapi"
        saved_charge_path = charge_path.rename(charge_path.with_suffix(".saved"))

        try:
            self.engine = self.open_engine()
            with self.assertRaisesRegex(AuthorityError, "LIVE_AUTHORITY_CHARGE_MISSING_OR_INVALID"):
                self.engine.reconcile(second_batch, second_proof)
            self.assertEqual(self.view(second_batch)["reconciliations"], [])
        finally:
            saved_charge_path.rename(charge_path)

        with self.assertRaisesRegex(Conflict, "LIVE_RECONCILIATION_PROVIDER_REQUEST_CONFLICT"):
            self.engine.reconcile(second_batch, second_proof)
        self.assertEqual(self.view(second_batch)["reconciliations"], [])
        self.assertEqual(self.view(second_batch)["requests"][0]["state"], "reconciliation")
        self.assertEqual(self.engine.reconcile(self.batch, first_proof), first_result)
        self.assertEqual(len(self.view()["reconciliations"]), 1)
        self.assertEqual(self.opener.call_count, 2)

    def test_later_provider_reply_cannot_reuse_a_reconciled_provider_request_id(self):
        self.opener.side_effect = URLError("fixture disconnect")
        _, _, first = self.execute_search(account_budget=SHARED_ACCOUNT_BUDGET)
        self.engine.reconcile(self.batch, self.search_bill(first))
        self.opener.side_effect = self.reply
        second_batch = self.draft_batch("fixture-second-batch")
        _, _, second = self.execute_search(batch=second_batch, account_budget=SHARED_ACCOUNT_BUDGET)
        self.assertTrue(second["dispatched"])
        self.assertFalse(second["eligible"])
        self.assertIsNone(self.receipt(second["request_id"]))
        event = self.store.one(
            "SELECT state, reason FROM personal_validation_request_events WHERE request_id=? ORDER BY sequence DESC LIMIT 1",
            (second["request_id"],),
        )
        self.assertEqual((event["state"], event["reason"]), ("reconciliation", "provider_receipt_conflict"))
        self.assertEqual(self.opener.call_count, 2)

    def test_concurrent_reconciliations_bind_provider_request_id_to_only_one_local_request(self):
        self.opener.side_effect = URLError("fixture disconnect")
        second_batch = self.draft_batch("fixture-second-batch")
        requests = {}
        for batch in (self.batch, second_batch):
            _, _, result = self.execute_search(batch=batch, account_budget=SHARED_ACCOUNT_BUDGET)
            requests[batch] = self.search_bill(result)

        barrier = Barrier(len(requests))

        def reconcile(batch):
            engine = self.open_engine()
            barrier.wait(timeout=5)
            try:
                return engine.reconcile(batch, requests[batch])["request_id"]
            except Conflict as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=len(requests)) as workers:
            outcomes = dict(zip(requests, workers.map(reconcile, requests), strict=True))
        conflict = "LIVE_RECONCILIATION_PROVIDER_REQUEST_CONFLICT"
        self.assertEqual(list(outcomes.values()).count(conflict), 1)
        for batch, proof in requests.items():
            reconciliations = self.view(batch)["reconciliations"]
            if outcomes[batch] == conflict:
                self.assertEqual(reconciliations, [])
            else:
                self.assertEqual(outcomes[batch], proof["request_id"])
                self.assertEqual([row["request_id"] for row in reconciliations], [proof["request_id"]])
        self.assertEqual(self.opener.call_count, 2)

    def test_missing_protected_charge_blocks_resume_and_preapproved_sends(self):
        _, _, result = self.execute_search(account_budget=SHARED_ACCOUNT_BUDGET)
        proof = self.search_bill(result)
        self.engine.reconcile(self.batch, proof)
        charge_path = self.authority_path / f"live-charge-{result['request_id']}.dpapi"
        saved_charge_path = charge_path.rename(charge_path.with_suffix(".saved"))
        self.engine = self.open_engine()
        with self.assertRaisesRegex(Conflict, "VALIDATION_AUTHORITY_CHANGED"):
            self.engine.resume(self.batch)
        with self.assertRaisesRegex(AuthorityError, "LIVE_AUTHORITY_CHARGE_MISSING_OR_INVALID"):
            self.engine.reconcile(self.batch, proof)
        self.assertEqual(len(self.view()["reconciliations"]), 1)
        saved_charge_path.rename(charge_path)
        self.engine.resume(self.batch)
        source = self.packet("source", parent=self.receipt(result["request_id"]))
        grant = self.engine.authorize(self.batch, source)
        other_batch = self.draft_batch("fixture-other-batch")
        search = self.packet("search", batch=other_batch, account_budget=SHARED_ACCOUNT_BUDGET)
        search_grant = self.engine.authorize(other_batch, search)
        charge_path.rename(saved_charge_path)
        try:
            for batch_id, grant_id, packet in ((self.batch, grant, source), (other_batch, search_grant, search)):
                with self.subTest(batch_id=batch_id), self.assertRaisesRegex(
                        Conflict, "VALIDATION_RESTORE_CONTINUITY_REQUIRED"):
                    self.engine.execute(batch_id, grant_id, packet)
            self.assertEqual(len(self.view()["requests"]), 1)
            self.assertEqual(self.view(other_batch)["requests"], [])
            self.opener.assert_called_once()
        finally:
            saved_charge_path.rename(charge_path)

    def test_charge_file_missing_from_restored_ledger_blocks_other_batch_until_reconciled(self):
        _, _, result = self.execute_search()
        proof = self.search_bill(result)
        with closing(sqlite3.connect(":memory:")) as snapshot:
            with self.store.db() as database:
                database.backup(snapshot)
            self.engine.reconcile(self.batch, proof)
            with self.store.db() as database:
                snapshot.backup(database)
        self.engine = self.open_engine()
        self.assertEqual(self.view()["reconciliations"], [])
        other_batch = self.draft_batch("fixture-other-batch")
        packet = self.packet("search", batch=other_batch)
        with self.assertRaisesRegex(Conflict, "VALIDATION_RESTORE_CONTINUITY_REQUIRED"):
            self.engine.authorize(other_batch, packet)
        self.assertEqual(self.engine.reconcile(self.batch, proof)["actual_units"], proof["actual_units"])
        self.assertTrue(self.engine.authorize(other_batch, packet))
        self.opener.assert_called_once()

    def test_nonformal_ledger_cannot_write_formal_batch_history(self):
        _, _, result = self.execute_search()
        request_id = result["request_id"]
        ledger = ValidationLedger(self.store, engineering_fixture=True)
        owner = self.engine._owner
        operations = {
            "mark_unknown": (request_id, self.context, "fixture-unknown", owner),
            "reconcile": (request_id, self.context, 12, "fixture-bill", "fixture-proof", owner),
            "release": (request_id, self.context, "fixture-release", owner),
            "transition": (self.batch, self.context, "revoked", "fixture-revoke", owner),
            "recover": (self.batch, self.context, owner),
            "add_evidence": (self.batch, self.context, "C0-5", "local_regression", "fixture-proof", "0" * 64,
                             "fixture-review", owner),
        }
        for operation, arguments in operations.items():
            with self.subTest(operation=operation), self.assertRaisesRegex(
                    Conflict, "VALIDATION_FORMAL_OWNER_COMMAND_REQUIRED"):
                getattr(ledger, operation)(*arguments)
        self.assertEqual(self.view()["batch"]["state"], "reconciliation")
        self.assertEqual(self.view()["reconciliations"], [])
        self.assertEqual(self.view()["evidence"], [])
        self.opener.assert_called_once()

    def test_restore_before_dispatch_cannot_replay_a_previously_claimed_grant(self):
        packet = self.packet("search")
        grant = self.engine.authorize(self.batch, packet)
        with closing(sqlite3.connect(":memory:")) as snapshot:
            with self.store.db() as database:
                database.backup(snapshot)
            self.assertTrue(self.engine.execute(self.batch, grant, packet)["dispatched"])
            with self.store.db() as database:
                snapshot.backup(database)
        self.engine = self.open_engine()
        self.assertEqual(self.view()["requests"], [])
        with self.assertRaisesRegex(Conflict, "VALIDATION_RESTORE_CONTINUITY_REQUIRED"):
            self.engine.execute(self.batch, grant, packet)
        self.assertEqual(self.view()["requests"], [])
        self.opener.assert_called_once()
