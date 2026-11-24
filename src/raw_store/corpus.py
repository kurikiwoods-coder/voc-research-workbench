"""Local review and replay of immutable M04 import records."""

from datetime import date
import hashlib
import json
from unicodedata import normalize

from src.raw_store.corpus_policy import (
    CONTROL, SENSITIVE, permission_recorded, safe_metadata, validate_snapshot, valid_snapshot_source,
)
from src.raw_store.imports import RESTRICTED_SOURCE_ROWS, source_withdrawal
from src.raw_store.store import Conflict, dump, now
from src.raw_store.studies import StudyStore


PAGE_SIZE = 20
ROLES = {"user_quote", "background", "internal", "synthetic"}

# The v3 view excludes revoked rows; reviewed rows remain visible for local audit.
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
"""
CANDIDATE = "(v.review_id IS NOT NULL OR r.status IN ('staged', 'pending_review'))"
SOURCE_ALIAS_RESTRICTED = f"""EXISTS (
    SELECT 1 {RESTRICTED_SOURCE_ROWS}
    AND restricted_file.study_id=f.study_id AND restricted_file.sha256=f.sha256
    AND restricted_batch.sheet_index=b.sheet_index AND restricted_row.line_number=r.line_number
    AND restricted_row.record_id<>r.record_id
)"""
EFFECTIVE_RETENTION = """
    CASE WHEN v.decision='excluded' THEN (
        SELECT MIN(h.retention_until) FROM corpus_reviews h WHERE h.record_id=r.record_id
        AND h.review_id>=COALESCE((SELECT MAX(a.review_id) FROM corpus_reviews a
                                   WHERE a.record_id=r.record_id AND a.decision='verified'), 0)
    ) ELSE v.retention_until END
"""
SOURCE_WITHDRAWN = source_withdrawal("r.record_id")
ROW_COLUMNS = f"""
    r.record_id, r.line_number, r.privacy, r.fields_json, r.raw_text, s.content_json,
    b.revoked_at, p.status AS project_status,
    v.decision, v.role, {EFFECTIVE_RETENTION} AS retention_until, {SOURCE_ALIAS_RESTRICTED} AS alias_restricted,
    {SOURCE_WITHDRAWN} AS source_permission_revoked
"""
RESTRICTED_STATUSES = {"excluded", "revoked", "retention_expired", "source_restricted", "policy_restricted"}


def checksum(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def require_review_text(value, label, max_length, *, required):
    if not isinstance(value, str):
        raise ValueError(f"{label}必须是文本。")
    value = value.strip()
    if (required and not value) or len(value) > max_length:
        raise ValueError(f"请填写有效的{label}（最多 {max_length} 字）。")
    if CONTROL.search(value) or SENSITIVE.search(value):
        raise ValueError(f"请先从{label}中移除个人识别信息。")
    return value


def review_retention(value, today, *, required):
    if value in (None, "") and not required:
        return None
    try:
        valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value and value >= today
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("请提供有效的保留截止日期（YYYY-MM-DD，UTC，且未到期）。")
    return value


def effective_status(row, today):
    if row["revoked_at"]:
        return "revoked"
    if row["retention_until"] and row["retention_until"] < today:
        return "retention_expired"
    if row["source_permission_revoked"]:
        return "policy_restricted"
    if row["alias_restricted"] and row["decision"] != "excluded":
        return "source_restricted"
    if row["decision"] == "verified" and not snapshot_valid(row):
        return "policy_restricted"
    return row["decision"] or "pending_review"


def record_summary(row, today):
    status = effective_status(row, today)
    metadata = {} if status in RESTRICTED_STATUSES else safe_metadata(row["fields_json"])
    return {
        "record_id": row["record_id"], "line_number": row["line_number"], "privacy": row["privacy"],
        "role": row["role"], "status": status, "source_type": metadata.get("source_type"),
        "published_at": metadata.get("published_at"),
        "source_permission_revoked": bool(row["source_permission_revoked"]),
        "can_review": (status == "excluded" or status not in RESTRICTED_STATUSES)
        and row["project_status"] != "archived",
    }


def dedupe_key(study_id, text, metadata):
    quote = " ".join(normalize("NFC", text).split())
    if len(quote) >= 24:
        # Match exact, substantial quotes across sources. A short reply needs a shared source identity.
        return checksum(dump([study_id, "public", "user_quote", quote]))
    if metadata.get("external_id"):
        return checksum(dump([study_id, "public", "user_quote", quote, metadata["source_url"], metadata["external_id"]]))
    return None


def snapshot_valid(row):
    return valid_snapshot_source(
        row["privacy"], row["raw_text"], row["role"], row["fields_json"], row["content_json"],
    )


class CorpusStore:
    def __init__(self, store):
        if store.fixture or store.diagnostic:
            raise ValueError("原文库只允许使用工作台主库。")
        self.store = store

    def batches(self, study_id, offset=0):
        with self.store.db() as db:
            db.execute("BEGIN")
            StudyStore.project_row(db, study_id)
            rows = db.execute(
                """SELECT b.batch_id, f.filename, b.sheet_name, b.scope_id, 'v' || s.version_no AS scope_version,
                          b.created_at AS collected_at, b.revoked_at,
                          (SELECT COUNT(*) FROM import_rows r WHERE r.batch_id=b.batch_id
                           AND r.status IN ('staged', 'pending_review')) AS candidate_count,
                          (SELECT COUNT(*) FROM import_rows r WHERE r.batch_id=b.batch_id AND EXISTS
                           (SELECT 1 FROM corpus_reviews h WHERE h.record_id=r.record_id)) AS reviewed_count
                   FROM import_batches b JOIN import_files f ON f.file_id=b.file_id
                   JOIN study_scopes s ON s.study_id=b.study_id AND s.scope_id=b.scope_id
                   WHERE b.study_id=? ORDER BY b.created_at DESC, b.rowid DESC LIMIT ? OFFSET ?""",
                (study_id, PAGE_SIZE + 1, offset),
            ).fetchall()
            return {"batches": [dict(row) for row in rows[:PAGE_SIZE]], "more": len(rows) > PAGE_SIZE}

    def candidates(self, study_id, batch_id, offset=0):
        with self.store.db() as db:
            db.execute("BEGIN")
            if db.execute("SELECT 1 FROM import_batches WHERE study_id=? AND batch_id=?",
                          (study_id, batch_id)).fetchone() is None:
                raise KeyError(batch_id)
            today = now()[:10]
            rows = db.execute(
                f"""SELECT {ROW_COLUMNS} {ROW_SOURCE}
                    WHERE b.study_id=:study_id AND b.batch_id=:batch_id AND {CANDIDATE}
                    ORDER BY r.line_number LIMIT :limit OFFSET :offset""",
                {"study_id": study_id, "batch_id": batch_id, "today": today,
                 "limit": PAGE_SIZE + 1, "offset": offset},
            ).fetchall()
            return {"batch_id": batch_id, "records": [record_summary(row, today) for row in rows[:PAGE_SIZE]],
                    "more": len(rows) > PAGE_SIZE}

    @staticmethod
    def source_row(db, study_id, record_id, today):
        row = db.execute(
            f"""SELECT {ROW_COLUMNS}, r.issues_json, r.status AS import_status,
                       b.batch_id, b.study_id, b.scope_id, 'v' || s.version_no AS scope_version,
                       b.file_id, f.filename, f.kind, f.sha256 AS file_sha256, b.sheet_name,
                       b.created_at AS collected_at, snap.raw_sha256, v.dedupe_group
                {ROW_SOURCE} WHERE b.study_id=:study_id AND r.record_id=:record_id AND {CANDIDATE}""",
            {"study_id": study_id, "record_id": record_id, "today": today},
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return row

    @staticmethod
    def duplicate(db, row, today, status):
        if not row["dedupe_group"] or row["role"] != "user_quote" or status != "verified":
            return None
        group = db.execute(
            f"""SELECT r.record_id, r.privacy, r.raw_text, r.fields_json, s.content_json, v.role {ROW_SOURCE}
                WHERE b.study_id=:study_id AND v.dedupe_group=:dedupe_group AND b.revoked_at IS NULL
                    AND v.decision='verified' AND v.role='user_quote' AND v.retention_until>=:today
                    AND NOT {SOURCE_WITHDRAWN}
                    AND NOT {SOURCE_ALIAS_RESTRICTED}
                ORDER BY snap.created_at, snap.record_id""",
            {"study_id": row["study_id"], "dedupe_group": row["dedupe_group"], "today": today},
        )
        members = [entry["record_id"] for entry in group if snapshot_valid(entry)]
        return {"group_id": row["dedupe_group"], "canonical_record_id": members[0],
                "record_count": len(members), "is_duplicate": members[0] != row["record_id"]}

    def describe(self, db, row, today):
        summary = record_summary(row, today)
        raw_text = row["raw_text"]
        restricted = summary["status"] in RESTRICTED_STATUSES
        metadata = {} if restricted else safe_metadata(row["fields_json"])
        visible = summary["status"] == "verified" or (
            summary["status"] == "pending_review" and row["privacy"] == "public"
            and permission_recorded(metadata) and not SENSITIVE.search(raw_text) and not CONTROL.search(raw_text)
        )
        trace = {key_: row[key_] for key_ in (
            "batch_id", "study_id", "scope_id", "scope_version", "file_id", "filename",
            "file_sha256", "sheet_name", "line_number", "collected_at",
        )}
        trace.update({"time_window": json.loads(row["content_json"])["date_window"],
                      "extraction_method": "csv_upload" if row["kind"] == "csv" else "manual_import",
                      "extraction_rule": "按导入字段映射保存原单元格文本", "query_terms": None})
        history = [dict(event) for event in db.execute(
            """SELECT decision, role, reason, basis, retention_until, reviewed_at FROM corpus_reviews
               WHERE record_id=? ORDER BY review_id DESC LIMIT 20""",
            (row["record_id"],),
        )]
        if restricted:
            # Source cells and free-form notes may repeat an original or a partial quote.
            for event in history:
                event.update(reason=None, basis=None)
        return {**summary, "raw_text": raw_text if visible else None, "raw_sha256": row["raw_sha256"],
                "metadata": metadata, "trace": trace,
                "import_status": row["import_status"], "import_issues": json.loads(row["issues_json"]),
                "duplicate": self.duplicate(db, row, today, summary["status"]), "history": history,
                "decision": row["decision"], "retention_until": row["retention_until"], "revoked_at": row["revoked_at"],
                "research_eligible": False, "outbound_allowed": False}

    def detail(self, study_id, record_id):
        with self.store.db() as db:
            db.execute("BEGIN")
            today = now()[:10]
            return self.describe(db, self.source_row(db, study_id, record_id, today), today)

    def review(self, study_id, record_id, decision, role, reason, basis="", retention_until=None):
        if decision not in {"verified", "excluded"} or role not in ROLES:
            raise ValueError("核验处理和内容角色无效。")
        verified = decision == "verified"
        reason = require_review_text(reason, "处理原因", 500, required=True)
        basis = require_review_text(basis, "核验依据", 1000, required=verified)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            at = now()
            today = at[:10]
            retention_until = review_retention(retention_until, today, required=verified)
            row = self.source_row(db, study_id, record_id, today)
            summary = record_summary(row, today)
            payload = (decision, role, reason, basis, retention_until)
            previous = db.execute(
                """SELECT decision, role, reason, basis, retention_until FROM corpus_reviews
                   WHERE record_id=? ORDER BY review_id DESC LIMIT 1""", (record_id,),
            ).fetchone()
            if previous and tuple(previous) == payload and (
                summary["can_review"] or (row["source_permission_revoked"] and not verified)
            ):
                return self.describe(db, row, today)
            if not summary["can_review"]:
                raise Conflict("项目或原文当前受归档、批次撤销、审核结论或保留期限限制。")
            group_id = None
            if verified:
                metadata = safe_metadata(row["fields_json"])
                validate_snapshot(row, role, metadata, json.loads(row["content_json"]))
                group_id = dedupe_key(study_id, row["raw_text"], metadata) if role == "user_quote" else None
                db.execute(
                    """INSERT INTO corpus_snapshots (record_id, study_id, scope_id, raw_sha256, created_at)
                       VALUES (?, ?, ?, ?, ?) ON CONFLICT(record_id) DO NOTHING""",
                    (record_id, study_id, row["scope_id"], checksum(row["raw_text"]), at),
                )
            db.execute(
                """INSERT INTO corpus_reviews (record_id, decision, role, reason, basis, retention_until, dedupe_group, reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (record_id, *payload, group_id, at),
            )
            return self.describe(db, self.source_row(db, study_id, record_id, today), today)
