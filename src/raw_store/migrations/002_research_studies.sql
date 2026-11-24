CREATE TABLE IF NOT EXISTS study_projects (
    study_id TEXT PRIMARY KEY NOT NULL,
    request_key TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    description TEXT NOT NULL,
    background TEXT NOT NULL,
    objective TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'archived')),
    status_before_archive TEXT,
    revision INTEGER NOT NULL CHECK (revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK ((status = 'archived' AND status_before_archive IS NOT NULL
            AND status_before_archive IN ('draft', 'active'))
           OR (status <> 'archived' AND status_before_archive IS NULL))
);

CREATE TABLE IF NOT EXISTS study_scopes (
    study_id TEXT NOT NULL REFERENCES study_projects(study_id),
    scope_id TEXT PRIMARY KEY NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    content_json TEXT NOT NULL,
    changed_fields_json TEXT NOT NULL,
    change_note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (study_id, version_no),
    UNIQUE (study_id, scope_id)
);

CREATE TABLE IF NOT EXISTS study_scope_freezes (
    study_id TEXT NOT NULL,
    scope_id TEXT PRIMARY KEY NOT NULL,
    frozen_at TEXT NOT NULL,
    UNIQUE (study_id, scope_id),
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scopes(study_id, scope_id)
);

CREATE TABLE IF NOT EXISTS study_workspace (
    slot INTEGER PRIMARY KEY CHECK (slot = 1),
    study_id TEXT REFERENCES study_projects(study_id)
);

CREATE TRIGGER IF NOT EXISTS immutable_study_scope_update BEFORE UPDATE ON study_scopes
BEGIN SELECT RAISE(ABORT, 'immutable study scope'); END;
CREATE TRIGGER IF NOT EXISTS immutable_study_scope_delete BEFORE DELETE ON study_scopes
BEGIN SELECT RAISE(ABORT, 'immutable study scope'); END;
CREATE TRIGGER IF NOT EXISTS immutable_study_freeze_update BEFORE UPDATE ON study_scope_freezes
BEGIN SELECT RAISE(ABORT, 'immutable study freeze'); END;
CREATE TRIGGER IF NOT EXISTS immutable_study_freeze_delete BEFORE DELETE ON study_scope_freezes
BEGIN SELECT RAISE(ABORT, 'immutable study freeze'); END;

PRAGMA user_version=2;
