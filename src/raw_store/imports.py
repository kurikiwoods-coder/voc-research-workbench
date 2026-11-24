"""Local import drafts and batch receipts. Imported rows are staging, never published evidence."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

from src.raw_store.store import Conflict, dump, now
from src.raw_store.studies import StudyStore, scope_record, SCOPE_SELECT


FILE_COLUMNS = "file_id, study_id, scope_id, filename, kind, sha256, length(source_bytes) AS size, sheets_json, uploaded_at"
BATCH_SELECT = """SELECT b.*, f.filename, f.kind, f.sha256, length(f.source_bytes) AS size,
                         'v' || s.version_no AS scope_version, p.name AS project_name
    FROM import_batches b JOIN import_files f USING(file_id)
    JOIN study_scopes s ON s.study_id=b.study_id AND s.scope_id=b.scope_id
    JOIN study_projects p ON p.study_id=b.study_id"""
MAX_DRAFTS = 8


def source_withdrawal(record_id):
    return f"""EXISTS (
        SELECT 1 FROM corpus_reviews withdrawal WHERE withdrawal.record_id={record_id}
        AND withdrawal.decision='excluded' AND source_permission_revoked(withdrawal.reason)
    )"""


RESTRICTED_SOURCE_ROWS = f"""
    FROM import_files restricted_file
    JOIN import_batches restricted_batch ON restricted_batch.file_id=restricted_file.file_id
    JOIN import_rows restricted_row ON restricted_row.batch_id=restricted_batch.batch_id
    JOIN study_scopes restricted_scope ON restricted_scope.study_id=restricted_batch.study_id
        AND restricted_scope.scope_id=restricted_batch.scope_id
    JOIN corpus_reviews restricted_review ON restricted_review.review_id=(
        SELECT MAX(h.review_id) FROM corpus_reviews h WHERE h.record_id=restricted_row.record_id
    )
    WHERE (restricted_review.decision='excluded' OR restricted_review.retention_until<:today
           OR restricted_batch.revoked_at IS NOT NULL
           OR {source_withdrawal("restricted_row.record_id")}
           OR CASE WHEN restricted_review.decision='verified' THEN NOT valid_snapshot_source(
               restricted_row.privacy, restricted_row.raw_text, restricted_review.role,
               restricted_row.fields_json, restricted_scope.content_json
           ) ELSE 0 END)
"""


def decoded(row):
    return {key.removesuffix("_json"): json.loads(value) if key.endswith("_json") else value
            for key, value in dict(row).items()}


def batch_record(db, row):
    batch = decoded(row)
    batch.pop("signature")
    if restricted_source_lines(db, batch, batch["sheet_index"]):
        # Source type labels come from user-mapped cells and may contain original text.
        batch["summary"]["source_types"] = {}
    return {**batch, "status": "revoked" if batch["revoked_at"] else "imported", "research_eligible": False}


def restricted_source_lines(db, file, sheet_index):
    # A second import of the same bytes can have a different file ID or field mapping.
    rows = db.execute(f"""SELECT DISTINCT restricted_row.line_number {RESTRICTED_SOURCE_ROWS}
                          AND restricted_file.study_id=:study_id AND restricted_file.sha256=:sha256
                          AND restricted_batch.sheet_index=:sheet_index""",
                      {"study_id": file["study_id"], "sha256": file["sha256"],
                       "sheet_index": sheet_index, "today": now()[:10]})
    return {row["line_number"] for row in rows}


def check_sheet_access(db, file, sheet_index):
    if restricted_source_lines(db, file, sheet_index):
        raise Conflict("该工作表含受语料审核或保留条件限制的内容，请从批次历史查看可用记录。")


def visible_import_row(row, restricted_lines):
    record = decoded(row)
    if record["line_number"] in restricted_lines or record["duplicate_of_line"] in restricted_lines:
        record.update(raw_text=None, originals=[], fields={}, content_restricted=True)
    return record


class ImportStore:
    def __init__(self, store):
        if store.fixture or store.diagnostic:
            raise ValueError("研究导入只允许使用工作台主库")
        self.store = store

    @contextmanager
    def write(self):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    @staticmethod
    def target(db, study_id, scope_id):
        project = StudyStore.project_row(db, study_id)
        if project["status"] == "archived":
            raise Conflict("项目已归档。请恢复项目后再导入。")
        row = db.execute(SCOPE_SELECT + " WHERE s.study_id=? AND s.scope_id=?", (study_id, scope_id)).fetchone()
        if row is None:
            raise KeyError(scope_id)
        if not row["frozen_at"]:
            raise Conflict("请先在研究项目中冻结所选范围版本。")
        return scope_record(row)

    def check_target(self, study_id, scope_id):
        with self.store.db() as db:
            return self.target(db, study_id, scope_id)

    def upload(self, study_id, scope_id, filename, kind, data, sheets):
        digest = hashlib.sha256(data).hexdigest()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="milliseconds")
        with self.write() as db:
            self.target(db, study_id, scope_id)
            db.execute("""DELETE FROM import_files WHERE uploaded_at < ?
                       AND NOT EXISTS (SELECT 1 FROM import_batches b WHERE b.file_id=import_files.file_id)""", (cutoff,))
            row = db.execute(f"""SELECT {FILE_COLUMNS} FROM import_files
                             WHERE study_id=? AND scope_id=? AND sha256=? AND filename=?""",
                             (study_id, scope_id, digest, filename)).fetchone()
            if row:
                return decoded(row)
            drafts = db.execute("""SELECT COUNT(*) FROM import_files f
                                   WHERE NOT EXISTS (SELECT 1 FROM import_batches b WHERE b.file_id=f.file_id)""").fetchone()[0]
            if drafts >= MAX_DRAFTS:
                raise Conflict("待导入文件已达到 8 个。请在导入首页丢弃不再需要的文件或继续已有导入。")
            file_id = str(uuid4())
            db.execute("""INSERT INTO import_files
                       (file_id, study_id, scope_id, filename, kind, sha256, source_bytes, sheets_json, uploaded_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (file_id, study_id, scope_id, filename, kind, digest, data, dump(sheets), now()))
            return decoded(db.execute(f"SELECT {FILE_COLUMNS} FROM import_files WHERE file_id=?", (file_id,)).fetchone())

    def get_file(self, study_id, file_id, sheet_index):
        with self.store.db() as db:
            db.execute("BEGIN")
            row = db.execute(f"SELECT {FILE_COLUMNS} FROM import_files WHERE study_id=? AND file_id=?",
                             (study_id, file_id)).fetchone()
            if row is None:
                raise KeyError(file_id)
            result = decoded(row)
            target = self.target(db, study_id, result["scope_id"])
            check_sheet_access(db, result, sheet_index)
            result["source_bytes"] = db.execute("SELECT source_bytes FROM import_files WHERE file_id=?",
                                                (file_id,)).fetchone()["source_bytes"]
            return result, target

    def confirmation_receipt(self, study_id, file_id, sheet_index, mapping, privacy, signature):
        with self.store.db() as db:
            db.execute("BEGIN")
            row = db.execute(BATCH_SELECT + """
                JOIN import_files requested ON requested.study_id=b.study_id
                    AND requested.scope_id=b.scope_id AND requested.sha256=f.sha256
                WHERE requested.study_id=? AND requested.file_id=? AND b.sheet_index=?
                    AND b.mapping_json=? AND b.privacy=? AND b.signature=?""",
                (study_id, file_id, sheet_index, dump(mapping), privacy, signature)).fetchone()
            if row is None:
                return None
            self.target(db, study_id, row["scope_id"])
            return batch_record(db, row)

    def discard(self, study_id, file_id):
        with self.write() as db:
            attached = db.execute("SELECT 1 FROM import_batches WHERE study_id=? AND file_id=?",
                                  (study_id, file_id)).fetchone()
            if attached:
                raise Conflict("该文件已归入批次，可通过撤销批次停止后续使用。")
            db.execute("DELETE FROM import_files WHERE study_id=? AND file_id=?", (study_id, file_id))

    @staticmethod
    def saved_batch(db, study_id, batch_id):
        row = db.execute(BATCH_SELECT + " WHERE b.study_id=? AND b.batch_id=?", (study_id, batch_id)).fetchone()
        if row is None:
            raise KeyError(batch_id)
        return batch_record(db, row)

    def commit(self, file, sheet, index, mapping, privacy, signature, rows, summary):
        study_id, scope_id, file_id = (file[field] for field in ("study_id", "scope_id", "file_id"))
        with self.write() as db:
            self.target(db, study_id, scope_id)
            if not db.execute("SELECT 1 FROM import_files WHERE study_id=? AND file_id=?",
                              (study_id, file_id)).fetchone():
                raise KeyError(file_id)
            previous = db.execute("""SELECT batch_id FROM import_batches
                                     WHERE study_id=? AND scope_id=? AND signature=?""",
                                  (study_id, scope_id, signature)).fetchone()
            if previous:
                return self.saved_batch(db, study_id, previous["batch_id"])
            check_sheet_access(db, file, index)
            ident = str(uuid4())
            db.execute("""INSERT INTO import_batches
                       (batch_id, study_id, scope_id, file_id, sheet_index, sheet_name, header_line, headers_json,
                        mapping_json, privacy, signature, summary_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (ident, study_id, scope_id, file_id, index, sheet.name, sheet.header_line, dump(sheet.columns),
                        dump(mapping), privacy, signature, dump(summary), now()))
            db.executemany("""INSERT INTO import_rows
                           (record_id, batch_id, line_number, raw_text, originals_json, fields_json, status,
                            privacy, text_fingerprint, duplicate_of_line, issues_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          ((f"{ident}:{row['line_number']}", ident, row["line_number"], row["raw_text"],
                            dump(row["original_fields"]), dump(row["fields"]), row["status"], row["privacy"],
                            row["text_fingerprint"], row["duplicate_of_line"], dump(row["issues"])) for row in rows))
            return self.saved_batch(db, study_id, ident)

    def history(self, study_id, offset):
        with self.store.db() as db:
            db.execute("BEGIN")
            StudyStore.project_row(db, study_id)
            rows = db.execute(BATCH_SELECT + """ WHERE b.study_id=?
                              ORDER BY b.created_at DESC, b.rowid DESC LIMIT 21 OFFSET ?""", (study_id, offset)).fetchall()
            drafts = db.execute("""SELECT f.file_id, f.scope_id, f.filename, f.sheets_json, f.uploaded_at,
                                      'v' || s.version_no AS scope_version FROM import_files f JOIN study_scopes s
                                   ON s.study_id=f.study_id AND s.scope_id=f.scope_id
                                   WHERE f.study_id=? AND NOT EXISTS
                                      (SELECT 1 FROM import_batches b WHERE b.file_id=f.file_id)
                                   ORDER BY f.uploaded_at DESC""", (study_id,))
            return {"batches": [batch_record(db, row) for row in rows[:20]],
                    "more": len(rows) > 20, "drafts": [decoded(row) for row in drafts]}

    def get_batch(self, study_id, batch_id, status, offset):
        with self.store.db() as db:
            db.execute("BEGIN")
            batch = self.saved_batch(db, study_id, batch_id)
            rows = db.execute("""SELECT record_id, line_number, raw_text, originals_json, fields_json, status,
                                        privacy, duplicate_of_line, issues_json FROM import_rows
                                 WHERE batch_id=? AND (?='all' OR status=?)
                                 ORDER BY line_number LIMIT 21 OFFSET ?""", (batch_id, status, status, offset)).fetchall()
            restricted = restricted_source_lines(db, batch, batch["sheet_index"])
            return {"batch": batch, "rows": [visible_import_row(row, restricted) for row in rows[:20]],
                    "more": len(rows) > 20}

    def report(self, study_id, batch_id):
        with self.store.db() as db:
            batch = self.saved_batch(db, study_id, batch_id)
            issues = db.execute("""SELECT line_number, status, duplicate_of_line, issues_json FROM import_rows
                                   WHERE batch_id=? AND issues_json<>'[]' ORDER BY line_number""", (batch_id,))
            return batch, [decoded(row) for row in issues]

    def revoke(self, study_id, batch_id):
        with self.write() as db:
            batch = self.saved_batch(db, study_id, batch_id)
            if not batch["revoked_at"]:
                db.execute("UPDATE import_batches SET revoked_at=? WHERE batch_id=?", (now(), batch_id))
            return self.saved_batch(db, study_id, batch_id)
