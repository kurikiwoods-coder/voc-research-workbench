"""Offline candidate topics over the ordered M09-A document and vector batch."""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import version
from math import isfinite
import re
from tempfile import TemporaryDirectory

import numpy as np

from src.discovery.embedding_backend import EmbeddingBackend, EmbeddingProfile
from src.discovery.embedding_inputs import OfflineEvidence
from src.discovery.embeddings import EmbeddingBatch, PREPROCESSING_VERSION, _language, _row, embed_offline
from src.raw_store.store import Conflict, dump


TOPIC_PIPELINE_VERSION = "m09-b-bertopic-v1"
TOKENIZER_VERSION = "m09-b-jieba-dictionary-en-stop-v1"
TOPIC_DIAGNOSTICS_VERSION = "m09-c-hdbscan-core-centroid-v1"
_CENTROID_CORE_PROBABILITY = 0.95
_RUNTIME_PACKAGES = (
    "bertopic", "umap-learn", "hdbscan", "scikit-learn", "jieba",
    "numpy", "scipy", "pandas", "numba", "llvmlite", "pynndescent",
)
_HAN = r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U000323af]"

_HAN_CHAR = re.compile(_HAN)
_ZH_STOP = frozenset("的 了 在 和 与 为 是 有 都 就 也 还 很 但 将 并 而 或 又 我 你 他 它 可以 这个 那个 这些 那些 一个 一种 因为 所以 如果".split())
_OUTLIER = -1


@dataclass(frozen=True)
class TopicConfig:
    random_seed: int = 42
    n_neighbors: int = 10
    n_components: int = 2
    min_dist: float = 0.05
    min_cluster_size: int = 5
    min_samples: int = 3
    top_n_words: int = 10

    def __post_init__(self):
        integer_ranges = (
            ("random_seed", 0, 2**32 - 1),
            ("n_neighbors", 2, None),
            ("n_components", 1, None),
            ("min_cluster_size", 2, None),
            ("min_samples", 1, None),
            ("top_n_words", 1, 100),
        )
        for name, minimum, maximum in integer_ranges:
            value = getattr(self, name)
            if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
                raise ValueError(f"m09_topic_invalid_{name}")
        if type(self.min_dist) not in (int, float) or not 0 <= self.min_dist <= 1:
            raise ValueError("m09_topic_invalid_min_dist")


@dataclass(frozen=True)
class TopicKeyword:
    term: str
    weight: float


@dataclass(frozen=True)
class TopicAssignment:
    document_id: str
    topic_id: int
    raw_topic_id: int | None = None
    hdbscan_cluster_id: int | None = None
    hdbscan_membership_probability: float | None = None
    hdbscan_outlier_score: float | None = None
    centroid_cosine: float | None = None


@dataclass(frozen=True)
class CandidateTopic:
    topic_id: int
    member_count: int
    keywords: tuple[TopicKeyword, ...]


@dataclass(frozen=True)
class TopicMetadata:
    embedding_run_id: str | None
    model: EmbeddingProfile
    preprocessing_version: str
    registry_version: str
    analysis_language: str
    output_language: str
    input_languages: tuple[str, ...]
    vector_sha256: str | None
    requested_config: TopicConfig
    effective_config: TopicConfig | None
    runtime_versions: tuple[tuple[str, str], ...]
    pipeline_version: str = TOPIC_PIPELINE_VERSION
    tokenizer_version: str = TOKENIZER_VERSION


@dataclass(frozen=True)
class TopicRun:
    run_id: str
    status: str
    metadata: TopicMetadata
    assignments: tuple[TopicAssignment, ...]
    topics: tuple[CandidateTopic, ...]
    mode: str = "offline_synthetic"
    research_denominator: int = 0
    outbound_allowed: bool = False
    diagnostics_version: str = TOPIC_DIAGNOSTICS_VERSION


def _terms(text, chinese_cut, english_stop):
    # Split Han runs first so Latin words adjacent to Han text remain separate.
    words = []
    for span in re.finditer(rf"{_HAN}+|(?:(?!{_HAN})[^\W\d_])+", text):
        token = span.group().casefold()
        if _HAN_CHAR.match(token):
            words.extend(word for word in chinese_cut(token, HMM=False) if word not in _ZH_STOP)
        elif token not in english_stop:
            words.append(token)
    return " ".join(words)


def _diagnostic_values(clusterer, name, size):
    values = getattr(clusterer, name, None)
    if values is None:
        return (None,) * size
    if np.shape(values) != (size,):
        raise RuntimeError("m09_topic_diagnostic_alignment")
    return values


def _unit_score(value):
    if value is not None and isfinite(value) and 0.0 <= value <= 1.0:
        return float(value)
    return None


def _assignment_diagnostics(batch, labels, clusterer):
    size = len(labels)
    clusters = _diagnostic_values(clusterer, "labels_", size)
    memberships = tuple(_unit_score(value) for value in _diagnostic_values(clusterer, "probabilities_", size))
    outlier_scores = _diagnostic_values(clusterer, "outlier_scores_", size)
    groups = defaultdict(list)
    for index, label in enumerate(labels):
        if label != _OUTLIER:
            groups[label].append(index)

    similarities = [None] * size
    for group in groups.values():
        vectors = batch.vectors[group].astype(np.float64)
        unit_vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        core = [
            offset for offset, index in enumerate(group)
            if memberships[index] is not None and memberships[index] >= _CENTROID_CORE_PROBABILITY
        ]
        centroid = (unit_vectors[core] if len(core) >= 2 else unit_vectors).mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm:
            scores = np.clip(unit_vectors @ (centroid / norm), -1.0, 1.0)
            for index, score in zip(group, scores, strict=True):
                similarities[index] = float(score)

    return tuple(
        TopicAssignment(
            document_id=row.document_id,
            topic_id=labels[index],
            raw_topic_id=labels[index],
            hdbscan_cluster_id=None if clusters[index] is None else int(clusters[index]),
            hdbscan_membership_probability=memberships[index],
            hdbscan_outlier_score=_unit_score(outlier_scores[index]),
            centroid_cosine=similarities[index],
        )
        for index, row in enumerate(batch.rows)
    )


def _fit_topics(batch, config, *, observe_diagnostics=None):
    from bertopic import BERTopic
    from bertopic.vectorizers import ClassTfidfTransformer
    from hdbscan import HDBSCAN
    import jieba
    from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
    from umap import UMAP

    # Use jieba's bundled dictionary only. No user dictionary or HMM state is used.
    with TemporaryDirectory(prefix="voc-m09-jieba-") as dictionary_cache:
        tokenizer = jieba.Tokenizer()
        tokenizer.tmp_dir = dictionary_cache
        documents = [_terms(row.model_text, tokenizer.cut, ENGLISH_STOP_WORDS) for row in batch.rows]
    if not any(documents):
        return "empty_vocabulary", (_OUTLIER,) * len(documents), ()
    # Keep stop-word-only rows tokenless through BERTopic's empty-document preprocessing.
    documents = [document or " " for document in documents]

    model = BERTopic(
        language="multilingual",
        embedding_model=None,
        umap_model=UMAP(
            n_neighbors=config.n_neighbors, n_components=config.n_components,
            min_dist=config.min_dist, metric="cosine", random_state=config.random_seed,
            init="random", n_jobs=1,
        ),
        hdbscan_model=HDBSCAN(
            min_cluster_size=config.min_cluster_size, min_samples=config.min_samples, metric="euclidean",
            allow_single_cluster=False, approx_min_span_tree=False, core_dist_n_jobs=1,
        ),
        vectorizer_model=CountVectorizer(tokenizer=str.split, token_pattern=None, lowercase=False),
        ctfidf_model=ClassTfidfTransformer(),
        nr_topics=None,
        top_n_words=config.top_n_words,
        calculate_probabilities=False,
    )
    predictions, _ = model.fit_transform(documents, embeddings=batch.vectors)
    if len(predictions) != len(batch.rows) or any(label < _OUTLIER for label in predictions):
        raise RuntimeError("m09_topic_invalid_assignments")
    labels = tuple(int(label) for label in predictions)
    counts = Counter(label for label in labels if label != _OUTLIER)
    topics = []
    for topic_id, count in sorted(counts.items()):
        keywords = tuple(
            TopicKeyword(term, float(weight)) for term, weight in model.get_topic(topic_id)
            if term and isfinite(weight) and weight > 0
        )
        topics.append(CandidateTopic(topic_id, count, keywords))
    if observe_diagnostics is not None:
        observe_diagnostics(_assignment_diagnostics(batch, labels, model.hdbscan_model))
    return ("clustered" if topics else "no_clusters"), labels, tuple(topics)


def _cluster_batch(batch: EmbeddingBatch, config: TopicConfig, *, observe_diagnostics=None):
    size = len(batch.rows)
    if size < max(3, 2 * config.min_cluster_size, config.min_samples + 1):
        return "insufficient_samples", (_OUTLIER,) * size, (), None, ()
    effective = TopicConfig(
        random_seed=config.random_seed,
        n_neighbors=min(config.n_neighbors, size - 1),
        n_components=min(config.n_components, size - 2),
        min_dist=config.min_dist,
        min_cluster_size=config.min_cluster_size,
        min_samples=config.min_samples,
        top_n_words=config.top_n_words,
    )
    runtime = tuple((package, version(package)) for package in _RUNTIME_PACKAGES)
    status, labels, topics = _fit_topics(batch, effective, observe_diagnostics=observe_diagnostics)
    return status, labels, topics, effective, runtime


def cluster_offline(evidence: OfflineEvidence, backend: EmbeddingBackend, refs, *,
                    registry_version, analysis_language, output_language,
                    config: TopicConfig = TopicConfig(), cache_dir=None, observe_rows=None) -> TopicRun:
    """Embed approved fixtures and recheck current exact evidence before releasing candidates.

    An internal observer can bind the exact revalidated embedding rows to a stored run.
    """
    refs = tuple(refs)
    if not refs:
        metadata = TopicMetadata(
            None, backend.profile, PREPROCESSING_VERSION, evidence.registry_version(registry_version),
            _language(analysis_language), _language(output_language), (), None, config, None, (),
        )
        if observe_rows is not None:
            observe_rows(())
        return TopicRun(sha256(dump(asdict(metadata)).encode()).hexdigest(), "empty", metadata, (), ())

    batch = embed_offline(
        evidence, backend, refs, registry_version=registry_version,
        analysis_language=analysis_language, output_language=output_language, cache_dir=cache_dir,
    )
    diagnostics = []
    status, labels, topics, effective, runtime = _cluster_batch(batch, config, observe_diagnostics=diagnostics.extend)
    languages = tuple(_language(tag) for tag in batch.model.supported_languages)
    current_rows = tuple(sorted(
        (_row(evidence.read(ref), languages) for ref in refs), key=lambda row: row.document_id,
    ))
    if (current_rows != batch.rows or evidence.registry_version(batch.registry_version) != batch.registry_version
            or backend.profile != batch.model):
        raise Conflict("m09_topic_dependencies_changed")

    metadata = TopicMetadata(
        batch.run_id, batch.model, batch.preprocessing_version, batch.registry_version,
        batch.analysis_language, batch.output_language, tuple(sorted({row.original_language for row in batch.rows})),
        sha256(batch.vectors.tobytes()).hexdigest(), config, effective, runtime,
    )
    assignments = tuple(diagnostics) or tuple(
        TopicAssignment(row.document_id, label) for row, label in zip(batch.rows, labels, strict=True)
    )
    if len(assignments) != len(batch.rows):
        raise RuntimeError("m09_topic_diagnostic_alignment")
    if observe_rows is not None:
        observe_rows(batch.rows)
    return TopicRun(sha256(dump(asdict(metadata)).encode()).hexdigest(), status, metadata, assignments, topics)
