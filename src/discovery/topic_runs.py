"""Persist, trace, and replay offline M09 candidates in one authorized frozen scope."""

from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256

from src.discovery.embedding_inputs import FixtureRecord, MentionEvidence, SamplingEvidence
from src.discovery.embeddings import PREPROCESSING_VERSION, _language, _row
from src.discovery.topic_store import TopicRunStore
from src.discovery.topics import (
    TOKENIZER_VERSION, TOPIC_DIAGNOSTICS_VERSION, TOPIC_PIPELINE_VERSION, TopicConfig, cluster_offline,
)
from src.edition_policy import REFERENCE
from src.ingestion.m08_tasks import AuthorizationBlocked
from src.raw_store.store import Conflict, dump, now
from src.raw_store.studies import StudyStore


def _digest(value):
    return sha256(dump(value).encode("utf-8")).hexdigest()


def _reference(ref):
    if isinstance(ref, MentionEvidence):
        return {
            "kind": "mention", "segment_revision": ref.segment_revision, "mention_id": ref.mention_id,
            "evidence_id": ref.evidence_id, "original_language": _language(ref.original_language),
        }
    if isinstance(ref, SamplingEvidence):
        return {
            "kind": "sampling", "task_id": ref.task_id, "receipt_index": ref.receipt_index,
            "original_language": _language(ref.original_language),
        }
    raise TypeError("m09_evidence_reference_required")


def _restore_reference(member):
    ref = {key: value for key, value in member["reference"].items() if key != "kind"}
    if member["reference"]["kind"] == "sampling":
        return SamplingEvidence(**ref)
    lineage = member["lineage"]
    record = FixtureRecord(*(lineage[key] for key in (
        "study_id", "scope_id", "scope_version", "record_id", "raw_sha256",
    )))
    return MentionEvidence(record, **ref)


def _capture(result, rows, references):
    assignments = {item.document_id: item for item in result.assignments}
    if assignments.keys() != references.keys() or len(assignments) != len(result.assignments):
        raise Conflict("m09_topic_assignment_mismatch")
    if tuple(row.document_id for row in rows) != tuple(sorted(references)):
        raise Conflict("m09_topic_input_mismatch")

    members = []
    grouped = defaultdict(list)
    for row in rows:
        item = assignments[row.document_id]
        member = {
            "document_id": row.document_id, "topic_id": item.topic_id, "reference": references[row.document_id],
            "lineage": asdict(row.lineage), "original_language": row.original_language,
            "original_excerpt_sha256": row.original_excerpt_sha256, "model_input_sha256": row.model_input_sha256,
            "raw_topic_id": item.raw_topic_id, "hdbscan_cluster_id": item.hdbscan_cluster_id,
            "membership_probability": item.hdbscan_membership_probability, "outlier_score": item.hdbscan_outlier_score,
            "centroid_similarity": item.centroid_cosine, "postprocessing": None,
        }
        members.append(member)
        grouped[item.topic_id].append(member)

    topics = []
    if -1 in grouped:
        topics.append({"topic_id": -1, "keywords": [], "representative_document_ids": []})
    if set(grouped) - {-1} != {topic.topic_id for topic in result.topics}:
        raise Conflict("m09_topic_membership_mismatch")
    for topic in result.topics:
        group = grouped[topic.topic_id]
        if len(group) != topic.member_count:
            raise Conflict("m09_topic_membership_mismatch")
        ranked = sorted(group, key=lambda member: (
            member["centroid_similarity"] is None, -(member["centroid_similarity"] or 0), member["document_id"],
        ))
        topics.append({
            "topic_id": topic.topic_id, "keywords": [asdict(keyword) for keyword in topic.keywords],
            "representative_document_ids": [member["document_id"] for member in ranked[:3]],
        })
    return members, topics


def _quality():
    return {
        "review": "PENDING", "diagnostic": "QUALITY_DIAGNOSTIC_WARNING", "g3": "G3_PENDING",
        "m09_b_synthetic_purity": [[8, 11], [8, 12], [8, 13]],
        "m09_b_synthetic_threshold": 0.75, "postprocessing": "NOT_APPLIED",
    }


def _compare(left, right):
    first = {item["document_id"]: item for item in left["members"]}
    second = {item["document_id"]: item for item in right["members"]}
    left_topics = {topic["topic_id"]: topic["keywords"] for topic in left["topics"]}
    right_topics = {topic["topic_id"]: topic["keywords"] for topic in right["topics"]}
    sizes_left = Counter(item["topic_id"] for item in first.values())
    sizes_right = Counter(item["topic_id"] for item in second.values())
    overlap = Counter(
        (first[doc]["topic_id"], second[doc]["topic_id"]) for doc in first.keys() & second.keys()
    )
    matches = [
        {"left_topic_id": a, "right_topic_id": b, "shared_documents": count,
         "union_documents": sizes_left[a] + sizes_right[b] - count}
        for (a, b), count in sorted(overlap.items()) if a >= 0 and b >= 0
    ]
    metadata = {
        key: {"left": left["metadata"].get(key), "right": right["metadata"].get(key)}
        for key in sorted(left["metadata"].keys() | right["metadata"].keys())
        if left["metadata"].get(key) != right["metadata"].get(key)
    }
    membership, outliers, evidence, diagnostics = [], [], [], []
    identity_fields = ("reference", "lineage", "original_excerpt_sha256", "model_input_sha256")
    diagnostic_fields = (
        "raw_topic_id", "hdbscan_cluster_id", "membership_probability", "outlier_score",
        "centroid_similarity", "postprocessing",
    )
    for doc in sorted(first.keys() | second.keys()):
        before, after = first.get(doc, {}), second.get(doc, {})
        a, b = before.get("topic_id"), after.get("topic_id")
        if a != b:
            membership.append({"document_id": doc, "left_topic_id": a, "right_topic_id": b})
        if (a == -1) != (b == -1):
            outliers.append({"document_id": doc, "left_outlier": a == -1, "right_outlier": b == -1})
        changed = [key for key in identity_fields if before.get(key) != after.get(key)]
        if changed:
            evidence.append({"document_id": doc, "changed_fields": changed})
        changed = [key for key in diagnostic_fields if before.get(key) != after.get(key)]
        if changed:
            diagnostics.append({"document_id": doc, "changed_fields": changed})

    # Numeric labels are run-local. Only report keyword deltas against overlapping topics.
    pairs = {(item["left_topic_id"], item["right_topic_id"]) for item in matches}
    if -1 in left_topics and -1 in right_topics:
        pairs.add((-1, -1))
    pairs.update((topic, None) for topic in left_topics.keys() - {a for a, _ in pairs})
    pairs.update((None, topic) for topic in right_topics.keys() - {b for _, b in pairs})
    keywords = [
        {"left_topic_id": a, "right_topic_id": b, "left": left_topics.get(a), "right": right_topics.get(b)}
        for a, b in sorted(pairs, key=lambda pair: tuple(-2 if value is None else value for value in pair))
        if left_topics.get(a) != right_topics.get(b)
    ]
    return {
        "left_run_id": left["run_id"], "right_run_id": right["run_id"], "topic_matches": matches,
        "metadata_changes": metadata, "membership_changes": membership, "outlier_changes": outliers,
        "keyword_changes": keywords, "evidence_changes": evidence, "diagnostic_changes": diagnostics,
        "same_result": all(left[field] == right[field] for field in ("status", "topics", "members")),
    }


class TopicRuns:
    """Service entry point for trusted local discovery, shared by both editions."""

    def __init__(self, workspace_store, evidence, *, authorize_project):
        if not callable(authorize_project):
            raise TypeError("m09_project_authorizer_required")
        if evidence.mentions is not None and evidence.mentions.store is not workspace_store:
            raise Conflict("m09_evidence_workspace_mismatch")
        if evidence.registry is not None and evidence.registry.relations.store is not workspace_store:
            raise Conflict("m09_registry_workspace_mismatch")
        if evidence.sampling is not None and evidence.sampling.studies.store is not workspace_store:
            raise Conflict("m09_sampling_workspace_mismatch")
        self.evidence = evidence
        self._scope = evidence.study_id, evidence.scope_id, evidence.scope_version
        self._authorize_project = authorize_project
        self._studies = StudyStore(workspace_store)
        self._authorize()
        self._store = TopicRunStore(workspace_store)

    def _authorize(self):
        study, scope_id, version = self._scope
        if (self.evidence.study_id, self.evidence.scope_id, self.evidence.scope_version) != self._scope:
            raise Conflict("m09_frozen_scope_mismatch")
        if self._authorize_project(study) is not True:
            raise Conflict("m09_project_permission_required")
        scope = self._studies.get_scope(study, scope_id)
        if not scope["frozen_at"] or scope["scope_version"] != version:
            raise Conflict("m09_frozen_scope_mismatch")
        if self._studies.get(study)["status"] == "archived":
            raise Conflict("m09_project_archived")

    def _snapshot(self, run_id):
        self._authorize()
        snapshot = self._store.get(self._scope[0], run_id)
        if (snapshot["scope_id"], snapshot["scope_version"]) != self._scope[1:]:
            raise KeyError(run_id)
        return snapshot

    def _read_member(self, member):
        document = self.evidence.read(_restore_reference(member))
        if (document.lineage.document_id != member["document_id"]
                or dump(asdict(document.lineage)) != dump(member["lineage"])
                or sha256(document.original_text.encode("utf-8")).hexdigest() != member["original_excerpt_sha256"]):
            raise Conflict("m09_topic_evidence_changed")
        return document

    def _view(self, snapshot):
        self._authorize()
        restricted = set()
        members = []
        for member in snapshot["members"]:
            try:
                self._read_member(member)
            except (Conflict, AuthorizationBlocked, KeyError, PermissionError):
                restricted.add(member["topic_id"])
                members.append({"document_id": member["document_id"], "topic_id": member["topic_id"],
                                "evidence_eligible": False})
            else:
                members.append({**member, "evidence_eligible": True})
        topics = [
            {**topic, "keywords": [], "representative_document_ids": [], "evidence_eligible": False}
            if topic["topic_id"] in restricted else {**topic, "evidence_eligible": True}
            for topic in snapshot["topics"]
        ]
        self._authorize()
        return {**snapshot, "members": members, "topics": topics}

    def create(self, backend, refs, *, request_id, registry_version, analysis_language, output_language,
               config=TopicConfig(), cache_dir=None):
        return self._create(backend, refs, request_id, registry_version, analysis_language, output_language,
                            config, cache_dir)

    def _create(self, backend, refs, request_id, registry_version, analysis_language, output_language,
                config, cache_dir, parent=None, *, recalculation=False):
        self._authorize()
        started_at = now()
        if not isinstance(request_id, str) or not REFERENCE.fullmatch(request_id):
            raise ValueError("m09_invalid_request_id")
        refs = tuple(refs)
        registry_version = self.evidence.registry_version(registry_version)
        analysis_language, output_language = _language(analysis_language), _language(output_language)
        profile = backend.profile
        documents = [(self.evidence.read(ref), _reference(ref)) for ref in refs]
        references = {doc.lineage.document_id: ref for doc, ref in documents}
        if len(references) != len(refs):
            raise ValueError("m09_duplicate_document")
        languages = tuple(_language(tag) for tag in profile.supported_languages)
        expected_rows = tuple(sorted(
            (_row(doc, languages) for doc, _ in documents), key=lambda row: row.document_id,
        ))
        input_sha256 = _digest([
            (row.document_id, asdict(row.lineage), row.original_language, row.original_excerpt_sha256,
             row.model_input_sha256) for row in expected_rows
        ])
        replay_of = None if parent is None else parent["run_id"]
        request_identity = (
            self._scope, registry_version, analysis_language, output_language, asdict(config), asdict(profile),
            sorted(references.items()), input_sha256, replay_of,
        )
        request_sha256 = _digest((*request_identity, "recalculation") if recalculation else request_identity)
        stored = self._store.by_request(self._scope[0], request_id, request_sha256)
        if stored is not None:
            return self._view(stored)

        observed_rows = []
        result = cluster_offline(
            self.evidence, backend, refs, registry_version=registry_version, analysis_language=analysis_language,
            output_language=output_language, config=config, cache_dir=cache_dir, observe_rows=observed_rows.extend,
        )
        if tuple(observed_rows) != expected_rows or result.metadata.model != profile:
            raise Conflict("m09_topic_dependencies_changed")
        members, topics = _capture(result, observed_rows, references)
        metadata = {
            **asdict(result.metadata), "input_sha256": input_sha256, "computation_id": result.run_id,
            "diagnostics_version": TOPIC_DIAGNOSTICS_VERSION,
            "mode": result.mode, "research_denominator": result.research_denominator,
            "outbound_allowed": result.outbound_allowed,
        }
        if recalculation:
            metadata["operation"] = "recalculation"
            if input_sha256 != parent["metadata"]["input_sha256"]:
                raise Conflict("m09_recalculation_inputs_changed")
        if parent is not None and not recalculation and any(
            dump(metadata[key]) != dump(parent["metadata"][key])
            for key in ("input_sha256", "vector_sha256", "embedding_run_id", "runtime_versions", "effective_config")
        ):
            raise Conflict("m09_replay_inputs_or_runtime_changed")

        # Recheck the exact references before sealing. Historical views always recheck again.
        for member in members:
            self._read_member(member)
        self._authorize()
        study, scope_id, scope_version = self._scope
        stored = self._store.save(
            study_id=study, scope_id=scope_id, scope_version=scope_version, idempotency_key=request_id,
            request_sha256=request_sha256, started_at=started_at, status=result.status, metadata=metadata,
            members=members, topics=topics, quality=_quality(), replay_of=replay_of,
        )
        return self._view(stored)

    def get(self, run_id):
        return self._view(self._snapshot(run_id))

    def list_runs(self):
        self._authorize()
        return self._store.list_by_scope(*self._scope)

    def evidence_for(self, run_id, document_id):
        snapshot = self._snapshot(run_id)
        for member in snapshot["members"]:
            if member["document_id"] == document_id:
                result = self._read_member(member)
                self._authorize()
                return result
        raise KeyError(document_id)

    def replay(self, run_id, backend, *, request_id, cache_dir=None):
        parent = self._snapshot(run_id)
        metadata = parent["metadata"]
        if dump(asdict(backend.profile)) != dump(metadata["model"]):
            raise Conflict("m09_replay_model_changed")
        if (metadata["pipeline_version"], metadata["tokenizer_version"], metadata["preprocessing_version"],
                metadata["diagnostics_version"]) != (
                    TOPIC_PIPELINE_VERSION, TOKENIZER_VERSION, PREPROCESSING_VERSION, TOPIC_DIAGNOSTICS_VERSION,
                ):
            raise Conflict("m09_replay_pipeline_changed")
        refs = []
        for member in parent["members"]:
            self._read_member(member)
            refs.append(_restore_reference(member))
        return self._create(
            backend, refs, request_id, metadata["registry_version"], metadata["analysis_language"],
            metadata["output_language"], TopicConfig(**metadata["requested_config"]), cache_dir, parent=parent,
        )

    def compare(self, left_run_id, right_run_id):
        left, right = self._snapshot(left_run_id), self._snapshot(right_run_id)
        for snapshot in (left, right):
            for member in snapshot["members"]:
                self._read_member(member)
        self._authorize()
        return _compare(left, right)

    def recalculate(self, run_id, backend, *, request_id, config=None, cache_dir=None):
        """Recompute the same qualified evidence under explicit settings and seal a new snapshot."""
        parent = self._snapshot(run_id)
        metadata = parent["metadata"]
        refs = []
        for member in parent["members"]:
            self._read_member(member)
            refs.append(_restore_reference(member))
        return self._create(
            backend, refs, request_id, metadata["registry_version"], metadata["analysis_language"],
            metadata["output_language"], config or TopicConfig(**metadata["requested_config"]),
            cache_dir, parent=parent, recalculation=True,
        )
