"""C4 definition, grant and historical protection checks on synthetic data."""

from dataclasses import replace
from hashlib import sha256
import unittest

from fastapi.testclient import TestClient

import test_corpus as corpus_fixtures
import test_m06_relations_transactions as fixtures
from src.dashboard.app import create_app
from src.raw_store.mentions import EvidenceInterval, MentionStore
from src.raw_store.relation_registry import protect_published_products
from src.raw_store.relations import PublishedProductRef, RelationStore
from src.raw_store.store import Conflict
from test_m06_constraints import insert, registry, seal_registry


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RelationTransactionTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.store = self.fixture.store
        self.study = self.fixture.study
        self.refs = self.fixture.representative_refs

    def preflight(self, operation, **changes):
        args = {"operation": operation, "candidate_intent_id": fixtures.INTENT.intent_id,
                "expected_registry_version": fixtures.REGISTRY, "expected_segment_revision": 1,
                "representative_refs": self.refs}
        return self.store.validate(self.study, **(args | changes))

    def test_one_primary_and_secondary_use_the_same_definition_edges(self):
        self.fixture.publish()
        intent = fixtures.INTENT.intent_id
        descending = self.store.task_intent_edges(intent_id=intent, lifecycle_status="confirmed")["items"]
        self.assertEqual([(row["category_id"], row["role"]) for row in descending],
                         [(fixtures.PRIMARY, "primary"), (fixtures.SECONDARY, "secondary")])
        for edge in descending:
            ascending = self.store.task_intent_edges(task_id=edge["category_id"], role=edge["role"])["items"]
            self.assertEqual(ascending, [edge])
        self.assertEqual(self.store.task_intent_edges(intent_id=intent, role="secondary")["items"], descending[1:])

    def test_invalid_primary_edges_leave_no_registry_rows(self):
        before = self.fixture.snapshot()
        cases = (
            {"primary_category_id": None, "secondary_ids": ()},
            {"secondary_ids": (fixtures.PRIMARY,)},
            {"tasks": (fixtures.OTHER_TASK,), "primary_category_id": fixtures.PRIMARY},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.fixture.publish(**arguments)
            self.assertEqual(self.fixture.snapshot(), before)

    def test_candidate_without_parent_can_be_saved_and_public_read_is_allowlisted(self):
        candidate = replace(fixtures.INTENT, lifecycle_status="candidate")
        self.fixture.publish(intent=candidate, primary_category_id=None, secondary_ids=(), representative_refs=())
        anonymous = RelationStore(self.fixture.db)
        item = anonymous.definitions("intent", object_id=candidate.intent_id)["items"][0]
        self.assertEqual(item["lifecycle_status"], "pending_parent")
        self.assertIsNone(item["primary_category_id"])
        self.assertEqual(item["category_ids"], [])
        self.assertNotIn("supports", item)
        self.assertNotIn("study_id", item)
        self.assertEqual(anonymous.definitions("intent", q=fixtures.APPROVAL)["items"], [])
        self.assertFalse(self.preflight("confirm")["valid"])
        self.assertIn("PRIMARY_REQUIRED", self.preflight("confirm")["violations"])
        self.assertTrue(self.preflight("candidate")["candidate_allowed"])
        self.assertEqual(self.store.definitions("intent", object_id=candidate.intent_id)["items"], [item])

    def test_six_roles_use_explicit_operations_and_same_actor(self):
        combinations = {
            "owner": (True, True, True, False),
            "researcher": (True, True, False, False),
            "project_reviewer": (True, True, True, False),
            "registry_reviewer": (True, True, True, True),
            "governance_reviewer": (True, True, False, False),
            "report_reader": (False, False, False, False),
        }
        self.fixture.publish()
        grant = self.fixture.grants[1]
        mention, evidence = self.refs[0]
        for role, (read, drill, validate, publish) in combinations.items():
            with self.subTest(role=role):
                self.fixture.grants[:] = [
                    replace(grant, role=role, operations=frozenset({"read", "evidence", "validate", "attribute", "audit"})),
                    replace(grant, role=role, study_id=None, operations=frozenset({"publish_registry"})),
                ]
                self.assertEqual(self.store.can_read_project(self.study), read)
                self.assertEqual(self.store._access().permits("publish_registry", None), publish)
                if drill:
                    projection = self.store.read_evidence(self.study, 1, mention, evidence)
                    self.assertTrue(projection["excerpt"])
                    self.assertFalse(projection["outbound_allowed"])
                else:
                    with self.assertRaises(KeyError):
                        self.store.read_evidence(self.study, 1, mention, evidence)
                if validate:
                    self.assertTrue(self.preflight("confirm", primary_category_id=fixtures.PRIMARY)["valid"])
                else:
                    with self.assertRaises((KeyError, PermissionError)):
                        self.preflight("confirm", primary_category_id=fixtures.PRIMARY)
        self.fixture.grants.append(replace(grant, actor_ref="different-actor"))
        self.assertFalse(self.store.can_read_project(self.study))

    def test_exact_evidence_grant_expires_without_changing_record_qualification(self):
        self.fixture.publish()
        grant = self.fixture.grants[1]
        mention, evidence = self.refs[0]
        exact = replace(grant, evidence_refs=frozenset({(1, mention, evidence)}))
        self.fixture.grants[:] = [exact]
        rows = self.store.project_mentions(self.study)["items"]
        self.assertEqual([row["mention_id"] for row in rows], [mention])
        same = self.store.read_evidence(self.study, 1, mention, evidence)
        with self.assertRaises(KeyError):
            self.store.read_evidence(self.study, 1, *self.refs[1])
        self.fixture.grants[:] = [replace(exact, expires_at="2001-01-01T00:00:00Z")]
        with self.assertRaises(KeyError):
            self.store.read_evidence(self.study, 1, mention, evidence)
        self.fixture.grants[:] = [exact]
        self.assertEqual(self.store.read_evidence(self.study, 1, mention, evidence), same)

    def test_project_relationship_views_require_read_access_to_the_resolved_revision(self):
        self.fixture.publish()
        self.fixture.case.publish([
            replace(draft, mention_id=mention)
            for draft, (mention, _) in zip(self.fixture.drafts, self.refs, strict=True)
        ], key="revision-two", expected=1)
        mention, evidence = self.refs[0]
        self.fixture.grants[:] = [replace(
            self.fixture.grants[1], evidence_refs=frozenset({(1, mention, evidence)}),
        )]
        for mode in ("engineering", "formal"):
            for query in (self.store.project_mentions, self.store.product_intent_edges):
                with self.subTest(mode=mode, query=query.__name__):
                    permitted = query(self.study, segment_revision=1, mode=mode)
                    self.assertEqual(permitted["resolved_versions"]["segment_revision"], 1)
                    for revision in (2, None, 999):
                        with self.assertRaises(KeyError):
                            query(self.study, segment_revision=revision, mode=mode)

    def test_commands_do_not_disclose_a_revision_outside_the_read_grant(self):
        self.fixture.publish()
        self.fixture.case.publish([
            replace(draft, mention_id=mention)
            for draft, (mention, _) in zip(self.fixture.drafts, self.refs, strict=True)
        ], key="preflight-revision-two", expected=1)
        mention, evidence = self.refs[0]
        grant = self.fixture.grants[1]
        project_grant = replace(grant, evidence_refs=frozenset({(1, mention, evidence)}))
        self.fixture.grants[1] = project_grant
        self.fixture.grants.append(replace(
            project_grant, role="project_reviewer", operations=frozenset({"attribute"}),
        ))
        before = self.fixture.snapshot()
        for revision in (1, 2, 999):
            with self.subTest(revision=revision), self.assertRaises(KeyError):
                self.preflight("candidate", expected_segment_revision=revision, representative_refs=())
            with self.subTest(revision=revision), self.assertRaises(KeyError):
                self.fixture.publish(key="hidden-revision", expected_segment_revision=revision,
                                     representative_refs=())
            with self.subTest(revision=revision), self.assertRaises(KeyError):
                self.store.attribute(self.study, key="hidden-attribution", expected_registry_version=fixtures.REGISTRY,
                                     expected_segment_revision=revision, intent_id="intent", supports=[(mention, evidence)])
        self.assertEqual(self.fixture.snapshot(), before)
        self.fixture.grants[1] = replace(project_grant, evidence_refs=frozenset({(1, mention, evidence), (2, mention, evidence)}))
        with self.assertRaises(Conflict):
            self.preflight("candidate", expected_segment_revision=1, representative_refs=())
        self.fixture.grants[1] = replace(project_grant, evidence_refs=frozenset({(2, mention, evidence)}))
        result = self.preflight("candidate", expected_segment_revision=2, representative_refs=())
        self.assertEqual(result["segment_revision"], 2)
        self.assertTrue(result["candidate_allowed"])

    def test_http_source_filter_accepts_exact_english_and_chinese_source_labels(self):
        self.fixture.publish()
        corpus = self.fixture.case.case
        study, scope = corpus.project()
        sources = ("论坛", "社区", "forum")
        drafts = []
        for number, source in enumerate(sources, 1):
            text = f"合成公开原话 {number}"
            row = [text, source, f"https://synthetic.invalid/source/{number}", *corpus_fixtures.ROW[3:]]
            _, [record] = corpus.import_rows([row], study=study, scope=scope)
            corpus.app.state.corpus.review(
                study, record, decision="verified", role="user_quote", reason="合成资料人工核验",
                basis="核对合成来源和许可", retention_until=corpus.retain,
                license_status="authorized", license_evidence_ref="local:synthetic-license",
            )
            interval = EvidenceInterval(record, sha256(text.encode()).hexdigest(), 0, len(text))
            drafts.append(self.fixture.case.member(f"source-{number}", interval, segment_no=number))
        mentions = MentionStore(self.fixture.db, authorize=lambda target, _: fixtures.ACTOR if target == study else None)
        mentions.publish_revision(study, key="synthetic-source-labels", expected_revision=0,
                                  rule_version="synthetic-v1", members=drafts)
        grant = replace(self.fixture.grants[1], study_id=study)
        app = create_app(corpus.settings, relation_grants=lambda: (grant,))
        path = f"/api/studies/{study}/mentions"
        with TestClient(app, base_url=str(corpus.client.base_url), client=("127.0.0.1", 29205)) as client:
            for labels in (("论坛",), ("论坛", "社区"), ("论坛", "forum")):
                with self.subTest(labels=labels):
                    reply = client.get(path, params={"source": labels})
                    self.assertEqual(reply.status_code, 200, reply.text)
                    self.assertEqual(reply.headers["Cache-Control"], "no-store")
                    payload = reply.json()
                    self.assertCountEqual(payload["filter_echo"]["source"], labels)
                    self.assertCountEqual(
                        [ref["source"] for row in payload["items"] for ref in row["evidence_refs"]], labels,
                    )
            invalid = "synthetic-control" + chr(1) + "论坛"
            for label in (invalid, " " * 2, "论坛" * 65):
                reply = client.get(path, params={"source": label})
                self.assertEqual(reply.status_code, 422, reply.text)
                self.assertEqual(reply.json()["code"], "INVALID_REQUEST")
                self.assertNotIn(label, reply.text)

    def test_protected_product_ancestor_and_historical_registry_are_immutable(self):
        db_store = self.fixture.db
        with db_store.db() as db:
            registry(db, "1.0.0")
            for product, parent in (("P-ROOT", None), ("P-CHILD", "P-ROOT")):
                insert(db, "m06_product", registry_version="1.0.0", product_category_id=product,
                       name=product, description="", parent_id=parent, status="confirmed", version="1.0.0")
            seal_registry(db, "1.0.0")
            registry(db, "2.0.0", "1.0.0")
            db.execute("""INSERT INTO m06_product
                          SELECT '2.0.0', product_category_id, name, description, parent_id, status, version
                          FROM m06_product WHERE registry_version='1.0.0'""")
            refs = [PublishedProductRef("1.0.0", "P-CHILD")]
            protect_published_products(db, "2.0.0", refs)
            db.execute("UPDATE m06_product SET status='retired' WHERE registry_version='2.0.0' AND parent_id IS NULL")
            with self.assertRaises(Conflict):
                protect_published_products(db, "2.0.0", refs)
            db.execute("DELETE FROM m06_product WHERE registry_version='2.0.0' AND parent_id IS NOT NULL")
            db.execute("DELETE FROM m06_product WHERE registry_version='2.0.0'")
            db.execute("DELETE FROM m06_registry WHERE registry_version='2.0.0'")
        historical = self.store.definitions("product", registry_version="1.0.0")["items"]
        self.assertEqual([(row["product_category_id"], row["parent_id"], row["status"]) for row in historical],
                         [("P-CHILD", "P-ROOT", "confirmed"), ("P-ROOT", None, "confirmed")])


if __name__ == "__main__":
    unittest.main()
