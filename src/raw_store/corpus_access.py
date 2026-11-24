"""Resolve the current local eligibility of imported records in the project context."""

import json

from src.raw_store.corpus_policy import license_note_state, safe_metadata, snapshot_content_valid, valid_snapshot_source


ROW_SOURCE = """
    FROM import_rows r
    JOIN import_batches b ON b.batch_id=r.batch_id
    JOIN import_files f ON f.file_id=b.file_id
    JOIN study_scopes s ON s.study_id=b.study_id AND s.scope_id=b.scope_id
    JOIN study_projects p ON p.study_id=b.study_id
    LEFT JOIN corpus_snapshots snap ON snap.record_id=r.record_id
    LEFT JOIN corpus_reviews v ON v.review_id=(
        SELECT MAX(h.review_id) FROM corpus_reviews h WHERE h.record_id=r.record_id
    )
    LEFT JOIN corpus_licenses l ON l.review_id=v.review_id
"""
CANDIDATE = "(v.review_id IS NOT NULL OR r.status IN ('staged', 'pending_review'))"


def withdrawal_match(study_id, record_id, originals):
    return f"""w.study_id={study_id} AND (w.record_id={record_id} OR (
        w.source IS NOT NULL AND EXISTS (
            SELECT 1 FROM json_each({originals}) AS cell WHERE source_identity(cell.value)=w.source
        )
    ))"""


def withdrawal_id(study_id, record_id, originals):
    return f"""(SELECT MAX(w.review_id) FROM corpus_withdrawals w
        WHERE {withdrawal_match(study_id, record_id, originals)})"""


def current_restore(record_id, review_id):
    return f"""EXISTS (
        SELECT 1 FROM corpus_reviews grant_review JOIN corpus_licenses grant_license USING(review_id)
        JOIN import_rows grant_row USING(record_id) JOIN import_batches grant_batch USING(batch_id)
        WHERE grant_review.record_id={record_id} AND grant_license.restored_withdrawal_id>={review_id}
          AND grant_review.review_id=(SELECT MAX(g.review_id) FROM corpus_reviews g
                                    WHERE g.record_id=grant_review.record_id)
          AND grant_review.retention_until>=:today AND grant_batch.revoked_at IS NULL
    )"""


def unresolved_sources(study_id):
    return f"""SELECT DISTINCT w.source FROM corpus_withdrawals w WHERE w.study_id={study_id}
           AND w.source IS NOT NULL AND NOT {current_restore("w.record_id", "w.review_id")}"""


EFFECTIVE_RETENTION = """
    CASE WHEN v.decision='excluded' THEN (
        SELECT MIN(h.retention_until) FROM corpus_reviews h WHERE h.record_id=r.record_id
        AND h.review_id>=COALESCE((SELECT MAX(a.review_id) FROM corpus_reviews a
                                   WHERE a.record_id=r.record_id AND a.decision='verified'), 0)
    ) ELSE v.retention_until END
"""

# Preserve restrictions attached to one retained file and line, also for separately imported copies.
# Project-wide source withdrawals have their own history and restoration boundary.
RESTRICTED_FILE_ROWS = """
    FROM import_files restricted_file
    JOIN import_batches restricted_batch ON restricted_batch.file_id=restricted_file.file_id
    JOIN import_rows restricted_row ON restricted_row.batch_id=restricted_batch.batch_id
    JOIN study_scopes restricted_scope ON restricted_scope.study_id=restricted_batch.study_id
        AND restricted_scope.scope_id=restricted_batch.scope_id
    JOIN corpus_reviews restricted_review ON restricted_review.review_id=(
        SELECT MAX(h.review_id) FROM corpus_reviews h WHERE h.record_id=restricted_row.record_id
    )
    LEFT JOIN corpus_licenses restricted_license ON restricted_license.review_id=restricted_review.review_id
    WHERE (restricted_batch.revoked_at IS NOT NULL OR restricted_review.retention_until<:today
        OR (restricted_review.decision='excluded' AND NOT EXISTS (
            SELECT 1 FROM corpus_withdrawals w WHERE w.review_id=restricted_review.review_id
        ))
        OR CASE WHEN restricted_review.decision='verified' THEN NOT valid_snapshot_source(
            restricted_row.privacy, restricted_row.raw_text, restricted_review.role,
            restricted_row.fields_json, restricted_scope.content_json,
            restricted_license.state, restricted_license.evidence_ref
        ) ELSE 0 END)
"""
FILE_ALIAS_RESTRICTED = f"""EXISTS (
    SELECT 1 {RESTRICTED_FILE_ROWS}
    AND restricted_file.study_id=f.study_id AND restricted_file.sha256=f.sha256
    AND restricted_batch.sheet_index=b.sheet_index AND restricted_row.line_number=r.line_number
    AND restricted_row.record_id<>r.record_id
)"""
ROW_COLUMNS = f"""
    r.record_id, r.line_number, r.privacy, r.fields_json, r.raw_text, s.content_json,
    b.revoked_at, p.status AS project_status, v.review_id, v.decision, v.role,
    l.state AS license_state, l.evidence_ref, l.issued_on, l.restored_withdrawal_id,
    {EFFECTIVE_RETENTION} AS retention_until, {FILE_ALIAS_RESTRICTED} AS alias_restricted,
    {withdrawal_id("b.study_id", "r.record_id", "r.originals_json")} AS withdrawal_id,
    (SELECT MAX(w.review_id) FROM corpus_withdrawals w WHERE w.record_id=r.record_id) AS own_withdrawal_id
"""


def withdrawal_applies(row):
    return (row["withdrawal_id"] or 0) > (row["restored_withdrawal_id"] or 0)


def snapshot_valid(row):
    return valid_snapshot_source(
        row["privacy"], row["raw_text"], row["role"], row["fields_json"], row["content_json"],
        row["license_state"], row["evidence_ref"],
    )


def qualification(row, today):
    """The same eligibility rules serve corpus, deduplication and import history."""
    declared = license_note_state(json.loads(row["fields_json"]).get("access_policy", ""))
    state = row["license_state"] or declared
    expired = bool(row["retention_until"] and row["retention_until"] < today)
    withdrawn = withdrawal_applies(row)
    if withdrawn:
        state = "revoked"
    elif expired:
        state = "expired"
    elif row["decision"] == "verified" and row["license_state"] is None and declared == "unknown":
        state = "pending"

    if row["revoked_at"]:
        status = "revoked"
    elif expired:
        status = "retention_expired"
    elif withdrawn:
        status = "policy_restricted" if row["own_withdrawal_id"] else "source_restricted"
    elif row["alias_restricted"] and row["decision"] != "excluded":
        status = "source_restricted"
    elif row["decision"] == "verified" and snapshot_valid(row):
        status = "verified"
    elif row["decision"] == "verified" and (
        row["license_state"] is not None or declared != "unknown" or not snapshot_content_valid(
            row["privacy"], row["raw_text"], row["role"], row["fields_json"], row["content_json"],
        )
    ):
        status = "policy_restricted"
    elif row["decision"] == "excluded":
        status = "excluded"
    elif state in {"denied", "revoked", "expired"}:
        status = "policy_restricted"
    else:
        status = "pending_review"

    writable = not row["revoked_at"] and row["project_status"] != "archived" and not row["alias_restricted"]
    return {
        "status": status, "license_status": state,
        "source_permission_revoked": withdrawn,
        "can_review": writable and not expired and not withdrawn
        and (row["decision"] is None or status in {"pending_review", "verified", "excluded"}),
        "can_reauthorize": writable and withdrawn,
        "engineering_eligible": (status == "verified" and row["privacy"] == "public"
                                 and row["role"] == "user_quote" and row["project_status"] != "archived"),
    }


def record_summary(row, today):
    access = qualification(row, today)
    metadata = safe_metadata(row["fields_json"]) if access["status"] == "verified" else {}
    return {
        "record_id": row["record_id"], "line_number": row["line_number"], "privacy": row["privacy"],
        "role": row["role"], "source_type": metadata.get("source_type"),
        "published_at": metadata.get("published_at"), **access,
    }
