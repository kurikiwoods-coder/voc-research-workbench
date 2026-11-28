"""Opt-in M09-A acceptance against the approved local multilingual model."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from src.discovery.embedding_backend import (
    EmbeddingProfile, LOCAL_BACKEND, LOCAL_BACKEND_VERSION, LocalSentenceTransformer,
    local_runtime_version, manifest_fingerprint,
)
import test_m09_embeddings as embedding_fixtures


MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


def approved_backend():
    assets = json.loads(Path(os.environ["VOC_M09_MODEL_MANIFEST"]).read_text(encoding="utf-8"))
    agreed = json.loads(
        (Path(__file__).resolve().parents[1] / "docs/evidence/m09-a/model-assets.json").read_text(encoding="utf-8")
    )
    if assets != agreed:
        raise ValueError("The manifest differs from the verified model revision")
    profile = EmbeddingProfile(
        MODEL, REVISION, manifest_fingerprint(agreed), 384, ("zh", "en"), 128, 4, True,
        LOCAL_BACKEND, LOCAL_BACKEND_VERSION, local_runtime_version(),
    )
    return LocalSentenceTransformer(os.environ["VOC_M09_MODEL_DIR"], profile, agreed)


@unittest.skipUnless(
    os.environ.get("VOC_M09_MODEL_DIR") and os.environ.get("VOC_M09_MODEL_MANIFEST"),
    "requires the separately provisioned and verified local model",
)
class ApprovedModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = approved_backend()
        cls.addClassCleanup(cls.backend.close)

    def test_semantic_ranking_and_vector_contract(self):
        anchor, paraphrase, chinese, unrelated, other_chinese = self.backend.encode((
            "The battery runs out after just one hour of use.",
            "It only lasts an hour before the battery is empty.",
            "电池只能用一个小时就没电了。",
            "The zipper on the backpack is difficult to open.",
            "这个背包的拉链很难拉开。",
        ))
        vectors = np.stack((anchor, paraphrase, chinese, unrelated, other_chinese))
        self.assertEqual(vectors.shape, (5, 384))
        self.assertEqual(vectors.dtype, np.float32)
        self.assertTrue(np.isfinite(vectors).all())
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, rtol=1e-5, atol=1e-6)
        en_same, zh_same = float(anchor @ paraphrase), float(anchor @ chinese)
        en_different, zh_different = float(anchor @ unrelated), float(chinese @ other_chinese)
        self.assertGreater(en_same, 0.65)
        self.assertGreater(zh_same, 0.55)
        self.assertGreater(en_same - en_different, 0.25)
        self.assertGreater(zh_same - zh_different, 0.25)
        print(f"Cosine: en/en same={en_same:.4f}, en/zh same={zh_same:.4f}, "
              f"en/en different={en_different:.4f}, zh/zh different={zh_different:.4f}", flush=True)

    def test_long_input_truncates_at_recorded_model_limit(self):
        prefix = "the battery needs charging " * 140
        first = prefix + "lasts a week"
        second = prefix + "runs out immediately"
        vectors = self.backend.encode((first, second))
        transformer = self.backend._model
        untruncated = transformer.tokenizer(first, truncation=False)["input_ids"]
        truncated = transformer.tokenize([first])["input_ids"].shape[1]
        self.assertGreater(len(untruncated), self.backend.profile.max_sequence_length)
        self.assertEqual(truncated, self.backend.profile.max_sequence_length)
        np.testing.assert_allclose(vectors[0], vectors[1], rtol=1e-5, atol=1e-6)
        print(f"Tokenized length: {len(untruncated)} before truncation, {truncated} at inference", flush=True)

    def test_authorized_fixture_lineage_cache_repair_and_uncached_replay(self):
        fixture = embedding_fixtures.EmbeddingTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        run = embedding_fixtures.run
        first = run(fixture.evidence, self.backend, fixture.refs, cache=fixture.cache)
        self.assertFalse(first.cache_hit)
        self.assertEqual(first.model.revision, REVISION)
        self.assertEqual(first.vectors.dtype, np.float32)
        self.assertEqual(first.vectors.shape, (2, 384))
        ids = tuple(row.document_id for row in first.rows)
        self.assertEqual(ids, tuple(sorted(ids)))
        self.assertEqual(
            {row.lineage.evidence_id for row in first.rows}, {ref.evidence_id for ref in fixture.refs}
        )
        self.assertTrue(all(len(row.model_input_sha256) == 64 for row in first.rows))
        with patch.object(self.backend, "encode", side_effect=AssertionError("cache must avoid inference")):
            cached = run(fixture.evidence, self.backend, fixture.refs[::-1], cache=fixture.cache)
        self.assertTrue(cached.cache_hit)
        self.assertEqual(first.run_id, cached.run_id)
        np.testing.assert_array_equal(first.vectors, cached.vectors)
        uncached = run(fixture.evidence, self.backend, fixture.refs[::-1])
        self.assertFalse(uncached.cache_hit)
        self.assertEqual(first.run_id, uncached.run_id)
        self.assertEqual(ids, tuple(row.document_id for row in uncached.rows))
        np.testing.assert_allclose(first.vectors, uncached.vectors, rtol=1e-5, atol=1e-6)
        entry = fixture.cache / f"{first.run_id}.vec"
        with entry.open("r+b") as stream:
            original_checksum_byte = stream.read(1)
            stream.seek(0)
            stream.write(bytes([original_checksum_byte[0] ^ 1]))
        repaired = run(fixture.evidence, self.backend, fixture.refs, cache=fixture.cache)
        self.assertFalse(repaired.cache_hit)
        np.testing.assert_allclose(first.vectors, repaired.vectors, rtol=1e-5, atol=1e-6)
        self.assertTrue(run(fixture.evidence, self.backend, fixture.refs, cache=fixture.cache).cache_hit)
        fixture.assert_no_network()
