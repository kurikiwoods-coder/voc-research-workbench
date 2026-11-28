"""Exercise M09-C persistence and replay through the existing offline fixture pipeline."""

from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import json
import sqlite3
import unittest
from unittest.mock import patch

from src.discovery.topic_runs import TopicRuns
from src.discovery.topic_store import TopicRunStore
from src.discovery.topics import CandidateTopic, TopicAssignment, TopicConfig, TopicKeyword
from src.raw_store.mentions import MentionStore
from src.raw_store.registry_versions import RegistryVersions
from src.raw_store.relations import RelationStore
from src.raw_store.store import Conflict, Store
import test_m06_mentions as mentions
import test_m09_embeddings as fixtures


def cluster_fixture(batch, config, *, observe_diagnostics=None):
    # Pin a deterministic two-document result for storage checks. The upstream
    # M09-B actual-model tests exercise BERTopic's own clustering behavior.
    if len(batch.rows) == 1:
        labels = (0,)
    else:
        labels = (0, -1) if config.random_seed == 42 else (-1, 0)
    assignments = tuple(
        TopicAssignment(
            row.document_id, label, raw_topic_id=label, hdbscan_cluster_id=label,
            hdbscan_membership_probability=0.9 if label == 0 else 0.0,
            hdbscan_outlier_score=0.1 if label == 0 else 0.8,
            centroid_cosine=1.0 if label == 0 else None,
        )
        for row, label in zip(batch.rows, labels, strict=True)
    )
    if observe_diagnostics is not None:
        observe_diagnostics(assignments)
    term = "offline" if config.random_seed == 42 else "resume"
    topic = CandidateTopic(0, 1, (TopicKeyword(term, 1.0),))
    return "clustered", labels, (topic,), config, ()


class TopicPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.EmbeddingTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.addCleanup(self.fixture.assert_no_network)
        self.workspace = self.fixture.case.db
        self.authorized = {self.fixture.case.study}
        self.runs = self.service()

    def service(self, *, workspace=None, evidence=None):
        if workspace is not None and evidence is None:
            evidence = self.fixture.reader(
                mentions=MentionStore(workspace, authorize=self.fixture.case.authorize),
                registry=RegistryVersions(RelationStore(workspace)),
            )
        return TopicRuns(
            workspace or self.workspace, evidence or self.fixture.evidence,
            authorize_project=self.authorized.__contains__,
        )

    def create(self, request_id, refs=None, *, service=None, backend=None, config=TopicConfig()):
        return (service or self.runs).create(
            backend or self.fixture.backend,
            self.fixture.refs if refs is None else refs,
            request_id=request_id, registry_version=mentions.CATALOG,
            analysis_language="zh-CN", output_language="en-US", config=config,
        )

    @staticmethod
    def by_id(run, collection, field):
        return {row[field]: row for row in run[collection]}

    def test_exact_membership_and_evidence_reopen_without_copying_raw_text(self):
        run = self.create("exact-lineage")
        self.assertEqual(
            (run["study_id"], run["scope_id"], run["scope_version"]),
            (self.fixture.case.study, self.fixture.case.scope, "v1"),
        )
        self.assertTrue(run["started_at"])
        self.assertTrue(run["finished_at"])
        self.assertEqual(run["metadata"]["registry_version"], mentions.CATALOG)
        self.assertEqual(run["metadata"]["model"]["model_id"], self.fixture.backend.profile.model_id)
        self.assertEqual(run["metadata"]["model"]["revision"], self.fixture.backend.profile.revision)
        self.assertEqual(len(run["metadata"]["vector_sha256"]), 64)
        self.assertEqual(run["metadata"]["analysis_language"], "zh-cn")
        self.assertEqual(run["metadata"]["output_language"], "en-us")

        expected = {
            document.lineage.document_id: document
            for document in map(self.fixture.evidence.read, self.fixture.refs)
        }
        members = self.by_id(run, "members", "document_id")
        self.assertEqual(set(members), set(expected))
        self.assertNotIn(self.fixture.quote, json.dumps(run, ensure_ascii=False))

        workspace = Store(self.workspace.directory, edition=self.workspace.edition)
        reopened = self.service(workspace=workspace)
        self.assertEqual(reopened.get(run["run_id"]), run)
        for document_id, document in expected.items():
            lineage = members[document_id]["lineage"]
            self.assertEqual(
                (lineage["record_id"], lineage["scope_version"], lineage["segment_revision"],
                 lineage["mention_id"], lineage["evidence_id"], lineage["raw_sha256"],
                 lineage["source_locator"], lineage["start_cp"], lineage["end_cp"]),
                (document.lineage.record_id, document.lineage.scope_version, document.lineage.segment_revision,
                 document.lineage.mention_id, document.lineage.evidence_id, document.lineage.raw_sha256,
                 document.lineage.source_locator, document.lineage.start_cp, document.lineage.end_cp),
            )
            self.assertEqual(
                members[document_id]["original_excerpt_sha256"], sha256(document.original_text.encode()).hexdigest()
            )
            self.assertEqual(
                reopened.evidence_for(run["run_id"], document_id),
                replace(document, original_language=document.original_language.lower()),
            )

    def test_empty_batch_has_no_topic_or_members_and_does_not_embed(self):
        run = self.create("empty-batch", ())
        self.assertEqual(run["status"], "empty")
        self.assertFalse(run["members"])
        self.assertFalse(run["topics"])
        self.assertIsNone(run["metadata"]["embedding_run_id"])
        self.assertEqual(self.fixture.backend.inputs, [])
        self.assertEqual(self.runs.get(run["run_id"]), run)

    def test_small_batch_preserves_the_outlier_topic_and_all_members(self):
        run = self.create("small-batch")
        self.assertEqual(run["status"], "insufficient_samples")
        self.assertEqual([topic["topic_id"] for topic in run["topics"]], [-1])
        self.assertEqual([member["topic_id"] for member in run["members"]], [-1, -1])
        self.assertTrue(all(member["membership_probability"] is None for member in run["members"]))
        self.assertTrue(all(member["outlier_score"] is None for member in run["members"]))

    def test_raw_diagnostics_remain_linked_to_all_input_documents(self):
        with patch("src.discovery.topics._cluster_batch", side_effect=cluster_fixture):
            run = self.create("clustered")
        topics = self.by_id(run, "topics", "topic_id")
        members = self.by_id(run, "members", "topic_id")
        self.assertEqual(set(topics), {-1, 0})
        self.assertEqual(
            topics[0]["representative_document_ids"], [members[0]["document_id"]],
        )
        self.assertEqual(members[0]["membership_probability"], 0.9)
        self.assertEqual(members[0]["outlier_score"], 0.1)
        self.assertEqual(members[0]["centroid_similarity"], 1.0)
        self.assertEqual(members[-1]["membership_probability"], 0.0)
        self.assertEqual(members[-1]["outlier_score"], 0.8)
        self.assertIsNone(members[-1]["centroid_similarity"])
        self.assertFalse(members[-1]["postprocessing"])
        self.assertEqual(run["quality"]["m09_b_synthetic_purity"], [[8, 11], [8, 12], [8, 13]])
        self.assertEqual(run["quality"]["diagnostic"], "QUALITY_DIAGNOSTIC_WARNING")
        self.assertEqual(run["quality"]["g3"], "G3_PENDING")
        self.assertEqual(run["quality"]["postprocessing"], "NOT_APPLIED")

    def test_revocation_blocks_drilldown_and_replay_and_masks_the_derived_terms(self):
        with patch("src.discovery.topics._cluster_batch", side_effect=cluster_fixture):
            run = self.create("before-revocation", self.fixture.refs[:1])
        document_id = run["members"][0]["document_id"]
        self.fixture.case.revoke_batch(self.fixture.batch)
        with self.assertRaises((PermissionError, Conflict, KeyError)):
            self.runs.evidence_for(run["run_id"], document_id)
        with self.assertRaises((PermissionError, Conflict, KeyError)):
            self.runs.replay(run["run_id"], self.fixture.backend, request_id="revoked-replay")
        saved = self.runs.get(run["run_id"])
        self.assertEqual(saved["members"][0]["document_id"], document_id)
        self.assertFalse(self.by_id(saved, "topics", "topic_id")[0]["keywords"])
        self.assertNotIn("synthetic.invalid", json.dumps(saved))
        self.assertEqual(len(self.fixture.backend.inputs), 1)

    def test_project_access_and_frozen_scope_are_checked_on_every_use(self):
        run = self.create("project-run")
        run_id = run["run_id"]
        document_id = run["members"][0]["document_id"]
        self.authorized.clear()
        for action in (
            lambda: self.create("denied-project"),
            lambda: self.runs.get(run_id),
            lambda: self.runs.evidence_for(run_id, document_id),
            lambda: self.runs.replay(run_id, self.fixture.backend, request_id="denied-replay"),
            lambda: self.runs.compare(run_id, run_id),
        ):
            with self.subTest(action=action), self.assertRaises((PermissionError, Conflict, KeyError)):
                action()

        another_study, another_scope = self.fixture.case.case.project()
        self.authorized.add(another_study)
        another = self.service(evidence=self.fixture.reader(study_id=another_study, scope_id=another_scope))
        with self.assertRaises((PermissionError, Conflict, KeyError)):
            another.get(run_id)
        with self.assertRaises((PermissionError, Conflict, KeyError)):
            self.create("wrong-project-input", service=another)
        self.assertEqual(len(self.fixture.backend.inputs), 1)

    def test_replay_retains_both_snapshots_and_pins_the_model_artifact(self):
        run = self.create("first")
        result = self.runs.replay(run["run_id"], self.fixture.backend, request_id="replay")
        self.assertNotEqual(result["run_id"], run["run_id"])
        self.assertEqual(result["replay_of"], run["run_id"])
        self.assertEqual(result["metadata"], run["metadata"])
        self.assertEqual(result["members"], run["members"])
        self.assertEqual(result["topics"], run["topics"])
        self.assertEqual(self.runs.get(run["run_id"]), run)
        self.assertTrue(self.runs.compare(run["run_id"], result["run_id"])["same_result"])

        another = fixtures.FixtureBackend()
        another.profile = replace(another.profile, artifact_sha256="2" * 64)
        with self.assertRaises((ValueError, Conflict)):
            self.runs.replay(run["run_id"], another, request_id="wrong-model")
        self.assertEqual(another.inputs, [])
        self.assertEqual(len(self.fixture.backend.inputs), 2)

    def test_replay_checks_actual_vectors_before_publishing(self):
        run = self.create("vector-base")
        with patch.object(self.fixture.backend, "encode", return_value=[[1, 2, 3], [3, 2, 1]]):
            with self.assertRaises((ValueError, Conflict)):
                self.runs.replay(run["run_id"], self.fixture.backend, request_id="vector-replay")
        self.assertEqual(self.runs.get(run["run_id"]), run)
        result = self.runs.replay(run["run_id"], self.fixture.backend, request_id="vector-replay")
        self.assertEqual(result["metadata"]["vector_sha256"], run["metadata"]["vector_sha256"])

    def test_compare_reports_model_parameter_member_keyword_and_evidence_changes(self):
        with patch("src.discovery.topics._cluster_batch", side_effect=cluster_fixture):
            original = self.create("comparison-original")
            rerun = self.create("comparison-parameter", config=TopicConfig(random_seed=43))
        comparison = self.runs.compare(original["run_id"], rerun["run_id"])
        self.assertFalse(comparison["same_result"])
        self.assertTrue(comparison["metadata_changes"])
        self.assertTrue(comparison["membership_changes"])
        self.assertTrue(comparison["outlier_changes"])
        self.assertTrue(comparison["keyword_changes"])
        self.assertFalse(comparison["evidence_changes"])

        renamed = fixtures.FixtureBackend()
        renamed.profile = replace(renamed.profile, revision="v2")
        smaller = self.create("comparison-model", self.fixture.refs[:1], backend=renamed)
        comparison = self.runs.compare(original["run_id"], smaller["run_id"])
        self.assertFalse(comparison["same_result"])
        self.assertTrue(comparison["metadata_changes"])
        self.assertTrue(comparison["evidence_changes"])
        self.assertEqual(self.runs.get(original["run_id"]), original)

    def test_distinct_requests_create_distinct_immutable_runs(self):
        first = self.create("first-identical-request")
        second = self.create("second-identical-request")
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["metadata"], second["metadata"])
        self.assertTrue(self.runs.compare(first["run_id"], second["run_id"])["same_result"])
        detached = self.runs.get(first["run_id"])
        detached["metadata"]["analysis_language"] = "fr"
        self.assertEqual(self.runs.get(first["run_id"]), first)

    def test_sealed_sqlite_rows_resist_tamper_and_restore_from_consistent_backup(self):
        with patch("src.discovery.topics._cluster_batch", side_effect=cluster_fixture):
            before = self.create("backup-original")
        store = TopicRunStore(self.workspace)
        path = store.path
        backup = self.workspace.directory / "topic-backup.sqlite3"
        tampering = (
            "UPDATE topic_runs SET status='empty'",
            "DELETE FROM topic_runs",
            "UPDATE topics SET keywords='[]'",
            "INSERT OR REPLACE INTO topics SELECT run_id, topic_id, '[]' FROM topics",
            "UPDATE topic_members SET topic_id=0",
            "DELETE FROM topic_members",
            "DELETE FROM topic_representatives",
        )
        with closing(sqlite3.connect(path)) as current, closing(sqlite3.connect(backup)) as saved:
            current.execute("PRAGMA foreign_keys=ON")
            for sql in tampering:
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), current:
                    current.execute(sql)
            self.assertEqual(current.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
            self.assertEqual(current.execute("PRAGMA foreign_key_check").fetchall(), [])
            current.backup(saved)

        later = self.create("backup-later")
        with closing(sqlite3.connect(backup)) as saved, closing(sqlite3.connect(path)) as recovered:
            saved.backup(recovered)
        restarted = self.service(workspace=Store(self.workspace.directory, edition=self.workspace.edition))
        self.assertEqual(restarted.get(before["run_id"]), before)
        with self.assertRaises(KeyError):
            restarted.get(later["run_id"])

    def test_interruption_recovers_idempotently_after_reopening(self):
        with patch.object(self.fixture.backend, "encode", side_effect=RuntimeError("fixture interruption")):
            with self.assertRaisesRegex(RuntimeError, "fixture interruption"):
                self.create("interrupted")
        reopened = self.service(workspace=Store(self.workspace.directory, edition=self.workspace.edition))
        run = self.create("interrupted", service=reopened)
        self.assertEqual(self.create("interrupted", self.fixture.refs[::-1], service=reopened), run)
        self.assertEqual(len(self.fixture.backend.inputs), 1)
        with self.assertRaises((ValueError, Conflict)):
            self.create("interrupted", self.fixture.refs[:1], service=reopened)
        self.assertEqual(reopened.get(run["run_id"]), run)
        self.assertEqual(len(self.fixture.backend.inputs), 1)
