from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from src.edition_policy import Edition
from src.raw_store.runtime_binding import APPLICATION_IDS, bind_directory
from src.raw_store.corpus_policy import snapshot_requires_restriction, source_identity, source_permission_revoked


MIGRATIONS = (
    "001_connectivity.sql",
    "002_research_studies.sql",
    "003_research_imports.sql",
    "004_corpus.sql",
    "005_corpus_licenses.sql",
    "006_corpus_withdrawal_compat.sql",
    "007_m06_core.sql",
    "008_m07_registry_drafts.sql",
    "009_personal_provider_approvals.sql",
)
PERSONAL_MIGRATIONS = ("010_personal_pre_admission.sql",)
MIGRATION_DIRECTORY = Path(__file__).parent / "migrations"
SQLITE_TIMEOUT = 12


def configure_workspace_connection(db):
    db.create_function("snapshot_requires_restriction", 8, snapshot_requires_restriction, deterministic=True)
    db.create_function("source_permission_revoked", 1, source_permission_revoked, deterministic=True)
    db.create_function("source_identity", 1, source_identity, deterministic=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Busy(RuntimeError):
    pass


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, directory, *, fixture=False, diagnostic=False, edition=Edition.BUSINESS):
        root = bind_directory(directory, Edition(edition))
        self.edition = Edition(edition)
        self.directory = root / "api-diagnostics" if diagnostic else root
        self.directory.mkdir(parents=True, exist_ok=True)
        self.fixture = fixture
        self.diagnostic = diagnostic
        self.schema_target = 1 if fixture or diagnostic else len(self._migrations(self.edition))
        self.path = self.directory / (
            "synthetic_contract.sqlite3" if fixture else "connectivity.sqlite3"
        )
        if self.edition == Edition.PERSONAL and (
            self.directory.is_symlink() or self.path.is_symlink()
        ):
            raise ValueError("个人工作库不能通过符号链接引用。")
        connect = self._connect if self.edition == Edition.PERSONAL else self.connect
        with closing(connect()) as db:
            self._migrate(db, self.schema_target, self.edition)

    @staticmethod
    def _migrations(edition):
        return MIGRATIONS + PERSONAL_MIGRATIONS if edition == Edition.PERSONAL else MIGRATIONS

    @staticmethod
    def _inspect_migration_source(db, target, edition):
        application_id, version, has_schema = db.execute(
            """
            SELECT application_id, user_version, EXISTS(SELECT 1 FROM sqlite_schema)
            FROM pragma_application_id(), pragma_user_version()
            """
        ).fetchone()
        new_personal = edition == Edition.PERSONAL and application_id == 0 and version == 0 and not has_schema
        if application_id != APPLICATION_IDS[edition] and not new_personal:
            raise ValueError("SQLite 工作库的产品版本与运行实例不符。")
        if not 0 <= version <= target:
            raise ValueError("不支持的数据库版本")
        return version, new_personal

    @staticmethod
    def _migrate(db, target, edition=Edition.BUSINESS):
        migrations = Store._migrations(edition)
        if not 1 <= target <= len(migrations):
            raise ValueError("不支持的数据库用途或目标版本")
        Store._inspect_migration_source(db, target, edition)
        # Journal mode changes happen outside transactions and can return busy
        # immediately when two processes open a brand-new file.
        deadline = time.monotonic() + SQLITE_TIMEOUT
        while True:
            try:
                mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                break
            except sqlite3.OperationalError as exc:
                if exc.sqlite_errorcode & 0xff != sqlite3.SQLITE_BUSY or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        if mode != "wal":
            raise sqlite3.OperationalError("Could not enable SQLite WAL")

        # In legacy transaction mode executescript would commit our lock
        # before the first statement. Use SQL transaction control here.
        db.autocommit = True
        db.execute("BEGIN IMMEDIATE")
        try:
            version, new_personal = Store._inspect_migration_source(db, target, edition)
            if new_personal:
                db.execute(f"PRAGMA application_id={APPLICATION_IDS[edition]}")
            if version < target:
                for number in range(version + 1, target + 1):
                    script = (MIGRATION_DIRECTORY / migrations[number - 1]).read_text("utf-8")
                    db.executescript(script)
                    if db.execute("PRAGMA user_version").fetchone()[0] != number:
                        raise sqlite3.DatabaseError("数据库迁移版本与预期不一致")
                if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise sqlite3.IntegrityError("数据库迁移外键检查失败")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("数据库迁移完整性检查失败")
            if target >= 7:
                db.execute("""CREATE INDEX IF NOT EXISTS corpus_review_excluded
                              ON corpus_reviews(review_id) WHERE decision='excluded'""")
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise

    def connect(self):
        db = self._connect()
        try:
            if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_IDS[self.edition]:
                raise ValueError("SQLite 工作库的产品版本与运行实例不符。")
            if self.edition == Edition.PERSONAL and not (
                0 <= db.execute("PRAGMA user_version").fetchone()[0] <= self.schema_target
            ):
                raise ValueError("不支持的数据库版本")
        except BaseException:
            db.close()
            raise
        return db

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=SQLITE_TIMEOUT)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        if not (self.fixture or self.diagnostic):
            configure_workspace_connection(db)
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

    def restore_search_batch(self, run, account_tag, search, post_request, citation, archive):
        """Write a verified restoration atomically while the caller holds the writer lock."""
        run_id = run["id"]
        checked = now()
        with self.db() as db:
            db.execute(
                """INSERT INTO runs(id,request_key,provider,account_tag,started_at,finished_at,state)
                   VALUES (?,?,?,?,?,?,'paused')""",
                (run_id, "archive:" + run_id, run["provider"], account_tag, run["started_at"], checked),
            )
            attempt = db.execute(
                "INSERT INTO attempts(run_id,started_at,finished_at) VALUES (?,?,?)",
                (run_id, checked, checked),
            ).lastrowid
            search_id = self._record(
                db, attempt, search["name"], "archived_live_http",
                search["request"], search["response"], search["status_code"],
                checked_at=search["checked_at"],
            )
            post_id = self._record(db, attempt, "forum_post", "live_http", post_request, citation, 200)
            proof_id = self._record(
                db, attempt, "source_archive_recovery", "archive_recovery",
                archive,
                {"restored_search_id": search_id, "rechecked_post_id": post_id, "tavily_requests": 0},
                None,
            )
            db.executemany(
                "INSERT INTO results VALUES (?,?,?,?,?,?,?)",
                [
                    (attempt, "C0-3", "PASS", "同批搜索证据已复用，许可原帖已重新核对。",
                     None, dump([search_id, post_id, proof_id]), checked),
                    (attempt, "G-1", "BLOCKED", "恢复后等待同一批的完整验收。",
                     "待重新执行 C0-1 至 C0-6 和供应商留存审查。", dump([proof_id]), checked),
                ],
            )
        return proof_id

    def finish(self, run_id, attempt, passed):
        with self.db() as db:
            ts = now()
            db.execute(
                "UPDATE runs SET finished_at=?,state=? WHERE id=?",
                (ts, "complete" if passed else "paused", run_id),
            )
            db.execute("UPDATE attempts SET finished_at=? WHERE id=?", (ts, attempt))

    def _record(self, db, attempt, name, mode, request, response, status, *, checked_at=None):
        if self.fixture and mode == "live_http":
            mode = "synthetic_contract"
        return db.execute(
            """INSERT INTO evidence(attempt_id,name,mode,checked_at,status_code,request_json,response_json)
               VALUES (?,?,?,?,?,?,?)""",
            (attempt, name, mode, checked_at or now(), status, dump(request), dump(response)),
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
