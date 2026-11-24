CREATE TABLE IF NOT EXISTS corpus_snapshots (
    record_id TEXT PRIMARY KEY NOT NULL REFERENCES import_rows(record_id),
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL CHECK (length(raw_sha256) = 64),
    created_at TEXT NOT NULL,
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id)
);

CREATE TABLE IF NOT EXISTS corpus_reviews (
    review_id INTEGER PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES import_rows(record_id),
    decision TEXT NOT NULL CHECK (decision IN ('verified', 'excluded')),
    role TEXT NOT NULL CHECK (role IN ('user_quote', 'background', 'internal', 'synthetic')),
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    basis TEXT NOT NULL CHECK (length(basis) <= 1000),
    retention_until TEXT,
    dedupe_group TEXT,
    reviewed_at TEXT NOT NULL,
    CHECK (decision <> 'verified' OR (length(basis) > 0 AND retention_until IS NOT NULL)),
    CHECK (dedupe_group IS NULL OR (decision = 'verified' AND role = 'user_quote'))
);

CREATE INDEX IF NOT EXISTS corpus_review_history ON corpus_reviews(record_id, review_id DESC);
CREATE INDEX IF NOT EXISTS corpus_review_groups ON corpus_reviews(dedupe_group) WHERE dedupe_group IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS corpus_snapshot_source BEFORE INSERT ON corpus_snapshots
WHEN NOT EXISTS (
    SELECT 1 FROM import_candidates c WHERE c.record_id = NEW.record_id
        AND c.study_id = NEW.study_id AND c.scope_id = NEW.scope_id
)
BEGIN SELECT RAISE(ABORT, 'invalid corpus snapshot source'); END;

CREATE TRIGGER IF NOT EXISTS immutable_corpus_source_receipt
BEFORE UPDATE OF batch_id, study_id, scope_id, file_id, sheet_index, sheet_name, header_line,
    headers_json, mapping_json, privacy, signature, summary_json, created_at ON import_batches
WHEN EXISTS (
    SELECT 1 FROM import_rows r JOIN corpus_snapshots s ON s.record_id = r.record_id
    WHERE r.batch_id = OLD.batch_id
)
BEGIN SELECT RAISE(ABORT, 'immutable corpus source receipt'); END;

CREATE TRIGGER IF NOT EXISTS corpus_review_source BEFORE INSERT ON corpus_reviews
WHEN NOT EXISTS (SELECT 1 FROM import_candidates c WHERE c.record_id = NEW.record_id)
    OR (NEW.decision = 'verified' AND NOT EXISTS (
        SELECT 1 FROM corpus_snapshots s WHERE s.record_id = NEW.record_id))
BEGIN SELECT RAISE(ABORT, 'invalid corpus review source'); END;

CREATE TRIGGER IF NOT EXISTS immutable_corpus_snapshot_update BEFORE UPDATE ON corpus_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable corpus snapshot'); END;
CREATE TRIGGER IF NOT EXISTS immutable_corpus_snapshot_delete BEFORE DELETE ON corpus_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable corpus snapshot'); END;
CREATE TRIGGER IF NOT EXISTS immutable_corpus_review_update BEFORE UPDATE ON corpus_reviews
BEGIN SELECT RAISE(ABORT, 'immutable corpus review'); END;
CREATE TRIGGER IF NOT EXISTS immutable_corpus_review_delete BEFORE DELETE ON corpus_reviews
BEGIN SELECT RAISE(ABORT, 'immutable corpus review'); END;

PRAGMA user_version=4;
