-- Reevaluate historical exclusion notes with the current withdrawal policy.
-- Keep all underlying rows, review IDs, and restored_withdrawal_id references.
DROP VIEW IF EXISTS corpus_withdrawals;
CREATE VIEW corpus_withdrawals AS
SELECT r.review_id, r.record_id, r.reviewed_at, b.study_id,
       source_identity(json_extract(i.fields_json, '$.source_url')) AS source
FROM corpus_reviews r JOIN import_rows i USING(record_id) JOIN import_batches b USING(batch_id)
LEFT JOIN corpus_licenses l USING(review_id)
WHERE r.decision='excluded'
  AND (l.state='revoked' OR source_permission_revoked(r.reason));

PRAGMA user_version=6;
