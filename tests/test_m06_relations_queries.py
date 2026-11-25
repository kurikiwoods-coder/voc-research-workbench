"""C4 relation projections with trusted grants and synthetic C3 evidence."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import unittest

import test_m06_mentions as c3
from test_m06_constraints import insert, registry, seal_registry
from src.raw_store.mention_segments import EvidenceInterval, MentionDraft, Replacement, SupportDraft
from src.raw_store.relation_access import RelationGrant
from src.raw_store.relations import RelationStore
from src.raw_store.store import Conflict


INTENT = "A-SAFE"
PENDING = "A-PENDING"
PRIMARY = "T-SAFE"
SECONDARY = "T-SETUP"
VERSION = "3.0.0"


class RelationQueryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = c3.MentionTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.study = self.fixture.study
        self.scope = self.fixture.scope
        self.scope_filters = {"scope_id": self.scope, "scope_version": "v1"}
        self.grants = [self.grant("project_reviewer", "read", "evidence", "attribute")]
        self.relations = RelationStore(self.fixture.db, grants=lambda: self.grants)

    def grant(self, role, *operations, evidence=None):
        now = datetime.now(timezone.utc)
        return RelationGrant(
            "synthetic-reviewer", role, "fixture-owner", "local:query-fixture",
            (now - timedelta(days=1)).isoformat(), (now + timedelta(days=1)).isoformat(),
            frozenset(operations), self.study, evidence,
        )

    def publish(self, members, *, proposals=()):
        members = list(members)
        for index in range(len(members), 3):
            ref = f"representative-{index}"
            _, interval = self.fixture.add_quote(ref, f"Synthetic safety concern {index}")
            members.append(self.fixture.member(ref, interval))
        return self.fixture.publish(members, proposals=proposals)["members"]

    def seal_definitions(self, representatives, *, parent=c3.CATALOG):
        with self.fixture.db.db() as db:
            db.execute("BEGIN IMMEDIATE")
            registry(db, VERSION, parent)
            for task in (PRIMARY, SECONDARY):
                insert(
                    db, "m06_task", registry_version=VERSION, category_id=task, name=task,
                    definition="Synthetic task definition", inclusion_criteria="", exclusion_criteria="",
                    discovery="preset", lifecycle_status="confirmed", version="1.0.0",
                )
            for intent, status, primary in ((INTENT, "confirmed", PRIMARY), (PENDING, "pending_parent", None)):
                insert(
                    db, "m06_intent", registry_version=VERSION, intent_id=intent, name=intent,
                    definition="Synthetic intent definition", inclusion_criteria="", exclusion_criteria="",
                    lifecycle_status=status, primary_category_id=primary,
                    survey_validation_status="unvalidated", version="1.0.0",
                )
            for task in (PRIMARY, SECONDARY):
                insert(db, "m06_intent_task", registry_version=VERSION, intent_id=INTENT,
                       category_id=task, is_primary=int(task == PRIMARY))
            for representative in representatives:
                insert(db, "m06_representative", registry_version=VERSION, intent_id=INTENT, study_id=self.study,
                       segment_revision=1, **self.ref(representative))
            seal_registry(db, VERSION)

    @staticmethod
    def ref(member, index=0):
        return {"mention_id": member["mention_id"], "evidence_id": member["evidence_ids"][index]}

    def attribute(self, *refs, key="attribute", revision=1):
        return self.relations.attribute(
            self.study, key=key, expected_registry_version=VERSION, expected_segment_revision=revision,
            intent_id=INTENT, supports=refs,
        )

    def edges(self, *, product=None, intent=None, filters=None, **versions):
        return self.relations.product_intent_edges(
            self.study, product_id=product, intent_id=intent, filters=filters, **versions,
        )

    def two_products(self):
        f = self.fixture
        f.bind_products((c3.PRODUCT_A, c3.PRODUCT_B))
        batch_a, first = f.add_quote("scale", f"Needs a safety lock on {c3.PRODUCT_A}")
        batch_b, second = f.add_quote("fryer", f"Needs a safety lock on {c3.PRODUCT_B}")
        representatives = self.publish(
            [f.member("scale", first), f.member("fryer", second)],
            proposals=[f.proposal("scale", first), f.proposal("fryer", second, c3.PRODUCT_B)],
        )
        first_member, second_member = representatives[:2]
        f.review(f.decision(first_member), f.decision(second_member, c3.PRODUCT_B))
        self.seal_definitions(representatives)
        self.attribute(self.ref(first_member), self.ref(second_member))
        return (batch_a, first_member), (batch_b, second_member)

    def test_both_directions_use_the_same_intent_and_witnesses(self):
        (_, first), (_, second) = self.two_products()
        reverse = self.edges(intent=INTENT)
        self.assertEqual(reverse["resolved_versions"]["registry_version"], VERSION)
        self.assertEqual(reverse["resolved_versions"]["catalog_version"], c3.CATALOG)
        self.assertEqual(reverse["resolved_versions"]["segment_revision"], 1)
        self.assertEqual({row["product_category_id"] for row in reverse["items"]}, {c3.PRODUCT_A, c3.PRODUCT_B})
        for product, member in ((c3.PRODUCT_A, first), (c3.PRODUCT_B, second)):
            forward = self.edges(product=product)
            self.assertEqual([row["intent_id"] for row in forward["items"]], [INTENT])
            row = forward["items"][0]
            mirrored = next(item for item in reverse["items"] if item["product_category_id"] == product)
            self.assertEqual(row["evidence_refs"], mirrored["evidence_refs"])
            self.assertEqual(row["evidence_refs"][0]["evidence_id"], member["evidence_ids"][0])
            self.assertEqual(row["distinct_mention_n"], 1)
            self.assertEqual(row["source_breakdown"], {"forum": 1})

    def test_task_intent_roles_candidate_and_shared_search_stay_within_the_sealed_version(self):
        self.two_products()
        self.assertEqual(self.relations.definitions("intent", q="Needs a safety lock")["items"], [])
        self.assertEqual([row["intent_id"] for row in self.relations.definitions(
            "intent", lifecycle_status="pending_parent",
        )["items"]], [PENDING])
        categories = self.relations.task_intent_edges(intent_id=INTENT)["items"]
        self.assertEqual([(row["category_id"], row["role"]) for row in categories], [
            (PRIMARY, "primary"), (SECONDARY, "secondary"),
        ])
        self.assertEqual(self.relations.task_intent_edges(task_id=SECONDARY, role="secondary")["items"], categories[1:])
        self.assertEqual(self.relations.task_intent_edges(task_id=PRIMARY, role="secondary")["items"], [])
        self.assertEqual(self.relations.task_intent_edges(intent_id=PENDING)["items"], [])

    def test_current_revocation_masks_old_witness_and_leaves_independent_product(self):
        (first_batch, first), (_, second) = self.two_products()
        first_ref = self.ref(first)
        second_ref = self.ref(second)
        self.assertEqual(self.relations.read_evidence(self.study, 1, **first_ref)["excerpt"],
                         f"Needs a safety lock on {c3.PRODUCT_A}")
        self.fixture.revoke_batch(first_batch)
        versions = {"registry_version": VERSION, "segment_revision": 1}
        self.assertEqual(self.edges(product=c3.PRODUCT_A, **versions)["items"], [])
        result = self.edges(intent=INTENT, **versions)
        self.assertEqual([row["product_category_id"] for row in result["items"]], [c3.PRODUCT_B])
        self.assertEqual(result["items"][0]["evidence_refs"][0]["evidence_id"], second_ref["evidence_id"])
        with self.assertRaises((Conflict, KeyError)):
            self.relations.read_evidence(self.study, 1, **first_ref)
        self.assertEqual(self.relations.read_evidence(self.study, 1, **second_ref)["excerpt"],
                         f"Needs a safety lock on {c3.PRODUCT_B}")

    def test_evidence_scope_does_not_reveal_independent_witnesses(self):
        (_, first), (_, second) = self.two_products()
        ref = self.ref(first)
        self.grants[:] = [self.grant(
            "researcher", "read", "evidence", evidence=frozenset({(1, ref["mention_id"], ref["evidence_id"])}),
        )]
        self.assertEqual([row["product_category_id"] for row in self.edges(intent=INTENT)["items"]], [c3.PRODUCT_A])
        self.assertEqual([row["mention_id"] for row in self.relations.project_mentions(self.study)["items"]], [
            first["mention_id"],
        ])
        with self.assertRaises(KeyError):
            self.relations.read_evidence(self.study, 1, **self.ref(second))

    def test_same_mention_cannot_join_a_product_and_intent_from_different_evidence(self):
        f = self.fixture
        f.bind_products((c3.PRODUCT_A,))
        excerpt = f"Needs a safety lock on {c3.PRODUCT_A}"
        original_batch, original = f.add_quote("original", excerpt)
        row = [excerpt, "reddit", "https://synthetic.invalid/copy/1", "2026-11-10", "Synthetic license", "public"]
        copied_batch, [copied_id] = f.case.import_rows([row])
        f.case.verify(copied_id)
        copied = EvidenceInterval(copied_id, sha256(excerpt.encode()).hexdigest(), 0, len(excerpt))
        member = MentionDraft("joined", (
            SupportDraft(original, 1, "independent", c3.BASIS),
            SupportDraft(copied, 1, "repost", c3.BASIS, original=original),
        ))
        representatives = self.publish([member], proposals=[f.proposal("joined", original), f.proposal("joined", copied)])
        item = representatives[0]
        first_decision = f.decision(item)
        copied_decision = replace(first_decision, evidence_id=item["evidence_ids"][1])
        f.review(first_decision)
        self.seal_definitions(representatives)
        self.attribute(self.ref(item, 1))
        self.assertEqual(self.edges(product=c3.PRODUCT_A)["items"], [])
        self.assertEqual(self.edges(intent=INTENT)["items"], [])
        projection = self.relations.project_mentions(self.study, mention_id=item["mention_id"])
        self.assertEqual(projection["items"][0]["product_intent_edges"], [])

        self.attribute(self.ref(item), key="attribute-original")
        filters = {**self.scope_filters, "batch_id": (original_batch,), "source": ("forum",),
                   "from": "2026-11-11T00:00:00Z", "to": "2026-11-12T00:00:00Z"}
        forward = self.edges(product=c3.PRODUCT_A, filters=filters)["items"]
        self.assertEqual(len(forward), 1)
        self.assertEqual(forward[0]["evidence_refs"][0]["evidence_id"], item["evidence_ids"][0])
        for mismatched in (
            {"batch_id": (copied_batch,)},
            {"source": ("reddit",)},
            {"from": "2026-11-10T00:00:00Z", "to": "2026-11-11T00:00:00Z"},
        ):
            with self.subTest(mismatched=mismatched):
                self.assertEqual(self.edges(product=c3.PRODUCT_A, filters=filters | mismatched)["items"], [])
                self.assertEqual(self.edges(intent=INTENT, filters=filters | mismatched)["items"], [])
        f.review(copied_decision, key="review-copied")
        result = self.edges(product=c3.PRODUCT_A)["items"][0]
        self.assertEqual(result["distinct_mention_n"], 1)
        self.assertEqual({ref["evidence_id"] for ref in result["evidence_refs"]}, set(item["evidence_ids"]))

    def test_same_name_products_and_mapping_versions_remain_separate(self):
        f = self.fixture
        f.bind_products((c3.PRODUCT_A,))
        _, interval = f.add_quote("scale-old", f"Needs a safety lock on {c3.PRODUCT_A}")
        representatives = self.publish([f.member("scale", interval)], proposals=[f.proposal("scale", interval)])
        first = representatives[0]
        f.review(f.decision(first))
        f.bind_products((c3.PRODUCT_B,), revision=2, version=c3.NEXT_CATALOG)
        self.seal_definitions(representatives, parent=c3.NEXT_CATALOG)
        self.attribute(self.ref(first))
        options = {"registry_version": VERSION, "segment_revision": 1}
        old = self.edges(intent=INTENT, filters=self.scope_filters, **options)
        self.assertEqual([row["product_category_id"] for row in old["items"]], [c3.PRODUCT_A])
        self.assertEqual(old["resolved_versions"]["scope_mappings"], [{
            **self.scope_filters, "mapping_revision": 1, "catalog_version": c3.CATALOG,
            "mapping_status": "mapped_product",
        }])
        names = [self.relations.definitions("product", registry_version=catalog, object_id=product)["items"][0]["name"]
                 for catalog, product in ((c3.CATALOG, c3.PRODUCT_A), (c3.NEXT_CATALOG, c3.PRODUCT_B))]
        self.assertEqual(names[0], names[1])
        self.assertEqual(self.edges(product=c3.PRODUCT_B, filters={
            **self.scope_filters, "mapping_revision": 2, "catalog_version": c3.NEXT_CATALOG,
        }, **options)["items"], [])
        self.assertEqual(self.edges(product=c3.PRODUCT_A, filters={
            **self.scope_filters, "mapping_revision": 2, "catalog_version": c3.NEXT_CATALOG,
        }, **options)["items"], [])

        client = f.case.client
        project_path = f"/api/studies/{self.study}"
        project = client.get(project_path).json()
        updated = client.put(project_path, json={
            "revision": project["revision"], "name": project["name"],
            "scope": {"mode": "open", "topic": "Synthetic new scope"},
            "change_note": "Synthetic scope reassessment",
        })
        updated.raise_for_status()
        other_scope = updated.json()["scope"]["scope_id"]
        client.post(f"{project_path}/scopes/{other_scope}/freeze").raise_for_status()
        f.bind_products((c3.PRODUCT_B,), version=c3.NEXT_CATALOG, scope=other_scope)
        _, other = f.add_quote("fryer-new", f"Needs a safety lock on {c3.PRODUCT_B}", scope=other_scope)
        new = f.publish(
            [f.member("fryer", other)], key="new-scope", expected=1,
            proposals=[f.proposal("fryer", other, c3.PRODUCT_B, catalog_version=c3.NEXT_CATALOG)],
        )["members"][0]
        f.review(f.decision(new, c3.PRODUCT_B, catalog_version=c3.NEXT_CATALOG), key="review-new", expected=2)
        self.attribute(self.ref(new), key="attribute-new", revision=2)
        new_scope_filters = {"scope_id": other_scope, "scope_version": "v2"}
        latest = self.edges(intent=INTENT, filters=new_scope_filters)
        self.assertEqual([item["product_category_id"] for item in latest["items"]], [c3.PRODUCT_B])
        self.assertEqual(latest["resolved_versions"]["scope_mappings"][0]["catalog_version"], c3.NEXT_CATALOG)
        self.assertEqual(self.edges(product=c3.PRODUCT_B, filters=self.scope_filters)["items"], [])
        self.assertEqual(self.edges(intent=INTENT, filters=self.scope_filters, **options), old)

    def test_historical_replacements_require_current_access_to_both_ends(self):
        f = self.fixture
        batch, interval = f.add_quote("split", "Synthetic original sentence")
        old = f.publish([f.member("whole", interval)])["members"][0]
        left, right = replace(interval, end_cp=9), replace(interval, start_cp=10)
        new = f.publish(
            [f.member("left", left), f.member("right", right, segment_no=2)], key="split", expected=1,
            replacements=[Replacement(old["mention_id"], side, "split") for side in ("left", "right")],
        )["members"][0]
        link = {"from_revision": 1, "from_mention_id": old["mention_id"], "to_revision": 2,
                "to_mention_id": new["mention_id"], "reason": "split"}
        before = self.relations.project_mentions(self.study, segment_revision=1, mention_id=old["mention_id"])
        self.assertIn(link, before["items"][0]["replacements"])
        after = self.relations.project_mentions(self.study, segment_revision=2, mention_id=new["mention_id"])
        self.assertEqual(after["items"][0]["replacements"], [link])

        ref = self.ref(new)
        self.grants[:] = [self.grant(
            "researcher", "read", evidence=frozenset({(2, ref["mention_id"], ref["evidence_id"])}),
        )]
        detail = self.relations.project_mentions(self.study, segment_revision=2, mention_id=new["mention_id"])
        self.assertEqual(detail["items"][0]["replacements"], [])
        f.revoke_batch(batch)
        with self.assertRaises(KeyError):
            self.relations.project_mentions(self.study, segment_revision=2, mention_id=new["mention_id"])

    def test_non_product_study_retains_the_mention_and_has_an_available_empty_relation(self):
        f = self.fixture
        f.bind_products(status="non_product")
        _, interval = f.add_quote("community", "Needs clear opening hours")
        representatives = self.publish([f.member("community", interval)])
        member = representatives[0]
        self.seal_definitions(representatives)
        self.attribute(self.ref(member))
        result = self.relations.project_mentions(self.study, mention_id=member["mention_id"], filters=self.scope_filters)
        self.assertEqual(result["items"][0]["mention_id"], member["mention_id"])
        self.assertEqual([intent["intent_id"] for intent in result["items"][0]["intents"]], [INTENT])
        self.assertEqual(result["items"][0]["products"], [])
        reverse = self.edges(intent=INTENT, filters=self.scope_filters)
        self.assertEqual(reverse["availability"], "available")
        self.assertEqual(reverse["items"], [])
        self.assertEqual(reverse["resolved_versions"]["scope_mappings"][0]["mapping_status"], "non_product")
        formal = self.edges(intent=INTENT, filters=self.scope_filters, mode="formal")
        self.assertEqual(formal["items"], [])
        self.assertIsNone(formal["counts"])
