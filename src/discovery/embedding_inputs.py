"""Read exact, current evidence for isolated M09 engineering runs."""

from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit

from src.raw_store.store import Conflict, dump


@dataclass(frozen=True)
class FixtureRecord:
    """Trusted fixture setup pins the generated record before any M09 read."""

    study_id: str
    scope_id: str
    scope_version: str
    record_id: str
    raw_sha256: str


@dataclass(frozen=True)
class MentionEvidence:
    record: FixtureRecord
    segment_revision: int
    mention_id: str
    evidence_id: str
    original_language: str


@dataclass(frozen=True)
class SamplingEvidence:
    task_id: str
    receipt_index: int
    original_language: str


@dataclass(frozen=True)
class Lineage:
    study_id: str
    scope_id: str
    scope_version: str
    batch_id: str
    record_id: str
    raw_sha256: str
    start_cp: int
    end_cp: int
    source_locator: str
    extraction_version: str
    mention_id: str | None = None
    evidence_id: str | None = None
    segment_revision: int | None = None
    acquisition_task_id: str | None = None
    source_id: str | None = None
    source_object_id: str | None = None
    context_ids: tuple[str, ...] = ()
    duplicate_group_id: str | None = None
    license_status: str = "authorized"
    privacy: str | None = None
    license_reference: str | None = None
    source_response_sha256: str | None = None

    @property
    def document_id(self):
        key = (
            self.study_id, self.scope_id, self.scope_version, self.record_id,
            self.raw_sha256, self.start_cp, self.end_cp, self.mention_id,
            self.evidence_id, self.acquisition_task_id,
        )
        return "m09-" + sha256(dump(key).encode()).hexdigest()


@dataclass(frozen=True)
class EvidenceDocument:
    lineage: Lineage
    original_text: str
    original_language: str


class OfflineEvidence:
    """Bind one isolated workspace and frozen scope to existing M05–M08 readers.

    Fixture grants are supplied by trusted test setup, never from an API request.
    """

    def __init__(self, *, study_id, scope_id, scope_version, mentions=None, registry=None,
                 sampling=None, fixture_records=()):
        self.study_id = study_id
        self.scope_id = scope_id
        self.scope_version = scope_version
        self.mentions = mentions
        self.registry = registry
        self.sampling = sampling
        self.fixture_records = frozenset(fixture_records)

    def registry_version(self, version):
        if self.registry is None or not version:
            raise Conflict("m09_sealed_registry_required")
        return self.registry.consumer(version, limit=1)["registry_version"]

    def read(self, ref):
        if isinstance(ref, MentionEvidence):
            return self._mention(ref)
        if isinstance(ref, SamplingEvidence):
            return self._sampling(ref)
        raise TypeError("m09_evidence_reference_required")

    def _check_scope(self, study, scope, version):
        if (study, scope, version) != (self.study_id, self.scope_id, self.scope_version):
            raise Conflict("m09_frozen_scope_mismatch")

    def _mention(self, ref):
        receipt = ref.record
        self._check_scope(receipt.study_id, receipt.scope_id, receipt.scope_version)
        if self.mentions is None or receipt not in self.fixture_records:
            raise Conflict("m09_fixture_provenance_required")
        evidence = self.mentions.read_evidence(
            self.study_id, ref.segment_revision, ref.mention_id, ref.evidence_id,
        )
        if evidence["record_id"] != receipt.record_id or evidence["raw_sha256"] != receipt.raw_sha256:
            raise Conflict("m09_fixture_identity_mismatch")
        record = self.mentions.corpus.qualified_record(
            self.study_id, receipt.record_id, scope_id=self.scope_id,
        )
        self._check_scope(evidence["study_id"], evidence["scope_id"], evidence["scope_version"])
        self._check_scope(record["trace"]["study_id"], record["trace"]["scope_id"], record["trace"]["scope_version"])
        locator = evidence["source_url"] or ""
        host = urlsplit(locator).hostname or ""
        start, end = evidence["start_cp"], evidence["end_cp"]
        if (not host.endswith(".invalid") or record["raw_sha256"] != receipt.raw_sha256
                or record["metadata"].get("source_url") != locator
                or record["trace"]["batch_id"] != evidence["batch_id"]
                or record["raw_text"][start:end] != evidence["excerpt"]):
            raise Conflict("m09_fixture_identity_mismatch")
        lineage = Lineage(
            self.study_id, self.scope_id, self.scope_version, evidence["batch_id"],
            receipt.record_id, receipt.raw_sha256, start, end, locator, evidence["rule_version"],
            mention_id=ref.mention_id, evidence_id=ref.evidence_id, segment_revision=ref.segment_revision,
            context_ids=tuple(sorted(evidence["contexts"])),
            duplicate_group_id=(evidence["duplicate"] or {}).get("group_id"), privacy=evidence["privacy"],
            license_status=evidence["license_status"],
        )
        return EvidenceDocument(lineage, evidence["excerpt"], ref.original_language)

    def _sampling(self, ref):
        if self.sampling is None:
            raise Conflict("m09_sampling_reader_required")
        self.sampling.authorize_project(self.study_id)
        task = self.sampling.ledger.get(self.study_id, ref.task_id)
        config = {**task["config"], "acquisition_task_id": ref.task_id}
        self._check_scope(config["study_id"], config["scope_id"], config["scope_version"])
        self.sampling.authorize(config)
        items = [item for attempt in task["attempts"]
                 if attempt["state"] == "reconciled" and attempt["receipt"] is not None
                 for item in attempt["receipt"].get("evidence", ())]
        if not 0 <= ref.receipt_index < len(items):
            raise KeyError(ref.receipt_index)
        row = self.sampling.evidence(config, items[ref.receipt_index])
        self._check_scope(row["study_id"], row["scope_id"], row["scope_version"])
        if (row["role"] != "synthetic" or row["engineering_eligible"] or row["research_eligible"]
                or row["outbound_allowed"] or any(row[key] is not None for key in (
                    "mention_id", "evidence_id", "segment_revision", "registry_version",
                ))):
            raise Conflict("m09_synthetic_receipt_required")
        lineage = Lineage(
            self.study_id, self.scope_id, self.scope_version, row["batch_id"], row["record_id"],
            row["raw_sha256"], row["start_cp"], row["end_cp"], row["source_locator"], row["extraction_version"],
            acquisition_task_id=ref.task_id, source_id=row["source_id"], source_object_id=row["source_object_id"],
            license_reference=row["license_reference"], source_response_sha256=row["response_body_sha256"],
        )
        return EvidenceDocument(lineage, row["text"], ref.original_language)
