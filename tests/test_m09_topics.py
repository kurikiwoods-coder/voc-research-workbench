"""Lightweight M09-B contract checks with temporary M05/M06 fixtures."""

import unittest
from unittest.mock import patch

from src.discovery.topics import TopicConfig, _terms, cluster_offline
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
        def revoke(batch, config):
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

    def test_invalid_configuration_is_rejected(self):
        for options in ({"random_seed": -1}, {"n_neighbors": 1}, {"n_components": 0}, {"min_dist": float("nan")},
                        {"min_cluster_size": 1}, {"min_samples": False}, {"top_n_words": 101}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "m09_topic_invalid_"):
                TopicConfig(**options)
