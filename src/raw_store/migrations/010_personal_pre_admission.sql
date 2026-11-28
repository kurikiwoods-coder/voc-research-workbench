CREATE TABLE personal_validation_batches (
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
    mode TEXT NOT NULL DEFAULT 'engineering_fixture' CHECK (mode = 'engineering_fixture'),
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
    CHECK (julianday(starts_at) IS NOT NULL AND julianday(expires_at) IS NOT NULL AND expires_at > starts_at)
) STRICT;

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

CREATE TABLE personal_validation_batch_events (
    sequence INTEGER PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES personal_validation_batches(batch_id),
    state TEXT NOT NULL CHECK (state IN ('draft', 'approved', 'executing', 'paused', 'revoked',
        'reconciliation', 'evidence_review', 'complete', 'blocked')),
    reason TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL
) STRICT;

CREATE INDEX personal_validation_batch_history ON personal_validation_batch_events(batch_id, sequence);

CREATE TABLE personal_validation_grants (
    grant_id TEXT PRIMARY KEY NOT NULL,
    batch_id TEXT NOT NULL REFERENCES personal_validation_batches(batch_id),
    operation TEXT NOT NULL CHECK (operation IN ('search', 'source', 'model')),
    slot INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 2 AND (operation = 'model' OR slot = 1)),
    provider TEXT NOT NULL,
    account_ref TEXT NOT NULL,
    channel_ref TEXT NOT NULL,
    credential_revision TEXT NOT NULL CHECK (length(credential_revision) > 0),
    model TEXT NOT NULL,
    approval_event_id TEXT REFERENCES personal_provider_approval_events(event_id),
    material_revision TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    question_version TEXT NOT NULL,
    depends_on TEXT REFERENCES personal_validation_requests(request_id),
    depends_on_sha256 TEXT,
    valid_from TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    created_after_sequence INTEGER NOT NULL CHECK (created_after_sequence >= 0),
    request_limit INTEGER NOT NULL CHECK (request_limit >= 0),
    credit_limit INTEGER NOT NULL CHECK (credit_limit >= 0),
    input_limit INTEGER NOT NULL CHECK (input_limit >= 0),
    output_limit INTEGER NOT NULL CHECK (output_limit >= 0),
    token_limit INTEGER NOT NULL CHECK (token_limit >= 0),
    cost_limit INTEGER NOT NULL CHECK (cost_limit >= 0),
    account_limits TEXT NOT NULL CHECK (json_valid(account_limits) AND json_type(account_limits) = 'array'),
    UNIQUE (batch_id, grant_id),
    CHECK (julianday(valid_from) IS NOT NULL AND julianday(expires_at) IS NOT NULL AND expires_at > valid_from),
    CHECK ((depends_on IS NULL) = (depends_on_sha256 IS NULL)),
    CHECK (operation <> 'model' OR approval_event_id IS NOT NULL),
    CHECK ((operation = 'search' AND provider = 'tavily' AND model = '')
        OR (operation = 'source' AND provider = 'stackexchange' AND model = '')
        OR (operation = 'model' AND provider = 'packycode' AND channel_ref = 'typesafe-officially'
            AND model = 'jev-1.14.0'))
) STRICT;

CREATE INDEX personal_validation_grant_account
ON personal_validation_grants(provider, account_ref, batch_id);

CREATE TABLE personal_validation_requests (
    request_id TEXT PRIMARY KEY NOT NULL,
    batch_id TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('search', 'source', 'model')),
    slot INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 2 AND (operation = 'model' OR slot = 1)),
    payload_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    requests INTEGER NOT NULL CHECK (requests = 1),
    credits INTEGER NOT NULL CHECK (credits >= 0),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    total_tokens INTEGER NOT NULL CHECK (total_tokens = input_tokens + output_tokens),
    units INTEGER NOT NULL CHECK (units >= 0),
    UNIQUE (batch_id, operation, slot),
    FOREIGN KEY (batch_id, grant_id) REFERENCES personal_validation_grants(batch_id, grant_id)
) STRICT;

CREATE TABLE personal_validation_request_events (
    sequence INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES personal_validation_requests(request_id),
    state TEXT NOT NULL CHECK (state IN ('reserved', 'claimed', 'released', 'reconciliation', 'settled')),
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL
) STRICT;

CREATE INDEX personal_validation_request_history ON personal_validation_request_events(request_id, sequence);
CREATE UNIQUE INDEX personal_validation_one_send ON personal_validation_request_events(request_id)
WHERE state = 'claimed';

CREATE TABLE personal_validation_receipts (
    request_id TEXT PRIMARY KEY NOT NULL REFERENCES personal_validation_requests(request_id),
    provider TEXT NOT NULL,
    account_ref TEXT NOT NULL,
    provider_request_id TEXT,
    model TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    response_sha256 TEXT NOT NULL,
    source_sha256 TEXT,
    quote_sha256 TEXT,
    response_status INTEGER CHECK (response_status BETWEEN 100 AND 599),
    credits INTEGER CHECK (credits >= 0),
    input_tokens INTEGER CHECK (input_tokens >= 0),
    output_tokens INTEGER CHECK (output_tokens >= 0),
    total_tokens INTEGER CHECK (total_tokens >= 0),
    estimated_units INTEGER NOT NULL CHECK (estimated_units >= 0),
    actual_units INTEGER CHECK (actual_units >= 0),
    balance_status TEXT NOT NULL CHECK (balance_status IN ('unsynced', 'verified', 'not_applicable')),
    evidence_ref TEXT NOT NULL,
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE (provider, account_ref, provider_request_id)
) STRICT;

CREATE TABLE personal_validation_reconciliations (
    sequence INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES personal_validation_requests(request_id),
    actual_units INTEGER NOT NULL CHECK (actual_units >= 0),
    subject_ref TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE (request_id, subject_ref)
) STRICT;

CREATE TABLE personal_validation_evidence (
    sequence INTEGER PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES personal_validation_batches(batch_id),
    requirement TEXT NOT NULL CHECK (requirement IN ('C0-1', 'C0-2', 'C0-3', 'C0-4', 'C0-5', 'C0-6')),
    kind TEXT NOT NULL CHECK (kind IN ('historical_review', 'synthetic_fixture', 'local_regression', 'missing')),
    evidence_ref TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    reason TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE (batch_id, requirement, kind, evidence_ref, evidence_sha256)
) STRICT;

CREATE TABLE personal_validation_authority (
    sequence INTEGER PRIMARY KEY,
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    revision TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('current', 'revoked', 'restore_hold')),
    evidence_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id)
) STRICT;

CREATE INDEX personal_validation_authority_history
ON personal_validation_authority(study_id, scope_id, subject, sequence);

CREATE TABLE personal_validation_credentials (
    sequence INTEGER PRIMARY KEY,
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    scope_version TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('search', 'source', 'model')),
    provider TEXT NOT NULL,
    account_ref TEXT NOT NULL,
    channel_ref TEXT NOT NULL,
    credential_revision TEXT CHECK (length(credential_revision) > 0),
    evidence_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id),
    CHECK ((operation = 'search' AND provider = 'tavily')
        OR (operation = 'source' AND provider = 'stackexchange')
        OR (operation = 'model' AND provider = 'packycode' AND channel_ref = 'typesafe-officially'))
) STRICT;

CREATE INDEX personal_validation_credential_history
ON personal_validation_credentials(study_id, scope_id, scope_version, operation, provider, sequence);

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

CREATE TRIGGER personal_validation_batch_events_retain_insert
BEFORE INSERT ON personal_validation_batch_events
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_batch_events WHERE sequence = NEW.sequence)
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_batch_events_retain_update
BEFORE UPDATE ON personal_validation_batch_events
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_batch_events_retain_delete
BEFORE DELETE ON personal_validation_batch_events
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_grants_retain_insert
BEFORE INSERT ON personal_validation_grants
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_grants WHERE grant_id = NEW.grant_id)
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_grants_retain_update
BEFORE UPDATE ON personal_validation_grants
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_grants_retain_delete
BEFORE DELETE ON personal_validation_grants
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_requests_retain_insert
BEFORE INSERT ON personal_validation_requests
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_requests WHERE request_id = NEW.request_id OR (batch_id = NEW.batch_id AND operation = NEW.operation AND slot = NEW.slot))
    OR NOT EXISTS (
        SELECT 1 FROM personal_validation_grants g WHERE g.grant_id=NEW.grant_id AND g.batch_id=NEW.batch_id
          AND g.operation=NEW.operation AND g.slot=NEW.slot AND g.payload_sha256=NEW.payload_sha256
    )
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_requests_retain_update
BEFORE UPDATE ON personal_validation_requests
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_requests_retain_delete
BEFORE DELETE ON personal_validation_requests
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_request_events_retain_insert
BEFORE INSERT ON personal_validation_request_events
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_request_events WHERE sequence = NEW.sequence OR (request_id = NEW.request_id AND state = 'claimed' AND NEW.state = 'claimed'))
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_request_events_retain_update
BEFORE UPDATE ON personal_validation_request_events
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_request_events_retain_delete
BEFORE DELETE ON personal_validation_request_events
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_receipts_retain_insert
BEFORE INSERT ON personal_validation_receipts
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_receipts WHERE request_id = NEW.request_id OR (provider = NEW.provider AND account_ref = NEW.account_ref AND provider_request_id = NEW.provider_request_id))
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_receipts_retain_update
BEFORE UPDATE ON personal_validation_receipts
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_receipts_retain_delete
BEFORE DELETE ON personal_validation_receipts
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_reconciliations_retain_insert
BEFORE INSERT ON personal_validation_reconciliations
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_reconciliations WHERE sequence = NEW.sequence OR (request_id = NEW.request_id AND subject_ref = NEW.subject_ref))
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_reconciliations_retain_update
BEFORE UPDATE ON personal_validation_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_reconciliations_retain_delete
BEFORE DELETE ON personal_validation_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_evidence_retain_insert
BEFORE INSERT ON personal_validation_evidence
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_evidence WHERE sequence = NEW.sequence OR (batch_id = NEW.batch_id AND requirement = NEW.requirement AND kind = NEW.kind AND evidence_ref = NEW.evidence_ref AND evidence_sha256 = NEW.evidence_sha256))
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

CREATE TRIGGER personal_validation_authority_retain_insert
BEFORE INSERT ON personal_validation_authority
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_authority WHERE sequence = NEW.sequence)
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_authority_retain_update
BEFORE UPDATE ON personal_validation_authority
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_authority_retain_delete
BEFORE DELETE ON personal_validation_authority
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_credentials_retain_insert
BEFORE INSERT ON personal_validation_credentials
WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
    OR EXISTS (SELECT 1 FROM personal_validation_credentials WHERE sequence = NEW.sequence)
    OR NOT EXISTS (
        SELECT 1 FROM study_scope_freezes f JOIN study_scopes s USING(study_id, scope_id)
        WHERE f.study_id=NEW.study_id AND f.scope_id=NEW.scope_id AND 'v' || s.version_no=NEW.scope_version
    )
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_credentials_retain_update
BEFORE UPDATE ON personal_validation_credentials
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

CREATE TRIGGER personal_validation_credentials_retain_delete
BEFORE DELETE ON personal_validation_credentials
BEGIN
    SELECT RAISE(ABORT, 'retained personal validation ledger');
END;

PRAGMA user_version=10;
