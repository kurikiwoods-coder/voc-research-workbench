"""Exercise the local model boundary with synthetic files and a stub inference runtime."""

from dataclasses import FrozenInstanceError, replace
from hashlib import file_digest
from importlib.metadata import PackageNotFoundError
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

import numpy as np

from src.discovery.embedding_backend import (
    EmbeddingBackendError, EmbeddingProfile, LOCAL_BACKEND, LOCAL_BACKEND_VERSION,
    LocalSentenceTransformer, local_runtime_version, manifest_fingerprint,
)


class LocalSentenceTransformerTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "model"
        self.root.mkdir()
        (self.root / "1_Pooling").mkdir()
        self.modules = [
            {"idx": 0, "name": "0", "path": "", "type": "sentence_transformers.models.Transformer"},
            {"idx": 1, "name": "1", "path": "1_Pooling", "type": "sentence_transformers.models.Pooling"},
        ]
        self.write_json("modules.json", self.modules)
        self.write_json("config.json", {"model_type": "bert"})
        self.write_json("tokenizer.json", {})
        self.write_json("tokenizer_config.json", {"tokenizer_class": "PreTrainedTokenizerFast"})
        self.write_json("1_Pooling/config.json", {"word_embedding_dimension": 2})
        (self.root / "model.safetensors").write_bytes(b"synthetic stand-in for model weights")
        self.vector = np.array([[0.6, 0.8], [0.8, 0.6]], dtype=np.float32)
        self.model = Mock(max_seq_length=128)
        self.model.get_sentence_embedding_dimension.return_value = 2
        self.model.tokenizer.is_fast = True
        self.model.encode.return_value = self.vector
        self.load_model = Mock(return_value=self.model)
        module = ModuleType("sentence_transformers")
        module.SentenceTransformer = self.load_model
        self.enterContext(patch.dict(sys.modules, {"sentence_transformers": module}))
        self.runtime_version = "synthetic-runtime-v1"
        self.enterContext(patch(
            "src.discovery.embedding_backend.local_runtime_version", return_value=self.runtime_version,
        ))

    def write_json(self, relative, value):
        (self.root / relative).write_text(json.dumps(value), encoding="utf-8")

    def manifest(self):
        manifest = {}
        for path in self.root.rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    manifest[path.relative_to(self.root).as_posix()] = file_digest(stream, "sha256").hexdigest()
        return manifest

    def profile(self, manifest, **overrides):
        fields = {
            "model_id": "synthetic-model", "revision": "pinned-synthetic-revision",
            "artifact_sha256": manifest_fingerprint(manifest), "dimensions": 2,
            "supported_languages": ("en", "zh-CN"), "max_sequence_length": 128, "batch_size": 2,
            "normalize": True, "backend": LOCAL_BACKEND, "backend_version": LOCAL_BACKEND_VERSION,
            "runtime_version": self.runtime_version,
        }
        return EmbeddingProfile(**(fields | overrides))

    def backend(self, **overrides):
        manifest = self.manifest()
        backend = LocalSentenceTransformer(self.root, self.profile(manifest, **overrides), manifest)
        self.addCleanup(backend.close)
        return backend

    def test_verified_assets_and_verbatim_inputs_reach_cpu_runtime(self):
        manifest = self.manifest()
        backend = self.backend()
        self.load_model.assert_not_called()
        self.assertEqual(backend.encode([]).shape, (0, 2))
        self.load_model.assert_not_called()

        inputs = ("  A  synthetic item\r\n", "合成文字👍")
        self.assertIs(backend.encode(inputs), self.vector)
        snapshot = Path(self.load_model.call_args.args[0])
        self.assertNotEqual(snapshot, self.root)
        self.assertEqual(
            set(manifest), {path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()},
        )
        self.load_model.assert_called_once_with(
            str(snapshot), device="cpu", backend="torch", local_files_only=True, trust_remote_code=False,
            model_kwargs={"use_safetensors": True}, tokenizer_kwargs={"use_fast": True},
        )
        self.model.encode.assert_called_once_with(
            list(inputs), batch_size=2, normalize_embeddings=True, device="cpu", show_progress_bar=False,
            convert_to_numpy=True, convert_to_tensor=False,
        )
        self.assertIs(backend.encode(inputs), self.vector)
        self.assertEqual(self.load_model.call_count, 1)
        backend.close()
        self.assertFalse(snapshot.exists())

    def test_profile_and_manifest_have_stable_immutable_identity(self):
        manifest = self.manifest()
        profile = self.profile(manifest)
        self.assertEqual(manifest_fingerprint(dict(reversed(tuple(manifest.items())))), profile.artifact_sha256)
        with self.assertRaises(FrozenInstanceError):
            profile.dimensions = 3
        with self.assertRaisesRegex(EmbeddingBackendError, "does not match the asset manifest"):
            LocalSentenceTransformer(self.root, replace(profile, artifact_sha256="f" * 64), manifest)
        with self.assertRaisesRegex(EmbeddingBackendError, "does not match the local backend"):
            self.backend(backend="hosted")
        self.load_model.assert_not_called()

    def test_missing_directory_and_missing_model_file_never_fall_back_to_hub(self):
        manifest = self.manifest()
        backend = LocalSentenceTransformer(self.root / "missing", self.profile(manifest), manifest)
        with self.assertRaisesRegex(EmbeddingBackendError, "could not be verified or loaded"):
            backend.encode(["synthetic"])

        backend = self.backend()
        (self.root / "model.safetensors").unlink()
        with self.assertRaisesRegex(EmbeddingBackendError, "missing a manifest asset"):
            backend.encode(["synthetic"])
        self.load_model.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows remote drive detection")
    def test_windows_rejects_unc_paths_and_mapped_network_drives(self):
        from ctypes import windll

        manifest = self.manifest()
        profile = self.profile(manifest)
        backend = LocalSentenceTransformer(r"\\server\share\model", profile, manifest)
        with self.assertRaisesRegex(EmbeddingBackendError, "A local embedding model directory is required"):
            backend.encode(["synthetic"])
        with patch.object(windll.kernel32, "GetDriveTypeW", return_value=4):
            with self.assertRaisesRegex(EmbeddingBackendError, "A local embedding model directory is required"):
                self.backend().encode(["synthetic"])
        self.load_model.assert_not_called()

    def test_file_content_mutation_and_unmanifested_weight_are_rejected(self):
        backend = self.backend()
        weight = self.root / "model.safetensors"
        original = weight.read_bytes()
        weight.write_bytes(b"different weights")
        with self.assertRaisesRegex(EmbeddingBackendError, "failed SHA-256 verification"):
            backend.encode(["synthetic"])
        weight.write_bytes(original)
        (self.root / "pytorch_model.bin").write_bytes(b"untrusted pickle")
        with self.assertRaisesRegex(EmbeddingBackendError, "unmanifested or unsafe"):
            backend.encode(["synthetic"])
        with self.assertRaisesRegex(EmbeddingBackendError, "supported safetensors model layout"):
            self.backend()
        self.load_model.assert_not_called()

    def test_custom_module_and_traversal_are_rejected_even_when_content_is_pinned(self):
        cases = ({"type": "custom.Module"}, {"type": "sentence_transformers.models.Unreviewed"},
                 {"path": "../escape"}, {"kwargs": ["token", "cache_dir"]})
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.write_json("modules.json", [self.modules[0], self.modules[1] | overrides])
                with self.assertRaisesRegex(EmbeddingBackendError, "unsafe or unsupported module"):
                    self.backend().encode(["synthetic"])
        self.load_model.assert_not_called()

    def test_config_asset_overrides_are_rejected_even_when_content_is_pinned(self):
        self.write_json("config.json", {"model_type": "bert", "auto_map": {"AutoModel": "unexpected.Transformer"}})
        with self.assertRaisesRegex(EmbeddingBackendError, "override local model assets"):
            self.backend().encode(["synthetic"])
        self.write_json("config.json", {"model_type": "bert"})
        self.write_json("tokenizer_config.json", {"tokenizer_file": "../tokenizer.json"})
        with self.assertRaisesRegex(EmbeddingBackendError, "override local model assets"):
            self.backend().encode(["synthetic"])
        self.write_json("tokenizer_config.json", {})
        self.write_json("sentence_bert_config.json", {"model_args": {"use_safetensors": False}})
        with self.assertRaisesRegex(EmbeddingBackendError, "configuration is unsupported"):
            self.backend().encode(["synthetic"])
        self.load_model.assert_not_called()

    def test_optional_normalizer_matches_declared_normalization(self):
        self.modules.append(
            {"idx": 2, "name": "2", "path": "2_Normalize", "type": "sentence_transformers.models.Normalize"},
        )
        self.write_json("modules.json", self.modules)
        with self.assertRaisesRegex(EmbeddingBackendError, "normalizes vectors"):
            self.backend(normalize=False).encode(["synthetic"])
        self.assertIs(self.backend().encode(["synthetic", "another synthetic item"]), self.vector)

    def test_dimension_sequence_length_runtime_and_load_failures_fail_closed(self):
        for overrides in ({"dimensions": 3}, {"max_sequence_length": 64}):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(EmbeddingBackendError, "dimensions or sequence length"):
                    self.backend(**overrides).encode(["synthetic"])
        self.model.encode.assert_not_called()
        self.load_model.reset_mock()
        with self.assertRaisesRegex(EmbeddingBackendError, "installed runtime does not match"):
            self.backend(runtime_version="different").encode(["synthetic"])
        self.load_model.assert_not_called()

        self.model.tokenizer.is_fast = False
        with self.assertRaisesRegex(EmbeddingBackendError, "requires a fast local tokenizer"):
            self.backend().encode(["synthetic"])
        self.model.tokenizer.is_fast = True

        self.load_model.side_effect = ImportError("details from optional runtime")
        backend = self.backend()
        with self.assertRaisesRegex(EmbeddingBackendError, "could not be verified or loaded"):
            backend.encode(["synthetic"])
        self.load_model.side_effect = None
        self.assertIs(backend.encode(["synthetic", "another synthetic item"]), self.vector)

    def test_invalid_inputs_and_invalid_runtime_vectors_fail_closed(self):
        backend = self.backend()
        for texts in ("single string", ["synthetic", 7]):
            with self.subTest(texts=texts), self.assertRaises(TypeError):
                backend.encode(texts)
        self.load_model.assert_not_called()
        for value in ([[1.0]], [["a", "b"]], [[1j, 2j]], [[float("nan"), 0.0]]):
            self.model.encode.return_value = value
            with self.subTest(value=value), self.assertRaisesRegex(EmbeddingBackendError, "invalid vectors"):
                backend.encode(["synthetic"])

    def test_runtime_failure_does_not_include_input_or_engine_details(self):
        self.model.encode.side_effect = ValueError("private input echoed by upstream")
        with self.assertRaises(EmbeddingBackendError) as failure:
            self.backend().encode(["private input"])
        self.assertNotIn("private input", str(failure.exception))
        self.assertIsNone(failure.exception.__cause__)


class RuntimeVersionTests(unittest.TestCase):
    @patch("src.discovery.embedding_backend.version")
    def test_runtime_identity_includes_all_required_installed_dependencies(self, package_version):
        package_version.return_value = "1.0"
        self.assertEqual(
            local_runtime_version(),
            "sentence-transformers==1.0;transformers==1.0;torch==1.0;tokenizers==1.0;safetensors==1.0;"
            "huggingface-hub==1.0",
        )

    @patch("src.discovery.embedding_backend.version")
    def test_missing_optional_inference_packages_fail_closed(self, package_version):
        package_version.side_effect = PackageNotFoundError("sentence-transformers")
        with self.assertRaisesRegex(EmbeddingBackendError, "optional local embedding runtime is unavailable"):
            local_runtime_version()
