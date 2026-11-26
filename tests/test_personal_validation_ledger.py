from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from uuid import uuid4

from src.dashboard.personal_workspace import provision
from src.edition_policy import Edition
from src.raw_store.personal_validation import (
    MAX_INTEGER,
    REQUIREMENTS,
    BatchContext,
    Budget,
    OperationGrant,
    Receipt,
    ValidationLedger,
)
from src.raw_store.store import Conflict, Store


START = "2026-01-01T00:00:00Z"
END = "2026-01-03T00:00:00Z"
PAYLOAD = "1" * 64
SOURCE = "2" * 64
RESPONSE = "3" * 64
LIMIT = Budget(4, 4, 80, 40, 120, 100)
ESTIMATE = Budget(1, 1, 0, 0, 0, 10)


def authorized(db, batch, grant):
    return True


class PersonalValidationLedgerTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory())).resolve()
        binding = provision(directory, "Synthetic validation", "Synthetic scope", uuid4())
        self.store = Store(directory, edition=Edition.PERSONAL)
        self.context = BatchContext(
            binding["study_id"], binding["scope_id"], binding["scope_version"],
            "tester", "fixture-owner", "fixture-authorization", "fixture.v1",
        )
        self.now = datetime(2026, 1, 2, tzinfo=UTC)
        self.ledger = ValidationLedger(self.store, engineering_fixture=True, clock=lambda: self.now)
        self.bind("search", "tavily", "fixture-search", "search-fixture", "search.v1")
        self.batch_id = self.draft()["batch_id"]

    def draft(self, *, starts=START, ends=END, budget=LIMIT, single_cost=25):
        return self.ledger.draft(self.context, starts, ends, budget, "USD", 6, single_cost,
                                 "synthetic-batch", authorized)

    def bind(self, operation, provider, account, channel, revision):
        return self.ledger.bind_credential(
            self.context, operation, provider, account, channel, revision, "fixture-credential", authorized,
        )

    def grant(self, **kwargs):
        return replace(OperationGrant(
            "search", "tavily", "fixture-search", "search-fixture", "search.v1", "", None, "material.v1",
            "source-fixture", SOURCE, PAYLOAD, "", START, END, LIMIT, "synthetic-grant",
        ), **kwargs)

    def approve(self, grant=None, batch_id=None):
        return self.ledger.authorize(batch_id or self.batch_id, self.context, grant or self.grant(), authorized)

    def reserve(self, approval, estimate=ESTIMATE):
        return self.ledger.reserve(approval["batch_id"], self.context, approval["grant_id"], approval["slot"],
                                   approval["payload_sha256"], estimate, authorized)

    def claim(self, request, recheck=authorized):
        return self.ledger.claim(request["request_id"], self.context, recheck)

    def receipt(self, request, recheck=authorized, **kwargs):
        receipt = replace(Receipt(RESPONSE, 200, "synthetic-receipt", credits=1, actual_units=7,
                                  balance_status="not_applicable", valid=True, reason="fixture_valid"), **kwargs)
        return self.ledger.receipt(request["request_id"], self.context, receipt, recheck)

    def state(self):
        return self.ledger.view(self.batch_id, self.context, authorized)

    def test_utc_and_integer_limits_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "INVALID_VALIDATION_SCOPE"):
            replace(self.context, study_id=None)
        for start in ("2026-01-01T00:00:00", "2026-01-01T05:00:00+05:00", "unknown"):
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, "INVALID_VALIDATION_WINDOW"):
                self.draft(starts=start)
        for units in (-1, MAX_INTEGER + 1, True):
            with self.subTest(units=units), self.assertRaisesRegex(ValueError, "INVALID_BUDGET_VALUE"):
                replace(LIMIT, units=units)

    def test_default_workspace_cannot_reserve_or_claim_transport(self):
        approval = self.approve()
        request = self.reserve(approval)
        normal = ValidationLedger(self.store, clock=lambda: self.now)
        with self.assertRaisesRegex(Conflict, "VALIDATION_TRANSPORT_DISABLED"):
            normal.reserve(self.batch_id, self.context, approval["grant_id"], 1, PAYLOAD, ESTIMATE, authorized)
        with self.assertRaisesRegex(Conflict, "VALIDATION_TRANSPORT_DISABLED"):
            normal.claim(request["request_id"], self.context, authorized)

    def test_idempotent_single_reservation_claim_and_receipt(self):
        approval = self.approve()
        self.assertEqual(self.approve(), approval)
        request = self.reserve(approval)
        self.assertEqual(self.reserve(approval), request)
        with self.assertRaisesRegex(Conflict, "VALIDATION_SLOT_ALREADY_BOUND"):
            self.reserve(approval, replace(ESTIMATE, units=9))
        with self.assertRaisesRegex(Conflict, "VALIDATION_SLOT_ALREADY_BOUND"):
            self.approve(self.grant(payload_sha256=SOURCE))

        barrier = Barrier(2)

        def claim():
            barrier.wait(timeout=10)
            return self.claim(request)

        with ThreadPoolExecutor(max_workers=2) as pool:
            workers = [pool.submit(claim) for _ in range(2)]
            outcomes = [worker.result(timeout=20) for worker in workers]
        self.assertEqual(sum(bool(outcome) for outcome in outcomes), 1)
        receipt = self.receipt(request)
        self.assertEqual(receipt["eligible"], 1)
        self.assertEqual(self.receipt(request), receipt)
        self.assertEqual(self.state()["remaining"], {
            "requests": 3, "credits": 3, "input_tokens": 80, "output_tokens": 40, "total_tokens": 120, "units": 93,
        })
        self.assertEqual(self.state()["formal_status"], dict.fromkeys(REQUIREMENTS, "BLOCKED"))
        self.assertEqual(self.state()["research_denominator"], 0)
        with self.store.db() as db:
            for table in ("batches", "grants", "requests", "batch_events", "request_events", "receipts"):
                with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                    db.execute(f"DELETE FROM personal_validation_{table}")

    def test_scoped_account_and_operation_budget_limits(self):
        for field, value in (("requests", 0), ("credits", 0), ("units", 9)):
            with self.subTest(field=field):
                account = f"fixture-limit-{field}"
                revision = f"fixture-revision-{field}"
                self.bind("search", "tavily", account, "search-fixture", revision)
                approval = self.approve(self.grant(account_ref=account, credential_revision=revision,
                                                   account_limit=replace(LIMIT, **{field: value})),
                                        batch_id=self.draft()["batch_id"])
                with self.assertRaisesRegex(Conflict, "VALIDATION_BUDGET_EXHAUSTED"):
                    self.reserve(approval)
                self.bind("search", "tavily", "fixture-search", "search-fixture", f"search.{field}")
                approval = self.approve(self.grant(credential_revision=f"search.{field}",
                                                   limit=replace(LIMIT, **{field: value})),
                                        batch_id=self.draft()["batch_id"])
                with self.assertRaisesRegex(Conflict, "VALIDATION_BUDGET_EXHAUSTED"):
                    self.reserve(approval)
        with self.assertRaisesRegex(Conflict, "VALIDATION_BUDGET_EXHAUSTED"):
            self.reserve(self.approve(self.grant(credential_revision="search.units")), replace(ESTIMATE, units=26))

    def test_overlapping_batches_share_account_cap_across_channel_changes(self):
        account_cap = replace(LIMIT, requests=1)
        first = self.reserve(self.approve(self.grant(account_limit=account_cap)))
        self.claim(first)
        self.ledger.transition(self.batch_id, self.context, "revoked", "owner-revoked", authorized)
        self.bind("search", "tavily", "fixture-search", "search-fixture-two", "search.v2")
        second = self.draft()["batch_id"]
        new_grant = self.grant(channel_ref="search-fixture-two", credential_revision="search.v2")
        with self.assertRaisesRegex(Conflict, "VALIDATION_ACCOUNT_LIMIT_CHANGED"):
            self.approve(new_grant, batch_id=second)
        approval = self.approve(replace(new_grant, account_limit=account_cap), batch_id=second)
        with self.assertRaisesRegex(Conflict, "VALIDATION_BUDGET_EXHAUSTED"):
            self.reserve(approval)
        self.assertEqual(self.state()["spent"]["requests"], 1)

    def test_pause_expiry_release_and_restore_invalidate_send_authority(self):
        approval = self.approve()
        request = self.reserve(approval)
        self.ledger.transition(self.batch_id, self.context, "paused", "review-pause", authorized)
        with self.assertRaisesRegex(Conflict, "VALIDATION_BATCH_NOT_ACTIVE"):
            self.claim(request)
        self.ledger.transition(self.batch_id, self.context, "approved", "review-resume", authorized)
        self.now = datetime(2026, 1, 3, tzinfo=UTC)
        with self.assertRaisesRegex(Conflict, "VALIDATION_WINDOW_CLOSED"):
            self.claim(request)
        self.now = datetime(2026, 1, 2, tzinfo=UTC)
        self.ledger.release(request["request_id"], self.context, "confirmed-unsent", authorized)
        self.assertEqual(self.reserve(approval)["state"], "released")
        self.assertIsNone(self.claim(request))
        self.assertEqual(self.state()["remaining"]["units"], LIMIT.units)

        self.ledger.record_authority(
            self.context, "source:synthetic", "source.v1", "current", "fixture-terms", authorized,
        )
        self.ledger.record_authority(
            self.context, "restore-continuity", "restore.1", "restore_hold", "continuity-audit", authorized,
        )
        other_batch = self.draft()["batch_id"]
        with self.assertRaisesRegex(Conflict, "VALIDATION_RESTORE_HOLD"):
            self.approve(batch_id=other_batch)
        self.ledger.rebind_after_restore(self.context, "reviewed-continuity", authorized)
        self.assertEqual(self.state()["batch"]["state"], "revoked")
        fresh_batch = self.draft()["batch_id"]
        with self.assertRaisesRegex(Conflict, "VALIDATION_CREDENTIAL_CHANGED"):
            self.approve(batch_id=fresh_batch)
        with self.assertRaisesRegex(Conflict, "VALIDATION_CREDENTIAL_REVISION_RETIRED"):
            self.bind("search", "tavily", "fixture-search", "search-fixture", "search.v1")
        with self.assertRaisesRegex(Conflict, "VALIDATION_AUTHORITY_REVISION_RETIRED"):
            self.ledger.record_authority(
                self.context, "source:synthetic", "source.v1", "current", "fixture-terms", authorized,
            )
        self.ledger.record_authority(
            self.context, "source:synthetic", "source.v2", "current", "fresh-fixture-terms", authorized,
        )
        self.bind("search", "tavily", "fixture-search", "search-fixture", "search.v2")
        approval = self.approve(self.grant(credential_revision="search.v2"), batch_id=fresh_batch)
        self.assertIsNotNone(self.claim(self.reserve(approval)))

    def test_recheck_failure_and_revocation_keep_auditable_cost(self):
        request = self.reserve(self.approve())
        self.claim(request)

        def unavailable(db, batch, grant):
            raise RuntimeError("fixture authority unavailable")

        self.ledger.transition(self.batch_id, self.context, "revoked", "owner-revoked", authorized)
        receipt = self.receipt(request, unavailable)
        self.assertEqual((receipt["eligible"], receipt["actual_units"], receipt["reason"]), (0, 7, "authority_changed"))
        self.assertEqual(self.state()["batch"]["state"], "revoked")
        self.assertEqual(self.state()["requests"][0]["state"], "settled")
        self.assertEqual(self.state()["remaining"]["units"], 93)

    def test_overflow_freezes_and_survives_reconciliation(self):
        request = self.reserve(self.approve())
        self.claim(request)
        receipt = self.receipt(request, actual_units=12)
        self.assertEqual((receipt["eligible"], receipt["actual_units"], receipt["reason"]), (0, 12, "usage_over_budget"))
        self.assertEqual(self.state()["batch"]["state"], "reconciliation")
        with self.assertRaisesRegex(Conflict, "VALIDATION_RECONCILIATION_CONFLICT"):
            self.ledger.reconcile(request["request_id"], self.context, 11, "recon", "ledger-evidence", authorized)
        settlement = self.ledger.reconcile(
            request["request_id"], self.context, 12, "recon", "ledger-evidence", authorized,
        )
        self.assertEqual(settlement["actual_units"], 12)
        with self.assertRaisesRegex(Conflict, "VALIDATION_USAGE_OVER_BUDGET"):
            self.ledger.transition(self.batch_id, self.context, "approved", "cannot-resume", authorized)

    def test_restart_keeps_claim_unknown_and_prevents_resend(self):
        request = self.reserve(self.approve())
        self.claim(request)
        restarted = ValidationLedger(self.store, engineering_fixture=True, clock=lambda: self.now)
        self.assertEqual(restarted.recover(self.batch_id, self.context, authorized)["state"], "reconciliation")
        self.assertIsNone(restarted.claim(request["request_id"], self.context, authorized))
        self.assertEqual(self.state()["remaining"]["units"], 90)
        self.ledger.transition(self.batch_id, self.context, "revoked", "owner-revoked", authorized)
        settled = restarted.reconcile(request["request_id"], self.context, 8, "recon", "ledger-evidence", authorized)
        self.assertEqual(settled["actual_units"], 8)
        self.assertEqual(self.state()["batch"]["state"], "revoked")

    def test_duplicate_provider_receipt_freezes_original_claim(self):
        first = self.reserve(self.approve())
        self.claim(first)
        self.receipt(first, provider_request_id="fixture-provider-receipt")
        second_batch = self.draft()["batch_id"]
        second = self.reserve(self.approve(batch_id=second_batch))
        self.claim(second)
        duplicate = self.receipt(second, provider_request_id="fixture-provider-receipt")
        self.assertTrue(duplicate["conflict"])
        view = self.ledger.view(second_batch, self.context, authorized)
        self.assertEqual(view["batch"]["state"], "reconciliation")
        self.assertEqual(view["requests"][0]["state"], "reconciliation")
        self.assertEqual(view["remaining"]["units"], 90)

    def test_scope_view_rechecks_all_batches_under_one_snapshot(self):
        second_batch = self.draft()["batch_id"]
        checks = []

        def audit(db, batch, grant):
            self.assertTrue(db.in_transaction)
            checks.append((db, batch["batch_id"] if batch else None))
            return True

        views = self.ledger.views(self.context, audit)
        self.assertEqual([batch["batch"]["batch_id"] for batch in views], [second_batch, self.batch_id])
        self.assertEqual([batch for _, batch in checks], [None, second_batch, self.batch_id])
        self.assertTrue(all(db is checks[0][0] for db, _ in checks))
        self.assertEqual(self.ledger.views(replace(self.context, actor_ref="another-actor"), authorized), [])

    def test_dependency_is_same_batch_settled_receipt_with_bound_digest(self):
        first = self.reserve(self.approve())
        self.claim(first)
        self.bind("source", "stackexchange", "public-source", "source-fixture", "anonymous-first")
        source = self.grant(
            operation="source", provider="stackexchange", account_ref="public-source", channel_ref="source-fixture",
            credential_revision="anonymous-first", depends_on=first["request_id"], depends_on_sha256=RESPONSE,
        )
        with self.assertRaisesRegex(Conflict, "VALIDATION_DEPENDENCY_NOT_CURRENT"):
            self.approve(source)
        self.receipt(first)
        for wrong in (
            {"grant": replace(source, depends_on_sha256=SOURCE)},
            {"grant": source, "batch_id": self.draft()["batch_id"]},
        ):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(Conflict, "VALIDATION_DEPENDENCY_NOT_CURRENT"):
                self.approve(**wrong)
        second = self.reserve(self.approve(source), replace(ESTIMATE, credits=0))
        self.assertIsNotNone(self.claim(second))
        for requirement in REQUIREMENTS:
            self.ledger.add_evidence(self.batch_id, self.context, requirement, "synthetic_fixture",
                                     f"fixture-{requirement}", SOURCE, "fixture", authorized)
        self.receipt(second, credits=None)
        with self.assertRaisesRegex(Conflict, "VALIDATION_EVIDENCE_INCOMPLETE"):
            self.ledger.transition(self.batch_id, self.context, "evidence_review", "review", authorized)


if __name__ == "__main__":
    unittest.main()
