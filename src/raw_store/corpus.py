"""Local review and replay of immutable M04 import records."""

from datetime import date
import hashlib
import json
from unicodedata import normalize

from src.raw_store.corpus_access import (
    CANDIDATE, ROW_COLUMNS, ROW_SOURCE, qualification, record_summary, withdrawal_match,
)
from src.raw_store.corpus_policy import (
    CONTROL, LICENSE_STATES, SENSITIVE, evidence_identity, legacy_evidence_identities, license_note_state,
    safe_metadata, source_identity, source_permission_revoked, validate_snapshot,
)
from src.raw_store.store import Conflict, dump, now
from src.raw_store.studies import StudyStore


PAGE_SIZE = 20
ROLES = {"user_quote", "background", "internal", "synthetic"}


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


def dedupe_key(study_id, text, metadata):
    quote = " ".join(normalize("NFC", text).split())
    if len(quote) >= 24:
        # Match exact, substantial quotes across sources. A short reply needs a shared source identity.
        return checksum(dump([study_id, "public", "user_quote", quote]))
    if metadata.get("external_id"):
        return checksum(dump([study_id, "public", "user_quote", quote, metadata["source_url"], metadata["external_id"]]))
    return None


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
            f"""SELECT {ROW_COLUMNS}, r.originals_json, r.issues_json, r.status AS import_status,
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
            f"""SELECT {ROW_COLUMNS} {ROW_SOURCE}
                WHERE b.study_id=:study_id AND v.dedupe_group=:dedupe_group
                    AND v.decision='verified' AND v.role='user_quote'
                ORDER BY snap.created_at, snap.record_id""",
            {"study_id": row["study_id"], "dedupe_group": row["dedupe_group"], "today": today},
        )
        members = [entry["record_id"] for entry in group if qualification(entry, today)["engineering_eligible"]]
        if not members:
            return None
        return {"group_id": row["dedupe_group"], "canonical_record_id": members[0],
                "record_count": len(members), "is_duplicate": members[0] != row["record_id"]}

    def describe(self, db, row, today):
        summary = record_summary(row, today)
        visible = summary["status"] == "verified"
        metadata = safe_metadata(row["fields_json"]) if visible else {}
        trace = {key_: row[key_] for key_ in (
            "batch_id", "study_id", "scope_id", "scope_version", "file_id", "filename",
            "file_sha256", "sheet_name", "line_number", "collected_at",
        )}
        trace.update({"time_window": json.loads(row["content_json"])["date_window"],
                      "extraction_method": "csv_upload" if row["kind"] == "csv" else "manual_import",
                      "extraction_rule": "按导入字段映射保存原单元格文本", "query_terms": None})
        history = [dict(event) for event in db.execute(
            """SELECT r.decision, r.role, r.reason, r.basis, r.retention_until, r.reviewed_at,
                      l.state AS license_status, l.evidence_ref, l.issued_on, l.restored_withdrawal_id
               FROM corpus_reviews r LEFT JOIN corpus_licenses l USING(review_id)
               WHERE r.record_id=? ORDER BY r.review_id DESC LIMIT 20""",
            (row["record_id"],),
        )]
        if not visible:
            # Source cells and free-form notes may repeat an original or a partial quote.
            for event in history:
                event.update(reason=None, basis=None, evidence_ref=None)
        return {**summary, "raw_text": row["raw_text"] if visible else None,
                "raw_sha256": row["raw_sha256"] if visible else None,
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

    def qualified_record(self, study_id, record_id):
        with self.store.db() as db:
            db.execute("BEGIN")
            today = now()[:10]
            row = self.source_row(db, study_id, record_id, today)
            if not qualification(row, today)["engineering_eligible"]:
                raise Conflict("这条语料当前不符合本机原话处理资格。")
            record = self.describe(db, row, today)
            return {name: record[name] for name in (
                "record_id", "trace", "raw_text", "raw_sha256", "metadata", "duplicate", "status", "license_status",
                "privacy", "role", "retention_until", "engineering_eligible", "research_eligible", "outbound_allowed",
            )}

    @staticmethod
    def restoration_proof(db, row, evidence_ref, issued_on, today):
        withdrawal = db.execute(
            "SELECT reviewed_at FROM corpus_withdrawals WHERE review_id=?", (row["withdrawal_id"],),
        ).fetchone()
        if withdrawal is None:
            raise ValueError("当前记录没有可恢复的许可撤销。")
        if not issued_on or not withdrawal["reviewed_at"][:10] <= issued_on <= today:
            raise ValueError("请登记撤销当天或之后签发的新授权证据日期。")
        prior = db.execute(
            f"""SELECT l.evidence_ref, v.basis
                FROM corpus_reviews v LEFT JOIN corpus_licenses l USING(review_id)
                JOIN import_rows r USING(record_id) JOIN import_batches b USING(batch_id)
                WHERE b.study_id=:study_id AND v.review_id<=:withdrawal_id AND v.decision='verified'
                AND (v.record_id=:record_id OR EXISTS (
                    SELECT 1 FROM corpus_withdrawals w
                    WHERE {withdrawal_match("b.study_id", "v.record_id", "r.originals_json")}
                      AND w.review_id=:withdrawal_id
                ))""",
            {"study_id": row["study_id"], "record_id": row["record_id"], "withdrawal_id": row["withdrawal_id"]},
        )
        replacement = evidence_identity(evidence_ref)
        for event in prior:
            old = ({evidence_identity(event["evidence_ref"])} if event["evidence_ref"]
                   else legacy_evidence_identities(event["basis"]))
            if replacement in old:
                raise ValueError("撤销前的授权证据不可复用，请登记新的许可。")
        return row["withdrawal_id"]

    def review(self, study_id, record_id, decision, role, reason, basis="", retention_until=None,
               license_status=None, license_evidence_ref=None, license_issued_on=None, reauthorize=False):
        if decision not in {"verified", "excluded"} or role not in ROLES:
            raise ValueError("核验处理和内容角色无效。")
        verified = decision == "verified"
        reason = require_review_text(reason, "处理原因", 500, required=True)
        basis = require_review_text(basis, "核验依据", 1000, required=verified)
        # Recognize a withdrawal in an older client or an explicit exclusion note.
        if not verified and source_permission_revoked(reason):
            license_status = "revoked"
        if license_status is None:
            license_status = "unknown"
        if license_status not in LICENSE_STATES or (not verified and license_status == "authorized"):
            raise ValueError("审核结论与许可状态不一致。")
        if not verified and (license_evidence_ref is not None or license_issued_on is not None or reauthorize):
            raise ValueError("新授权证据只能与核验通过一同登记。")

        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            at = now()
            today = at[:10]
            retention_until = review_retention(retention_until, today, required=verified)
            row = self.source_row(db, study_id, record_id, today)
            access = qualification(row, today)
            previous = db.execute(
                """SELECT r.decision, r.role, r.reason, r.basis, r.retention_until,
                          l.state, l.evidence_ref, l.issued_on, l.restored_withdrawal_id
                   FROM corpus_reviews r LEFT JOIN corpus_licenses l USING(review_id)
                   WHERE r.record_id=? ORDER BY r.review_id DESC LIMIT 1""",
                (record_id,),
            ).fetchone()
            payload = (decision, role, reason, basis, retention_until)
            if verified and not reauthorize and row["restored_withdrawal_id"] and not access["source_permission_revoked"]:
                if evidence_identity(license_evidence_ref) != evidence_identity(row["evidence_ref"]):
                    raise ValueError("更换已恢复的授权证据时，请重新执行新授权复核。")
                if license_issued_on not in (None, row["issued_on"]):
                    raise ValueError("新授权证据签发日期须与既有材料一致。")
                license_issued_on = row["issued_on"]
            grant = (license_status, license_evidence_ref, license_issued_on)
            if previous and tuple(previous)[:8] == payload + grant and (
                (not verified and license_status == "revoked") or (
                    access["can_review"] and (not reauthorize or previous["restored_withdrawal_id"] is not None)
                )
            ):
                return self.describe(db, row, today)
            if not access["can_review"] and not (access["can_reauthorize"] and verified and reauthorize):
                raise Conflict("项目或原文当前受归档、批次撤销、审核结论或保留期限限制。")

            group_id = None
            restored = row["restored_withdrawal_id"] if verified else None
            if verified:
                metadata = safe_metadata(row["fields_json"])
                evidence_key = evidence_identity(license_evidence_ref)
                if license_status != "authorized" or evidence_key is None:
                    raise ValueError("请确认许可已授权，并填写可追溯的授权材料链接或本机材料编号。")
                if evidence_key == source_identity(metadata.get("source_url")):
                    raise ValueError("原文地址只能证明来源，请另行登记许可依据。")
                if license_issued_on and license_issued_on > today:
                    raise ValueError("授权证据签发日期不能晚于当前 UTC 日期。")
                declared = license_note_state(json.loads(row["fields_json"]).get("access_policy", ""))
                if reauthorize:
                    restored = self.restoration_proof(db, row, license_evidence_ref, license_issued_on, today)
                elif not restored and declared != "unknown":
                    raise ValueError("来源记录或核验说明包含未确认、无授权、过期或撤销信息，请先核对许可。")
                if any(license_note_state(note) != "unknown" for note in (reason, basis)):
                    raise ValueError("核验原因和依据须说明当前有效的授权。")
                if (not reauthorize and row["license_state"] == "authorized" and row["retention_until"]
                        and retention_until > row["retention_until"] and evidence_key == evidence_identity(row["evidence_ref"])):
                    raise ValueError("延长保留期限须登记新的授权依据。")
                validate_snapshot(row, role, metadata, json.loads(row["content_json"]))
                group_id = dedupe_key(study_id, row["raw_text"], metadata) if role == "user_quote" else None
                db.execute(
                    """INSERT INTO corpus_snapshots (record_id, study_id, scope_id, raw_sha256, created_at)
                       VALUES (?, ?, ?, ?, ?) ON CONFLICT(record_id) DO NOTHING""",
                    (record_id, study_id, row["scope_id"], checksum(row["raw_text"]), at),
                )
            review_id = db.execute(
                """INSERT INTO corpus_reviews (record_id, decision, role, reason, basis, retention_until, dedupe_group, reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (record_id, *payload, group_id, at),
            ).lastrowid
            db.execute("INSERT INTO corpus_licenses VALUES (?, ?, ?, ?, ?)", (review_id, *grant, restored))
            return self.describe(db, self.source_row(db, study_id, record_id, today), today)
