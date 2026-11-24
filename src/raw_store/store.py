from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Busy(RuntimeError):
    pass


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, directory, *, fixture=False, diagnostic=False):
        self.directory = Path(directory) / "api-diagnostics" if diagnostic else Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.fixture = fixture
        self.diagnostic = diagnostic
        self.path = self.directory / (
            "synthetic_contract.sqlite3" if fixture else "connectivity.sqlite3"
        )
        with closing(self.connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("数据库版本高于当前程序")
            if version == 0:
                migration = Path(__file__).parent / "migrations/001_connectivity.sql"
                db.executescript("BEGIN IMMEDIATE;\n" + migration.read_text("utf-8") + "\nCOMMIT;")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=12)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def db(self):
        with closing(self.connect()) as conn, conn:
            yield conn

    @contextmanager
    def writer(self):
        # OS releases the lock even if the process is interrupted. GETs stay usable.
        with (self.directory / "runner.lock").open("a+b") as handle:
            try:
                if os.name == "nt":
                    import msvcrt

                    if handle.seek(0, 2) == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise Busy("已有批次正在执行，可继续查看已有证据。") from exc
            yield

    def rows(self, query, args=()):
        with self.db() as db:
            return [dict(row) for row in db.execute(query, args)]

    def one(self, query, args=()):
        return next(iter(self.rows(query, args)), None)

    def begin(self, request_key, settings, resume_id=None):
        tag = settings.account_tag()
        with self.db() as db:
            if resume_id:
                run = db.execute("SELECT * FROM runs WHERE id=?", (resume_id,)).fetchone()
                if not run:
                    raise KeyError(resume_id)
                if run["provider"] != settings.provider:
                    raise Conflict("供应商或账户配置已变化，请新建批次。")
                if run["account_tag"] != tag:
                    empty_tag = hashlib.sha256((settings.provider+"\n").encode()).hexdigest()
                    reserved = db.execute("SELECT 1 FROM shards WHERE run_id=? LIMIT 1",(resume_id,)).fetchone()
                    if run["account_tag"] != empty_tag or reserved:
                        raise Conflict("此批次已绑定账户，请新建批次。")
                    db.execute("UPDATE runs SET account_tag=? WHERE id=?",(tag,resume_id))
                if run["state"] == "complete":
                    return run["id"], None
                run_id = run["id"]
            else:
                existing = db.execute(
                    "SELECT id FROM runs WHERE request_key=?", (request_key,)
                ).fetchone()
                if existing:
                    return existing["id"], None
                run_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO runs VALUES (?,?,?,?,?,NULL,'running')",
                    (run_id, request_key, settings.provider, tag, now()),
                )
            db.execute("UPDATE runs SET state='running',finished_at=NULL WHERE id=?", (run_id,))
            attempt = db.execute(
                "INSERT INTO attempts(run_id,started_at) VALUES (?,?)", (run_id, now())
            ).lastrowid
            return run_id, attempt

    def finish(self, run_id, attempt, passed):
        with self.db() as db:
            ts = now()
            db.execute(
                "UPDATE runs SET finished_at=?,state=? WHERE id=?",
                (ts, "complete" if passed else "paused", run_id),
            )
            db.execute("UPDATE attempts SET finished_at=? WHERE id=?", (ts, attempt))

    def _record(self, db, attempt, name, mode, request, response, status):
        if self.fixture and mode == "live_http":
            mode = "synthetic_contract"
        return db.execute(
            """INSERT INTO evidence(attempt_id,name,mode,checked_at,status_code,request_json,response_json)
               VALUES (?,?,?,?,?,?,?)""",
            (attempt, name, mode, now(), status, dump(request), dump(response)),
        ).lastrowid

    def record(self, attempt, name, mode, request, response, status=None):
        with self.db() as db:
            return self._record(db, attempt, name, mode, request, response, status)

    def result(self, attempt, rid, status, detail, evidence, blocker=None):
        with self.db() as db:
            db.execute(
                "INSERT INTO results VALUES (?,?,?,?,?,?,?)",
                (attempt, rid, status, detail, blocker, dump(evidence), now()),
            )

    def results(self, run_id):
        attempt = self.one("SELECT MAX(id) AS id FROM attempts WHERE run_id=?", (run_id,))
        rows = self.rows(
            "SELECT * FROM results WHERE attempt_id=? ORDER BY requirement_id", (attempt["id"],)
        )
        for row in rows:
            row["evidence"] = json.loads(row.pop("evidence_json"))
        return rows

    def history(self):
        return self.rows(
            """SELECT r.id,r.provider,r.started_at,r.finished_at,r.state,
            (SELECT COUNT(*) FROM attempts a WHERE a.run_id=r.id) AS attempts,
            (SELECT status FROM results WHERE requirement_id='G-1' AND attempt_id=
             (SELECT MAX(id) FROM attempts a WHERE a.run_id=r.id)) AS gate
            FROM runs r ORDER BY r.rowid DESC"""
        )

    def audit(self, run_id):
        run = self.one("SELECT id,provider,started_at,finished_at,state FROM runs WHERE id=?", (run_id,))
        if not run:
            raise KeyError(run_id)
        attempts = self.rows("SELECT * FROM attempts WHERE run_id=? ORDER BY id", (run_id,))
        for attempt in attempts:
            ev = self.rows("SELECT * FROM evidence WHERE attempt_id=? ORDER BY id", (attempt["id"],))
            for row in ev:
                row["request"] = json.loads(row.pop("request_json"))
                row["response"] = json.loads(row.pop("response_json"))
            attempt["evidence"] = ev
            checks = self.rows(
                "SELECT * FROM results WHERE attempt_id=? ORDER BY requirement_id", (attempt["id"],)
            )
            for row in checks:
                row["evidence"] = json.loads(row.pop("evidence_json"))
            attempt["checks"] = checks
        return {"run": run, "attempts": attempts}

    def reserve(self, run_id, number, body):
        key = f"{run_id}-shard-{number}"
        digest = hashlib.sha256(dump(body).encode()).hexdigest()
        with self.db() as db:
            row = db.execute("SELECT * FROM shards WHERE request_key=?", (key,)).fetchone()
            if row and row["body_hash"] != digest:
                raise Conflict("本批次分片内容发生变化，请新建批次。")
            if not row:
                db.execute(
                    "INSERT INTO shards(request_key,run_id,shard_no,body_hash,state,updated_at) VALUES (?,?,?,?,'sending',?)",
                    (key, run_id, number, digest, now()),
                )
            elif row["state"] == "retryable":
                db.execute(
                    "UPDATE shards SET state='sending',updated_at=? WHERE request_key=?", (now(), key)
                )
            return key, dict(row) if row else None

    def _settle_shard(self, db, key, state, body, tokens, remaining, evidence_id):
        updated = db.execute(
            """UPDATE shards SET state=?,response_json=?,tokens=?,remaining=?,evidence_id=?,
                      updated_at=(SELECT checked_at FROM evidence WHERE id=?)
               WHERE request_key=? AND state='sending'""",
            (state, dump(body), tokens, remaining, evidence_id, evidence_id, key),
        )
        if updated.rowcount != 1:
            raise Conflict("此分片未处于发送状态，无法回填。")

    def record_shard_response(self, attempt, key, request, response, status, *, state=None, tokens=None):
        with self.db() as db:
            ref = self._record(db, attempt, "jev_shard", "live_http", request, response, status)
            if state is not None:
                remaining = response.get("X-Tokens-Remaining") if state == "received" else None
                self._settle_shard(db, key, state, response["body"], tokens, remaining, ref)
            return ref

    def recorded_shard_success(self, run_id, key):
        return self.one(
            """SELECT e.id,e.request_json,e.response_json FROM evidence e
               JOIN attempts a ON a.id=e.attempt_id WHERE a.run_id=? AND e.name='jev_shard'
                 AND e.status_code=200 AND json_extract(e.request_json,'$.idempotency_key')=?
               ORDER BY e.id DESC LIMIT 1""",
            (run_id, key),
        )

    def recover_shard(self, key, evidence, body, tokens, remaining):
        with self.db() as db:
            self._settle_shard(db, key, "received", body, tokens, remaining, evidence["id"])

    def ledger(self, run_id):
        return self.rows(
            "SELECT request_key,shard_no,state,tokens,remaining,evidence_id,updated_at FROM shards WHERE run_id=? ORDER BY shard_no",
            (run_id,),
        )
