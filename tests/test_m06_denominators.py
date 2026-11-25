"""C5 accounting cross-checks with M04/M05 and C3/C4 synthetic fixtures."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from src.raw_store import denominators
from src.raw_store.mention_segments import EvidenceInterval, MentionDraft, SupportDraft
from src.raw_store.mentions import MentionStore, _dependencies, _get_support, _grants
from src.raw_store.relations import RelationStore
import test_corpus as corpus_fixture
import test_m06_mentions as mention_fixture
import test_m06_relations_queries as relation_fixture
from test_m06_constraints import insert, registry, seal_registry


BUCKETS = (
    "published_classified", "none_unknown", "review_pending", "partial_or_schema_gap", "pending_parent", "other_pending",
)


class DenominatorTests(TestCase):
    def setUp(self):
        self.scenario = self.enterContext(denominators.synthetic_database())
        store = self.scenario.store
        self.grants = []
        self.corpus = corpus_fixture.CorpusTests()
        self.corpus.settings = Settings(store.directory)
        self.corpus.app = create_app(self.corpus.settings, relation_grants=lambda: self.grants)
        self.corpus.client = self.enterContext(TestClient(
            self.corpus.app, base_url=corpus_fixture.ORIGIN, client=("127.0.0.1", 29205), headers=corpus_fixture.HEADERS,
        ))
        self.study, self.scope = self.corpus.project()
        self.corpus.study, self.corpus.scope = self.study, self.scope
        self.corpus.root = f"/api/corpus/{self.study}"
        self.corpus.retain = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
        self.mentions = mention_fixture.MentionTests()
        self.mentions.case = self.corpus
        self.mentions.study, self.mentions.scope = self.study, self.scope
        self.mentions.db = store
        self.mentions.corpus = self.corpus.app.state.corpus
        self.mentions.permissions = {
            (self.study, operation): f"synthetic-{operation}"
            for operation in ("read", "segment", "identity", "product_review")
        }
        self.mentions.store = MentionStore(store, authorize=self.mentions.authorize)
        self.definitions = relation_fixture.RelationQueryTests()
        self.definitions.fixture = self.mentions
        self.definitions.study = self.study
        self.grants = [self.definitions.grant("project_reviewer", "read", "evidence", "attribute")]
        self.relations = RelationStore(store, grants=lambda: self.grants)
        self.definitions.relations = self.relations
        self.addCleanup(self.mentions.assert_integrity)

    def add_quote(self, name, text=None, *, source="forum", date="2026-11-11", scope=None, reviewed=True):
        text = text or f"Synthetic need {name}."
        batch, [record] = self.corpus.import_rows(
            [[text, source, f"https://synthetic.invalid/{name}", date, "Synthetic license", "public"]], scope=scope,
        )
        if reviewed:
            self.corpus.verify(record)
        return batch, EvidenceInterval(record, sha256(text.encode()).hexdigest(), 0, len(text))

    def publish(self, drafts, *, proposals=()):
        members = self.mentions.publish(drafts, proposals=proposals)["members"]
        self.definitions.seal_definitions(members[:3], parent=mention_fixture.CATALOG)
        return members

    def seed(self, count=3):
        self.mentions.bind_products(status="non_product")
        quotes = [self.add_quote(f"need-{number}") for number in range(count)]
        members = self.publish([self.mentions.member(f"need-{number}", quote) for number, (_, quote) in enumerate(quotes)])
        return quotes, members

    def decision(self, member, *, indexes=(0,), **changes):
        dependencies = {}
        with self.scenario.store.db() as db:
            for index in indexes:
                evidence = member["evidence_ids"][index]
                support = _get_support(db, self.study, 1, member["mention_id"], evidence)
                dependencies.update(_dependencies(db, self.study, 1, member["mention_id"], support))
            grants = _grants(db, dependencies)
        decision = denominators.SyntheticDecision(**({
            "registry_version": relation_fixture.VERSION, "segment_revision": 1,
            "evidence_grants": grants, "choice": relation_fixture.INTENT, "noul": True,
        } | changes))
        self.scenario.decisions[member["mention_id"]] = (decision,)
        return decision

    def discover(self, member, intent, *, context_ids=()):
        command_id = f"fixture-discovery-{member['mention_id']}"
        evidence = member["evidence_ids"][0]
        key = {"study_id": self.study, "segment_revision": 1, "mention_id": member["mention_id"],
               "registry_version": relation_fixture.VERSION, "seq": 1}
        with self.scenario.store.db() as db:
            insert(db, "m06_command", command_id=command_id, study_id=self.study, namespace=f"study:{self.study}",
                   operation="fixture_discovery", idempotency_key=command_id, input_hash="a" * 64,
                   actor_ref="synthetic-reviewer", reason="synthetic discovery review",
                   created_at=datetime.now(UTC).isoformat(), result_ref="{}")
            insert(db, "m06_discovery_review", **key, intent_id=intent, review_state="accepted",
                   reason_code="fixture", command_id=command_id)
            insert(db, "m06_discovery_input", **key, evidence_id=evidence, dependency_role="occurrence", target_e=evidence)
            for context_id in context_ids:
                insert(db, "m06_discovery_input", **key, evidence_id=context_id, dependency_role="context", target_e=None)

    def stats(self, *, filters=None, mode="synthetic", **versions):
        return self.relations.denominators(
            self.study, filters=filters, mode=mode,
            **({"synthetic": self.scenario} if mode == "synthetic" else {}), **versions,
        )

    def assert_totals(self, result, *, eligible, published=0, buckets=None):
        self.assertEqual(result["availability"], "available", result)
        counts = result["counts"]
        self.assertEqual(counts["N_eligible_dedup"], eligible)
        if result["mode"] == "engineering":
            self.assertEqual(published, 0)
            self.assertIsNone(counts["N_published_classified"])
            self.assertIn("M12_RECEIPTS_MISSING", result["coverage"]["N_published_classified"])
        else:
            self.assertEqual(counts["N_published_classified"], published)
        self.assertEqual(counts["buckets"]["published_classified"], published)
        self.assertEqual(sum(counts["buckets"].values()), eligible)
        self.assertEqual(sum(row["count"] for row in result["by_primary_category"]), published)
        self.assertEqual(result["reconciliation"]["eligible_difference"], 0)
        self.assertEqual(result["reconciliation"]["primary_difference"], 0)
        if buckets is not None:
            self.assertEqual(counts["buckets"], dict.fromkeys(BUCKETS, 0) | buckets)

    def test_a_one_quote_two_occurrences_and_b_multiple_supports(self):
        self.mentions.bind_products(status="non_product")
        text = "First synthetic purpose. Second synthetic purpose."
        split = text.index("Second")
        _, original = self.add_quote("two-purposes", text)
        _, repost = self.add_quote("confirmed-repost", text, source="reddit")
        first, second = replace(original, end_cp=split), replace(original, start_cp=split)
        duplicate = replace(repost, end_cp=split)
        _, representative = self.add_quote("representative")
        members = self.publish([
            MentionDraft("first", (SupportDraft(first, 1, "independent", mention_fixture.BASIS),
                                   SupportDraft(duplicate, 1, "repost", mention_fixture.BASIS, original=first))),
            self.mentions.member("second", second, segment_no=2), self.mentions.member("representative", representative),
        ])
        self.assertEqual(len({member["mention_id"] for member in members}), 3)
        self.assertEqual(len(members[0]["evidence_ids"]), 2)
        result = self.stats()
        self.assert_totals(result, eligible=3)
        self.assertEqual(result["counts"]["N_extracted_mentions"], 4)

    def test_c_independent_same_text_and_d_repost_union(self):
        self.mentions.bind_products(status="non_product")
        text = "Identical synthetic text from two unrelated sources."
        original_batch, original = self.add_quote("original", text)
        repost_batch, repost = self.add_quote("repost", text, source="reddit")
        _, independent = self.add_quote("independent", text, source="youtube")
        _, representative = self.add_quote("representative")
        self.publish([
            MentionDraft("original", (SupportDraft(original, 1, "independent", mention_fixture.BASIS),
                                      SupportDraft(repost, 1, "repost", mention_fixture.BASIS, original=original))),
            self.mentions.member("independent", independent), self.mentions.member("representative", representative),
        ])
        for filters in ({"batch_id": (original_batch,)}, {"source": ("reddit",)}, {"source": ("youtube",)}):
            result = self.stats(filters=filters)
            self.assert_totals(result, eligible=1)
            self.assertEqual(result["counts"]["N_excluded"], 0)
        for filters, expected in (({"source": ("forum", "reddit")}, 2), ({"batch_id": (original_batch, repost_batch)}, 1)):
            result = self.stats(filters=filters)
            self.assert_totals(result, eligible=expected)
            self.assertEqual(result["counts"]["N_excluded"], 1)
        self.assert_totals(self.stats(filters={"source": ("forum", "reddit", "youtube")}), eligible=3)
        peer_before = self.mentions.corpus.qualified_record(self.study, independent.record_id)["duplicate"]
        self.mentions.revoke_batch(original_batch)
        peer_after = self.mentions.corpus.qualified_record(self.study, independent.record_id)["duplicate"]
        self.assertNotEqual(peer_after["canonical_record_id"], peer_before["canonical_record_id"])
        self.assert_totals(self.stats(filters={"source": ("youtube",)}), eligible=1)

    def test_e_product_union_and_f_no_cross_evidence_matching(self):
        product_a, product_b = mention_fixture.PRODUCT_A, mention_fixture.PRODUCT_B
        self.mentions.bind_products((product_a, product_b))
        text = "Synthetic need affects both products."
        original_batch, original = self.add_quote("same-event", text)
        _, repost = self.add_quote("same-event-repost", text, source="reddit", date="2026-11-12")
        _, extra = self.add_quote("extra-product-a")
        _, representative = self.add_quote("representative")
        shared, other, _ = self.publish([
            MentionDraft("shared", (SupportDraft(original, 1, "independent", mention_fixture.BASIS),
                                    SupportDraft(repost, 1, "repost", mention_fixture.BASIS, original=original))),
            self.mentions.member("other", extra), self.mentions.member("representative", representative),
        ], proposals=(self.mentions.proposal("shared", original, product_a), self.mentions.proposal("shared", repost, product_b),
                      self.mentions.proposal("other", extra, product_a)))
        self.mentions.review(self.mentions.decision(shared, product_a), self.mentions.decision(other, product_a),
                             replace(self.mentions.decision(shared, product_b), evidence_id=shared["evidence_ids"][1]))
        for products, expected in (((product_a,), 2), ((product_b,), 1), ((product_a, product_b), 2)):
            self.assert_totals(self.stats(filters={"product_category_id": products}), eligible=expected)
        for other_filter in ({"source": ("forum",)}, {"batch_id": (original_batch,)}, {"to": "2026-11-12"}):
            self.assert_totals(self.stats(filters={"product_category_id": (product_b,)} | other_filter), eligible=0)
        self.assert_totals(self.stats(filters={"product_category_id": (product_b,), "source": ("reddit",),
                                              "from": "2026-11-12", "to": "2026-11-13"}), eligible=1)

    def test_g_secondary_task_filter_accounts_under_the_primary(self):
        _, members = self.seed()
        self.decision(members[0], publication_status="published", disposition="human_confirmed")
        result = self.stats(filters={"category_id": (relation_fixture.SECONDARY,)})
        self.assert_totals(result, eligible=1, published=1, buckets={"published_classified": 1})
        self.assertEqual([(row["category_id"], row["count"], row["ratio"]) for row in result["by_primary_category"]],
                         [(relation_fixture.PRIMARY, 1, 1.0)])

    def test_h_mixed_six_buckets_and_i_overlapping_reasons(self):
        self.mentions.bind_products(status="non_product")
        quotes = [self.add_quote(f"mix-{number}") for number in range(9)]
        _, repost = self.add_quote("mix-repost", "Synthetic need mix-0.", source="reddit")
        first = quotes[0][1]
        members = self.publish([
            MentionDraft("mix-0", (SupportDraft(first, 1, "independent", mention_fixture.BASIS),
                                   SupportDraft(repost, 1, "repost", mention_fixture.BASIS, original=first))),
            *(self.mentions.member(f"mix-{number}", interval, identity="disputed" if number == 8 else "independent")
              for number, (_, interval) in enumerate(quotes[1:], start=1)),
        ])
        for member in members[:2]:
            self.decision(member, publication_status="published", disposition="auto")
        self.decision(members[2], noul=False, review_pending=True)
        self.decision(members[3], choice=relation_fixture.PENDING, review_pending=True)
        self.decision(members[4], choice=None, issues=("SCORE_PROBABILITIES_MISSING",))
        self.discover(members[5], relation_fixture.PENDING)
        self.mentions.revoke_batch(quotes[7][0])
        self.mentions.revoke_batch(quotes[8][0])
        result = self.stats()
        self.assert_totals(result, eligible=7, published=2, buckets=dict(zip(BUCKETS, (2, 1, 1, 1, 1, 1))))
        self.assertEqual(result["counts"]["N_extracted_mentions"], 10)
        self.assertEqual(result["counts"]["N_excluded"], 3)
        self.assertEqual(result["excluded_by_reason"]["primary"], {"LICENSE_RESTRICTED": 2, "DUPLICATE_OCCURRENCE": 1})
        self.assertEqual(result["excluded_by_reason"]["secondary"], {"IDENTITY_PENDING": 1})
        self.assertEqual(result["reconciliation"]["publication_allowed"], False)

    def test_invalid_probabilities_precede_none_and_publication(self):
        _, members = self.seed()
        self.decision(members[0], probabilities=(0.8,), choice=None, noul=False)
        self.decision(members[1], probabilities=(0.6, 0.6), publication_status="published", disposition="auto")
        self.decision(members[2], probabilities=(float("nan"), 0.2), review_pending=True)
        self.assert_totals(self.stats(), eligible=3, buckets={"partial_or_schema_gap": 3})

    def test_only_an_active_candidate_missing_a_primary_is_pending_parent(self):
        _, members = self.seed()
        version = "4.0.0"
        primary = relation_fixture.PRIMARY
        intentions = (("rejected", "rejected", None), ("with-parent", "candidate", primary),
                      ("without-parent", "candidate", None))
        with self.scenario.store.db() as db:
            registry(db, version, relation_fixture.VERSION)
            insert(db, "m06_task", registry_version=version, category_id=primary, name=primary,
                   definition="Synthetic task", inclusion_criteria="", exclusion_criteria="",
                   discovery="preset", lifecycle_status="confirmed", version="1.0.0")
            for intent, status, category in intentions:
                insert(db, "m06_intent", registry_version=version, intent_id=intent, name=intent,
                       definition="Synthetic intent", inclusion_criteria="", exclusion_criteria="",
                       lifecycle_status=status, primary_category_id=category,
                       survey_validation_status="unvalidated", version="1.0.0")
                if category:
                    insert(db, "m06_intent_task", registry_version=version, intent_id=intent,
                           category_id=category, is_primary=1)
            seal_registry(db, version)
        for member, (intent, _, _) in zip(members, intentions, strict=True):
            self.decision(member, registry_version=version, choice=intent, publication_status="published", disposition="auto")
        self.assert_totals(self.stats(), eligible=3, buckets={"pending_parent": 1, "other_pending": 2})

    def test_j_engineering_attestation_is_not_a_formal_encoding_receipt(self):
        _, members = self.seed()
        self.definitions.attribute(self.definitions.ref(members[0]))
        self.assert_totals(self.stats(mode="engineering"), eligible=3, buckets={"other_pending": 3})
        self.assertEqual(self.relations.project_mentions(self.study, mention_id=members[0]["mention_id"])["items"][0]["intents"][0]["intent_id"],
                         relation_fixture.INTENT)

    def test_k_formal_unavailable_and_l_verified_empty_zero(self):
        self.seed()
        formal = self.stats(mode="formal")
        self.assertEqual((formal["availability"], formal["counts"], formal["reconciliation"]), ("unavailable", None, None))
        self.assertIn("G1_BLOCKED", formal["reasons"])
        empty = self.stats(filters={"source": ("unmatched",)})
        self.assert_totals(empty, eligible=0)
        self.assertEqual(empty["counts"]["N_excluded"], 0)
        self.assertIsNone(empty["counts"]["published_ratio"])

    def test_m_revoke_only_encoding_context_preserves_independent_occurrence(self):
        self.mentions.bind_products(status="non_product")
        text = "Synthetic need with alternate evidence."
        _, first = self.add_quote("first", text)
        _, repost = self.add_quote("repost-with-context", text, source="reddit")
        _, context = self.add_quote("context")
        _, second = self.add_quote("second")
        _, third = self.add_quote("third")
        first_draft = MentionDraft("one", (
            SupportDraft(first, 1, "independent", mention_fixture.BASIS),
            SupportDraft(repost, 1, "repost", mention_fixture.BASIS, (context,), first),
        ))
        members = self.publish([first_draft, self.mentions.member("two", second), self.mentions.member("three", third)])
        self.decision(members[0], indexes=(1,), publication_status="published", disposition="auto")
        self.assert_totals(self.stats(), eligible=3, published=1)
        self.corpus.verify(context.record_id, decision="excluded", license_status="revoked")
        self.assert_totals(self.stats(), eligible=3, buckets={"other_pending": 3})
        withdrawn = self.mentions.rows("SELECT reviewed_at FROM corpus_withdrawals WHERE record_id=?", (context.record_id,))
        self.corpus.verify(context.record_id, reauthorize=True, license_issued_on=withdrawn[0][0][:10],
                           license_evidence_ref="local:renewed-context-grant")
        self.assert_totals(self.stats(), eligible=3, buckets={"other_pending": 3})

    def test_exact_reader_does_not_borrow_hidden_encoding_context(self):
        _, members = self.seed()
        primary, context = members[:2]
        context_id = context["evidence_ids"][0]
        context_binding = self.decision(context).evidence_grants
        self.scenario.decisions.clear()
        decision = self.decision(primary, context_ids=(context_id,), publication_status="published", disposition="auto")
        self.scenario.decisions[primary["mention_id"]] = (replace(decision, evidence_grants=decision.evidence_grants | context_binding),)
        self.assert_totals(self.stats(), eligible=3, published=1)
        only_primary = (1, primary["mention_id"], primary["evidence_ids"][0])
        self.grants[:] = [self.definitions.grant("project_reviewer", "read", "evidence", evidence=frozenset({only_primary}))]
        result = self.stats()
        self.assert_totals(result, eligible=1, buckets={"other_pending": 1})
        self.assertIsNone(result["excluded_by_reason"]["excluded_unsegmented_records"]["count"])
        self.assertNotIn(context_id, repr(result))

    def test_hidden_discovery_keeps_visible_shared_context_eligible(self):
        self.mentions.bind_products(status="non_product")
        _, occurrence = self.add_quote("visible-occurrence")
        _, hidden = self.add_quote("hidden-occurrence")
        _, third = self.add_quote("representative")
        _, context = self.add_quote("shared-context")
        members = self.publish([
            MentionDraft("visible", (SupportDraft(occurrence, 1, "independent", mention_fixture.BASIS, (context,)),)),
            self.mentions.member("hidden", hidden), self.mentions.member("third", third),
        ])
        [(context_id,)] = self.mentions.rows("SELECT evidence_id FROM m06_evidence WHERE record_id=?", (context.record_id,))
        visible_ref = (1, members[0]["mention_id"], members[0]["evidence_ids"][0])
        self.grants[:] = [self.definitions.grant("project_reviewer", "read", "evidence", evidence=frozenset({visible_ref}))]
        self.assert_totals(self.stats(), eligible=1, buckets={"other_pending": 1})
        self.discover(members[1], relation_fixture.PENDING, context_ids=(context_id,))
        result = self.stats()
        self.assert_totals(result, eligible=1, buckets={"other_pending": 1})
        self.assertNotIn(context_id, repr(result))

    def test_n_source_revocation_mid_query_and_o_grant_withdrawal(self):
        quotes, members = self.seed()
        qualify = denominators._dependencies_for
        changes = [lambda: self.mentions.revoke_batch(quotes[0][0])]

        def interleave(*args, **kwargs):
            result = qualify(*args, **kwargs)
            if changes:
                changes.pop(0)()
            return result

        with patch.object(denominators, "_dependencies_for", side_effect=interleave):
            self.assert_totals(self.stats(batch_qualification=False), eligible=2)
        self.assertFalse(changes)
        changes.append(self.grants.clear)
        with patch.object(denominators, "_dependencies_for", side_effect=interleave):
            with self.assertRaises(KeyError):
                self.stats(batch_qualification=False)
        self.assertFalse(changes)
        self.assertTrue(self.mentions.corpus.qualified_record(self.study, quotes[1][1].record_id)["engineering_eligible"])
        self.assertEqual(len({member["mention_id"] for member in members}), 3)

    def test_long_query_rechecks_utc_retention_after_midnight(self):
        _, members = self.seed()
        self.decision(members[0], publication_status="published", disposition="auto")
        before = datetime.fromisoformat(self.corpus.retain + "T23:59:59+00:00")
        after = before + timedelta(seconds=1)
        self.grants[:] = [replace(self.grants[0], expires_at=(after + timedelta(days=1)).isoformat())]
        now = before
        snapshots = []
        calculate = denominators._calculate

        def rollover(*args, **kwargs):
            nonlocal now
            result = calculate(*args, **kwargs)
            snapshots.append((result["as_of_utc"], result["counts"]["N_eligible_dedup"]))
            now = after
            return result

        with (patch("src.raw_store.relations.now", side_effect=lambda: now.isoformat()),
              patch("src.raw_store.corpus.now", side_effect=lambda: now.isoformat()),
              patch.object(denominators, "_calculate", side_effect=rollover)):
            result = self.stats()
        self.assertEqual(snapshots, [(before.isoformat(), 3), (after.isoformat(), 0)])
        self.assertEqual(result["as_of_utc"], after.isoformat())
        self.assert_totals(result, eligible=0)
        self.assertEqual(result["excluded_by_reason"]["primary"], {"LICENSE_RESTRICTED": 3})

    def test_p_old_version_rechecks_qualification(self):
        quotes, members = self.seed()
        self.decision(members[0], publication_status="published", disposition="auto")
        pinned = {"registry_version": relation_fixture.VERSION, "segment_revision": 1}
        self.assert_totals(self.stats(**pinned), eligible=3, published=1)
        self.assert_totals(self.stats(filters={"index_version": "synthetic-index"}, **pinned), eligible=1, published=1)
        self.assert_totals(self.stats(filters={"index_version": "different-index"}, **pinned), eligible=0)
        self.mentions.publish([
            self.mentions.member(f"new-{number}", interval, mention_id=member["mention_id"])
            for number, ((_, interval), member) in enumerate(zip(quotes, members, strict=True))
        ], expected=1, key="second-revision")
        self.assert_totals(self.stats(), eligible=3)
        with self.scenario.store.db() as db:
            registry(db, "4.0.0", relation_fixture.VERSION, seal=True)
        self.assert_totals(self.stats(segment_revision=1), eligible=3)
        self.assert_totals(self.stats(**pinned), eligible=3, published=1)
        self.mentions.revoke_batch(quotes[0][0])
        self.assert_totals(self.stats(**pinned), eligible=2)

    def test_q_unresolved_product_mapping_is_unavailable(self):
        self.mentions.bind_products(status="unresolved")
        quotes = [self.add_quote(f"unresolved-{number}") for number in range(3)]
        self.publish([self.mentions.member(f"unresolved-{number}", quote) for number, (_, quote) in enumerate(quotes)])
        result = self.stats(filters={"product_category_id": (mention_fixture.PRODUCT_A,)})
        self.assertEqual((result["availability"], result["counts"]), ("unavailable", None))
        self.assertIn("SCOPE_MAPPING_UNRESOLVED", result["reasons"])

    def test_r_unsegmented_record_remains_separate_from_excluded_candidate(self):
        quotes, _ = self.seed()
        revoked_unsegmented, _ = self.add_quote("whole-unsegmented")
        self.mentions.revoke_batch(quotes[0][0])
        self.mentions.revoke_batch(revoked_unsegmented)
        result = self.stats()
        self.assert_totals(result, eligible=2)
        self.assertEqual(result["counts"]["N_extracted_mentions"], 3)
        self.assertEqual(result["counts"]["N_excluded"], 1)
        self.assertEqual(result["excluded_by_reason"]["excluded_unsegmented_records"]["count"], 1)

    def test_unverified_denial_counts_as_whole_row_while_unreviewed_stage_does_not(self):
        self.seed()
        _, denied = self.add_quote("denied-before-verification", reviewed=False)
        _, staged = self.add_quote("unreviewed-staging", reviewed=False)
        self.corpus.verify(denied.record_id, decision="excluded", license_status="denied", retention_until=None)
        self.assertEqual(self.mentions.rows(
            "SELECT 1 FROM corpus_snapshots WHERE record_id IN (?, ?)", (denied.record_id, staged.record_id),
        ), [])
        result = self.stats(mode="engineering")
        self.assert_totals(result, eligible=3)
        self.assertEqual(result["counts"]["N_extracted_mentions"], 3)
        self.assertEqual(result["counts"]["N_excluded"], 0)
        self.assertEqual(result["excluded_by_reason"]["excluded_unsegmented_records"],
                         {"count": 1, "by_reason": {"LICENSE_RESTRICTED": 1}})

    def test_s_accounting_difference_blocks_publication(self):
        _, members = self.seed()
        self.decision(members[0], publication_status="published", disposition="auto")
        primary_counts = denominators._primary_counts

        def inconsistent(assigned):
            counts = primary_counts(assigned)
            counts.pop(relation_fixture.PRIMARY)
            return counts

        with patch.object(denominators, "_primary_counts", side_effect=inconsistent):
            result = self.stats()
        self.assertEqual((result["availability"], result["reasons"]), ("unavailable", ["RECONCILIATION_MISMATCH"]))
        self.assertEqual(result["reconciliation"]["primary_difference"], 1)
        self.assertFalse(result["reconciliation"]["publication_allowed"])

    def test_s_competing_current_decisions_block_reconciliation(self):
        _, members = self.seed()
        decision = self.decision(members[0], publication_status="published", disposition="auto")
        self.scenario.decisions[members[0]["mention_id"]] = (decision, replace(decision, receipt_id="competing-receipt"))
        result = self.stats()
        self.assertEqual((result["availability"], result["counts"]), ("unavailable", None))

    def test_api_rechecks_grants_and_never_exposes_synthetic_receipts(self):
        _, members = self.seed()
        self.decision(members[0], publication_status="published", disposition="auto")
        path = f"/api/studies/{self.study}/denominators"
        client = self.corpus.client
        response = client.get(path, params={"mode": "formal"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIsNone(response.json()["counts"])
        engineering = client.get(path, params={"mode": "engineering"})
        self.assertEqual(engineering.status_code, 200, engineering.text)
        self.assert_totals(engineering.json(), eligible=3)
        synthetic = client.get(path, params={"mode": "synthetic"})
        self.assertIsNone(synthetic.json().get("counts"))
        self.assertEqual(client.get(path, params={"mode": "engineering", "limit": 1}).status_code, 422)
        self.grants.clear()
        refused = client.get(path, params={"mode": "engineering"}, headers={"X-VOC-Role": "owner"})
        missing = client.get(f"/api/studies/{uuid4()}/denominators", params={"mode": "engineering"})
        self.assertEqual((refused.status_code, refused.json()), (404, missing.json()))

    def test_formal_exact_reader_cannot_probe_a_hidden_revision(self):
        quotes, members = self.seed()
        self.mentions.publish([
            self.mentions.member(f"revision-2-{number}", interval, mention_id=member["mention_id"])
            for number, ((_, interval), member) in enumerate(zip(quotes, members, strict=True))
        ], expected=1, key="second-revision")
        ref = (1, members[0]["mention_id"], members[0]["evidence_ids"][0])
        self.grants[:] = [replace(self.grants[0], evidence_refs=frozenset({ref}))]
        client = self.corpus.client
        route = f"/api/studies/{self.study}/denominators"
        permitted = client.get(route, params={"mode": "formal", "segment_revision": 1})
        absent = client.get(route, params={"mode": "formal", "segment_revision": 999})
        self.assertEqual(permitted.status_code, 200)
        self.assertIsNone(permitted.json()["counts"])
        self.assertEqual(absent.status_code, 404)
        for revision in ({"segment_revision": 2}, {}):
            hidden = client.get(route, params={"mode": "formal"} | revision)
            self.assertEqual((hidden.status_code, hidden.json()), (404, absent.json()))
