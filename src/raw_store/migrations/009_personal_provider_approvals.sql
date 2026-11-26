CREATE TABLE personal_provider_approval_events (
    event_id TEXT PRIMARY KEY NOT NULL CHECK(length(trim(event_id)) > 0),
    kind TEXT NOT NULL CHECK(kind IN ('submitted', 'approved', 'revoked')),
    prior_event_id TEXT UNIQUE REFERENCES personal_provider_approval_events(event_id),
    edition TEXT NOT NULL CHECK(edition = 'PERSONAL'),
    study_id TEXT NOT NULL REFERENCES study_projects(study_id),
    scope_id TEXT NOT NULL,
    scope_version TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK(length(trim(purpose)) > 0),
    provider TEXT NOT NULL CHECK(length(trim(provider)) > 0),
    channel_ref TEXT NOT NULL CHECK(length(trim(channel_ref)) > 0),
    model TEXT NOT NULL CHECK(length(trim(model)) > 0),
    account_ref TEXT NOT NULL CHECK(length(trim(account_ref)) > 0),
    credential_revision TEXT NOT NULL CHECK(length(trim(credential_revision)) > 0),
    policy_version TEXT NOT NULL CHECK(length(trim(policy_version)) > 0),
    actor_ref TEXT NOT NULL CHECK(length(trim(actor_ref)) > 0),
    owner_ref TEXT NOT NULL CHECK(length(trim(owner_ref)) > 0),
    authorization_ref TEXT NOT NULL CHECK(length(trim(authorization_ref)) > 0),
    effective_at TEXT NOT NULL CHECK(julianday(effective_at) IS NOT NULL),
    expires_at TEXT NOT NULL CHECK(julianday(expires_at) IS NOT NULL
                                    AND (kind = 'revoked' OR julianday(expires_at) > julianday(effective_at))),
    budget_unit TEXT NOT NULL CHECK(length(trim(budget_unit)) > 0),
    budget_limit INTEGER NOT NULL CHECK(budget_limit >= 0),
    risks TEXT NOT NULL CHECK(json_valid(risks) AND json_type(risks) IN ('object', 'array')),
    request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
    request_key TEXT NOT NULL CHECK(length(trim(request_key)) > 0),
    UNIQUE (study_id, scope_id, request_key),
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id),
    CHECK ((kind = 'submitted') = (prior_event_id IS NULL))
) STRICT;

CREATE INDEX personal_provider_approval_identity
ON personal_provider_approval_events (
    study_id, scope_id, purpose, provider, channel_ref, model, account_ref,
    credential_revision, effective_at, event_id
);

CREATE TRIGGER personal_provider_approval_event_validate
BEFORE INSERT ON personal_provider_approval_events
BEGIN
    SELECT CASE
      WHEN (SELECT application_id FROM pragma_application_id) <> 0x564F4350
        THEN RAISE(ABORT, 'provider approval requires a personal workspace')
      WHEN EXISTS (
          SELECT 1 FROM personal_provider_approval_events
          WHERE event_id = NEW.event_id
             OR (study_id = NEW.study_id AND scope_id = NEW.scope_id AND request_key = NEW.request_key)
             OR prior_event_id = NEW.prior_event_id
      ) THEN RAISE(ABORT, 'retained provider approval event')
      WHEN NOT EXISTS (
          SELECT 1 FROM study_scope_freezes f
          JOIN study_scopes s USING(study_id, scope_id)
          WHERE f.study_id = NEW.study_id AND f.scope_id = NEW.scope_id
            AND 'v' || s.version_no = NEW.scope_version
      ) THEN RAISE(ABORT, 'provider approval frozen scope mismatch')
      WHEN NEW.prior_event_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM personal_provider_approval_events prior
          WHERE prior.event_id = NEW.prior_event_id
            AND prior.edition = NEW.edition
            AND prior.study_id = NEW.study_id AND prior.scope_id = NEW.scope_id
            AND prior.scope_version = NEW.scope_version AND prior.purpose = NEW.purpose
            AND prior.provider = NEW.provider AND prior.channel_ref = NEW.channel_ref
            AND prior.model = NEW.model AND prior.account_ref = NEW.account_ref
            AND prior.credential_revision = NEW.credential_revision
            AND julianday(prior.effective_at) <= julianday(NEW.effective_at)
            AND ((NEW.kind = 'approved' AND prior.kind = 'submitted')
              OR (NEW.kind = 'revoked' AND prior.kind IN ('submitted', 'approved')))
      ) THEN RAISE(ABORT, 'provider approval lineage mismatch')
    END;
END;

CREATE TRIGGER personal_provider_approval_event_no_update
BEFORE UPDATE ON personal_provider_approval_events
BEGIN
    SELECT RAISE(ABORT, 'retained provider approval event');
END;

CREATE TRIGGER personal_provider_approval_event_no_delete
BEFORE DELETE ON personal_provider_approval_events
BEGIN
    SELECT RAISE(ABORT, 'retained provider approval event');
END;

ALTER TABLE personal_provider_approval_events
ADD COLUMN evidence_count INTEGER NOT NULL DEFAULT 0 CHECK(evidence_count BETWEEN 0 AND 30);

CREATE TABLE personal_approval_evidence (
    event_id TEXT NOT NULL REFERENCES personal_provider_approval_events(event_id),
    evidence_ref TEXT NOT NULL CHECK(length(trim(evidence_ref)) > 0),
    kind TEXT NOT NULL CHECK(length(trim(kind)) > 0),
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    terms_version TEXT NOT NULL CHECK(length(trim(terms_version)) > 0),
    verified_at TEXT NOT NULL CHECK(julianday(verified_at) IS NOT NULL),
    expires_at TEXT CHECK(expires_at IS NULL OR (
        julianday(expires_at) IS NOT NULL AND julianday(expires_at) > julianday(verified_at)
    )),
    PRIMARY KEY (event_id, evidence_ref)
) STRICT;

CREATE TRIGGER personal_approval_evidence_no_replace
BEFORE INSERT ON personal_approval_evidence
WHEN EXISTS (
    SELECT 1 FROM personal_approval_evidence
    WHERE event_id = NEW.event_id AND evidence_ref = NEW.evidence_ref
) OR (
    SELECT COUNT(*) FROM personal_approval_evidence WHERE event_id = NEW.event_id
) >= (
    SELECT evidence_count FROM personal_provider_approval_events WHERE event_id = NEW.event_id
)
BEGIN
    SELECT RAISE(ABORT, 'retained provider approval evidence');
END;

CREATE TRIGGER personal_approval_evidence_no_update
BEFORE UPDATE ON personal_approval_evidence
BEGIN
    SELECT RAISE(ABORT, 'retained provider approval evidence');
END;

CREATE TRIGGER personal_approval_evidence_no_delete
BEFORE DELETE ON personal_approval_evidence
BEGIN
    SELECT RAISE(ABORT, 'retained provider approval evidence');
END;

CREATE TABLE personal_credential_binding (
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    credential_revision TEXT NOT NULL CHECK (
        length(credential_revision) = 32 AND credential_revision NOT GLOB '*[^0-9a-f]*'
    ),
    PRIMARY KEY (study_id, scope_id),
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id)
) WITHOUT ROWID;

CREATE TRIGGER personal_credential_binding_personal_only
BEFORE INSERT ON personal_credential_binding
WHEN (SELECT application_id FROM pragma_application_id) <> 1448035152
BEGIN
    SELECT RAISE(ABORT, 'requires personal workspace');
END;

PRAGMA user_version=9;
