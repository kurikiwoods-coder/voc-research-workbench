"""Cover M09-D candidate revisions and current evidence access."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import sqlite3
import unittest
from unittest.mock import patch

from src.discovery.topic_candidates import TopicCandidates
from src.discovery.topic_store import CANDIDATE_OUTPUT_VERSION, TopicRunStore
from src.discovery.topics import CandidateTopic, TopicConfig, TopicKeyword
from src.raw_store.store import Conflict, Store
import test_m09_persistence as persistence


def related_topics(batch, config, *, observe_diagnostics=None):
    return "clustered", (0, 1), (
        CandidateTopic(0, 1, (TopicKeyword("shared", 0.7), TopicKeyword("thread", 0.2))),
        CandidateTopic(1, 1, (TopicKeyword("shared", 0.5), TopicKeyword("sync", 0.4))),
    ), config, ()


class TopicCandidateTest(unittest.TestCase):
    def setUp(self):
        self.base = persistence.TopicPersistenceTest()
        self.addCleanup(self.base.doCleanups)
        self.base.setUp()
        self.candidates = TopicCandidates(self.base.runs)

    def run_with_topics(self, request_id, *, cluster=persistence.cluster_fixture, config=TopicConfig()):
        with patch("src.discovery.topics._cluster_batch", side_effect=cluster):
            return self.base.create(request_id, config=config)["run_id"]

    def test_projection_uses_stable_evidence_ids_and_separates_outliers(self):
        run_id = self.run_with_topics("candidates-and-outlier")
        output = self.candidates.get(run_id)
        self.assertEqual(output["output_version"], CANDIDATE_OUTPUT_VERSION)
        self.assertEqual(output["revision"], 0)
        self.assertEqual(output["coverage"], {
            "input_count": 2, "eligible_count": 2, "candidate_count": 1, "candidate_document_count": 1,
            "outlier_count": 1, "rejected_candidate_count": 0, "restricted_candidate_count": 0,
        })
        candidate, = output["candidates"]
        self.assertEqual(candidate["candidate_id"], f"{run_id}:0")
        self.assertEqual(candidate["decision"], "pending")
        self.assertEqual(candidate["description"], "offline")
        self.assertEqual(candidate["representative_document_ids"], candidate["member_document_ids"])
        document, = candidate["member_document_ids"]
        self.assertEqual(self.base.runs.evidence_for(run_id, document).lineage.document_id, document)
        self.assertNotIn(self.base.fixture.quote, json.dumps(output, ensure_ascii=False))
        self.assertIsNone(self.candidates.get(run_id)["candidates"][0]["decided_at"])

    def test_topic_relationships_reference_shared_keywords(self):
        run_id = self.run_with_topics("related-topics", cluster=related_topics)
        output = self.candidates.get(run_id)
        self.assertEqual(output["topic_relationships"], [{
            "left_topic_id": 0, "right_topic_id": 1, "shared_terms": ["shared"], "similarity": 1 / 3,
        }])
        self.assertEqual(output["coverage"]["candidate_count"], 2)

    def test_zero_candidates_are_valid_for_empty_and_all_outlier_runs(self):
        for request, refs in (("empty", ()), ("all-outliers", self.base.fixture.refs)):
            with self.subTest(request=request):
                output = self.candidates.get(self.base.create(request, refs)["run_id"])
                self.assertEqual(output["candidates"], [])
                self.assertEqual(output["coverage"]["candidate_count"], 0)
                self.assertEqual(output["coverage"]["outlier_count"], len(refs))
                self.assertEqual(output["topic_relationships"], [])

    def test_review_versions_reopen_and_replay_without_inference(self):
        run_id = self.run_with_topics("reviewable")
        original = self.candidates.get(run_id)
        rejected = self.candidates.review(
            run_id, 0, decision="rejected", expected_revision=0, request_id="first", actor_ref="owner-local",
        )
        retained = self.candidates.review(
            run_id, 0, decision="retained", expected_revision=1, request_id="second", actor_ref="owner-local",
        )
        self.assertEqual(rejected["coverage"]["candidate_count"], 0)
        self.assertEqual(rejected["candidates"][0]["decision_revision"], 1)
        self.assertEqual(rejected["candidates"][0]["decision_actor_ref"], "owner-local")
        self.assertEqual(retained["candidates"][0]["decision_revision"], 2)
        self.assertEqual(retained["coverage"]["candidate_count"], 1)

        workspace = self.base.workspace
        reopened = TopicCandidates(self.base.service(workspace=Store(workspace.directory, edition=workspace.edition)))
        self.assertEqual(reopened.get(run_id, revision=0), {**original, "latest_revision": 2})
        self.assertEqual(reopened.get(run_id, revision=1), {**rejected, "latest_revision": 2})
        self.assertEqual(reopened.get(run_id), retained)
        older_receipt = reopened.review(
            run_id, 0, decision="rejected", expected_revision=0, request_id="first", actor_ref="owner-local",
        )
        self.assertEqual(older_receipt, {**rejected, "latest_revision": 2})
        self.assertEqual(len(self.base.fixture.backend.inputs), 1)

    def test_review_rejects_invalid_stale_or_unmatched_requests(self):
        run_id = self.run_with_topics("review-guard")
        self.candidates.review(run_id, 0, decision="rejected", expected_revision=0, request_id="request-id", actor_ref="owner-local")
        with self.assertRaisesRegex(Conflict, "m09_candidate_idempotency_conflict"):
            self.candidates.review(run_id, 0, decision="retained", expected_revision=0, request_id="request-id", actor_ref="owner-local")
        with self.assertRaisesRegex(Conflict, "m09_candidate_idempotency_conflict"):
            self.candidates.review(run_id, 0, decision="rejected", expected_revision=0, request_id="request-id", actor_ref="other")
        with self.assertRaisesRegex(Conflict, "m09_candidate_revision_conflict"):
            self.candidates.review(run_id, 0, decision="retained", expected_revision=0, request_id="new-id", actor_ref="owner-local")
        for revision in (-1, True, 2**63):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.candidates.get(run_id, revision=revision)
        with self.assertRaises(KeyError):
            self.candidates.get(run_id, revision=2)
        with self.assertRaises(KeyError):
            self.candidates.review(run_id, 100, decision="retained", expected_revision=1, request_id="new-id", actor_ref="owner-local")
        with self.assertRaises(ValueError):
            self.candidates.review(run_id, -1, decision="retained", expected_revision=1, request_id="new-id", actor_ref="owner-local")

    def test_concurrent_reviews_cannot_overwrite_another_decision(self):
        run_id = self.run_with_topics("concurrent-review")

        def decide(decision):
            try:
                self.candidates.review(run_id, 0, decision=decision, expected_revision=0, request_id=decision, actor_ref="owner-local")
            except Conflict as exc:
                return str(exc)
            return decision

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(decide, ("retained", "rejected")))
        self.assertIn("m09_candidate_revision_conflict", results)
        output = self.candidates.get(run_id)
        self.assertEqual(output["latest_revision"], 1)
        self.assertIn(output["candidates"][0]["decision"], results)

    def test_revocation_removes_candidate_terms_and_support_from_all_revisions(self):
        run_id = self.run_with_topics("revocable", cluster=related_topics)
        initial = self.candidates.get(run_id)
        revoked, = (
            member for member in initial["run"]["members"]
            if member["lineage"]["batch_id"] == self.base.fixture.batch
        )
        topic_id = revoked["topic_id"]
        revoked_locator = revoked["lineage"]["source_locator"]
        self.assertTrue(initial["topic_relationships"])
        self.candidates.review(
            run_id, topic_id, decision="retained", expected_revision=0, request_id="review", actor_ref="owner-local",
        )
        self.base.fixture.case.revoke_batch(self.base.fixture.batch)
        for revision in (0, 1):
            with self.subTest(revision=revision):
                saved = self.candidates.get(run_id, revision=revision)
                candidate, = (item for item in saved["candidates"] if item["topic_id"] == topic_id)
                self.assertFalse(candidate["evidence_eligible"])
                self.assertIsNone(candidate["description"])
                for field in ("keywords", "representative_document_ids", "member_document_ids"):
                    self.assertEqual(candidate[field], [])
                self.assertEqual(saved["coverage"]["candidate_count"], 1)
                self.assertEqual(saved["coverage"]["restricted_candidate_count"], 1)
                self.assertNotIn(revoked_locator, json.dumps(saved))
                self.assertEqual(saved["coverage"]["eligible_count"], 1)
                self.assertEqual(saved["topic_relationships"], [])
        with self.assertRaisesRegex(Conflict, "m09_candidate_evidence_ineligible"):
            self.candidates.review(
                run_id, topic_id, decision="rejected", expected_revision=1,
                request_id="denied", actor_ref="owner-local",
            )
        with self.assertRaises((Conflict, KeyError, PermissionError)):
            self.candidates.compare(run_id, run_id, left_revision=0, right_revision=1)
        self.base.authorized.clear()
        with self.assertRaisesRegex(Conflict, "m09_project_permission_required"):
            self.candidates.get(run_id, revision=0)

    def test_comparison_uses_cluster_overlap_and_candidate_coverage(self):
        first = self.run_with_topics("original")
        second = self.run_with_topics("changed", config=TopicConfig(random_seed=7))
        self.candidates.review(second, 0, decision="rejected", expected_revision=0, request_id="rejected", actor_ref="owner-local")
        unchanged_topics = self.candidates.compare(second, second, left_revision=0, right_revision=1)
        self.assertTrue(unchanged_topics["same_result"])
        self.assertEqual(unchanged_topics["candidate_matches"][0]["similarity"], 1.0)
        self.assertEqual(unchanged_topics["candidate_matches"][0]["right_decision"], "rejected")
        changed = self.candidates.compare(first, second)
        self.assertEqual(changed["candidate_matches"], [])
        self.assertEqual(changed["unmatched_candidate_topics"], {"left": [0], "right": [0]})
        self.assertEqual(changed["candidate_coverage"]["delta"]["candidate_document_count"], -1)

    def test_existing_sidecar_upgrades_preserving_snapshots_and_seals_review_rows(self):
        run_id = self.run_with_topics("v1-existing")
        original = self.base.runs.get(run_id)
        store = TopicRunStore(self.base.workspace)
        with closing(sqlite3.connect(store.path)) as db, db:
            db.execute("DROP TABLE topic_candidate_reviews")
            db.execute("DROP TRIGGER topic_runs_candidate_output_version")
            db.execute("ALTER TABLE topic_runs DROP COLUMN candidate_output_version")
            db.execute("PRAGMA user_version=1")
        reopened = TopicCandidates(self.base.service())
        self.assertEqual(reopened.get(run_id)["run"], original)
        reopened.review(run_id, 0, decision="rejected", expected_revision=0, request_id="review", actor_ref="owner-local")
        with closing(sqlite3.connect(store.path)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            for sql in (
                "UPDATE topic_candidate_reviews SET decision='retained'",
                "DELETE FROM topic_candidate_reviews",
                "UPDATE topic_runs SET candidate_output_version='tampered'",
                "INSERT OR REPLACE INTO topic_candidate_reviews SELECT * FROM topic_candidate_reviews",
            ):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), db:
                    db.execute(sql)
