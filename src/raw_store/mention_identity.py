"""Validate occurrence identity from qualified M05 evidence and explicit review."""

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Literal

from src.raw_store.corpus_policy import safe_source_url, source_identity
from src.raw_store.mention_segments import EvidenceInterval, SupportDraft
from src.raw_store.store import dump


def _source(interval: EvidenceInterval, records: Mapping[str, Mapping]) -> tuple[str, str]:
    record = records.get(interval.record_id)
    if record is None or record.get("record_id") != interval.record_id:
        raise ValueError("转载核验需要原帖和转载各自的有效来源记录。")

    trace = record.get("trace")
    metadata = record.get("metadata")
    if not isinstance(trace, Mapping) or not isinstance(metadata, Mapping):
        raise ValueError("转载核验需要可追溯的原帖和转载来源。")
    url = metadata.get("source_url")
    source = source_identity(url)
    if not source or not safe_source_url(url) or not trace.get("study_id") or not trace.get("scope_id"):
        raise ValueError("转载核验需要可追溯的原帖和转载来源。")
    return source, trace["study_id"]


def validate_identity(
    supports: Sequence[SupportDraft], records: Mapping[str, Mapping],
) -> Literal["distinct", "needs_review"]:
    """Keep disputed input separate and require reposts to point directly to the original."""
    if len(supports) == 1 and supports[0].identity == "disputed" and supports[0].original is None:
        return "needs_review"

    originals = [support for support in supports if support.identity == "independent"]
    if len(originals) != 1 or originals[0].original is not None:
        raise ValueError("每次独立表达需要恰好一条不含转载引用的原帖证据。")
    if len(supports) == 1:
        return "distinct"

    original = originals[0]
    origin_source, origin_study = _source(original.interval, records)
    for support in supports:
        if support is original:
            continue
        if (
            support.identity != "repost"
            or support.original != original.interval
            or support.interval.record_id == original.interval.record_id
        ):
            raise ValueError("已核转载须指向同次表达中确切的独立原帖区间。")
        repost_source, repost_study = _source(support.interval, records)
        if origin_source == repost_source or origin_study != repost_study:
            raise ValueError("原帖和转载须来自同项目内分别可核对的来源。")
    return "distinct"


def event_anchor(record: Mapping, interval: EvidenceInterval) -> str | None:
    """Return a project-local fingerprint of a verified source event and exact interval."""
    metadata = record["metadata"]
    url = metadata.get("source_url")
    event = metadata.get("external_id")
    if not event or not safe_source_url(url):
        return None
    trace = record["trace"]
    identity = [trace["study_id"], trace["scope_id"], source_identity(url), event,
                interval.raw_sha256, interval.start_cp, interval.end_cp]
    return sha256(dump(identity).encode("utf-8")).hexdigest()
