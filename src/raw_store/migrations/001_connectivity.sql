CREATE TABLE IF NOT EXISTS runs(
 id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, provider TEXT NOT NULL, account_tag TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, state TEXT NOT NULL CHECK(state IN ('running','complete','paused'))
);
CREATE TABLE IF NOT EXISTS attempts(
 id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS results(
 attempt_id INTEGER NOT NULL REFERENCES attempts(id), requirement_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PASS','FAIL','BLOCKED','PENDING','NOT_TESTED')),
 detail TEXT NOT NULL, blocker TEXT, evidence_json TEXT NOT NULL, checked_at TEXT NOT NULL,
 PRIMARY KEY(attempt_id,requirement_id)
);
CREATE TABLE IF NOT EXISTS evidence(
 id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL REFERENCES attempts(id), name TEXT NOT NULL,
 mode TEXT NOT NULL, checked_at TEXT NOT NULL, status_code INTEGER,
 request_json TEXT NOT NULL, response_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shards(
 request_key TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), shard_no INTEGER NOT NULL,
 body_hash TEXT NOT NULL, state TEXT NOT NULL, response_json TEXT, tokens INTEGER, remaining INTEGER,
 evidence_id INTEGER REFERENCES evidence(id), updated_at TEXT NOT NULL, UNIQUE(run_id,shard_no)
);
CREATE TRIGGER IF NOT EXISTS immutable_evidence_update BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS immutable_evidence_delete BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS immutable_results_update BEFORE UPDATE ON results BEGIN SELECT RAISE(ABORT,'immutable result'); END;
CREATE TRIGGER IF NOT EXISTS immutable_results_delete BEFORE DELETE ON results BEGIN SELECT RAISE(ABORT,'immutable result'); END;
PRAGMA user_version=1;
