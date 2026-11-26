-- M06-C1 stores only versioned identities, relationships and audit references.
-- Existing source, scope and license records are not rewritten.
CREATE UNIQUE INDEX m06_snapshot_anchor
ON corpus_snapshots(study_id, record_id, scope_id, raw_sha256);

-- Preserve v6 immutability even for REPLACE with recursive triggers disabled.
CREATE TRIGGER m06_no_replace_study_scope
BEFORE INSERT ON study_scopes
WHEN EXISTS (
    SELECT 1 FROM study_scopes
    WHERE scope_id = NEW.scope_id
       OR (study_id = NEW.study_id AND version_no = NEW.version_no)
)
BEGIN SELECT RAISE(ABORT, 'immutable study scope'); END;

CREATE TRIGGER m06_no_replace_scope_freeze
BEFORE INSERT ON study_scope_freezes
WHEN EXISTS (SELECT 1 FROM study_scope_freezes WHERE scope_id = NEW.scope_id)
BEGIN SELECT RAISE(ABORT, 'immutable study freeze'); END;

CREATE TRIGGER m06_no_replace_corpus_batch
BEFORE INSERT ON import_batches
WHEN EXISTS (
    SELECT 1 FROM import_batches batch
    JOIN import_rows source ON source.batch_id = batch.batch_id
    JOIN corpus_snapshots snapshot ON snapshot.record_id = source.record_id
    WHERE batch.batch_id = NEW.batch_id
       OR (batch.study_id = NEW.study_id AND batch.scope_id = NEW.scope_id
           AND batch.signature = NEW.signature)
)
BEGIN SELECT RAISE(ABORT, 'immutable corpus source receipt'); END;

CREATE TRIGGER m06_no_replace_corpus_source
BEFORE INSERT ON import_rows
WHEN EXISTS (SELECT 1 FROM corpus_snapshots WHERE record_id = NEW.record_id)
   OR EXISTS (
       SELECT 1 FROM import_rows source JOIN corpus_snapshots snapshot USING (record_id)
       WHERE source.batch_id = NEW.batch_id AND source.line_number = NEW.line_number
   )
BEGIN SELECT RAISE(ABORT, 'immutable corpus source'); END;

CREATE TABLE m06_command (
    command_id TEXT PRIMARY KEY NOT NULL,
    study_id TEXT REFERENCES study_projects(study_id),
    namespace TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    result_ref TEXT NOT NULL CHECK (json_valid(result_ref)),
    UNIQUE (namespace, operation, idempotency_key),
    UNIQUE (study_id, command_id),
    CHECK ((study_id IS NULL AND namespace = 'global')
        OR (study_id IS NOT NULL AND namespace = 'study:' || study_id))
) STRICT;

CREATE TABLE m06_registry (
    registry_version TEXT PRIMARY KEY NOT NULL,
    parent_version TEXT UNIQUE REFERENCES m06_registry(registry_version),
    created_at TEXT NOT NULL,
    command_id TEXT NOT NULL REFERENCES m06_command(command_id),
    sealed INTEGER NOT NULL DEFAULT 0 CHECK (sealed IN (0, 1)),
    -- A staging row must find its own sealed key by COMMIT.
    committed_seal INTEGER GENERATED ALWAYS AS (1) VIRTUAL,
    UNIQUE (registry_version, sealed),
    FOREIGN KEY (registry_version, committed_seal)
        REFERENCES m06_registry(registry_version, sealed) DEFERRABLE INITIALLY DEFERRED,
    CHECK (parent_version IS NULL OR parent_version <> registry_version)
) STRICT;

CREATE UNIQUE INDEX m06_registry_single_root
ON m06_registry((1)) WHERE parent_version IS NULL;

CREATE TABLE m06_product (
    registry_version TEXT NOT NULL REFERENCES m06_registry(registry_version),
    product_category_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    parent_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'confirmed', 'merged', 'retired')),
    version TEXT NOT NULL,
    PRIMARY KEY (registry_version, product_category_id),
    FOREIGN KEY (registry_version, parent_id)
        REFERENCES m06_product(registry_version, product_category_id),
    CHECK (parent_id IS NULL OR parent_id <> product_category_id)
) STRICT;

CREATE INDEX m06_product_children ON m06_product(registry_version, parent_id);

CREATE TABLE m06_task (
    registry_version TEXT NOT NULL REFERENCES m06_registry(registry_version),
    category_id TEXT NOT NULL,
    name TEXT NOT NULL,
    definition TEXT NOT NULL,
    inclusion_criteria TEXT NOT NULL,
    exclusion_criteria TEXT NOT NULL,
    discovery TEXT NOT NULL CHECK (discovery IN ('preset', 'discovered')),
    lifecycle_status TEXT NOT NULL
        CHECK (lifecycle_status IN ('candidate', 'confirmed', 'rejected', 'merged', 'retired')),
    version TEXT NOT NULL,
    PRIMARY KEY (registry_version, category_id),
    UNIQUE (registry_version, category_id, lifecycle_status)
) STRICT;

CREATE TABLE m06_intent (
    registry_version TEXT NOT NULL REFERENCES m06_registry(registry_version),
    intent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    definition TEXT NOT NULL,
    inclusion_criteria TEXT NOT NULL,
    exclusion_criteria TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL
        CHECK (lifecycle_status IN ('candidate', 'pending_parent', 'confirmed', 'rejected', 'merged', 'retired')),
    primary_category_id TEXT,
    primary_marker INTEGER NOT NULL DEFAULT 1 CHECK (primary_marker = 1),
    survey_validation_status TEXT NOT NULL
        CHECK (survey_validation_status IN ('unvalidated', 'validating', 'validated', 'failed')),
    version TEXT NOT NULL,
    PRIMARY KEY (registry_version, intent_id),
    FOREIGN KEY (registry_version, intent_id, primary_category_id, primary_marker)
        REFERENCES m06_intent_task(registry_version, intent_id, category_id, is_primary)
        DEFERRABLE INITIALLY DEFERRED,
    CHECK (lifecycle_status <> 'confirmed' OR primary_category_id IS NOT NULL)
) STRICT;

CREATE TABLE m06_intent_task (
    registry_version TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    is_primary INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
    task_status TEXT NOT NULL DEFAULT 'confirmed' CHECK (task_status = 'confirmed'),
    PRIMARY KEY (registry_version, intent_id, category_id),
    UNIQUE (registry_version, intent_id, category_id, is_primary),
    FOREIGN KEY (registry_version, intent_id)
        REFERENCES m06_intent(registry_version, intent_id),
    FOREIGN KEY (registry_version, category_id, task_status)
        REFERENCES m06_task(registry_version, category_id, lifecycle_status)
) STRICT;

CREATE UNIQUE INDEX m06_intent_single_primary
ON m06_intent_task(registry_version, intent_id) WHERE is_primary = 1;
CREATE INDEX m06_intent_task_reverse
ON m06_intent_task(registry_version, category_id, intent_id);

CREATE TABLE m06_scope_binding (
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    mapping_revision INTEGER NOT NULL CHECK (mapping_revision > 0),
    previous_revision INTEGER,
    registry_version TEXT NOT NULL REFERENCES m06_registry(registry_version),
    mapping_status TEXT NOT NULL CHECK (mapping_status IN ('unresolved', 'mapped_product', 'non_product')),
    scope_reviewer_ref TEXT NOT NULL,
    catalog_reviewer_ref TEXT,
    basis_ref TEXT NOT NULL,
    command_id TEXT NOT NULL,
    PRIMARY KEY (study_id, scope_id, mapping_revision),
    UNIQUE (study_id, scope_id, mapping_revision, registry_version),
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id),
    FOREIGN KEY (study_id, scope_id, previous_revision)
        REFERENCES m06_scope_binding(study_id, scope_id, mapping_revision),
    FOREIGN KEY (study_id, command_id) REFERENCES m06_command(study_id, command_id),
    CHECK ((mapping_revision = 1 AND previous_revision IS NULL)
        OR (mapping_revision > 1 AND previous_revision IS NOT NULL
            AND previous_revision = mapping_revision - 1)),
    CHECK (mapping_status = 'unresolved' OR catalog_reviewer_ref IS NOT NULL)
) STRICT;

CREATE TABLE m06_scope_product (
    study_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    mapping_revision INTEGER NOT NULL,
    registry_version TEXT NOT NULL,
    product_category_id TEXT NOT NULL,
    PRIMARY KEY (study_id, scope_id, mapping_revision, registry_version, product_category_id),
    -- Insert the product choices before the final immutable binding.
    FOREIGN KEY (study_id, scope_id, mapping_revision, registry_version)
        REFERENCES m06_scope_binding(study_id, scope_id, mapping_revision, registry_version)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (registry_version, product_category_id)
        REFERENCES m06_product(registry_version, product_category_id)
) STRICT;

CREATE INDEX m06_scope_product_reverse
ON m06_scope_product(registry_version, product_category_id);

CREATE TABLE m06_evidence (
    study_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    start_cp INTEGER NOT NULL CHECK (start_cp >= 0),
    end_cp INTEGER NOT NULL CHECK (end_cp > start_cp),
    PRIMARY KEY (study_id, evidence_id),
    UNIQUE (study_id, record_id, raw_sha256, start_cp, end_cp),
    FOREIGN KEY (study_id, scope_id) REFERENCES study_scope_freezes(study_id, scope_id),
    FOREIGN KEY (study_id, record_id, scope_id, raw_sha256)
        REFERENCES corpus_snapshots(study_id, record_id, scope_id, raw_sha256)
) STRICT;

CREATE INDEX m06_evidence_scope_record ON m06_evidence(study_id, scope_id, record_id);

CREATE TABLE m06_mention (
    study_id TEXT NOT NULL REFERENCES study_projects(study_id),
    mention_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (study_id, mention_id)
) STRICT;

CREATE TABLE m06_segment_rev (
    study_id TEXT NOT NULL REFERENCES study_projects(study_id),
    segment_revision INTEGER NOT NULL CHECK (segment_revision > 0),
    parent_rev INTEGER,
    rule_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    command_id TEXT NOT NULL,
    sealed INTEGER NOT NULL DEFAULT 0 CHECK (sealed IN (0, 1)),
    committed_seal INTEGER GENERATED ALWAYS AS (1) VIRTUAL,
    PRIMARY KEY (study_id, segment_revision),
    UNIQUE (study_id, parent_rev),
    UNIQUE (study_id, segment_revision, parent_rev),
    UNIQUE (study_id, segment_revision, sealed),
    FOREIGN KEY (study_id, parent_rev) REFERENCES m06_segment_rev(study_id, segment_revision),
    FOREIGN KEY (study_id, command_id) REFERENCES m06_command(study_id, command_id),
    FOREIGN KEY (study_id, segment_revision, committed_seal)
        REFERENCES m06_segment_rev(study_id, segment_revision, sealed) DEFERRABLE INITIALLY DEFERRED,
    CHECK (parent_rev IS NULL OR (parent_rev > 0 AND parent_rev < segment_revision))
) STRICT;

CREATE UNIQUE INDEX m06_segment_single_root
ON m06_segment_rev(study_id) WHERE parent_rev IS NULL;

CREATE TABLE m06_member (
    study_id TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    mention_id TEXT NOT NULL,
    identity_state TEXT NOT NULL CHECK (identity_state IN ('distinct', 'needs_review')),
    PRIMARY KEY (study_id, segment_revision, mention_id),
    FOREIGN KEY (study_id, segment_revision) REFERENCES m06_segment_rev(study_id, segment_revision),
    FOREIGN KEY (study_id, mention_id) REFERENCES m06_mention(study_id, mention_id)
) STRICT;

CREATE TABLE m06_support (
    study_id TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    mention_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    segment_no INTEGER NOT NULL CHECK (segment_no > 0),
    occurrence_basis TEXT NOT NULL,
    review_ref TEXT NOT NULL,
    PRIMARY KEY (study_id, segment_revision, mention_id, evidence_id),
    UNIQUE (study_id, segment_revision, evidence_id),
    FOREIGN KEY (study_id, segment_revision, mention_id)
        REFERENCES m06_member(study_id, segment_revision, mention_id),
    FOREIGN KEY (study_id, evidence_id) REFERENCES m06_evidence(study_id, evidence_id)
) STRICT;

CREATE INDEX m06_support_reverse ON m06_support(study_id, evidence_id, segment_revision);

CREATE TABLE m06_representative (
    registry_version TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    study_id TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    mention_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (registry_version, intent_id, study_id, segment_revision, mention_id, evidence_id),
    FOREIGN KEY (registry_version, intent_id)
        REFERENCES m06_intent(registry_version, intent_id),
    FOREIGN KEY (study_id, segment_revision, mention_id, evidence_id)
        REFERENCES m06_support(study_id, segment_revision, mention_id, evidence_id)
) STRICT;

CREATE INDEX m06_representative_reverse
ON m06_representative(study_id, segment_revision, mention_id, evidence_id);

CREATE TABLE m06_mention_product (
    study_id TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    mention_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    product_category_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    command_id TEXT NOT NULL,
    PRIMARY KEY (study_id, segment_revision, mention_id, evidence_id, catalog_version, product_category_id),
    FOREIGN KEY (study_id, segment_revision, mention_id, evidence_id)
        REFERENCES m06_support(study_id, segment_revision, mention_id, evidence_id),
    FOREIGN KEY (catalog_version, product_category_id)
        REFERENCES m06_product(registry_version, product_category_id),
    FOREIGN KEY (study_id, command_id) REFERENCES m06_command(study_id, command_id)
) STRICT;

CREATE INDEX m06_mention_product_reverse
ON m06_mention_product(study_id, product_category_id, segment_revision, mention_id);

CREATE TABLE m06_product_review (
    study_id TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    mention_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    product_category_id TEXT NOT NULL,
    decision_seq INTEGER NOT NULL CHECK (decision_seq > 0),
    decision TEXT NOT NULL
        CHECK (decision IN ('proposed', 'queued', 'human_confirmed', 'suspended', 'withdrawn')),
    basis_ref TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    command_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('A', 'B', 'C')),
    proposal_provenance TEXT NOT NULL CHECK (json_valid(proposal_provenance)),
    PRIMARY KEY (
        study_id, segment_revision, mention_id, evidence_id, catalog_version, product_category_id, decision_seq
    ),
    FOREIGN KEY (study_id, segment_revision, mention_id, evidence_id, catalog_version, product_category_id)
        REFERENCES m06_mention_product(
            study_id, segment_revision, mention_id, evidence_id, catalog_version, product_category_id
        ),
    FOREIGN KEY (study_id, command_id) REFERENCES m06_command(study_id, command_id),
    CHECK (decision <> 'human_confirmed' OR mode = 'A')
) STRICT;

CREATE TABLE m06_replacement (
    study_id TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    old_rev INTEGER NOT NULL,
    old_mention_id TEXT NOT NULL,
    new_mention_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (study_id, segment_revision, old_mention_id, new_mention_id),
    FOREIGN KEY (study_id, segment_revision, old_rev)
        REFERENCES m06_segment_rev(study_id, segment_revision, parent_rev),
    FOREIGN KEY (study_id, old_rev, old_mention_id)
        REFERENCES m06_member(study_id, segment_revision, mention_id),
    FOREIGN KEY (study_id, segment_revision, new_mention_id)
        REFERENCES m06_member(study_id, segment_revision, mention_id),
    CHECK (old_mention_id <> new_mention_id)
) STRICT;

CREATE TABLE m06_discovery_review (
    study_id TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    mention_id TEXT NOT NULL,
    registry_version TEXT NOT NULL REFERENCES m06_registry(registry_version),
    seq INTEGER NOT NULL CHECK (seq > 0),
    intent_id TEXT,
    review_state TEXT NOT NULL CHECK (review_state IN ('open', 'accepted', 'rejected', 'closed')),
    reason_code TEXT NOT NULL,
    command_id TEXT NOT NULL,
    PRIMARY KEY (study_id, segment_revision, mention_id, registry_version, seq),
    FOREIGN KEY (study_id, segment_revision, mention_id)
        REFERENCES m06_member(study_id, segment_revision, mention_id),
    FOREIGN KEY (registry_version, intent_id)
        REFERENCES m06_intent(registry_version, intent_id),
    FOREIGN KEY (study_id, command_id) REFERENCES m06_command(study_id, command_id)
) STRICT;

CREATE TABLE m06_discovery_input (
    study_id TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    mention_id TEXT NOT NULL,
    registry_version TEXT NOT NULL,
    seq INTEGER NOT NULL,
    evidence_id TEXT NOT NULL,
    dependency_role TEXT NOT NULL,
    target_e TEXT,
    PRIMARY KEY (study_id, segment_revision, mention_id, registry_version, seq, evidence_id, dependency_role),
    FOREIGN KEY (study_id, segment_revision, mention_id, registry_version, seq)
        REFERENCES m06_discovery_review(study_id, segment_revision, mention_id, registry_version, seq),
    FOREIGN KEY (study_id, evidence_id) REFERENCES m06_evidence(study_id, evidence_id),
    FOREIGN KEY (study_id, segment_revision, mention_id, target_e)
        REFERENCES m06_support(study_id, segment_revision, mention_id, evidence_id),
    CHECK ((dependency_role = 'occurrence' AND target_e IS NOT NULL AND target_e = evidence_id)
        OR (dependency_role = 'context' AND target_e IS NULL))
) STRICT;

CREATE INDEX m06_discovery_input_reverse ON m06_discovery_input(study_id, evidence_id);

CREATE TABLE m06_change_edge (
    registry_version TEXT NOT NULL REFERENCES m06_registry(registry_version),
    seq INTEGER NOT NULL CHECK (seq > 0),
    command_id TEXT NOT NULL REFERENCES m06_command(command_id),
    kind TEXT NOT NULL CHECK (kind IN ('product', 'task', 'intent')),
    from_version TEXT REFERENCES m06_registry(registry_version),
    from_id TEXT,
    to_id TEXT,
    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'merge', 'split', 'retire')),
    PRIMARY KEY (registry_version, seq),
    CHECK ((action = 'create' AND from_version IS NULL AND from_id IS NULL AND to_id IS NOT NULL)
        OR (action IN ('update', 'merge', 'split') AND from_version IS NOT NULL
            AND from_id IS NOT NULL AND to_id IS NOT NULL)
        OR (action = 'retire' AND from_version IS NOT NULL AND from_id IS NOT NULL AND to_id IS NULL)),
    CHECK (from_version IS NULL OR from_version <> registry_version)
) STRICT;

CREATE VIEW m06_registry_head AS
SELECT version.registry_version
FROM m06_registry version
WHERE version.sealed = 1 AND NOT EXISTS (
    SELECT 1 FROM m06_registry child WHERE child.parent_version = version.registry_version AND child.sealed = 1
);

CREATE VIEW m06_segment_head AS
SELECT version.study_id, version.segment_revision
FROM m06_segment_rev version
WHERE version.sealed = 1 AND NOT EXISTS (
    SELECT 1 FROM m06_segment_rev child
    WHERE child.study_id = version.study_id AND child.parent_rev = version.segment_revision AND child.sealed = 1
);

-- A version is written as a private draft and published by sealing in the same transaction.
CREATE TRIGGER m06_registry_begin
BEFORE INSERT ON m06_registry
BEGIN
    SELECT RAISE(ABORT, 'registry draft must start unsealed') WHERE NEW.sealed <> 0;
    SELECT RAISE(ABORT, 'registry parent must be sealed') WHERE NEW.parent_version IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM m06_registry
            WHERE registry_version = NEW.parent_version AND sealed = 1
        );
    SELECT RAISE(ABORT, 'registry version or successor already exists') WHERE EXISTS (
        SELECT 1 FROM m06_registry
        WHERE registry_version = NEW.registry_version OR parent_version IS NEW.parent_version
    );
END;

CREATE TRIGGER m06_registry_publish
BEFORE UPDATE ON m06_registry
BEGIN
    SELECT RAISE(ABORT, 'registry permits only its initial seal')
    WHERE OLD.sealed <> 0 OR NEW.sealed <> 1
       OR OLD.registry_version IS NOT NEW.registry_version
       OR OLD.parent_version IS NOT NEW.parent_version
       OR OLD.created_at IS NOT NEW.created_at OR OLD.command_id IS NOT NEW.command_id;

    SELECT RAISE(ABORT, 'intent primary pointer does not match its primary edge') WHERE EXISTS (
        SELECT 1 FROM m06_intent intent
        LEFT JOIN m06_intent_task edge
          ON edge.registry_version = intent.registry_version AND edge.intent_id = intent.intent_id
         AND edge.is_primary = 1
        WHERE intent.registry_version = OLD.registry_version
          AND intent.primary_category_id IS NOT edge.category_id
    );

    -- The database counts distinct stored occurrences. Current eligibility,
    -- and whether occurrences in different studies coincide, are service checks.
    SELECT RAISE(ABORT, 'confirmed intent requires three distinct representative occurrences') WHERE EXISTS (
        SELECT 1 FROM m06_intent intent
        WHERE intent.registry_version = OLD.registry_version AND intent.lifecycle_status = 'confirmed'
          AND 3 > (
              SELECT count(*) FROM (
                  SELECT representative.study_id, representative.mention_id
                  FROM m06_representative representative
                  JOIN m06_member member
                    USING (study_id, segment_revision, mention_id)
                  JOIN m06_segment_rev segment
                    USING (study_id, segment_revision)
                  WHERE representative.registry_version = intent.registry_version
                    AND representative.intent_id = intent.intent_id
                    AND member.identity_state = 'distinct' AND segment.sealed = 1
                  GROUP BY representative.study_id, representative.mention_id
              )
          )
    );

    SELECT RAISE(ABORT, 'product category parent cycle') WHERE EXISTS (
        WITH RECURSIVE ancestors(node, ancestor) AS (
            SELECT product_category_id, parent_id FROM m06_product
            WHERE registry_version = OLD.registry_version AND parent_id IS NOT NULL
            UNION
            SELECT ancestors.node, product.parent_id FROM ancestors
            JOIN m06_product product ON product.registry_version = OLD.registry_version
                AND product.product_category_id = ancestors.ancestor
            WHERE product.parent_id IS NOT NULL
        )
        SELECT 1 FROM ancestors WHERE node = ancestor
    );

    SELECT RAISE(ABORT, 'registry change edge has an invalid version or endpoint') WHERE EXISTS (
        SELECT 1 FROM m06_change_edge edge
        WHERE edge.registry_version = OLD.registry_version AND (
                 (edge.from_version IS NOT NULL AND edge.from_version IS NOT OLD.parent_version)
              OR (edge.kind = 'product' AND edge.from_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM m06_product entity
                  WHERE entity.registry_version = edge.from_version AND entity.product_category_id = edge.from_id
              ))
              OR (edge.kind = 'product' AND edge.to_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM m06_product entity
                  WHERE entity.registry_version = edge.registry_version AND entity.product_category_id = edge.to_id
              ))
              OR (edge.kind = 'task' AND edge.from_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM m06_task entity
                  WHERE entity.registry_version = edge.from_version AND entity.category_id = edge.from_id
              ))
              OR (edge.kind = 'task' AND edge.to_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM m06_task entity
                  WHERE entity.registry_version = edge.registry_version AND entity.category_id = edge.to_id
              ))
              OR (edge.kind = 'intent' AND edge.from_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM m06_intent entity
                  WHERE entity.registry_version = edge.from_version AND entity.intent_id = edge.from_id
              ))
              OR (edge.kind = 'intent' AND edge.to_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM m06_intent entity
                  WHERE entity.registry_version = edge.registry_version AND entity.intent_id = edge.to_id
              ))
        )
    );
END;

CREATE TRIGGER m06_registry_no_delete
BEFORE DELETE ON m06_registry WHEN OLD.sealed = 1
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_segment_begin
BEFORE INSERT ON m06_segment_rev
BEGIN
    SELECT RAISE(ABORT, 'segment draft must start unsealed') WHERE NEW.sealed <> 0;
    SELECT RAISE(ABORT, 'segment parent must be sealed') WHERE NEW.parent_rev IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM m06_segment_rev
            WHERE study_id = NEW.study_id AND segment_revision = NEW.parent_rev AND sealed = 1
        );
    SELECT RAISE(ABORT, 'segment version or successor already exists') WHERE EXISTS (
        SELECT 1 FROM m06_segment_rev WHERE study_id = NEW.study_id
          AND (segment_revision = NEW.segment_revision OR parent_rev IS NEW.parent_rev)
    );
END;

CREATE TRIGGER m06_segment_publish
BEFORE UPDATE ON m06_segment_rev
BEGIN
    SELECT RAISE(ABORT, 'segment permits only its initial seal')
    WHERE OLD.sealed <> 0 OR NEW.sealed <> 1
       OR OLD.study_id IS NOT NEW.study_id OR OLD.segment_revision IS NOT NEW.segment_revision
       OR OLD.parent_rev IS NOT NEW.parent_rev OR OLD.rule_version IS NOT NEW.rule_version
       OR OLD.created_at IS NOT NEW.created_at OR OLD.command_id IS NOT NEW.command_id;

    SELECT RAISE(ABORT, 'segment member requires support') WHERE EXISTS (
        SELECT 1 FROM m06_member member
        WHERE member.study_id = OLD.study_id AND member.segment_revision = OLD.segment_revision
          AND NOT EXISTS (
              SELECT 1 FROM m06_support support
              WHERE support.study_id = member.study_id AND support.segment_revision = member.segment_revision
                AND support.mention_id = member.mention_id
          )
    );

    SELECT RAISE(ABORT, 'mention replacement cycle') WHERE EXISTS (
        WITH RECURSIVE successors(original, successor) AS (
            SELECT old_mention_id, new_mention_id FROM m06_replacement
            WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision
            UNION
            SELECT successors.original, replacement.new_mention_id FROM successors
            JOIN m06_replacement replacement ON replacement.study_id = OLD.study_id
                AND replacement.old_mention_id = successors.successor
        )
        SELECT 1 FROM successors WHERE original = successor
    );
END;

CREATE TRIGGER m06_segment_no_delete
BEFORE DELETE ON m06_segment_rev WHEN OLD.sealed = 1
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE INDEX m06_replacement_forward ON m06_replacement(study_id, old_mention_id);

CREATE TRIGGER m06_product_sealed_insert
BEFORE INSERT ON m06_product
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_product_sealed_update
BEFORE UPDATE ON m06_product
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_product_sealed_delete
BEFORE DELETE ON m06_product
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_task_sealed_insert
BEFORE INSERT ON m06_task
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_task_sealed_update
BEFORE UPDATE ON m06_task
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_task_sealed_delete
BEFORE DELETE ON m06_task
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_intent_sealed_insert
BEFORE INSERT ON m06_intent
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_intent_sealed_update
BEFORE UPDATE ON m06_intent
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_intent_sealed_delete
BEFORE DELETE ON m06_intent
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_intent_task_sealed_insert
BEFORE INSERT ON m06_intent_task
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_intent_task_sealed_update
BEFORE UPDATE ON m06_intent_task
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_intent_task_sealed_delete
BEFORE DELETE ON m06_intent_task
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_representative_sealed_insert
BEFORE INSERT ON m06_representative
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_representative_sealed_update
BEFORE UPDATE ON m06_representative
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_representative_sealed_delete
BEFORE DELETE ON m06_representative
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_change_edge_sealed_insert
BEFORE INSERT ON m06_change_edge
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_change_edge_sealed_update
BEFORE UPDATE ON m06_change_edge
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = NEW.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_change_edge_sealed_delete
BEFORE DELETE ON m06_change_edge
WHEN EXISTS (
    SELECT 1 FROM m06_registry
    WHERE registry_version = OLD.registry_version AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed registry is immutable'); END;

CREATE TRIGGER m06_member_sealed_insert
BEFORE INSERT ON m06_member
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = NEW.study_id AND segment_revision = NEW.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_member_sealed_update
BEFORE UPDATE ON m06_member
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = NEW.study_id AND segment_revision = NEW.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_member_sealed_delete
BEFORE DELETE ON m06_member
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_support_sealed_insert
BEFORE INSERT ON m06_support
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = NEW.study_id AND segment_revision = NEW.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_support_sealed_update
BEFORE UPDATE ON m06_support
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = NEW.study_id AND segment_revision = NEW.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_support_sealed_delete
BEFORE DELETE ON m06_support
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_mention_product_sealed_insert
BEFORE INSERT ON m06_mention_product
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = NEW.study_id AND segment_revision = NEW.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_mention_product_sealed_update
BEFORE UPDATE ON m06_mention_product
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = NEW.study_id AND segment_revision = NEW.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_mention_product_sealed_delete
BEFORE DELETE ON m06_mention_product
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_replacement_sealed_insert
BEFORE INSERT ON m06_replacement
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = NEW.study_id AND segment_revision = NEW.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_replacement_sealed_update
BEFORE UPDATE ON m06_replacement
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision AND sealed = 1
) OR EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = NEW.study_id AND segment_revision = NEW.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

CREATE TRIGGER m06_replacement_sealed_delete
BEFORE DELETE ON m06_replacement
WHEN EXISTS (
    SELECT 1 FROM m06_segment_rev
    WHERE study_id = OLD.study_id AND segment_revision = OLD.segment_revision AND sealed = 1
)
BEGIN SELECT RAISE(ABORT, 'sealed segment is immutable'); END;

-- A scope binding is the publication boundary for its exact set of product nodes.
CREATE TRIGGER m06_scope_binding_validate
BEFORE INSERT ON m06_scope_binding
BEGIN
    SELECT RAISE(ABORT, 'scope mapping version already exists') WHERE EXISTS (
        SELECT 1 FROM m06_scope_binding
        WHERE study_id = NEW.study_id AND scope_id = NEW.scope_id AND mapping_revision = NEW.mapping_revision
    );
    SELECT RAISE(ABORT, 'scope mapping requires a sealed registry') WHERE NOT EXISTS (
        SELECT 1 FROM m06_registry WHERE registry_version = NEW.registry_version AND sealed = 1
    );
    SELECT RAISE(ABORT, 'mapped scope requires confirmed same-version products')
    WHERE NEW.mapping_status = 'mapped_product' AND (
        NOT EXISTS (
            SELECT 1 FROM m06_scope_product node
            WHERE node.study_id = NEW.study_id AND node.scope_id = NEW.scope_id
              AND node.mapping_revision = NEW.mapping_revision AND node.registry_version = NEW.registry_version
        ) OR EXISTS (
            SELECT 1 FROM m06_scope_product node
            JOIN m06_product product USING (registry_version, product_category_id)
            WHERE node.study_id = NEW.study_id AND node.scope_id = NEW.scope_id
              AND node.mapping_revision = NEW.mapping_revision
              AND (node.registry_version <> NEW.registry_version OR product.status <> 'confirmed')
        )
    );
    SELECT RAISE(ABORT, 'unresolved or non-product scope cannot contain products')
    WHERE NEW.mapping_status <> 'mapped_product' AND EXISTS (
        SELECT 1 FROM m06_scope_product
        WHERE study_id = NEW.study_id AND scope_id = NEW.scope_id AND mapping_revision = NEW.mapping_revision
    );
END;

CREATE TRIGGER m06_scope_product_before_binding
BEFORE INSERT ON m06_scope_product
WHEN EXISTS (
    SELECT 1 FROM m06_scope_binding
    WHERE study_id = NEW.study_id AND scope_id = NEW.scope_id AND mapping_revision = NEW.mapping_revision
)
BEGIN SELECT RAISE(ABORT, 'published scope mapping is immutable'); END;

-- Coordinates are Unicode code point offsets in the immutable imported source.
-- SQLite length() truncates at NUL, which the supported import formats already reject.
CREATE TRIGGER m06_evidence_anchor_validate
BEFORE INSERT ON m06_evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence identity or source interval already exists') WHERE EXISTS (
        SELECT 1 FROM m06_evidence
        WHERE study_id = NEW.study_id AND (
            evidence_id = NEW.evidence_id OR
            (record_id = NEW.record_id AND raw_sha256 = NEW.raw_sha256
                AND start_cp = NEW.start_cp AND end_cp = NEW.end_cp)
        )
    );
    SELECT RAISE(ABORT, 'evidence source or interval does not match the immutable receipt') WHERE NOT EXISTS (
        SELECT 1 FROM corpus_snapshots snapshot
        JOIN import_rows source ON source.record_id = snapshot.record_id
        JOIN import_batches batch ON batch.batch_id = source.batch_id
        WHERE snapshot.study_id = NEW.study_id AND snapshot.record_id = NEW.record_id
          AND batch.study_id = snapshot.study_id AND batch.scope_id = snapshot.scope_id
          AND instr(source.raw_text, char(0)) = 0 AND NEW.end_cp <= length(source.raw_text)
    );
END;

CREATE TRIGGER m06_command_no_replace
BEFORE INSERT ON m06_command
WHEN EXISTS (
    SELECT 1 FROM m06_command
    WHERE command_id = NEW.command_id OR (
        namespace = NEW.namespace AND operation = NEW.operation AND idempotency_key = NEW.idempotency_key
    )
)
BEGIN SELECT RAISE(ABORT, 'command identity or idempotency key already exists'); END;

CREATE TRIGGER m06_mention_no_replace
BEFORE INSERT ON m06_mention
WHEN EXISTS (
    SELECT 1 FROM m06_mention
    WHERE study_id = NEW.study_id
      AND mention_id = NEW.mention_id
)
BEGIN SELECT RAISE(ABORT, 'existing mention is immutable'); END;

CREATE TRIGGER m06_product_review_no_replace
BEFORE INSERT ON m06_product_review
WHEN EXISTS (
    SELECT 1 FROM m06_product_review
    WHERE study_id = NEW.study_id
      AND segment_revision = NEW.segment_revision
      AND mention_id = NEW.mention_id
      AND evidence_id = NEW.evidence_id
      AND catalog_version = NEW.catalog_version
      AND product_category_id = NEW.product_category_id
      AND decision_seq = NEW.decision_seq
)
BEGIN SELECT RAISE(ABORT, 'existing product review is immutable'); END;

CREATE TRIGGER m06_discovery_review_no_replace
BEFORE INSERT ON m06_discovery_review
WHEN EXISTS (
    SELECT 1 FROM m06_discovery_review
    WHERE study_id = NEW.study_id
      AND segment_revision = NEW.segment_revision
      AND mention_id = NEW.mention_id
      AND registry_version = NEW.registry_version
      AND seq = NEW.seq
)
BEGIN SELECT RAISE(ABORT, 'existing discovery review is immutable'); END;

CREATE TRIGGER m06_discovery_input_no_replace
BEFORE INSERT ON m06_discovery_input
WHEN EXISTS (
    SELECT 1 FROM m06_discovery_input
    WHERE study_id = NEW.study_id
      AND segment_revision = NEW.segment_revision
      AND mention_id = NEW.mention_id
      AND registry_version = NEW.registry_version
      AND seq = NEW.seq
      AND evidence_id = NEW.evidence_id
      AND dependency_role = NEW.dependency_role
)
BEGIN SELECT RAISE(ABORT, 'existing discovery input is immutable'); END;

CREATE TRIGGER m06_command_no_update
BEFORE UPDATE ON m06_command
BEGIN SELECT RAISE(ABORT, 'command is append only'); END;

CREATE TRIGGER m06_command_no_delete
BEFORE DELETE ON m06_command
BEGIN SELECT RAISE(ABORT, 'command is append only'); END;

CREATE TRIGGER m06_scope_binding_no_update
BEFORE UPDATE ON m06_scope_binding
BEGIN SELECT RAISE(ABORT, 'scope binding is append only'); END;

CREATE TRIGGER m06_scope_binding_no_delete
BEFORE DELETE ON m06_scope_binding
BEGIN SELECT RAISE(ABORT, 'scope binding is append only'); END;

CREATE TRIGGER m06_scope_product_no_update
BEFORE UPDATE ON m06_scope_product
BEGIN SELECT RAISE(ABORT, 'scope product is append only'); END;

CREATE TRIGGER m06_scope_product_no_delete
BEFORE DELETE ON m06_scope_product
BEGIN SELECT RAISE(ABORT, 'scope product is append only'); END;

CREATE TRIGGER m06_evidence_no_update
BEFORE UPDATE ON m06_evidence
BEGIN SELECT RAISE(ABORT, 'evidence is append only'); END;

CREATE TRIGGER m06_evidence_no_delete
BEFORE DELETE ON m06_evidence
BEGIN SELECT RAISE(ABORT, 'evidence is append only'); END;

CREATE TRIGGER m06_mention_no_update
BEFORE UPDATE ON m06_mention
BEGIN SELECT RAISE(ABORT, 'mention is append only'); END;

CREATE TRIGGER m06_mention_no_delete
BEFORE DELETE ON m06_mention
BEGIN SELECT RAISE(ABORT, 'mention is append only'); END;

CREATE TRIGGER m06_product_review_no_update
BEFORE UPDATE ON m06_product_review
BEGIN SELECT RAISE(ABORT, 'product review is append only'); END;

CREATE TRIGGER m06_product_review_no_delete
BEFORE DELETE ON m06_product_review
BEGIN SELECT RAISE(ABORT, 'product review is append only'); END;

CREATE TRIGGER m06_discovery_review_no_update
BEFORE UPDATE ON m06_discovery_review
BEGIN SELECT RAISE(ABORT, 'discovery review is append only'); END;

CREATE TRIGGER m06_discovery_review_no_delete
BEFORE DELETE ON m06_discovery_review
BEGIN SELECT RAISE(ABORT, 'discovery review is append only'); END;

CREATE TRIGGER m06_discovery_input_no_update
BEFORE UPDATE ON m06_discovery_input
BEGIN SELECT RAISE(ABORT, 'discovery input is append only'); END;

CREATE TRIGGER m06_discovery_input_no_delete
BEFORE DELETE ON m06_discovery_input
BEGIN SELECT RAISE(ABORT, 'discovery input is append only'); END;

PRAGMA user_version=7;
