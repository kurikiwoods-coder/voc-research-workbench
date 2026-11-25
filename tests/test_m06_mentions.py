"""C3 acceptance with isolated synthetic sources imported and reviewed through M04/M05."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import sqlite3
from threading import Barrier
import unittest
from unittest.mock import patch

import test_corpus as fixtures
from test_m06_constraints import command, insert, registry, seal_registry
from src.raw_store.mentions import (
    EvidenceInterval, MentionDraft, MentionStore, ProductProposal, Replacement,
    ReviewDecision, SupportDraft,
)
from src.raw_store.store import Conflict


QUOTE = "想让秤🧪离线，导出e\u0301记录"
PRODUCT_A = "P-SCALE"
PRODUCT_B = "P-FRYER"
CATALOG = "1.0.0"
NEXT_CATALOG = "2.0.0"
BASIS = "local:synthetic-review"


class MentionTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.CorpusTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.study = self.case.study
        self.scope = self.case.scope
        self.db = self.case.app.state.store
        self.corpus = self.case.app.state.corpus
        self.permissions = {
            (self.study, permission): f"synthetic-{permission}"
            for permission in ("read", "segment", "identity", "product_review")
        }
        self.store = MentionStore(self.db, authorize=self.authorize)
        self.addCleanup(self.assert_integrity)

    def authorize(self, study, permission):
        return self.permissions.get((study, permission))

    def assert_integrity(self):
        self.assertEqual(self.rows("PRAGMA integrity_check"), [("ok",)])
        self.assertEqual(self.rows("PRAGMA foreign_key_check"), [])

    def add_quote(self, suffix, text=QUOTE, *, study=None, scope=None, reviewed=True, **review):
        row = [text, "forum", f"https://synthetic.invalid/post/{suffix}", *fixtures.ROW[3:]]
        batch, [record] = self.case.import_rows([row], study=study, scope=scope)
        if reviewed:
            payload = {
                "decision": "verified", "role": "user_quote", "reason": "合成来源人工审核",
                "basis": "已核对合成许可", "retention_until": self.case.retain,
                "license_status": "authorized", "license_evidence_ref": "local:synthetic-license",
            }
            self.corpus.review(study or self.study, record, **(payload | review))
        return batch, EvidenceInterval(record, sha256(text.encode()).hexdigest(), 0, len(text))

    def revoke_batch(self, batch):
        self.case.client.post(f"/api/imports/{self.study}/batches/{batch}/revoke").raise_for_status()

    def bind_products(self, products=(), *, status="mapped_product", revision=1, version=CATALOG, scope=None):
        # C3 consumes immutable bindings issued by the later scope workflow.
        scope = scope or self.scope
        with self.db.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM m06_registry WHERE registry_version=?", (version,)).fetchone() is None:
                registry(db, version, None if version == CATALOG else CATALOG)
                for product in (PRODUCT_A, PRODUCT_B):
                    insert(
                        db, "m06_product", registry_version=version, product_category_id=product,
                        name="同名合成品类", description="", parent_id=None, status="confirmed", version="1.0.0",
                    )
                seal_registry(db, version)
            ident = f"mapping-{scope}-{revision}"
            command(db, ident, self.study)
            for product in products:
                insert(
                    db, "m06_scope_product", study_id=self.study, scope_id=scope, mapping_revision=revision,
                    registry_version=version, product_category_id=product,
                )
            insert(
                db, "m06_scope_binding", study_id=self.study, scope_id=scope,
                mapping_revision=revision, previous_revision=revision - 1 or None,
                registry_version=version, mapping_status=status, scope_reviewer_ref="scope-review",
                catalog_reviewer_ref="catalog-review" if status != "unresolved" else None,
                basis_ref=BASIS, command_id=ident,
            )

    def rows(self, sql, values=()):
        with self.db.db() as db:
            return [tuple(row) for row in db.execute(sql, values)]

    def revision_rows(self):
        return self.rows(
            "SELECT segment_revision, parent_rev, sealed FROM m06_segment_rev WHERE study_id=? ORDER BY 1",
            (self.study,),
        )

    def counts(self):
        return tuple(self.rows(f"SELECT count(*) FROM {table}")[0][0] for table in (
            "m06_command", "m06_segment_rev", "m06_mention", "m06_evidence",
            "m06_member", "m06_support", "m06_replacement", "m06_mention_product", "m06_product_review",
        ))

    @staticmethod
    def member(ref, interval, *, segment_no=1, identity="independent", mention_id=None, contexts=()):
        return MentionDraft(ref, (SupportDraft(interval, segment_no, identity, BASIS, contexts),), mention_id)

    @staticmethod
    def proposal(ref, interval, product=PRODUCT_A, **options):
        args = {
            "mapping_revision": 1, "catalog_version": CATALOG, "basis_ref": BASIS,
            "rule_version": "synthetic-product-v1",
        } | options
        return ProductProposal(ref, interval, product_category_id=product, **args)

    @staticmethod
    def decision(member, product=PRODUCT_A, **options):
        args = {
            "mapping_revision": 1, "catalog_version": CATALOG, "expected_sequence": 1,
            "decision": "human_confirmed", "basis_ref": BASIS,
        } | options
        return ReviewDecision(member["mention_id"], member["evidence_ids"][0], product_category_id=product, **args)

    def publish(self, members, *, key="initial", expected=0, rule="synthetic-segments-v1", study=None, **extras):
        return self.store.publish_revision(
            study or self.study, key=key, expected_revision=expected, rule_version=rule, members=tuple(members),
            **extras,
        )

    def review(self, *decisions, key="review", expected=1):
        return self.store.review_products(self.study, key=key, expected_revision=expected, decisions=decisions)

    def read_evidence(self, member, index=0, revision=1, study=None):
        return self.store.read_evidence(
            study or self.study, revision, member["mention_id"], member["evidence_ids"][index],
        )

    def test_unicode_coordinates_replay_and_split_merge_keep_the_original_revision(self):
        _, full = self.add_quote("unicode")
        whole = self.publish([self.member("whole", full)])["members"][0]
        left = replace(full, start_cp=3, end_cp=7)
        right = replace(full, start_cp=8)
        members = [self.member("left", left), self.member("right", right, segment_no=2)]
        split = tuple(Replacement(whole["mention_id"], member.ref, "split") for member in members)

        with self.assertRaises(Conflict):
            self.publish(members, key="missing-lineage", expected=1)
        self.assertEqual(self.revision_rows(), [(1, None, 1)])
        result = self.publish(members, key="split", expected=1, rule="synthetic-segments-v2", replacements=split)
        self.assertEqual(self.publish(
            members, key="split", expected=1, rule="synthetic-segments-v2", replacements=split,
        ), result)
        self.assertEqual(self.revision_rows(), [(1, None, 1), (2, 1, 1)])
        self.assertEqual(len({whole["mention_id"], *(m["mention_id"] for m in result["members"])}), 3)
        for member, interval in zip(result["members"], [left, right], strict=True):
            self.assertEqual(self.read_evidence(member, revision=2)["excerpt"], QUOTE[interval.start_cp:interval.end_cp])

        merge = tuple(Replacement(m["mention_id"], "combined", "merge") for m in result["members"])
        merged = self.publish(
            [self.member("combined", full)], key="merge", expected=2, replacements=merge,
        )["members"][0]
        self.assertNotIn(merged["mention_id"], {whole["mention_id"], *(m["mention_id"] for m in result["members"])})
        self.assertEqual(merged["evidence_ids"], whole["evidence_ids"])
        self.assertEqual(self.read_evidence(whole)["excerpt"], QUOTE)
        self.assertEqual(self.rows(
            "SELECT segment_revision, old_rev, reason, COUNT(*) FROM m06_replacement GROUP BY 1,2,3 ORDER BY 1",
        ), [(2, 1, "split", 2), (3, 2, "merge", 2)])

    def test_equal_text_repost_and_disputed_identity_survive_dedupe_group_primary_change(self):
        text = fixtures.QUOTE
        original_batch, original = self.add_quote("original", text)
        _, peer = self.add_quote("independent", text)
        _, disputed = self.add_quote("unresolved-repost", text)
        _, repost = self.add_quote("confirmed-repost", text)
        self.assertEqual(
            self.corpus.qualified_record(self.study, peer.record_id)["duplicate"]["canonical_record_id"],
            original.record_id,
        )
        confirmed = MentionDraft("original", (
            SupportDraft(original, 1, "independent", BASIS),
            SupportDraft(repost, 1, "repost", BASIS, original=original),
        ))
        separate = self.member("independent", peer)
        waiting = self.member("disputed", disputed, identity="disputed")
        result = self.publish([confirmed, separate, waiting])
        first, second, third = result["members"]
        self.assertEqual(len({m["mention_id"] for m in result["members"]}), 3)
        self.assertEqual(len(first["evidence_ids"]), 2)
        self.assertEqual(self.rows("SELECT identity_state, COUNT(*) FROM m06_member GROUP BY 1 ORDER BY 1"), [
            ("distinct", 2), ("needs_review", 1),
        ])
        self.assertEqual(self.read_evidence(first, index=1)["excerpt"], text)

        self.revoke_batch(original_batch)
        self.assertNotEqual(
            self.corpus.qualified_record(self.study, peer.record_id)["duplicate"]["canonical_record_id"],
            original.record_id,
        )
        kept = replace(separate, mention_id=second["mention_id"])
        pending = replace(waiting, mention_id=third["mention_id"])
        updated = self.publish([kept, pending], key="new-revision", expected=1)
        self.assertEqual(updated["members"], [second, third])
        self.assertEqual(self.read_evidence(second, revision=2)["excerpt"], text)

    def test_invalid_digest_span_pending_or_foreign_source_rolls_back_revision(self):
        _, valid = self.add_quote("valid")
        _, pending = self.add_quote("pending", reviewed=False)
        other, other_scope = self.case.project()
        _, foreign = self.add_quote("foreign", study=other, scope=other_scope)
        start = self.counts()
        for bad in (replace(valid, raw_sha256="0" * 64), replace(valid, end_cp=len(QUOTE) + 1), pending, foreign):
            with self.subTest(bad=bad), self.assertRaises((Conflict, KeyError, ValueError)):
                self.publish([self.member("valid", valid), self.member("invalid", bad, segment_no=2)])
            self.assertEqual(self.counts(), start)
        self.assertEqual(self.publish([self.member("valid", valid)])["revision"], 1)

    def test_product_proposal_uses_exact_frozen_scope_binding_and_catalog(self):
        self.bind_products((PRODUCT_A,))
        self.bind_products((PRODUCT_B,), revision=2, version=NEXT_CATALOG)
        _, interval = self.add_quote("exact-product")
        members = [self.member("whole", interval)]
        start = self.counts()
        for proposal in (
            self.proposal("whole", interval, PRODUCT_B),
            self.proposal("whole", interval, PRODUCT_B, catalog_version=NEXT_CATALOG),
            self.proposal("whole", interval, PRODUCT_A, mapping_revision=2, catalog_version=NEXT_CATALOG),
        ):
            with self.subTest(proposal=proposal), self.assertRaises((Conflict, ValueError, KeyError)):
                self.publish(members, proposals=(proposal,))
            self.assertEqual(self.counts(), start)

        old = self.proposal("whole", interval)
        new = self.proposal("whole", interval, PRODUCT_B, mapping_revision=2, catalog_version=NEXT_CATALOG)
        first = self.publish(members, proposals=(old,))
        second = self.publish(
            [replace(members[0], mention_id=first["members"][0]["mention_id"])],
            key="next-mapping", expected=1, proposals=(new,),
        )
        self.assertEqual(first["members"], second["members"])
        self.assertEqual(self.rows(
            "SELECT segment_revision, catalog_version, product_category_id FROM m06_mention_product ORDER BY 1",
        ), [(1, CATALOG, PRODUCT_A), (2, NEXT_CATALOG, PRODUCT_B)])

    def test_non_product_scope_has_occurrences_and_no_invented_product_edge(self):
        self.bind_products(status="non_product")
        _, interval = self.add_quote("open-research", "希望社区活动可以延期报名")
        member = self.member("community", interval)
        with self.assertRaises((Conflict, ValueError)):
            self.publish([member], proposals=(self.proposal("community", interval),))
        result = self.publish([member])
        self.assertEqual(len(result["members"]), 1)
        self.assertEqual(self.rows("SELECT * FROM m06_mention_product"), [])
        self.assertEqual(self.rows("SELECT * FROM m06_product_review"), [])

    def test_two_supported_products_have_independent_human_decisions_and_replay_once(self):
        self.bind_products((PRODUCT_A, PRODUCT_B))
        _, interval = self.add_quote("two-products", "P-SCALE 和 P-FRYER 都希望能导出操作记录。")
        result = self.publish([self.member("whole", interval)], proposals=(
            self.proposal("whole", interval), self.proposal("whole", interval, PRODUCT_B),
        ))
        member = result["members"][0]
        decisions = (self.decision(member), self.decision(member, PRODUCT_B))
        self.assertEqual(self.rows(
            "SELECT product_category_id, decision FROM m06_product_review ORDER BY 1",
        ), [(PRODUCT_B, "proposed"), (PRODUCT_A, "proposed")])
        approved = self.review(*decisions)
        self.assertEqual(self.review(*decisions), approved)
        self.assertEqual(self.rows("""
            SELECT decision_seq, decision, mode, actor_ref, COUNT(*) FROM m06_product_review
            WHERE decision='human_confirmed' GROUP BY 1,2,3,4
        """), [(2, "human_confirmed", "A", "synthetic-product_review", 2)])
        with self.assertRaises(Conflict):
            self.review(decisions[0], replace(decisions[1], basis_ref="local:different-review"))
        suspended = replace(decisions[0], expected_sequence=2, decision="suspended")
        self.review(suspended, key="suspend")
        self.assertEqual(self.rows("""
            SELECT product_category_id, decision FROM m06_product_review AS r
            WHERE decision_seq=(SELECT MAX(p.decision_seq) FROM m06_product_review p
                                WHERE p.product_category_id=r.product_category_id)
            ORDER BY 1
        """), [(PRODUCT_B, "human_confirmed"), (PRODUCT_A, "suspended")])

    def test_review_batch_rolls_back_when_any_edge_is_stale_ambiguous_or_repeated(self):
        self.bind_products((PRODUCT_A, PRODUCT_B))
        _, interval = self.add_quote("batch", "秤和炸锅都希望能导出操作记录。")
        result = self.publish([self.member("whole", interval)], proposals=(
            self.proposal("whole", interval), self.proposal("whole", interval, PRODUCT_B),
        ))
        first = self.decision(result["members"][0])
        second = self.decision(result["members"][0], PRODUCT_B)
        start = self.counts()
        for decisions in (
            (first, replace(second, expected_sequence=0)),
            (first, replace(second, relation="comparison")),
            (first, first),
        ):
            with self.subTest(decisions=decisions), self.assertRaises((Conflict, ValueError)):
                self.review(*decisions)
            self.assertEqual(self.counts(), start)
        self.review(first, second)
        self.assertEqual(self.counts()[-1], start[-1] + 2)

    def test_review_batch_rechecks_withdrawn_support_and_retains_independent_edge(self):
        self.bind_products((PRODUCT_A, PRODUCT_B))
        _, independent = self.add_quote("retained")
        withdrawn_batch, withdrawn = self.add_quote("withdrawn", "希望能用炸锅导出操作记录。")
        result = self.publish(
            [self.member("retained", independent), self.member("withdrawn", withdrawn)],
            proposals=(self.proposal("retained", independent), self.proposal("withdrawn", withdrawn, PRODUCT_B)),
        )
        first, second = result["members"]
        self.revoke_batch(withdrawn_batch)
        start = self.counts()
        with self.assertRaises(Conflict):
            self.review(self.decision(first), self.decision(second, PRODUCT_B))
        self.assertEqual(self.counts(), start)
        with self.assertRaises((Conflict, KeyError)):
            self.read_evidence(second)
        self.assertEqual(self.read_evidence(first)["excerpt"], QUOTE)
        visible = self.store.read_revision(self.study)
        self.assertEqual([m["mention_id"] for m in visible["members"]], [first["mention_id"]])
        self.review(self.decision(first))
        self.assertEqual(self.counts()[-1], start[-1] + 1)

    def test_missing_authorization_and_revoked_replay_permission_leave_storage_unchanged(self):
        _, interval = self.add_quote("authorization")
        members = [self.member("whole", interval)]
        blocked = MentionStore(self.db)
        start = self.counts()
        with self.assertRaises((KeyError, PermissionError)):
            blocked.publish_revision(
                self.study, key="initial", expected_revision=0, rule_version="synthetic-v1", members=members,
            )
        self.assertEqual(self.counts(), start)
        result = self.publish(members)
        saved = self.counts()
        self.permissions.pop((self.study, "segment"))
        with self.assertRaises((KeyError, PermissionError)):
            self.publish(members)
        self.permissions.pop((self.study, "read"))
        with self.assertRaises((KeyError, PermissionError)):
            self.read_evidence(result["members"][0])
        self.assertEqual(self.counts(), saved)

    def test_two_concurrent_revisions_from_same_head_create_one_version_and_one_command(self):
        _, lhs = self.add_quote("concurrent-left")
        _, rhs = self.add_quote("concurrent-right")
        gate = Barrier(2)

        def attempt(key, interval):
            gate.wait(timeout=10)
            try:
                return self.publish([self.member(key, interval)], key=key)
            except Conflict:
                return None

        with ThreadPoolExecutor(2) as workers:
            attempts = [workers.submit(attempt, key, interval) for key, interval in (("left", lhs), ("right", rhs))]
            results = [attempt.result(timeout=15) for attempt in attempts]
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self.revision_rows(), [(1, None, 1)])
        self.assertEqual(self.counts()[:6], (1, 1, 1, 1, 1, 1))

    def test_replay_after_later_head_preserves_ids_and_rejects_changed_input(self):
        _, interval = self.add_quote("replay")
        original = self.member("whole", interval)
        first = self.publish([original])
        revised = replace(original, mention_id=first["members"][0]["mention_id"])
        second = self.publish([revised], key="next", expected=1)
        self.assertEqual(second["members"], first["members"])
        self.assertEqual(self.publish([original]), first)
        start = self.counts()
        with self.assertRaises(Conflict):
            self.publish([original], rule="changed-serialization")
        with self.assertRaises(Conflict):
            self.publish([original], key="different-command")
        self.assertEqual(self.counts(), start)

    def test_context_only_interval_is_persisted_and_its_withdrawal_masks_dependent_evidence(self):
        _, occurrence = self.add_quote("occurrence")
        context_batch, context = self.add_quote("context", "这里提到的设备指营养秤。")
        full_context = context
        context = replace(context, start_cp=2, end_cp=10)
        result = self.publish([self.member("whole", occurrence, contexts=(context,))])
        member = result["members"][0]
        visible = self.read_evidence(member)
        self.assertEqual(visible["excerpt"], QUOTE)
        self.assertEqual(visible["source_url"], "https://synthetic.invalid/post/occurrence")
        self.assertEqual(len(visible["contexts"]), 1)
        self.assertNotIn(visible["contexts"][0], member["evidence_ids"])
        self.assertEqual(self.rows(
            "SELECT start_cp, end_cp FROM m06_evidence WHERE evidence_id=?", (visible["contexts"][0],),
        ), [(context.start_cp, context.end_cp)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM m06_support"), [(1,)])
        self.revoke_batch(context_batch)
        self.assertTrue(self.corpus.qualified_record(self.study, occurrence.record_id)["engineering_eligible"])
        with self.assertRaises(Conflict):
            self.corpus.qualified_record(self.study, full_context.record_id)
        with self.assertRaises((Conflict, KeyError)):
            self.read_evidence(member)
        self.assertEqual(self.store.read_revision(self.study)["members"], [])

    def test_utc_day_change_before_commit_rolls_back_even_when_lease_is_still_current(self):
        _, interval = self.add_quote("utc-boundary")
        draft = self.member("whole", interval)
        start = self.counts()
        before = "2026-11-25T23:59:59.999+00:00"
        after = "2026-11-26T00:00:00.000+00:00"
        with (
            patch("src.raw_store.corpus.now", side_effect=[before, before, after]),
            self.assertRaises(Conflict),
        ):
            self.publish([draft])
        self.assertEqual(self.counts(), start)
        self.assertEqual(self.publish([draft])["revision"], 1)

    def test_one_quote_supports_two_purposes_and_coordinate_correction_keeps_id(self):
        _, full = self.add_quote("purpose", "Weigh offline 🧪。也导出e\u0301记录。")
        left = replace(full, end_cp=15)
        right = replace(full, start_cp=16)
        initial = [self.member("offline", left), self.member("export", right, segment_no=2)]
        first, second = self.publish(initial)["members"]
        corrected = replace(left, start_cp=6)
        next_version = self.publish([
            self.member("offline", corrected, mention_id=first["mention_id"]),
            self.member("export", right, segment_no=2),
        ], expected=1, key="correction")["members"]
        self.assertEqual(next_version[0]["mention_id"], first["mention_id"])
        self.assertNotEqual(next_version[0]["evidence_ids"], first["evidence_ids"])
        self.assertEqual(second, next_version[1])
        self.assertEqual(self.read_evidence(second)["excerpt"], "也导出e\u0301记录。")
        self.assertEqual(self.read_evidence(next_version[0], revision=2)["excerpt"], "offline 🧪")
        with self.assertRaises(KeyError):
            self.read_evidence(next_version[0])

    def test_unresolved_mapping_and_ambiguous_edge_require_human_review(self):
        self.bind_products(status="unresolved")
        _, interval = self.add_quote("ambiguous-product", "秤或炸锅，设备仍需核实。")
        draft = self.member("ambiguous", interval)
        self.assertEqual(self.store.read_scope_mapping(self.study, self.scope)["mapping_status"], "unresolved")
        with self.assertRaises(Conflict):
            self.publish([draft], proposals=(self.proposal("ambiguous", interval),))
        self.bind_products((PRODUCT_A, PRODUCT_B), revision=2, version=NEXT_CATALOG)
        proposal = self.proposal(
            "ambiguous", interval, mapping_revision=2, catalog_version=NEXT_CATALOG, relation="ambiguous",
        )
        member = self.publish([draft], proposals=(proposal,))["members"][0]
        [edge] = self.store.read_revision(self.study)["members"][0]["products"]
        self.assertEqual(edge["decision"], "queued")
        self.assertFalse(edge["effective"])
        decision = self.decision(
            member, mapping_revision=2, catalog_version=NEXT_CATALOG, relation="ambiguous",
        )
        with self.assertRaises(Conflict):
            self.review(decision)
        self.assertEqual(self.counts()[-1], 1)

    def test_review_version_and_cross_project_support_are_checked(self):
        _, interval = self.add_quote("project")
        [member] = self.publish([self.member("native", interval)])["members"]
        other, scope = self.case.project()
        self.permissions.update({(other, p): f"other-{p}" for p in ("read", "segment", "identity")})
        _, alternate = self.add_quote("foreign-project", study=other, scope=scope)
        self.publish([self.member("foreign", alternate)], study=other)
        with self.assertRaises(KeyError):
            self.read_evidence(member, study=other)
        with self.assertRaises(KeyError):
            self.read_evidence(member, revision=2)

    def test_all_evidence_withdrawn_masks_history_and_command_replay(self):
        batch, interval = self.add_quote("all-withdrawn")
        draft = self.member("whole", interval)
        [member] = self.publish([draft])["members"]
        self.revoke_batch(batch)
        start = self.counts()
        self.assertEqual(self.store.read_revision(self.study, 1)["members"], [])
        with self.assertRaises(Conflict):
            self.read_evidence(member)
        with self.assertRaises(Conflict):
            self.publish([draft])
        self.assertEqual(self.counts(), start)

    def test_read_discards_an_older_wal_snapshot_when_withdrawal_commits(self):
        batch, interval = self.add_quote("wal-read-withdrawal")
        [member] = self.publish([self.member("whole", interval)])["members"]
        qualify = self.store.corpus.qualified_record_in_transaction

        def withdraw_then_read(*args, **kwargs):
            self.revoke_batch(batch)
            return qualify(*args, **kwargs)

        with patch.object(self.store.corpus, "qualified_record_in_transaction", side_effect=withdraw_then_read):
            with self.assertRaises(Conflict):
                self.read_evidence(member)
        with self.assertRaises(Conflict):
            self.read_evidence(member)

    def test_withdrawal_after_preflight_rejects_write_under_lock(self):
        batch, interval = self.add_quote("after-preflight")
        self.assertTrue(self.corpus.qualified_record(self.study, interval.record_id)["engineering_eligible"])
        self.revoke_batch(batch)
        start = self.counts()
        with self.assertRaises(Conflict):
            self.publish([self.member("whole", interval)])
        self.assertEqual(self.counts(), start)

    def test_failure_at_sqlite_final_commit_rolls_back_the_whole_command(self):
        _, interval = self.add_quote("commit-abort")
        with self.db.db() as db:
            db.executescript("""
                CREATE TABLE commit_parent (id INTEGER PRIMARY KEY);
                CREATE TABLE commit_child (parent_id INTEGER REFERENCES commit_parent(id)
                    DEFERRABLE INITIALLY DEFERRED);
            """)
        trace = []
        connect = self.db.connect

        class CommitFault:
            def __init__(self, db):
                self.db = db

            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    self.db.execute("INSERT INTO commit_child VALUES (17)")
                return self.db.execute(sql, parameters)

            def __getattr__(self, name):
                return getattr(self.db, name)

        def connection_with_commit_fault():
            db = connect()
            db.set_trace_callback(trace.append)
            return CommitFault(db)

        start = self.counts()
        draft = self.member("whole", interval)
        with patch.object(self.db, "connect", side_effect=connection_with_commit_fault):
            with self.assertRaises(sqlite3.IntegrityError) as failure:
                self.publish([draft])
        self.assertEqual(failure.exception.sqlite_errorcode, sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY)
        self.assertIn("COMMIT", trace)
        self.assertIn("ROLLBACK", trace[trace.index("COMMIT") + 1:])
        self.assertEqual(self.counts(), start)
        self.assertEqual(self.rows("SELECT count(*) FROM commit_child"), [(0,)])
        self.assertEqual(self.publish([draft])["revision"], 1)

    def test_seal_refuses_a_deferred_orphan_left_by_an_earlier_statement(self):
        _, interval = self.add_quote("orphan-before-seal")
        with self.db.db() as db:
            db.executescript("""
                CREATE TABLE commit_parent (id INTEGER PRIMARY KEY);
                CREATE TABLE commit_child (parent_id INTEGER REFERENCES commit_parent(id)
                    DEFERRABLE INITIALLY DEFERRED);
                CREATE TRIGGER fail_segment_commit AFTER INSERT ON m06_support
                BEGIN INSERT INTO commit_child VALUES (17); END;
            """)
        start = self.counts()
        draft = self.member("whole", interval)
        with self.assertRaises(sqlite3.IntegrityError):
            self.publish([draft])
        self.assertEqual(self.counts(), start)
        self.assertEqual(self.rows("SELECT count(*) FROM commit_child"), [(0,)])
        with self.db.db() as db:
            db.execute("DROP TRIGGER fail_segment_commit")
        self.assertEqual(self.publish([draft])["revision"], 1)

    def test_regrant_requires_a_new_product_decision_and_leaves_independent_decision_active(self):
        self.bind_products((PRODUCT_A, PRODUCT_B))
        _, first = self.add_quote("product-regrant", "P-SCALE 可以导出记录。")
        _, second = self.add_quote("product-independent", "P-FRYER 也需要导出。")
        accepted = self.publish(
            [self.member("scale", first), self.member("fryer", second)],
            proposals=(self.proposal("scale", first), self.proposal("fryer", second, PRODUCT_B)),
        )["members"]
        review = self.decision(accepted[0])
        self.review(review, self.decision(accepted[1], PRODUCT_B))
        self.case.verify(first.record_id, decision="excluded", license_status="revoked")
        self.assertEqual(len(self.store.read_revision(self.study)["members"]), 1)
        day = self.rows("SELECT reviewed_at FROM corpus_withdrawals WHERE record_id=?", (first.record_id,))[0][0][:10]
        self.case.verify(first.record_id, reauthorize=True, license_issued_on=day,
                         license_evidence_ref="local:synthetic-new-grant")
        states = {
            m["products"][0]["product_category_id"]: m["products"][0]["effective"]
            for m in self.store.read_revision(self.study)["members"]
        }
        self.assertEqual(states, {PRODUCT_A: False, PRODUCT_B: True})
        self.review(replace(review, expected_sequence=2), key="confirm-new-grant")
        self.assertTrue(all(m["products"][0]["effective"] for m in self.store.read_revision(self.study)["members"]))

    def test_repost_read_requires_its_originals_context(self):
        _, original = self.add_quote("rep-original")
        _, repost = self.add_quote("rep-copy")
        batch, context = self.add_quote("rep-original-context", "前文交代用户在说营养秤。")
        draft = MentionDraft("repost", (
            SupportDraft(original, 1, "independent", BASIS, contexts=(context,)),
            SupportDraft(repost, 1, "repost", BASIS, original=original),
        ))
        [member] = self.publish([draft])["members"]
        self.assertEqual(self.read_evidence(member, index=1)["excerpt"], QUOTE)
        self.revoke_batch(batch)
        with self.assertRaises(Conflict):
            self.read_evidence(member, index=1)
        self.assertEqual(self.store.read_revision(self.study)["members"], [])

    def test_same_source_event_in_new_import_reuses_mention_but_has_an_independent_evidence_id(self):
        row = [QUOTE, "forum", "https://synthetic.invalid/event/7", *fixtures.ROW[3:], "synthetic-event-7"]
        columns = fixtures.BASE + ["external_id"]
        first_batch, [first] = self.case.import_rows([row], columns=columns)
        _, records = self.case.import_rows([row, [
            "第二条合成夹具，确保上传文件不同。", "forum", "https://synthetic.invalid/event/8",
            *fixtures.ROW[3:], "synthetic-event-8",
        ]], columns=columns)
        second = records[0]
        self.assertNotEqual(first, second)
        for record_id in (first, second):
            self.case.verify(record_id)
        digest = sha256(QUOTE.encode()).hexdigest()
        old = EvidenceInterval(first, digest, 0, len(QUOTE))
        new = replace(old, record_id=second)
        [parent] = self.publish([self.member("original", old)])["members"]
        with self.assertRaises(Conflict):
            self.publish([self.member("duplicate", new), self.member("original", old)], expected=1, key="duplicate")
        [child] = self.publish([self.member("reimport", new)], expected=1, key="reimport")["members"]
        self.assertEqual(child["mention_id"], parent["mention_id"])
        self.assertNotEqual(child["evidence_ids"], parent["evidence_ids"])
        self.assertEqual(self.read_evidence(child, revision=2)["excerpt"], QUOTE)
        self.revoke_batch(first_batch)
        self.assertEqual(self.read_evidence(child, revision=2)["excerpt"], QUOTE)
        with self.assertRaises(Conflict):
            self.read_evidence(parent)

    def test_context_withdrawal_inside_publication_rolls_back_supports_and_governance(self):
        _, main = self.add_quote("main")
        batch, context = self.add_quote("withdraw-in-write", "前文说明这里指营养秤。")
        with self.db.db() as db:
            db.execute("""CREATE TRIGGER lose_context AFTER INSERT ON m06_support BEGIN
                UPDATE import_batches SET revoked_at='2026-11-25T01:02:03+00:00'
                WHERE batch_id=(SELECT batch_id FROM import_rows
                                WHERE record_id=(SELECT record_id FROM m06_evidence
                                                 WHERE evidence_id=json_extract(NEW.occurrence_basis, '$.contexts[0]')));
                END""")
        start = self.counts()
        draft = self.member("dependent", main, contexts=(context,))
        with self.assertRaises(Conflict):
            self.publish([draft])
        self.assertEqual(self.counts(), start)
        self.assertEqual(self.rows("SELECT revoked_at FROM import_batches WHERE batch_id=?", (batch,)), [(None,)])
        with self.db.db() as db:
            db.execute("DROP TRIGGER lose_context")
        self.assertEqual(self.publish([draft])["revision"], 1)
