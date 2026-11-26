CREATE TABLE personal_validation_batches_v11 (
    batch_id TEXT PRIMARY KEY NOT NULL,
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    scope_version TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    owner_ref TEXT NOT NULL,
    authorization_ref TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    edition TEXT NOT NULL DEFAULT 'PERSONAL' CHECK (edition = 'PERSONAL'),
    gate_id TEXT NOT NULL DEFAULT 'G-1-PERSONAL' CHECK (gate_id = 'G-1-PERSONAL'),
    purpose TEXT NOT NULL DEFAULT 'g1_personal_acceptance' CHECK (purpose = 'g1_personal_acceptance'),
    mode TEXT NOT NULL DEFAULT 'engineering_fixture' CHECK (mode IN ('engineering_fixture', 'formal_live')),
    starts_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    request_limit INTEGER NOT NULL CHECK (request_limit >= 0),
    credit_limit INTEGER NOT NULL CHECK (credit_limit >= 0),
    input_limit INTEGER NOT NULL CHECK (input_limit >= 0),
    output_limit INTEGER NOT NULL CHECK (output_limit >= 0),
    token_limit INTEGER NOT NULL CHECK (token_limit >= 0),
    cost_limit INTEGER NOT NULL CHECK (cost_limit >= 0),
    single_cost INTEGER NOT NULL CHECK (single_cost BETWEEN 0 AND cost_limit),
    currency TEXT NOT NULL CHECK (currency GLOB '[A-Z][A-Z][A-Z]'),
    decimals INTEGER NOT NULL CHECK (decimals BETWEEN 0 AND 9),
    evidence_ref TEXT NOT NULL CHECK (length(evidence_ref) > 0),
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id),
    CHECK (julianday(starts_at) IS NOT NULL AND julianday(expires_at) IS NOT NULL AND expires_at > starts_at),
    CHECK (mode <> 'formal_live' OR request_limit BETWEEN 1 AND 4)
) STRICT;

INSERT INTO personal_validation_batches_v11 (
    batch_id, study_id, scope_id, scope_version, actor_ref, owner_ref, authorization_ref, policy_version,
    edition, gate_id, purpose, mode, starts_at, expires_at, created_at, request_limit, credit_limit, input_limit,
    output_limit, token_limit, cost_limit, single_cost, currency, decimals, evidence_ref
)
SELECT batch_id, study_id, scope_id, scope_version, actor_ref, owner_ref, authorization_ref, policy_version,
       edition, gate_id, purpose, mode, starts_at, expires_at, created_at, request_limit, credit_limit, input_limit,
       output_limit, token_limit, cost_limit, single_cost, currency, decimals, evidence_ref
FROM personal_validation_batches;

DROP TABLE personal_validation_batches;
ALTER TABLE personal_validation_batches_v11 RENAME TO personal_validation_batches;

CREATE TRIGGER personal_validation_batches_validate
BEFORE INSERT ON personal_validation_batches
BEGIN
    SELECT CASE
      WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
        THEN RAISE(ABORT, 'validation requires a personal workspace')
      WHEN EXISTS (SELECT 1 FROM personal_validation_batches WHERE batch_id = NEW.batch_id)
        THEN RAISE(ABORT, 'retained validation batch')
      WHEN NOT EXISTS (
        SELECT 1 FROM study_scope_freezes f
        JOIN study_scopes s USING(study_id, scope_id)
        WHERE f.study_id = NEW.study_id AND f.scope_id = NEW.scope_id
          AND 'v' || s.version_no = NEW.scope_version
      ) THEN RAISE(ABORT, 'validation frozen scope mismatch')
    END;
END;

CREATE TRIGGER personal_validation_batches_retain_update
BEFORE UPDATE ON personal_validation_batches
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_batches_retain_delete
BEFORE DELETE ON personal_validation_batches
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TABLE personal_validation_evidence_v11 (
    sequence INTEGER PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES personal_validation_batches(batch_id),
    requirement TEXT NOT NULL CHECK (requirement IN ('C0-1', 'C0-2', 'C0-3', 'C0-4', 'C0-5', 'C0-6')),
    kind TEXT NOT NULL CHECK (kind IN (
        'historical_review', 'synthetic_fixture', 'local_regression', 'missing', 'formal_live', 'formal_offline'
    )),
    evidence_ref TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    reason TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE (batch_id, requirement, kind, evidence_ref, evidence_sha256),
    CHECK (kind <> 'formal_live' OR requirement IN ('C0-1', 'C0-2', 'C0-3', 'C0-4')),
    CHECK (kind <> 'formal_offline' OR requirement IN ('C0-5', 'C0-6'))
) STRICT;

INSERT INTO personal_validation_evidence_v11 (
    sequence, batch_id, requirement, kind, evidence_ref, evidence_sha256, reason, actor_ref, occurred_at
)
SELECT sequence, batch_id, requirement, kind, evidence_ref, evidence_sha256, reason, actor_ref, occurred_at
FROM personal_validation_evidence;

DROP TABLE personal_validation_evidence;
ALTER TABLE personal_validation_evidence_v11 RENAME TO personal_validation_evidence;

CREATE TRIGGER personal_validation_evidence_retain_insert
BEFORE INSERT ON personal_validation_evidence
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (
        SELECT 1 FROM personal_validation_evidence
        WHERE sequence = NEW.sequence OR
            (batch_id = NEW.batch_id AND requirement = NEW.requirement AND kind = NEW.kind
             AND evidence_ref = NEW.evidence_ref AND evidence_sha256 = NEW.evidence_sha256)
    )
    OR (NEW.kind IN ('formal_live', 'formal_offline') AND NOT EXISTS (
        SELECT 1 FROM personal_validation_batches WHERE batch_id = NEW.batch_id AND mode = 'formal_live'
    ))
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_evidence_retain_update
BEFORE UPDATE ON personal_validation_evidence
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_evidence_retain_delete
BEFORE DELETE ON personal_validation_evidence
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

PRAGMA user_version=11;
