"""Synthetic end-to-end tests for D's authorized execution boundary."""

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import sqlite3
import unittest
from unittest.mock import patch

import test_personal_governance as governance_fixtures
from src.dashboard.edition_access import has_scope
from src.dashboard.personal_governance import governance_decision
from src.edition_policy import Domain, Permission
from src.execution.personal_admission import (
    FixtureReply, PersonalAdmission, SourcePermission, digest, model_payloads, question_version, search_payload,
    source_identity,
)
from src.execution.transport import ENDPOINTS, Response, network
from src.ingestion.public_source import DOMAIN
from src.raw_store.personal_validation import BatchContext, Budget, OperationGrant
from src.raw_store.personal_validation_credentials import put_validation_credential
from src.raw_store.store import Conflict


QUOTE = "The synthetic label shows how to measure the syrup."
URL = f"https://{DOMAIN}/questions/8452"
SEARCH = {"keywords": ["synthetic syrup fixture"], "allowed_domains": [DOMAIN]}
OPTIONS = {f"fixture-{index}": f"Synthetic intent {index}" for index in range(11)}
SHARDS = model_payloads(QUOTE, OPTIONS)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = governance_fixtures.PersonalGovernanceTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.identity["channel_ref"] = "typesafe-officially"
        self.client, app = self.fixture.open_client()
        self.enterContext(self.client)
        self.store = app.state.store
        self.policy = app.state.edition_policy
        self.owner = self.policy.owner
        self.calls = []
        self.engine = PersonalAdmission(self.store, fixture_transport=self.transport)
        self.ledger = self.engine.ledger
        self.now = datetime.now(UTC)
        self.start = (self.now - timedelta(minutes=5)).isoformat()
        self.expiry = (self.now + timedelta(minutes=30)).isoformat()
        self.source = SourcePermission("fixture-source", URL, "CC BY-SA 4.0", "public_approved",
                                       self.expiry, digest(QUOTE))
        self.revision = self.fixture.configure(self.client)
        self.fixture.write_evidence(records := self.fixture.development_evidence(self.revision))
        self.c_approval = self.fixture.approve(self.client, self.fixture.submit(self.client, records, budget_limit=55))
        with self.store.db() as db:
            decision = governance_decision(self.authorize(db), self.owner)
        self.context = BatchContext(
            decision.scope.study_id, decision.scope.scope_id, decision.scope.scope_version,
            decision.actor_ref, decision.owner_ref, decision.evidence_refs[0], decision.policy_version,
        )
        self.local_check, _ = self.engine.recheck(self.context, self.authorize, owner=self.owner)
        self.batch = self.ledger.draft(self.context, self.start, self.expiry, Budget(4, 1, 40, 20, 60, 100),
                                      "USD", 6, 30, "fixture-decision", self.local_check)
        self.auth_material("source:" + self.source.ref, digest(asdict(self.source)))
        self.bindings = {
            operation: put_validation_credential(
                self.store, authorize=lambda db: self.authorize(db, Permission.MANAGE_PERSONAL_CREDENTIALS),
                operation=operation, provider=provider, channel_ref=channel, account_ref=account,
                api_key=key, evidence_ref="fixture-binding",
            )
            for operation, provider, channel, account, key in (
                ("search", "tavily", "basic", "fixture-tavily", "fixture-local-tavily"),
                ("source", "stackexchange", "public-api", "fixture-source", None),
                ("model", self.fixture.identity["provider"], self.fixture.identity["channel_ref"],
                 self.fixture.identity["account_ref"], None),
            )
        }
        for binding in self.bindings.values():
            self.auth_material("risk:" + binding["provider"], "fixture-risk")
        self.script = None

    def authorize(self, db, permission=Permission.WRITE_PERSONAL_APPROVALS):
        return self.policy.decide(
            permission, Domain.LOCAL_WORKSPACE, proof=self.fixture.proof, study_id=self.fixture.scope["study_id"],
            current_scope=lambda scope: has_scope(db, scope),
        )

    def auth_material(self, subject, revision, state="current"):
        self.ledger.record_authority(self.context, subject, revision, state, "fixture-material", self.local_check)

    def transport(self, method, target, body, headers):
        self.calls.append((method, target))
        # An independent writer can enter while the transport callback runs.
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
        if self.script is not None:
            reply = self.script()
            if reply is not None:
                return reply
        if target == ENDPOINTS["tavily"]:
            self.assertEqual(body, search_payload(SEARCH))
            self.assertEqual(headers["Authorization"], "Bearer fixture-local-tavily")
            response = {"results": [{"url": URL, "content": "A search snippet is not the source."}],
                        "usage": {"credits": 1}}
        elif target.startswith(ENDPOINTS["stackexchange"]):
            self.assertNotIn("Authorization", headers)
            response = {"items": [{"question_id": 8452, "link": URL, "content_license": self.source.license_name,
                                   "body": f"<p>{QUOTE}</p>", "owner": {"display_name": "Fixture author"},
                                   "creation_date": 1630000000}]}
        else:
            self.assertEqual(target, ENDPOINTS["packycode"])
            self.assertEqual(body["state"], QUOTE)
            self.assertEqual(headers["Authorization"], "Bearer " + governance_fixtures.FIRST)
            answers = {}
            for key, question in body["questions"].items():
                kind = question["type"]
                answer = {"type": kind}
                if kind == "noul":
                    answer["noul"] = 0.9
                elif kind == "choice":
                    answer.update(choice="None", confidence=1,
                                  probabilities={option: int(option == "None") for option in question["criteria"]})
                else:
                    answer.update(score=1, confidence=1, probabilities={"0": 0, "1": 1, "2": 0})
                answers[key] = answer
            response = {"model": "jev-1.14.0", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 5}}
        return FixtureReply(Response(200, response), "fixture-reply", f"fixture-{len(self.calls)}", 5)

    def prepare(self, operation, slot=1, parent=None, model_estimate=None, shards=SHARDS):
        binding = self.bindings[operation]
        payload, estimate = {
            "search": (search_payload(SEARCH), Budget(1, 1, 0, 0, 0, 20)),
            "source": ({"url": URL, "site": "cooking", "filter": "withbody"}, Budget(1, 0, 0, 0, 0, 20)),
            "model": (shards[slot - 1], model_estimate or Budget(1, 0, 17, 10, 27, 20)),
        }[operation]
        identity = {"provider": binding["provider"], "account": binding["account_ref"],
                    "channel": binding["channel_ref"], "credential": binding["credential_revision"]}
        self.auth_material(f"limits:{operation}:{slot}",
                           digest({"payload": digest(payload), "limits": asdict(estimate), **identity}))
        model = operation == "model"
        grant = OperationGrant(
            operation, binding["provider"], binding["account_ref"], binding["channel_ref"],
            binding["credential_revision"], "jev-1.14.0" if model else "",
            self.c_approval["event_id"] if model else None, "fixture-risk", self.source.ref, digest(URL),
            digest(payload), question_version(shards) if model else "", self.start, self.expiry, estimate,
            "fixture-authorization", slot, depends_on=parent["request_id"] if parent else None,
            depends_on_sha256=parent["receipt"]["response_sha256"] if parent else None,
        )
        check, _ = self.engine.recheck(self.context, self.authorize, owner=self.owner, source=self.source,
                                     operation=operation, payload=payload, estimate=estimate,
                                     model_version=question_version(shards) if model else None)
        grant = self.ledger.authorize(self.batch["batch_id"], self.context, grant, check)
        return grant, estimate

    def run_operation(self, prepared, **changes):
        grant, estimate = prepared
        parameters = dict(source=self.source, estimate=estimate, authorize=self.authorize, owner=self.owner,
                          query=SEARCH, text=QUOTE, options=OPTIONS)
        return self.engine.execute(self.batch["batch_id"], self.context, grant, **(parameters | changes))

    def test_four_transports_use_separate_grants_and_leave_formal_statistics_empty(self):
        search = self.prepare("search")
        hit = self.run_operation(search)
        self.assertFalse(self.run_operation(search)["dispatched"])
        source = self.run_operation(self.prepare("source", parent=hit))
        first = self.run_operation(self.prepare("model", parent=source))
        second = self.run_operation(self.prepare("model", slot=2, parent=first))
        self.assertTrue(all(result["receipt"]["eligible"] for result in (hit, source, first, second)))
        self.assertEqual([len(shard["questions"]) for shard in SHARDS], [8, 3])
        self.assertEqual(set(SHARDS[0]["questions"]["intent"]["criteria"]), set(OPTIONS) | {"None"})
        self.assertEqual(len(self.calls), 4)
        view = self.ledger.view(self.batch["batch_id"], self.context, self.local_check)
        self.assertEqual(view["research_denominator"], 0)
        self.assertEqual(set(view["formal_status"].values()), {"BLOCKED"})
        self.assertTrue(all(QUOTE not in str(row) for row in view["receipts"]))

    def test_payload_substitution_scope_forgery_and_expired_source_do_not_send(self):
        search = self.prepare("search")
        for changes in (
            {"query": SEARCH | {"keywords": ["changed query"]}},
            {"source": replace(self.source, expires_at=self.start)},
            {"source": replace(self.source, classification="internal_cx")},
            {"authorize": lambda db: replace(self.authorize(db), actor_ref="other-owner")},
            {"estimate": Budget(1, 1, 0, 0, 0, 19)},
        ):
            with self.subTest(fields=sorted(changes)), self.assertRaises(Conflict):
                self.run_operation(search, **changes)
        for unsafe in ("http://localhost/", "https://other.invalid/questions/8452", URL + "?unexpected=value"):
            with self.assertRaises(ValueError):
                source_identity(unsafe)
        self.assertEqual(self.calls, [])

    def test_risk_revoked_after_send_retains_cost_and_blocks_chain(self):
        search = self.prepare("search")
        self.script = lambda: self.auth_material("risk:tavily", "fixture-risk", "revoked") and None
        hit = self.run_operation(search)
        self.assertEqual(hit["receipt"]["eligible"], 0)
        self.assertEqual(hit["receipt"]["actual_units"], 5)
        with self.assertRaises(Conflict):
            self.prepare("source", parent=hit)
        self.assertEqual(len(self.calls), 1)

    def test_redirect_pauses_and_cannot_create_eligible_source(self):
        search = self.prepare("search")
        hit = self.run_operation(search)
        source = self.prepare("source", parent=hit)
        self.script = lambda: FixtureReply(Response(302, {"location": "https://other.invalid"}), "fixture-redirect")
        result = self.run_operation(source)
        self.assertEqual(result["receipt"]["eligible"], 0)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(self.run_operation(source)["dispatched"])

    def test_failed_receipt_commit_preserves_the_claim_and_stops_retries(self):
        search = self.prepare("search")
        with patch.object(self.ledger, "receipt", side_effect=sqlite3.OperationalError):
            result = self.run_operation(search)
        self.assertEqual(result["state"], "reconciliation")
        self.assertFalse(self.run_operation(search)["dispatched"])
        self.assertEqual(len(self.calls), 1)

    def test_second_shard_requires_same_questions_and_remaining_c_approval_tokens(self):
        search = self.run_operation(self.prepare("search"))
        source = self.run_operation(self.prepare("source", parent=search))
        first = self.run_operation(self.prepare("model", parent=source))
        with self.assertRaises(Conflict):
            self.prepare("model", slot=2, parent=first, model_estimate=Budget(1, 0, 20, 10, 30, 20))
        with self.assertRaises(Conflict):
            altered = model_payloads(QUOTE, OPTIONS | {"fixture-0": "Changed option"})
            self.prepare("model", slot=2, parent=first, shards=altered)
        self.assertEqual(len(self.calls), 3)

    def test_production_has_no_transport(self):
        with self.assertRaises(ValueError):
            PersonalAdmission(self.store, fixture_transport=network)
        search = self.prepare("search")
        self.engine = PersonalAdmission(self.store)
        with self.assertRaisesRegex(Conflict, "TRANSPORT_DISABLED"):
            self.run_operation(search)
        self.assertEqual(self.calls, [])
