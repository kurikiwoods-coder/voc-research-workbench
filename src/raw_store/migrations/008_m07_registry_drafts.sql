CREATE TABLE m07_draft (
    study_id TEXT NOT NULL REFERENCES study_projects(study_id),
    draft_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('candidate', 'amend', 'merge', 'split', 'retire', 'restore')),
    intent_id TEXT NOT NULL,
    base_registry_version TEXT REFERENCES m06_registry(registry_version),
    origin_registry_version TEXT REFERENCES m06_registry(registry_version),
    created_at TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision > 0),
    PRIMARY KEY (study_id, draft_id),
    FOREIGN KEY (study_id, draft_id, revision)
        REFERENCES m07_draft_revision(study_id, draft_id, revision) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE INDEX m07_draft_intent ON m07_draft(study_id, intent_id);

CREATE TABLE m07_draft_revision (
    study_id TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision > 0),
    state TEXT NOT NULL CHECK(state IN ('draft', 'submitted', 'withdrawn')),
    lifecycle_status TEXT NOT NULL CHECK(lifecycle_status IN ('candidate', 'pending_parent')),
    definition_json TEXT NOT NULL CHECK(json_valid(definition_json) AND json_type(definition_json) = 'object'),
    source_refs_json TEXT NOT NULL CHECK(json_valid(source_refs_json) AND json_type(source_refs_json) = 'array'),
    target_ids_json TEXT NOT NULL CHECK(json_valid(target_ids_json) AND json_type(target_ids_json) = 'array'),
    reason TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (study_id, draft_id, revision),
    FOREIGN KEY (study_id, draft_id) REFERENCES m07_draft(study_id, draft_id)
) STRICT;

CREATE TRIGGER m07_draft_revision_no_replace
BEFORE INSERT ON m07_draft_revision
WHEN EXISTS (SELECT 1 FROM m07_draft_revision
             WHERE study_id=NEW.study_id AND draft_id=NEW.draft_id AND revision=NEW.revision)
BEGIN
    SELECT RAISE(ABORT, 'retained registry draft revision');
END;

CREATE TRIGGER m07_draft_revision_no_update
BEFORE UPDATE ON m07_draft_revision BEGIN
    SELECT RAISE(ABORT, 'retained registry draft revision');
END;

CREATE TRIGGER m07_draft_revision_no_delete
BEFORE DELETE ON m07_draft_revision BEGIN
    SELECT RAISE(ABORT, 'retained registry draft revision');
END;

CREATE TABLE m07_draft_command (
    study_id TEXT NOT NULL,
    request_key TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    PRIMARY KEY (study_id, request_key),
    FOREIGN KEY (study_id, draft_id, revision) REFERENCES m07_draft_revision(study_id, draft_id, revision)
) STRICT;

CREATE TABLE m07_shared_example (
    registry_version TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    seq INTEGER NOT NULL CHECK(seq > 0),
    kind TEXT NOT NULL CHECK(kind IN ('positive', 'negative')),
    example_text TEXT NOT NULL CHECK(length(trim(example_text)) BETWEEN 1 AND 4000),
    approval_ref TEXT NOT NULL CHECK(length(trim(approval_ref)) BETWEEN 1 AND 200),
    classification TEXT NOT NULL CHECK(classification IN ('synthetic', 'approved_shared')),
    PRIMARY KEY (registry_version, intent_id, seq),
    FOREIGN KEY (registry_version, intent_id) REFERENCES m06_intent(registry_version, intent_id)
) STRICT;

CREATE TRIGGER m07_example_stage_only
BEFORE INSERT ON m07_shared_example
WHEN COALESCE((SELECT sealed FROM m06_registry WHERE registry_version=NEW.registry_version), 1) <> 0
BEGIN
    SELECT RAISE(ABORT, 'shared examples require a registry being staged');
END;

CREATE TRIGGER m07_example_no_update
BEFORE UPDATE ON m07_shared_example BEGIN
    SELECT RAISE(ABORT, 'immutable shared example');
END;

CREATE TRIGGER m07_example_no_delete
BEFORE DELETE ON m07_shared_example BEGIN
    SELECT RAISE(ABORT, 'immutable shared example');
END;

PRAGMA user_version=8;
