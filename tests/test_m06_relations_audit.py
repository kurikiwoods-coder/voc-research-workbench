"""C4 governance projections verified against isolated synthetic corpus data."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import unittest
from uuid import uuid4

import test_m06_mentions as c3
from src.raw_store.mention_segments import EvidenceInterval, MentionDraft, SupportDraft
from src.raw_store.relations import RelationGrant, RelationStore


class RelationAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = c3.MentionTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.bind_products(status="non_product")
        self.study = self.fixture.study
        self.grants = []
        self.fixture.case.app.state.relations = RelationStore(self.fixture.db, grants=lambda: self.grants)
        self.client = self.fixture.case.client
        self.path = f"/api/studies/{self.study}/mentions"

    def grant(self, role, *operations, evidence=None):
        instant = datetime.now(timezone.utc)
        return RelationGrant(
            actor_ref="synthetic-governance", role=role, granted_by="synthetic-owner", basis_ref="local:audit-test",
            starts_at=(instant - timedelta(days=1)).isoformat(), expires_at=(instant + timedelta(days=1)).isoformat(),
            operations=frozenset(operations), study_id=self.study, evidence_refs=evidence,
        )

    def tombstone(self, member, revision=1):
        return {"mention_id": member["mention_id"], "segment_revision": revision,
                "tombstone": True, "reason": "EVIDENCE_UNAVAILABLE"}

    def test_only_the_exact_current_audit_grant_unlocks_a_minimal_tombstone(self):
        f = self.fixture
        batch, interval = f.add_quote("revoked", "Synthetic private review marker")
        hidden_batch, hidden = f.add_quote("another", "Different synthetic quote")
        member, other = f.publish([f.member("revoked", interval), f.member("another", hidden)])["members"]
        ref = (1, member["mention_id"], member["evidence_ids"][0])
        scoped = frozenset({ref})
        auditor = self.grant("governance_reviewer", "read", "evidence", "audit", evidence=scoped)
        self.grants[:] = [auditor]
        detail = f"{self.path}/{ref[1]}"
        f.revoke_batch(batch)
        f.revoke_batch(hidden_batch)

        result = self.client.get(self.path, params={"segment_revision": 1})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["items"], [self.tombstone(member)])
        result = self.client.get(detail, params={"segment_revision": 1})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual({key: value for key, value in result.json().items() if key not in {"resolved_versions", "mode"}},
                         self.tombstone(member))
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get(f"{detail}/evidence/{ref[2]}", params={"segment_revision": 1}).status_code, 409)
        hidden_detail = self.client.get(f"{self.path}/{other['mention_id']}")
        missing_detail = self.client.get(f"{self.path}/{uuid4()}")
        self.assertEqual(hidden_detail.status_code, 404)
        self.assertEqual(hidden_detail.json(), missing_detail.json())

        for grant in (
            self.grant("researcher", "read", "evidence", "audit", evidence=scoped),
            replace(auditor, evidence_refs=frozenset({(2, ref[1], ref[2])})),
            replace(auditor, revoked_at=auditor.starts_at),
        ):
            with self.subTest(grant=grant):
                self.grants[:] = [self.grant("researcher", "read"), grant]
                self.assertEqual(self.client.get(detail).status_code, 404)
                self.assertEqual(self.client.get(self.path).json()["items"], [])

    def test_tombstones_do_not_resolve_withdrawn_metadata_filters(self):
        f = self.fixture
        batch, interval = f.add_quote("filtered")
        member = f.publish([f.member("withdrawn", interval)])["members"][0]
        self.grants[:] = [self.grant("governance_reviewer", "read", "audit")]
        f.revoke_batch(batch)
        for filters in (
            {"scope_id": f.scope, "scope_version": "v1"}, {"batch_id": batch}, {"source": "forum"},
            {"from": "2026-11-11"}, {"product_category_id": c3.PRODUCT_A},
        ):
            with self.subTest(filters=filters):
                self.assertEqual(self.client.get(self.path, params=filters).json()["items"], [])
                self.assertEqual(self.client.get(f"{self.path}/{member['mention_id']}", params=filters).status_code, 404)
        result = self.client.get(self.path, params={"mode": "formal"}).json()
        self.assertEqual(result["items"], [])
        self.assertIsNone(result["counts"])

    def test_surviving_evidence_suppresses_tombstone_even_outside_the_read_grant(self):
        f = self.fixture
        quote = "Synthetic source event with two imports"
        row = [quote, "forum", "https://synthetic.invalid/audit/event", *c3.fixtures.ROW[3:], "synthetic-event"]
        other = ["Independent synthetic extra row", "forum", "https://synthetic.invalid/audit/extra",
                 *c3.fixtures.ROW[3:], "extra-event"]
        columns = c3.fixtures.BASE + ["external_id"]
        batch, [first] = f.case.import_rows([row], columns=columns)
        second_batch, [second, _] = f.case.import_rows([row, other], columns=columns)
        for record in (first, second):
            f.case.verify(record)
        before = EvidenceInterval(first, sha256(quote.encode()).hexdigest(), 0, len(quote))
        supports = tuple(SupportDraft(interval, 1, "independent", c3.BASIS)
                         for interval in (before, replace(before, record_id=second)))
        member = f.publish([MentionDraft("event", supports)])["members"][0]
        ref = (1, member["mention_id"], member["evidence_ids"][0])
        self.grants[:] = [self.grant("governance_reviewer", "read", "audit", evidence=frozenset({ref}))]
        f.revoke_batch(batch)
        self.assertEqual(self.client.get(self.path).json()["items"], [])
        self.assertEqual(self.client.get(f"{self.path}/{ref[1]}").status_code, 404)
        self.grants[:] = [self.grant("governance_reviewer", "read", "audit")]
        [live] = self.client.get(self.path).json()["items"]
        self.assertEqual([item["evidence_id"] for item in live["evidence_refs"]], member["evidence_ids"][1:])
        self.assertNotIn("tombstone", live)
        f.revoke_batch(second_batch)
        self.assertEqual(self.client.get(self.path).json()["items"], [self.tombstone(member)])
