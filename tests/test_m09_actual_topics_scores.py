"""Exercise edge outcomes through the provisioned M09-B runtime."""

from dataclasses import replace
import os
import unittest

import numpy as np

from src.discovery.embedding_backend import EmbeddingProfile
from src.discovery.embedding_inputs import Lineage
from src.discovery.embeddings import EmbeddingBatch, EmbeddingRow
from src.discovery.topics import TopicConfig, _cluster_batch


@unittest.skipUnless(
    os.environ.get("VOC_M09_MODEL_DIR") and os.environ.get("VOC_M09_MODEL_MANIFEST"),
    "requires the separately provisioned local model and BERTopic runtime",
)
class TopicRuntimeEdgeTests(unittest.TestCase):
    def setUp(self):
        profile = EmbeddingProfile(
            "m09-edge-fixture", "v1", "1" * 64, 12, ("en", "zh"), 128, 2, False, "fixture", "1", "1",
        )
        rows = tuple(
            EmbeddingRow(
                f"doc-{index}",
                Lineage("study", "scope", "v1", "batch", f"record-{index}", "0" * 64,
                        0, 1, "https://synthetic.invalid/x", "fixture"),
                "en-us", f"{index:064x}", f"{index + 1:064x}", "isolated point",
            )
            for index in range(12)
        )
        vectors = np.eye(len(rows), dtype=np.float32)
        self.batch = EmbeddingBatch("run", profile, "prep", "1.0.0", "en-us", "en-us", rows, vectors, False)
        self.config = TopicConfig(
            random_seed=19, n_neighbors=6, n_components=2, min_dist=0.1,
            min_cluster_size=6, min_samples=6, top_n_words=10,
        )

    def assert_all_outliers(self, batch, expected_status):
        status, labels, topics, effective, runtime = _cluster_batch(batch, self.config)
        self.assertEqual(status, expected_status)
        self.assertEqual(labels, (-1,) * len(batch.rows))
        self.assertEqual(topics, ())
        self.assertEqual(effective, self.config)
        self.assertIn("bertopic", dict(runtime))

    def test_real_tokenizer_returns_empty_vocabulary(self):
        rows = tuple(replace(row, model_text="there and 123") for row in self.batch.rows)
        self.assert_all_outliers(replace(self.batch, rows=rows), "empty_vocabulary")

    def test_real_clusterer_returns_natural_all_noise(self):
        self.assert_all_outliers(self.batch, "no_clusters")
