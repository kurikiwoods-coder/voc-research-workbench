"""Lightweight M09-B contract checks with temporary M05/M06 fixtures."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from src.discovery.topics import TopicConfig, _assignment_diagnostics, _terms, cluster_offline
from src.raw_store.store import Conflict
import test_m09_embeddings as fixtures
import test_m06_mentions as mentions


class TopicContractTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.EmbeddingTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def cluster(self, refs):
        return cluster_offline(
            self.fixture.evidence, self.fixture.backend, refs, registry_version=mentions.CATALOG,
            analysis_language="zh-CN", output_language="en-US",
        )

    def test_empty_batch_never_encodes(self):
        result = self.cluster(())
        self.assertEqual(result.status, "empty")
        self.assertEqual(result.assignments, ())
        self.assertEqual(result.topics, ())
        self.assertIsNone(result.metadata.embedding_run_id)
        self.assertEqual(self.fixture.backend.inputs, [])

    def test_small_batch_retains_every_document_without_forcing_topics(self):
        result = self.cluster(self.fixture.refs)
        expected = sorted(self.fixture.evidence.read(ref).lineage.document_id for ref in self.fixture.refs)
        self.assertEqual(result.status, "insufficient_samples")
        self.assertEqual(result.topics, ())
        self.assertEqual([(row.document_id, row.topic_id) for row in result.assignments],
                         [(document_id, -1) for document_id in expected])
        self.assertFalse(result.outbound_allowed)
        self.assertEqual(result.research_denominator, 0)

    def test_revocation_during_clustering_blocks_result(self):
        def revoke(batch, config, *, observe_diagnostics=None):
            self.fixture.case.revoke_batch(self.fixture.batch)
            return "no_clusters", (-1, -1), (), None, ()

        with patch("src.discovery.topics._cluster_batch", side_effect=revoke):
            with self.assertRaises(Conflict):
                self.cluster(self.fixture.refs)
        self.fixture.assert_no_network()

    def test_mixed_script_terms_filter_stop_words_and_preserve_boundaries(self):
        def cut(text, *, HMM):
            self.assertFalse(HMM)
            self.assertEqual(text, "的离线")
            return ("的", "离线")

        self.assertEqual(_terms("The WiFi的离线MODE 42", cut, {"the"}), "wifi 离线 mode")

    def test_raw_labels_and_scores_follow_document_order_without_filtering(self):
        batch = SimpleNamespace(
            rows=tuple(SimpleNamespace(document_id=f"doc-{index}") for index in range(4)),
            vectors=np.array([[1, 0], [1, 0], [0, 1], [-1, 0]], dtype=np.float32),
        )
        clusterer = SimpleNamespace(
            labels_=np.array([7, 7, 7, -1]),
            probabilities_=np.array([1.0, 0.95, 0.6, 0.0]),
            outlier_scores_=np.array([0.0, 0.25, 0.8, np.nan]),
        )

        assignments = _assignment_diagnostics(batch, (0, 0, 0, -1), clusterer)

        self.assertEqual([row.document_id for row in assignments], ["doc-0", "doc-1", "doc-2", "doc-3"])
        self.assertEqual([row.topic_id for row in assignments], [0, 0, 0, -1])
        self.assertEqual([row.raw_topic_id for row in assignments], [0, 0, 0, -1])
        self.assertEqual([row.hdbscan_cluster_id for row in assignments], [7, 7, 7, -1])
        self.assertEqual([row.hdbscan_membership_probability for row in assignments], [1.0, 0.95, 0.6, 0.0])
        self.assertEqual([row.hdbscan_outlier_score for row in assignments], [0.0, 0.25, 0.8, None])
        self.assertEqual([row.centroid_cosine for row in assignments], [1.0, 1.0, 0.0, None])

    def test_unavailable_diagnostics_use_null_and_centroid_uses_all_assigned_rows(self):
        batch = SimpleNamespace(
            rows=(SimpleNamespace(document_id="left"), SimpleNamespace(document_id="right")),
            vectors=np.array([[1, 0], [0, 2]], dtype=np.float32),
        )
        left, right = _assignment_diagnostics(batch, (0, 0), SimpleNamespace())

        for row in (left, right):
            self.assertIsNone(row.hdbscan_cluster_id)
            self.assertIsNone(row.hdbscan_membership_probability)
            self.assertIsNone(row.hdbscan_outlier_score)
            self.assertAlmostEqual(row.centroid_cosine, 2 ** -0.5)

    def test_misaligned_backend_diagnostics_are_rejected(self):
        batch = SimpleNamespace(rows=(SimpleNamespace(document_id="doc"),))
        with self.assertRaisesRegex(RuntimeError, "m09_topic_diagnostic_alignment"):
            _assignment_diagnostics(batch, (-1,), SimpleNamespace(probabilities_=[0.5, 0.0]))

    def test_invalid_configuration_is_rejected(self):
        for options in ({"random_seed": -1}, {"n_neighbors": 1}, {"n_components": 0}, {"min_dist": float("nan")},
                        {"min_cluster_size": 1}, {"min_samples": False}, {"top_n_words": 101}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "m09_topic_invalid_"):
                TopicConfig(**options)
