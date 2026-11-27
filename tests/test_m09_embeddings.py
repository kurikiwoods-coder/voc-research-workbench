"""Exercise M09-A against the existing isolated M05–M08 fixtures."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from src.discovery.embedding_backend import EmbeddingProfile
from src.discovery.embedding_inputs import FixtureRecord, MentionEvidence, OfflineEvidence, SamplingEvidence
from src.discovery.embeddings import _row, embed_offline
from src.ingestion.m08_tasks import AuthorizationBlocked
from src.raw_store.registry_versions import RegistryVersions
from src.raw_store.relations import RelationStore
from src.raw_store.store import Conflict
from test_m06_constraints import registry, seal_registry
import test_m06_mentions as mentions
import test_m08_sampling as sampling


class FixtureBackend:
    profile = EmbeddingProfile(
        "m09-test", "v1", "1" * 64, 3, ("en", "zh"), 128, 2, False, "fixture", "1", "1",
    )

    def __init__(self):
        self.inputs = []

    def encode(self, texts):
        self.inputs.append(texts)
        return [[1 + value for value in sha256(text.encode()).digest()[:3]] for text in texts]


def run(evidence, backend, refs, *, cache=None, registry_version=mentions.CATALOG, analysis_language="zh-CN"):
    return embed_offline(evidence, backend, refs, registry_version=registry_version,
                         analysis_language=analysis_language, output_language="en-US", cache_dir=cache)


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.case = mentions.MentionTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.backend = FixtureBackend()
        self.case.bind_products((mentions.PRODUCT_A, mentions.PRODUCT_B))
        self.quote = "锁定离线模式 🧪 e\u0301"
        self.batch, self.interval = self.case.add_quote("zh", self.quote)
        _, second = self.case.add_quote("en", "Resume offline after a power failure")
        self.published = self.case.publish(
            [self.case.member("zh", self.interval), self.case.member("en", second)],
            proposals=(self.case.proposal("zh", self.interval, mentions.PRODUCT_A),
                      self.case.proposal("en", second, mentions.PRODUCT_B)),
        )
        self.refs = tuple(self.reference(interval, member, language) for interval, member, language in zip(
            (self.interval, second), self.published["members"], ("zh-CN", "en-US"), strict=True,
        ))
        self.evidence = self.reader()
        self.cache = self.case.db.path.parent / "m09-cache"
        self.forbidden_network = self.enterContext(
            patch("socket.getaddrinfo", side_effect=AssertionError("M09 fixture DNS denied"))
        )
        self.forbidden_connect = self.enterContext(
            patch("socket.socket.connect", side_effect=AssertionError("M09 fixture connection denied"))
        )

    def reference(self, interval, member, language, revision=1):
        record = FixtureRecord(self.case.study, self.case.scope, "v1", interval.record_id, interval.raw_sha256)
        return MentionEvidence(record, revision, member["mention_id"], member["evidence_ids"][0], language)

    def reader(self, **changes):
        options = dict(study_id=self.case.study, scope_id=self.case.scope, scope_version="v1",
                       mentions=self.case.store,
                       registry=RegistryVersions(RelationStore(self.case.db)),
                       fixture_records=tuple(ref.record for ref in self.refs))
        return OfflineEvidence(**(options | changes))

    def assert_no_network(self):
        self.forbidden_network.assert_not_called()
        self.forbidden_connect.assert_not_called()

    def test_exact_evidence_and_two_languages_from_different_products(self):
        result = run(self.evidence, self.backend, self.refs)
        self.assertEqual(result.vectors.shape, (2, 3))
        self.assertEqual(result.vectors.dtype, np.float32)
        self.assertFalse(result.vectors.flags.writeable)
        self.assertEqual((result.analysis_language, result.output_language), ("zh-cn", "en-us"))
        self.assertEqual(result.registry_version, mentions.CATALOG)
        row = next(row for row in result.rows if row.original_language == "zh-cn")
        self.assertEqual(row.model_text, "锁定离线模式 🧪 é")
        self.assertEqual(row.original_excerpt_sha256, sha256(self.quote.encode()).hexdigest())
        self.assertEqual((row.lineage.start_cp, row.lineage.end_cp), (0, len(self.quote)))
        self.assertEqual(row.lineage.record_id, self.interval.record_id)
        self.assertEqual(row.lineage.mention_id, self.refs[0].mention_id)
        self.assertEqual(row.lineage.evidence_id, self.refs[0].evidence_id)
        self.assertEqual(row.lineage.source_locator, "https://synthetic.invalid/post/zh")
        self.assertEqual(row.lineage.license_status, "authorized")
        self.assertEqual(row.lineage.privacy, "public")
        self.assertEqual(self.case.corpus.qualified_record(self.case.study, self.interval.record_id)["raw_text"],
                         self.quote)
        self.assertEqual(self.backend.inputs, [tuple(item.model_text for item in result.rows)])
        self.assertEqual(result.research_denominator, 0)
        self.assertFalse(result.outbound_allowed)
        self.assert_no_network()

    def test_order_independent_replay_and_versioned_cache(self):
        original = run(self.evidence, self.backend, self.refs, cache=self.cache)
        again = run(self.evidence, self.backend, self.refs[::-1], cache=self.cache)
        self.assertFalse(original.cache_hit)
        self.assertTrue(again.cache_hit)
        self.assertEqual(again.run_id, original.run_id)
        np.testing.assert_array_equal(again.vectors, original.vectors)
        self.assertEqual(len(self.backend.inputs), 1)
        self.backend.profile = replace(self.backend.profile, revision="v2")
        changed = run(self.evidence, self.backend, self.refs, cache=self.cache)
        self.assertNotEqual(changed.run_id, original.run_id)
        self.assertEqual([row.document_id for row in changed.rows], [row.document_id for row in original.rows])
        self.assertEqual(len(self.backend.inputs), 2)
        entry = self.cache / f"{changed.run_id}.vec"
        entry.write_bytes((self.cache / f"{original.run_id}.vec").read_bytes())
        repaired = run(self.evidence, self.backend, self.refs, cache=self.cache)
        self.assertFalse(repaired.cache_hit)
        np.testing.assert_array_equal(repaired.vectors, changed.vectors)
        self.assertTrue(run(self.evidence, self.backend, self.refs, cache=self.cache).cache_hit)
        self.assert_no_network()

    def test_missing_grant_mixed_scope_and_missing_registry_fail_before_encoding(self):
        with self.assertRaisesRegex(Conflict, "m09_fixture_provenance_required"):
            run(self.reader(fixture_records=()), self.backend, self.refs)
        wrong = replace(self.refs[0], record=replace(self.refs[0].record, study_id="another-project"))
        with self.assertRaisesRegex(Conflict, "m09_frozen_scope_mismatch"):
            run(self.evidence, self.backend, (wrong,))
        with self.assertRaises((Conflict, KeyError)):
            run(self.evidence, self.backend, self.refs, registry_version="99.0.0")
        self.assertEqual(self.backend.inputs, [])

    def test_revoked_batch_cannot_reuse_cached_vectors(self):
        run(self.evidence, self.backend, self.refs, cache=self.cache)
        self.case.revoke_batch(self.batch)
        with self.assertRaises(Conflict):
            run(self.evidence, self.backend, self.refs, cache=self.cache)
        self.assertEqual(len(self.backend.inputs), 1)
        self.assert_no_network()

    def test_revoke_during_encoding_cannot_publish_cache(self):
        def encode(texts):
            self.case.revoke_batch(self.batch)
            return [[1, 2, 3]] * len(texts)

        with patch.object(self.backend, "encode", side_effect=encode):
            with self.assertRaises(Conflict):
                run(self.evidence, self.backend, self.refs, cache=self.cache)
        self.assertFalse(self.cache.exists())

    def test_input_validation_does_not_call_backend(self):
        cases = (
            ((), "zh", "m09_evidence_required"),
            (self.refs, "zh_cn", "m09_invalid_language_tag"),
            ((replace(self.refs[0], original_language="ru-RU"),), "zh", "m09_model_language_unsupported"),
            ((self.refs[0], self.refs[0]), "zh", "m09_duplicate_document"),
        )
        for refs, analysis, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                run(self.evidence, self.backend, refs, analysis_language=analysis)
        self.assertEqual(self.backend.inputs, [])

    def test_preprocessing_excludes_identifiers_without_mutating_original(self):
        document = self.evidence.read(self.refs[0])
        marked = replace(document, original_text="离线模式 @fixture https://fixture.invalid/x "
                         + "user@" + "example.invalid" + " +1 (202) 555-0100")
        row = _row(marked, ("zh",))
        self.assertEqual(row.model_text, "离线模式")
        self.assertIn("@fixture", marked.original_text)
        self.assertEqual(document.original_text, self.quote)

    def test_invalid_vectors_never_reach_cache(self):
        cases = (
            ([[1, 2, 3]], "m09_invalid_vector_shape_or_type"),
            ([[True] * 3] * 2, "m09_invalid_vector_shape_or_type"),
            ([[1, float("inf"), 2]] * 2, "m09_nonfinite_vector"),
            ([[1e100, 2, 3]] * 2, "m09_nonfinite_vector"),
            ([[0, 0, 0]] * 2, "m09_zero_vector"),
        )
        for result, error in cases:
            with self.subTest(error=error), patch.object(self.backend, "encode", return_value=result):
                with self.assertRaisesRegex(ValueError, error):
                    run(self.evidence, self.backend, self.refs, cache=self.cache)
        self.backend.profile = replace(self.backend.profile, normalize=True)
        with self.assertRaisesRegex(ValueError, "m09_vector_not_normalized"):
            run(self.evidence, self.backend, self.refs, cache=self.cache)
        self.assertFalse(self.cache.exists())


class SamplingEmbeddingTests(unittest.TestCase):
    def test_reconciled_synthetic_receipt_reuses_current_source_authority(self):
        case = sampling.SamplingIntegration()
        self.addCleanup(case.doCleanups)
        case.setUp()
        case.create()
        case.complete(case.action("queue"))
        with case.app.state.store.db() as db:
            registry(db, mentions.CATALOG)
            seal_registry(db, mentions.CATALOG)
        evidence = OfflineEvidence(
            study_id=case.study, scope_id=case.scope, scope_version="v1", sampling=case.app.state.sampling,
            registry=RegistryVersions(RelationStore(case.app.state.store)),
        )
        ref = SamplingEvidence(case.task, 0, "zh-CN")
        backend = FixtureBackend()
        cache = Path(case.directory) / "m09-cache"
        result = run(evidence, backend, [ref], cache=cache)
        row, = result.rows
        self.assertEqual(row.lineage.acquisition_task_id, case.task)
        self.assertIsNotNone(row.lineage.source_id)
        self.assertIsNotNone(row.lineage.source_object_id)
        self.assertIsNotNone(row.lineage.license_reference)
        self.assertEqual(len(row.lineage.source_response_sha256), 64)
        self.assertIsNone(row.lineage.mention_id)
        self.assertIsNone(row.lineage.evidence_id)
        self.assertIsNone(row.lineage.segment_revision)
        self.assertEqual(result.research_denominator, 0)
        with self.assertRaises(KeyError):
            run(evidence, backend, [replace(ref, receipt_index=-1)], cache=cache)
        case.denied.add(row.lineage.source_id)
        with self.assertRaisesRegex(AuthorizationBlocked, "source_permission_changed"):
            run(evidence, backend, [ref], cache=cache)
        self.assertEqual(len(backend.inputs), 1)


if __name__ == "__main__":
    unittest.main()
