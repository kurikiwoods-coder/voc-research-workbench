"""Immutable M06 segment inputs and validation shared by writes and reads."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.raw_store.corpus import checksum
from src.raw_store.store import Conflict


@dataclass(frozen=True)
class EvidenceInterval:
    record_id: str
    raw_sha256: str
    start_cp: int
    end_cp: int


@dataclass(frozen=True)
class SupportDraft:
    interval: EvidenceInterval
    segment_no: int
    identity: str
    basis_ref: str
    contexts: tuple[EvidenceInterval, ...] = ()
    original: EvidenceInterval | None = None

    def __post_init__(self):
        object.__setattr__(self, "contexts", tuple(self.contexts))


@dataclass(frozen=True)
class MentionDraft:
    ref: str
    supports: tuple[SupportDraft, ...]
    mention_id: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "supports", tuple(self.supports))


@dataclass(frozen=True)
class Replacement:
    from_mention_id: str
    to_ref: str
    reason: str


def validate_interval(
    interval: EvidenceInterval, record: Mapping, *, study_id: str, scope_id: str,
) -> str:
    """Slice the exact M05 text at half-open Unicode code point coordinates."""
    start, end = interval.start_cp, interval.end_cp
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ValueError("证据区间需要有效的 Unicode 码点起止位置。")

    trace = record.get("trace")
    raw_text = record.get("raw_text")
    if (
        not isinstance(trace, Mapping)
        or trace.get("study_id") != study_id
        or trace.get("scope_id") != scope_id
        or record.get("record_id") != interval.record_id
        or not isinstance(raw_text, str)
        or record.get("raw_sha256") != interval.raw_sha256
        or checksum(raw_text) != interval.raw_sha256
    ):
        raise Conflict("证据区间与当前原始记录、冻结范围或原文摘要不一致。")
    if end > len(raw_text):
        raise ValueError("证据区间超出原文的 Unicode 码点范围。")
    return raw_text[start:end]


def validate_replacements(
    replacements: Iterable[Replacement], parent_ids: Iterable[str],
    final_ids_by_ref: Mapping[str, str], fresh_ids: Iterable[str],
) -> None:
    """Validate independent split and merge relations within one revision."""
    parent_ids = set(parent_ids)
    final_ids = set(final_ids_by_ref.values())
    fresh_ids = set(fresh_ids)
    successors = defaultdict(set)
    predecessors = defaultdict(set)
    for replacement in replacements:
        old_id = replacement.from_mention_id
        new_id = final_ids_by_ref.get(replacement.to_ref)
        if old_id not in parent_ids or old_id in final_ids:
            raise ValueError("替代来源必须是原版中本次退出的发生。")
        if new_id not in fresh_ids or new_id in parent_ids:
            raise ValueError("替代去向必须是本次版新建的发生。")
        if not isinstance(replacement.reason, str) or not replacement.reason.strip():
            raise ValueError("请提供发生替代的审核依据。")
        if new_id in successors[old_id]:
            raise ValueError("发生替代边不能重复。")
        successors[old_id].add(new_id)
        predecessors[new_id].add(old_id)

    for targets in successors.values():
        is_split = len(targets) > 1
        for target in targets:
            is_merge = len(predecessors[target]) > 1
            if is_split == is_merge:
                raise ValueError("发生替代须为独立的一对多拆分或多对一合并。")


def require_replacement_lineage(parent_anchors, fresh_anchors, replacements):
    """Require explicit lineage when new intervals replace one or several old intervals."""
    new_by_record = defaultdict(list)
    for ref, interval in fresh_anchors.items():
        new_by_record[interval.record_id].append((ref, interval))
    linked = {(edge.from_mention_id, edge.to_ref) for edge in replacements}
    successors = defaultdict(set)
    predecessors = defaultdict(set)
    for old_id, interval in parent_anchors.items():
        for ref, new in new_by_record[interval.record_id]:
            if (interval.raw_sha256 == new.raw_sha256
                    and max(interval.start_cp, new.start_cp) < min(interval.end_cp, new.end_cp)):
                successors[old_id].add(ref)
                predecessors[ref].add(old_id)
    required = {
        (old_id, ref) for old_id, refs in successors.items() for ref in refs
        if len(refs) > 1 or len(predecessors[ref]) > 1
    }
    if required - linked:
        raise Conflict("同一原文区间拆分或合并时须记录全部受影响的发生谱系。")
