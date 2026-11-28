"""CPU embeddings from an explicitly reviewed, offline Sentence Transformers artifact."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import file_digest, sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import re
import shutil
import stat
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Protocol

import numpy as np
from numpy.typing import ArrayLike


LOCAL_BACKEND = "sentence-transformers"
LOCAL_BACKEND_VERSION = "1"
_RUNTIME_PACKAGES = (LOCAL_BACKEND, "transformers", "torch", "tokenizers", "safetensors", "huggingface-hub")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

_REQUIRED_ASSETS = frozenset({
    "modules.json", "config.json", "model.safetensors", "tokenizer.json", "1_Pooling/config.json",
})
_OPTIONAL_ASSETS = frozenset({
    "config_sentence_transformers.json", "sentence_bert_config.json", "tokenizer_config.json",
    "special_tokens_map.json", "added_tokens.json", "vocab.txt", "vocab.json", "merges.txt",
    "sentencepiece.bpe.model", "spiece.model", "README.md", "LICENSE", "LICENSE.txt",
})
_MODEL_TYPES = frozenset({"bert", "distilbert", "mpnet", "roberta", "xlm-roberta"})
_TOKENIZER_TYPES = frozenset({
    "BertTokenizer", "BertTokenizerFast", "DistilBertTokenizer", "DistilBertTokenizerFast",
    "MPNetTokenizer", "MPNetTokenizerFast", "PreTrainedTokenizerFast", "RobertaTokenizer", "RobertaTokenizerFast",
    "XLMRobertaTokenizer", "XLMRobertaTokenizerFast",
})
_MODULE_LAYOUT = (
    ("sentence_transformers.models.Transformer", ""),
    ("sentence_transformers.models.Pooling", "1_Pooling"),
    ("sentence_transformers.models.Normalize", "2_Normalize"),
)


class EmbeddingBackendError(RuntimeError):
    """A local embedding configuration or runtime failed to satisfy its contract."""


@dataclass(frozen=True)
class EmbeddingProfile:
    """Exact embedding configuration. An empty language tuple permits any input language."""

    model_id: str
    revision: str
    artifact_sha256: str
    dimensions: int
    supported_languages: tuple[str, ...]
    max_sequence_length: int
    batch_size: int
    normalize: bool
    backend: str
    backend_version: str
    runtime_version: str

    def __post_init__(self):
        for value in (self.model_id, self.revision, self.backend, self.backend_version, self.runtime_version):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Embedding model and runtime identities must be nonempty strings.")
        if not isinstance(self.artifact_sha256, str) or not _SHA256.fullmatch(self.artifact_sha256):
            raise ValueError("Embedding artifact identity must be a lowercase SHA-256 digest.")
        for value in (self.dimensions, self.max_sequence_length, self.batch_size):
            if type(value) is not int or value <= 0:
                raise ValueError("Embedding dimensions, maximum sequence length, and batch size must be positive integers.")
        if not isinstance(self.supported_languages, tuple) or any(
            not isinstance(language, str) or not language.strip() for language in self.supported_languages
        ):
            raise ValueError("Embedding supported languages must be a tuple of nonempty strings.")
        if type(self.normalize) is not bool:
            raise ValueError("Embedding normalization must be a boolean.")


class EmbeddingBackend(Protocol):
    @property
    def profile(self) -> EmbeddingProfile: ...

    def encode(self, texts: Sequence[str]) -> ArrayLike: ...


def manifest_fingerprint(asset_manifest: Mapping[str, str]) -> str:
    """Hash canonical UTF-8 JSON mapping relative POSIX paths to file SHA-256 digests."""
    if any(
        not isinstance(path, str) or not isinstance(digest, str) or not _SHA256.fullmatch(digest)
        for path, digest in asset_manifest.items()
    ):
        raise EmbeddingBackendError("Invalid embedding asset manifest.")
    canonical = json.dumps(dict(asset_manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def local_runtime_version() -> str:
    """Read the installed runtime versions without importing the inference stack."""
    try:
        return ";".join(f"{package}=={version(package)}" for package in _RUNTIME_PACKAGES)
    except PackageNotFoundError:
        raise EmbeddingBackendError("The optional local embedding runtime is unavailable.") from None


def _regular_asset(path: Path) -> int:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or (
        getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise EmbeddingBackendError("Embedding artifacts must use ordinary local files and directories.")
    return metadata.st_mode


def _copy_verified_assets(root: Path, target: Path, manifest: Mapping[str, str]) -> None:
    if root.drive.startswith("\\\\"):
        raise EmbeddingBackendError("A local embedding model directory is required.")
    if os.name == "nt":
        from ctypes import windll

        drive_remote = 4  # Win32 DRIVE_REMOTE covers network drives mounted to a letter.
        if windll.kernel32.GetDriveTypeW(root.anchor) == drive_remote:
            raise EmbeddingBackendError("A local embedding model directory is required.")
    for parent in reversed(root.parents):
        _regular_asset(parent)
    if not stat.S_ISDIR(_regular_asset(root)):
        raise EmbeddingBackendError("A local embedding model directory is required.")

    remaining = set(manifest)
    folders = [root]
    while folders:
        for path in folders.pop().iterdir():
            relative = path.relative_to(root).as_posix()
            mode = _regular_asset(path)
            if stat.S_ISDIR(mode) and relative in {"1_Pooling", "2_Normalize"}:
                (target / relative).mkdir()
                folders.append(path)
                continue
            if not stat.S_ISREG(mode) or relative not in remaining:
                raise EmbeddingBackendError("The embedding directory has an unmanifested or unsafe asset.")
            destination = target / relative
            shutil.copyfile(path, destination)
            with destination.open("rb") as stream:
                if file_digest(stream, "sha256").hexdigest() != manifest[relative]:
                    raise EmbeddingBackendError("An embedding model asset failed SHA-256 verification.")
            remaining.remove(relative)
    if remaining:
        raise EmbeddingBackendError("The embedding directory is missing a manifest asset.")


def _read_json(root: Path, name: str):
    with (root / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def _check_config(config: dict) -> None:
    if not isinstance(config, dict) or any(
        key in {"auto_map", "configuration_files", "custom_pipelines", "fast_tokenizer_files", "tokenizer_name_or_path"}
        or (key.endswith("_file") and value is not None)
        for key, value in config.items()
    ):
        raise EmbeddingBackendError("An embedding configuration attempts to override local model assets.")


def _check_model_layout(root: Path, profile: EmbeddingProfile) -> None:
    modules = _read_json(root, "modules.json")
    if not isinstance(modules, list) or len(modules) not in (2, 3):
        raise EmbeddingBackendError("The embedding model must use the built-in Transformer and Pooling stack.")
    for index, (module, (module_type, module_path)) in enumerate(zip(modules, _MODULE_LAYOUT)):
        if (
            not isinstance(module, dict) or set(module) != {"idx", "name", "path", "type"}
            or type(module["idx"]) is not int or module["idx"] != index or module["name"] != str(index)
            or module["path"] != module_path or module["type"] != module_type
        ):
            raise EmbeddingBackendError("The embedding model declares an unsafe or unsupported module.")
    if len(modules) == 3:
        if not profile.normalize:
            raise EmbeddingBackendError("The embedding model normalizes vectors and requires a matching profile.")
        (root / "2_Normalize").mkdir(exist_ok=True)

    config = _read_json(root, "config.json")
    _check_config(config)
    if config.get("model_type") not in _MODEL_TYPES or config.get("quantization_config") is not None:
        raise EmbeddingBackendError("The embedding model architecture is unsupported.")
    if (root / "tokenizer_config.json").is_file():
        tokenizer = _read_json(root, "tokenizer_config.json")
        _check_config(tokenizer)
        if tokenizer.get("tokenizer_class") not in _TOKENIZER_TYPES | {None}:
            raise EmbeddingBackendError("The embedding tokenizer is unsupported.")
    if (root / "sentence_bert_config.json").is_file():
        transformer = _read_json(root, "sentence_bert_config.json")
        if not isinstance(transformer, dict) or transformer.keys() - {"max_seq_length", "do_lower_case"}:
            raise EmbeddingBackendError("The embedding transformer configuration is unsupported.")
    if (root / "config_sentence_transformers.json").is_file():
        settings = _read_json(root, "config_sentence_transformers.json")
        _check_config(settings)
        if any(settings.get(key) is not None for key in ("default_prompt_name", "truncate_dim")):
            raise EmbeddingBackendError("An embedding configuration would modify the declared inputs or dimensions.")


class LocalSentenceTransformer:
    """Load a reviewed Transformer/Pooling artifact on demand from local safetensors.

    The trusted caller supplies a pinned profile and a separately trusted manifest.
    Supported layouts use a root transformer and 1_Pooling, with optional 2_Normalize.
    """

    def __init__(
        self, model_dir: str | os.PathLike[str], profile: EmbeddingProfile, asset_manifest: Mapping[str, str],
    ):
        manifest = dict(asset_manifest)
        if not _REQUIRED_ASSETS <= manifest.keys() <= _REQUIRED_ASSETS | _OPTIONAL_ASSETS:
            raise EmbeddingBackendError("The embedding manifest must identify a supported safetensors model layout.")
        if manifest_fingerprint(manifest) != profile.artifact_sha256:
            raise EmbeddingBackendError("The embedding profile does not match the asset manifest.")
        if (profile.backend, profile.backend_version) != (LOCAL_BACKEND, LOCAL_BACKEND_VERSION):
            raise EmbeddingBackendError("The embedding profile does not match the local backend.")
        self._model_dir = Path(model_dir).absolute()
        self._profile = profile
        self._manifest = manifest
        self._model = None
        self._snapshot = None
        self._lock = Lock()

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    def close(self) -> None:
        """Release the loaded model and its verified asset copy."""
        with self._lock:
            self._model = None
            if self._snapshot is not None:
                self._snapshot.cleanup()
                self._snapshot = None

    def _load(self):
        snapshot = TemporaryDirectory(prefix="voc-embedding-", ignore_cleanup_errors=True)
        try:
            target = Path(snapshot.name)
            _copy_verified_assets(self._model_dir, target, self._manifest)
            _check_model_layout(target, self.profile)
            if self.profile.runtime_version != local_runtime_version():
                raise EmbeddingBackendError("The installed runtime does not match the embedding profile.")

            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                str(target), device="cpu", backend="torch", local_files_only=True, trust_remote_code=False,
                model_kwargs={"use_safetensors": True}, tokenizer_kwargs={"use_fast": True},
            )
            if (
                model.get_sentence_embedding_dimension() != self.profile.dimensions
                or model.max_seq_length != self.profile.max_sequence_length
            ):
                raise EmbeddingBackendError("The loaded model does not match the embedding dimensions or sequence length.")
            if not model.tokenizer.is_fast:
                raise EmbeddingBackendError("The loaded embedding model requires a fast local tokenizer.")
        except EmbeddingBackendError:
            snapshot.cleanup()
            raise
        except Exception:
            snapshot.cleanup()
            raise EmbeddingBackendError("The local embedding model could not be verified or loaded.") from None
        self._snapshot = snapshot
        self._model = model

    def encode(self, texts: Sequence[str]) -> ArrayLike:
        if isinstance(texts, (str, bytes)):
            raise TypeError("Embedding input must be a sequence of strings.")
        inputs = list(texts)
        if any(not isinstance(item, str) for item in inputs):
            raise TypeError("Embedding input must be a sequence of strings.")
        if not inputs:
            return np.empty((0, self.profile.dimensions), dtype=np.float32)
        with self._lock:
            if self._model is None:
                self._load()
            try:
                vectors = np.asarray(self._model.encode(
                    inputs, batch_size=self.profile.batch_size, normalize_embeddings=self.profile.normalize,
                    device="cpu", show_progress_bar=False, convert_to_numpy=True, convert_to_tensor=False,
                ))
            except Exception:
                raise EmbeddingBackendError("The local embedding model could not encode the input.") from None
        if (
            vectors.shape != (len(inputs), self.profile.dimensions)
            or not np.issubdtype(vectors.dtype, np.floating)
            or not np.isfinite(vectors).all()
        ):
            raise EmbeddingBackendError("The local embedding runtime returned invalid vectors.")
        return vectors
