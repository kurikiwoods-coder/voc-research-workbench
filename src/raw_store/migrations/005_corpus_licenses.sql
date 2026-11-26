CREATE TABLE IF NOT EXISTS corpus_licenses (
    review_id INTEGER PRIMARY KEY REFERENCES corpus_reviews(review_id),
    state TEXT NOT NULL CHECK (state IN ('authorized', 'pending', 'denied', 'revoked', 'expired', 'unknown')),
    evidence_ref TEXT,
    issued_on TEXT,
    restored_withdrawal_id INTEGER REFERENCES corpus_reviews(review_id),
    CHECK ((state = 'authorized' AND evidence_ref IS NOT NULL AND length(evidence_ref) BETWEEN 1 AND 500)
        OR (state <> 'authorized' AND evidence_ref IS NULL AND issued_on IS NULL AND restored_withdrawal_id IS NULL)),
    CHECK (restored_withdrawal_id IS NULL OR (issued_on IS NOT NULL AND restored_withdrawal_id < review_id))
);

CREATE TRIGGER IF NOT EXISTS corpus_license_review BEFORE INSERT ON corpus_licenses
WHEN NOT EXISTS (
    SELECT 1 FROM corpus_reviews r WHERE r.review_id=NEW.review_id
    AND r.decision=CASE WHEN NEW.state='authorized' THEN 'verified' ELSE 'excluded' END
)
BEGIN SELECT RAISE(ABORT, 'invalid corpus license review'); END;

CREATE TRIGGER IF NOT EXISTS immutable_corpus_license_update BEFORE UPDATE ON corpus_licenses
BEGIN SELECT RAISE(ABORT, 'immutable corpus license'); END;

CREATE TRIGGER IF NOT EXISTS immutable_corpus_license_delete BEFORE DELETE ON corpus_licenses
BEGIN SELECT RAISE(ABORT, 'immutable corpus license'); END;

-- Keep the legacy negative signal, but never infer an affirmative grant from historical notes.
CREATE VIEW IF NOT EXISTS corpus_withdrawals AS
SELECT r.review_id, r.record_id, r.reviewed_at, b.study_id,
       source_identity(json_extract(i.fields_json, '$.source_url')) AS source
FROM corpus_reviews r JOIN import_rows i USING(record_id) JOIN import_batches b USING(batch_id)
LEFT JOIN corpus_licenses l USING(review_id)
WHERE r.decision='excluded'
  AND (l.state='revoked' OR (l.review_id IS NULL AND source_permission_revoked(r.reason)));

-- The staging view still supplies the identities required by the existing audit triggers.
-- Text and user-mapped cells are served only by the current eligibility service.
DROP VIEW IF EXISTS import_candidates;
CREATE VIEW import_candidates AS
    SELECT r.record_id, r.batch_id, r.line_number, r.status, r.privacy, r.duplicate_of_line, r.issues_json,
           NULL AS raw_text, '[]' AS originals_json, '{}' AS fields_json, NULL AS text_fingerprint,
           b.study_id, b.scope_id, 'v' || s.version_no AS scope_version, b.sheet_name,
           b.file_id, b.created_at AS collected_at, 0 AS research_eligible, 0 AS outbound_allowed
    FROM import_rows r JOIN import_batches b USING(batch_id)
    JOIN study_scopes s ON s.study_id=b.study_id AND s.scope_id=b.scope_id
    WHERE b.revoked_at IS NULL AND r.status IN ('staged', 'pending_review');

PRAGMA user_version=5;
