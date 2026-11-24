"""M06-B isolated SQLite and existing M05 eligibility probe."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from src.raw_store.corpus_access import qualification
from test_pre_m06_audit import CrossModuleAudit, SOURCE, row


def failed(action, error):
    try:
        action()
    except sqlite3.Error as exc:
        assert exc.sqlite_errorname == error, (exc.sqlite_errorname, error)
    else:
        raise AssertionError(f"expected {error}")


def connect(path):
    db = sqlite3.connect(path, timeout=0, isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    return db


def count(db, table):
    return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def run_constraints(path):
    with closing(connect(path)) as db, closing(connect(path)) as other:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        db.executescript("""
        CREATE TABLE registry(v INT PRIMARY KEY NOT NULL, parent INT UNIQUE REFERENCES registry(v));
        CREATE UNIQUE INDEX single_root ON registry((1)) WHERE parent IS NULL;
        INSERT INTO registry VALUES (1,NULL);
        CREATE TABLE task(
            v INT NOT NULL, c TEXT NOT NULL, confirmed INT NOT NULL CHECK(confirmed IN (0,1)),
            PRIMARY KEY(v,c), UNIQUE(v,c,confirmed)
        );
        CREATE TABLE intent(
            v INT NOT NULL, a TEXT NOT NULL, confirmed INT NOT NULL CHECK(confirmed IN (0,1)),
            primary_c TEXT, primary_marker INT NOT NULL DEFAULT 1 CHECK(primary_marker=1),
            PRIMARY KEY(v,a), CHECK(confirmed=0 OR primary_c IS NOT NULL),
            FOREIGN KEY(v,a,primary_c,primary_marker) REFERENCES edge(v,a,c,is_primary)
                DEFERRABLE INITIALLY DEFERRED
        );
        CREATE TABLE edge(
            v INT NOT NULL, a TEXT NOT NULL, c TEXT NOT NULL,
            is_primary INT NOT NULL CHECK(is_primary IN (0,1)),
            task_marker INT NOT NULL DEFAULT 1 CHECK(task_marker=1),
            PRIMARY KEY(v,a,c), UNIQUE(v,a,c,is_primary),
            FOREIGN KEY(v,a) REFERENCES intent(v,a),
            FOREIGN KEY(v,c,task_marker) REFERENCES task(v,c,confirmed)
        );
        CREATE UNIQUE INDEX one_primary ON edge(v,a) WHERE is_primary=1;
        CREATE TABLE command(namespace TEXT NOT NULL, op TEXT NOT NULL, k TEXT NOT NULL,
           digest TEXT NOT NULL, result INT NOT NULL REFERENCES registry(v),
           PRIMARY KEY(namespace,op,k));
        INSERT INTO task VALUES (1,'task-a',1), (1,'task-b',1), (1,'candidate-task',0),
                                (2,'task-there',1);
        """)
        failed(lambda: db.execute("INSERT INTO registry VALUES (99,NULL)"),
               "SQLITE_CONSTRAINT_UNIQUE")
        failed(lambda: db.execute("INSERT INTO intent(v,a,confirmed) VALUES (1,'null',1)"),
               "SQLITE_CONSTRAINT_CHECK")
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO intent(v,a,confirmed,primary_c) VALUES (1,'missing',1,'task-a')")
        db.execute("INSERT INTO registry VALUES (2,1)")
        db.execute("INSERT INTO command VALUES ('g','confirm','missing','digest',2)")
        failed(db.commit, "SQLITE_CONSTRAINT_FOREIGNKEY")
        assert db.in_transaction
        db.rollback()
        assert [count(db, t) for t in ("intent", "command", "registry")] == [0, 0, 1]

        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO intent(v,a,confirmed,primary_c) VALUES (1,'good',1,'task-a')")
        db.execute("INSERT INTO intent(v,a,confirmed) VALUES (1,'candidate',0)")
        db.execute("INSERT INTO edge(v,a,c,is_primary) VALUES (1,'good','task-a',1)")
        failed(lambda: db.execute(
            "INSERT INTO edge(v,a,c,is_primary) VALUES (1,'good','task-b',1)"),
            "SQLITE_CONSTRAINT_UNIQUE")
        for invalid in ("task-there", "candidate-task"):
            failed(lambda: db.execute(
                "INSERT INTO edge(v,a,c,is_primary) VALUES (1,'good',?,0)", (invalid,)),
                "SQLITE_CONSTRAINT_FOREIGNKEY")
        db.commit()
        assert count(db, "intent") == 2 and count(db, "edge") == 1
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        print("PASS single root, explicit NULL check, exact-version/confirmed task FK, one primary")
        print("PASS deferred missing primary rejects COMMIT; explicit rollback removes version and command")

        def lookup(connection, key, digest, expected):
            saved = connection.execute(
                "SELECT digest,result FROM command WHERE namespace='g' AND op='confirm' AND k=?",
                (key,)).fetchone()
            if saved:
                return ("replay", saved[1]) if saved[0] == digest else ("key_conflict", None)
            head = connection.execute("SELECT MAX(v) FROM registry").fetchone()[0]
            return ("new", head) if expected == head else ("stale", head)

        digest = hashlib.sha256(b"synthetic canonical command at head 1").hexdigest()
        db.execute("BEGIN IMMEDIATE")
        assert lookup(db, "same", digest, 1) == ("new", 1)
        db.execute("INSERT INTO registry VALUES (2,1)")
        db.execute("INSERT INTO command VALUES ('g','confirm','same',?,2)", (digest,))
        failed(lambda: other.execute("BEGIN IMMEDIATE"), "SQLITE_BUSY")
        db.commit()
        other.execute("BEGIN IMMEDIATE")
        assert lookup(other, "competing", digest, 1) == ("stale", 2)
        assert lookup(other, "same", digest, 1) == ("replay", 2)
        assert lookup(other, "same", digest.upper(), 1) == ("key_conflict", None)
        assert [count(other, t) for t in ("registry", "command")] == [2, 1]
        other.rollback()
        print("PASS competing writer busy then stale; same-key same-hash replay; changed hash conflict")


def run_corpus():
    audit = CrossModuleAudit()
    try:
        audit.setUp()
        store = audit.app.state.store
        corpus = audit.app.state.corpus
        _, project = audit.new_project()
        study = project["study_id"]
        _, first = audit.imported(project)
        _, copy = audit.imported(project, [row(source=SOURCE + "#comment-9")])
        _, independent = audit.imported(project, [row(source=SOURCE + "/independent")])
        paths = (first, copy, independent)
        records = tuple(p.rsplit("/", 1)[-1] for p in paths)
        today = datetime.now(timezone.utc).date()
        for path in paths:
            audit.review(path, retention_until=today.isoformat()).raise_for_status()

        def probe(connection, date):
            day = date.isoformat()
            return tuple(qualification(corpus.source_row(connection, study, record_id, day), day)
                         ["engineering_eligible"] for record_id in records)

        def status():
            return tuple(audit.client.get(path + "/eligible").status_code for path in paths)

        assert status() == (200, 200, 200)
        _, other_project = audit.new_project("Separate synthetic project")
        assert audit.client.get(f"/api/corpus/{other_project['study_id']}/records/"
                                f"{records[0]}/eligible").status_code == 404
        with closing(store.connect()) as stale, closing(store.connect()) as fresh:
            assert stale.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            stale.execute("BEGIN")
            assert probe(stale, today) == (True, True, True)
            audit.withdraw(first)
            assert status() == (409, 409, 200)
            assert probe(stale, today) == (True, True, True)
            failed(lambda: stale.execute("UPDATE corpus_reviews SET decision=decision WHERE 0"),
                   "SQLITE_BUSY_SNAPSHOT")
            stale.rollback()

            fresh.execute("BEGIN IMMEDIATE")
            assert probe(fresh, today) == (False, False, True)
            stale.execute("PRAGMA busy_timeout=0")
            failed(lambda: stale.execute("BEGIN IMMEDIATE"), "SQLITE_BUSY")
            assert probe(fresh, today + timedelta(days=1)) == (False, False, False)
            fresh.rollback()
            audit.withdraw(independent)
            assert status() == (409, 409, 409)

        restore = dict(reauthorize=True, license_issued_on=today.isoformat())
        blocked = audit.review(first, license_evidence_ref="local:audit-assent", **restore)
        assert blocked.status_code == 422
        audit.review(first, license_evidence_ref="local:m06-b-separate-grant", **restore).raise_for_status()
        assert status() == (200, 409, 409)
        available = audit.client.get(first + "/eligible").raise_for_status().json()
        assert available["engineering_eligible"] is True
        assert available["research_eligible"] is False and available["outbound_allowed"] is False
        assert audit.client.get(copy).json()["raw_text"] is None
        print("PASS actual v6 M05 WAL: stale read and SQLITE_BUSY_SNAPSHOT; fresh write lock and fresh qualification")
        print("PASS UTC day advance under write lock expires last independent support")
        print("PASS M05 GET 200/200/200 -> 409/409/200 -> 409/409/409 -> 200/409/409")
        print("PASS old grant rejected; wrong project 404; revoked excerpt masked; research/outbound false")
    finally:
        audit.doCleanups()


if __name__ == "__main__":
    print(f"Python {sys.version.split()[0]}, SQLite {sqlite3.sqlite_version}")
    with TemporaryDirectory(prefix="voc-m06-b sqlite ") as folder:
        run_constraints(Path(folder) / "constraints.sqlite3")
    run_corpus()
