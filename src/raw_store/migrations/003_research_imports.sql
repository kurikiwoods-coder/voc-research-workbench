CREATE TABLE IF NOT EXISTS import_files (
    file_id TEXT PRIMARY KEY NOT NULL,
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('csv', 'xlsx')),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    source_bytes BLOB NOT NULL CHECK (length(source_bytes) BETWEEN 1 AND 8388608),
    sheets_json TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id),
    UNIQUE (study_id, scope_id, sha256, filename),
    UNIQUE (study_id, scope_id, file_id)
);

CREATE TABLE IF NOT EXISTS import_batches (
    batch_id TEXT PRIMARY KEY NOT NULL,
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    sheet_index INTEGER NOT NULL CHECK (sheet_index >= 0),
    sheet_name TEXT NOT NULL,
    header_line INTEGER NOT NULL CHECK (header_line > 0),
    headers_json TEXT NOT NULL,
    mapping_json TEXT NOT NULL,
    privacy TEXT NOT NULL CHECK (privacy IN ('unknown', 'public', 'private', 'internal')),
    signature TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (study_id, scope_id, file_id) REFERENCES import_files(study_id, scope_id, file_id),
    UNIQUE (study_id, scope_id, signature)
);

CREATE TABLE IF NOT EXISTS import_rows (
    record_id TEXT PRIMARY KEY NOT NULL,
    batch_id TEXT NOT NULL REFERENCES import_batches(batch_id),
    line_number INTEGER NOT NULL CHECK (line_number > 0),
    raw_text TEXT NOT NULL,
    originals_json TEXT NOT NULL,
    fields_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('staged', 'pending_review', 'duplicate', 'rejected')),
    privacy TEXT NOT NULL CHECK (privacy IN ('unknown', 'public', 'private', 'internal')),
    text_fingerprint TEXT,
    duplicate_of_line INTEGER,
    issues_json TEXT NOT NULL,
    UNIQUE (batch_id, line_number),
    CHECK ((status = 'duplicate' AND duplicate_of_line IS NOT NULL AND duplicate_of_line > 0 AND duplicate_of_line < line_number)
           OR (status <> 'duplicate' AND duplicate_of_line IS NULL))
);

CREATE INDEX IF NOT EXISTS import_batches_by_study ON import_batches(study_id, created_at DESC);
CREATE INDEX IF NOT EXISTS import_batches_by_file ON import_batches(file_id);

CREATE TRIGGER IF NOT EXISTS immutable_import_file BEFORE UPDATE ON import_files
BEGIN SELECT RAISE(ABORT, 'immutable import file'); END;
CREATE TRIGGER IF NOT EXISTS immutable_import_row_update BEFORE UPDATE ON import_rows
BEGIN SELECT RAISE(ABORT, 'immutable import row'); END;
CREATE TRIGGER IF NOT EXISTS immutable_import_row_delete BEFORE DELETE ON import_rows
BEGIN SELECT RAISE(ABORT, 'immutable import row'); END;

CREATE VIEW IF NOT EXISTS import_candidates AS
    SELECT r.*, b.study_id, b.scope_id, 'v' || s.version_no AS scope_version, b.sheet_name,
           b.file_id, b.created_at AS collected_at, 0 AS research_eligible, 0 AS outbound_allowed
    FROM import_rows r JOIN import_batches b USING(batch_id)
    JOIN study_scopes s ON s.study_id=b.study_id AND s.scope_id=b.scope_id
    WHERE b.revoked_at IS NULL AND r.status IN ('staged', 'pending_review');

PRAGMA user_version=3;
