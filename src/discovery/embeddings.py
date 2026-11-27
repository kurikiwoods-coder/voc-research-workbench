"""Produce a reproducible vector matrix for the next offline discovery stage."""

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from unicodedata import normalize

import numpy as np

from src.discovery.embedding_backend import EmbeddingBackend, EmbeddingProfile
from src.discovery.embedding_inputs import Lineage, OfflineEvidence
from src.raw_store.corpus_policy import SENSITIVE
from src.raw_store.store import Conflict, dump


PREPROCESSING_VERSION = "m09-a-unicode-anonymize-v1"
LANGUAGE_TAG = re.compile(r"[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*")
IDENTIFIERS = (
    SENSITIVE,
    re.compile(r"(?i)(?:https?://|www\.)[^\s<>]+"),
    re.compile(r"(?i)[\w.+-]+@[\w.-]+\.[a-z]{2,}"),
    re.compile(r"(?<!\w)@[\w.]+"),
    re.compile(r"(?<!\w)\+?\d(?:[ .()-]*\d){6,}(?!\w)"),
)
CACHE_FORMAT = "m09-a-float32-v1"


@dataclass(frozen=True)
class EmbeddingRow:
    document_id: str
    lineage: Lineage
    original_language: str
    original_excerpt_sha256: str
    model_input_sha256: str
    model_text: str


@dataclass(frozen=True)
class EmbeddingBatch:
    run_id: str
    model: EmbeddingProfile
    preprocessing_version: str
    registry_version: str
    analysis_language: str
    output_language: str
    rows: tuple[EmbeddingRow, ...]
    vectors: np.ndarray
    cache_hit: bool
    mode: str = "offline_synthetic"
    research_denominator: int = 0
    outbound_allowed: bool = False


def _language(tag):
    if not isinstance(tag, str) or LANGUAGE_TAG.fullmatch(tag) is None:
        raise ValueError("m09_invalid_language_tag")
    return tag.lower()


def _digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


def _row(document, supported_languages):
    language = _language(document.original_language)
    if supported_languages and not (set(supported_languages) & {language, language.split("-")[0]}):
        raise ValueError("m09_model_language_unsupported")
    model_text = normalize("NFKC", document.original_text)
    for identifier in IDENTIFIERS:
        model_text = identifier.sub(" ", model_text)
    model_text = " ".join(model_text.split())
    if not model_text or not any(character.isalnum() for character in model_text):
        raise ValueError("m09_model_input_empty")
    return EmbeddingRow(
        document.lineage.document_id, document.lineage, language,
        _digest(document.original_text), _digest(model_text), model_text,
    )


def _matrix(values, rows, model):
    try:
        vectors = np.asarray(values)
        if vectors.shape != (rows, model.dimensions) or vectors.dtype.kind not in "iuf":
            raise ValueError
        with np.errstate(over="ignore", invalid="ignore", under="ignore"):
            vectors = np.array(vectors, dtype="<f4", order="C", copy=True)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("m09_invalid_vector_shape_or_type") from None
    if not np.isfinite(vectors).all():
        raise ValueError("m09_nonfinite_vector")
    norms = np.linalg.norm(vectors.astype(np.float64), axis=1)
    if np.any(norms == 0):
        raise ValueError("m09_zero_vector")
    if model.normalize and not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
        raise ValueError("m09_vector_not_normalized")
    vectors.setflags(write=False)
    return vectors


def _read_cache(path, rows, model):
    size = rows * model.dimensions * np.dtype("<f4").itemsize
    try:
        with path.open("rb") as handle:
            checksum, payload = handle.read(32), handle.read(size + 1)
    except FileNotFoundError:
        return None
    if len(payload) != size or sha256(bytes.fromhex(path.stem) + payload).digest() != checksum:
        return None
    try:
        return _matrix(np.frombuffer(payload, dtype="<f4").reshape(rows, model.dimensions), rows, model)
    except ValueError:
        return None


def _write_cache(path, matrix):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = matrix.tobytes()
    with NamedTemporaryFile(dir=path.parent, prefix=".m09-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(sha256(bytes.fromhex(path.stem) + payload).digest())
            handle.write(payload)
            handle.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def embed_offline(evidence: OfflineEvidence, backend: EmbeddingBackend, refs, *,
                  registry_version, analysis_language, output_language, cache_dir=None):
    """Read a fixture batch, encode only derived text, then recheck all dependencies."""
    refs = tuple(refs)
    if not refs:
        raise ValueError("m09_evidence_required")
    analysis_language = _language(analysis_language)
    output_language = _language(output_language)
    version = evidence.registry_version(registry_version)
    model = backend.profile
    languages = tuple(_language(tag) for tag in model.supported_languages)
    documents = tuple(evidence.read(ref) for ref in refs)
    rows = tuple(sorted((_row(document, languages) for document in documents), key=lambda row: row.document_id))
    if len({row.document_id for row in rows}) != len(rows):
        raise ValueError("m09_duplicate_document")
    key = (
        CACHE_FORMAT, asdict(model), PREPROCESSING_VERSION, version, analysis_language, output_language,
        [(asdict(row.lineage), row.original_language, row.original_excerpt_sha256, row.model_input_sha256)
         for row in rows],
    )
    run_id = _digest(dump(key))
    path = Path(cache_dir) / f"{run_id}.vec" if cache_dir is not None else None
    vectors = _read_cache(path, len(rows), model) if path is not None else None
    hit = vectors is not None
    if not hit:
        vectors = _matrix(backend.encode(tuple(row.model_text for row in rows)), len(rows), model)
    if (tuple(evidence.read(ref) for ref in refs) != documents or evidence.registry_version(version) != version
            or backend.profile != model):
        raise Conflict("m09_run_dependencies_changed")
    if path is not None and not hit:
        _write_cache(path, vectors)
    return EmbeddingBatch(
        run_id, model, PREPROCESSING_VERSION, version, analysis_language, output_language, rows, vectors, hit,
    )
