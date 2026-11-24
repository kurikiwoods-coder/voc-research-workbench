"""M06-C1 upgrades on disposable SQLite databases and independent processes."""

from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from src.raw_store import store as storage
import test_corpus as fixtures


V7 = 7
ROOT = Path(__file__).resolve().parents[1]
CHILD = """
from contextlib import closing
from pathlib import Path
import sys
import time
from src.raw_store.store import Store

directory, sync, role = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]

def trace(sql):
    sql = sql.strip().lower()
    checkpoint = None
    if role == "holder" and sql == "pragma user_version":
        checkpoint = "holder-locked"
    elif role == "waiter" and sql == "begin immediate":
        checkpoint = "waiter-attempting-lock"
    elif sql.startswith("pragma user_version=7"):
        (sync / f"{role}-ran-v7").touch()
        if role == "interrupt":
            checkpoint = "ddl-staged"
    if checkpoint and not (sync / checkpoint).exists():
        (sync / checkpoint).touch()
        if role != "waiter":
            deadline = time.monotonic() + 25
            while not (sync / "release").exists() and time.monotonic() < deadline:
                time.sleep(0.02)

class TracedStore(Store):
    def connect(self):
        db = super().connect()
        db.set_trace_callback(trace)
        return db

if role.startswith("fresh-"):
    (sync / role).touch()
    deadline = time.monotonic() + 25
    while not (sync / "release").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("Fresh database process was not released")
        time.sleep(0.02)

store = TracedStore(directory)
with closing(store.connect()) as db:
    print(db.execute("pragma user_version").fetchone()[0])
"""


def snapshot(db):
    tables = db.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return {
        name: {tuple(row) for row in db.execute(f'SELECT * FROM "{name}"')}
        for (name,) in tables
        if not name.startswith("m06_")
    }


class M06MigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(prefix="voc-m06 迁移 ")))
        self.enterContext(patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("egress")))

    def historical_v6(self):
        case = fixtures.CorpusTests()
        self.addCleanup(case.doCleanups)
        with patch.object(storage, "MIGRATIONS", storage.MIGRATIONS[:6]):
            case.setUp()
        _, (record_id,) = case.import_rows([fixtures.ROW])
        case.verify(record_id)
        case.verify(
            record_id, decision="excluded", reason="合成来源撤销",
            license_status="revoked", retention_until=None,
        )
        store = case.app.state.store
        with store.db() as db:
            db.executescript("""
                INSERT INTO runs VALUES ('run-1', 'request-1', 'fixture', 'synthetic', '2026-01-01', NULL, 'paused');
                INSERT INTO attempts VALUES (41, 'run-1', '2026-01-01', NULL);
                INSERT INTO evidence VALUES
                    (42, 41, 'contract', 'synthetic_contract', '2026-01-01', NULL, '{}', '{}');
                INSERT INTO results VALUES (41, 'G-1', 'BLOCKED', 'fixture', NULL, '[42]', '2026-01-01');
                INSERT INTO shards VALUES
                    ('shard-1', 'run-1', 1, 'fixture', 'complete', '{}', 0, 0, 42, '2026-01-01');
                INSERT INTO study_workspace VALUES (1, (SELECT study_id FROM study_projects))
                    ON CONFLICT(slot) DO UPDATE SET study_id = excluded.study_id;
            """)
        with closing(store.connect()) as db:
            self.assert_database(db, 6)
            rows = snapshot(db)
        for name in (
            "runs", "attempts", "results", "evidence", "shards", "study_workspace",
            "study_projects", "study_scopes", "study_scope_freezes", "import_files",
            "import_batches", "import_rows", "corpus_snapshots", "corpus_reviews", "corpus_licenses",
        ):
            self.assertTrue(rows[name], name)
        self.assertEqual(len(rows["corpus_reviews"]), 2)
        self.assertEqual(len(rows["corpus_licenses"]), 2)
        return store, rows

    def assert_database(self, db, version):
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], version)
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def assert_upgraded(self, directory, historical=None):
        with closing(storage.Store(directory).connect()) as db:
            self.assert_database(db, V7)
            self.assertTrue(db.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='m06_registry'"
            ).fetchone())
            if historical is not None:
                self.assertEqual(snapshot(db), historical)
                for (name,) in db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' AND name GLOB 'm06_*'"
                ):
                    self.assertEqual(db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0], 0)

    def child(self, directory, role, sync):
        process = subprocess.Popen(
            [sys.executable, "-c", CHILD, str(directory), str(sync), role],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        )

        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=15)

        self.addCleanup(cleanup)
        return process

    def checkpoint(self, process, marker):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and process.poll() is None:
            if marker.exists():
                return
            time.sleep(0.02)
        if process.poll() is not None:
            self.fail(f"Child exited before {marker.name}: {process.communicate()}")
        self.fail(f"Child did not reach {marker.name}")

    def test_empty_restarts_and_database_roles(self):
        self.assert_upgraded(self.root)
        self.assert_upgraded(self.root)
        fixture = storage.Store(self.root, fixture=True)
        diagnostic = storage.Store(self.root, diagnostic=True)
        self.assertEqual(fixture.path, self.root / "synthetic_contract.sqlite3")
        self.assertEqual(diagnostic.path, self.root / "api-diagnostics" / "connectivity.sqlite3")
        for isolated in (fixture, diagnostic):
            with closing(isolated.connect()) as db:
                self.assert_database(db, 1)
                self.assertFalse(db.execute(
                    "SELECT 1 FROM sqlite_schema WHERE name GLOB 'm06_*' OR name='study_projects'"
                ).fetchone())

    def test_each_store_connection_enforces_foreign_keys(self):
        store = storage.Store(self.root)
        with closing(store.connect()) as first, closing(store.connect()) as second:
            for db in (first, second):
                self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                with self.assertRaisesRegex(sqlite3.IntegrityError, "FOREIGN KEY"):
                    db.execute("INSERT INTO study_workspace VALUES (1, 'absent-study')")
                db.rollback()

    def test_unknown_high_version_refused_without_data_changes(self):
        path = self.root / "connectivity.sqlite3"
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("CREATE TABLE existing (id); INSERT INTO existing VALUES (49); PRAGMA user_version=999;")
        with self.assertRaisesRegex(ValueError, "不支持的数据库版本"):
            storage.Store(self.root)
        with closing(sqlite3.connect(path)) as db:
            self.assert_database(db, 999)
            self.assertEqual(db.execute("SELECT id FROM existing").fetchall(), [(49,)])

    def test_historical_v6_upgrades_without_changing_data(self):
        old, rows = self.historical_v6()
        self.assert_upgraded(old.directory, rows)
        self.assert_upgraded(old.directory, rows)

    def test_historical_v6_rebound_batch_is_preserved_but_cannot_anchor_evidence(self):
        case = fixtures.CorpusTests()
        self.addCleanup(case.doCleanups)
        with patch.object(storage, "MIGRATIONS", storage.MIGRATIONS[:6]):
            case.setUp()
        batch_id, (record_id,) = case.import_rows([fixtures.ROW])
        case.verify(record_id)
        other_study, other_scope = case.project()
        other_batch, _ = case.import_rows([fixtures.ROW], study=other_study, scope=other_scope)
        old = case.app.state.store
        with old.db() as db:
            db.execute("""
                INSERT OR REPLACE INTO import_batches (
                    batch_id, study_id, scope_id, file_id, sheet_index, sheet_name, header_line,
                    headers_json, mapping_json, privacy, signature, summary_json, created_at
                )
                SELECT ?, study_id, scope_id, file_id, sheet_index, sheet_name, header_line,
                    headers_json, mapping_json, privacy, 'historic-rebind', summary_json, created_at
                FROM import_batches WHERE batch_id=?
            """, (batch_id, other_batch))
            anchor = db.execute("""
                SELECT s.study_id, s.record_id, s.scope_id, s.raw_sha256, b.study_id, b.scope_id
                FROM corpus_snapshots s JOIN import_rows r ON s.record_id=r.record_id
                JOIN import_batches b ON r.batch_id=b.batch_id WHERE s.record_id=?
            """, (record_id,)).fetchone()
            self.assertEqual(anchor[:3], (case.study, record_id, case.scope))
            self.assertEqual(anchor[4:], (other_study, other_scope))
            self.assert_database(db, 6)
            historical = snapshot(db)

        self.assert_upgraded(old.directory, historical)
        with old.db() as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "does not match the immutable receipt"):
                db.execute("""
                    INSERT INTO m06_evidence (
                        study_id, evidence_id, record_id, scope_id, raw_sha256, start_cp, end_cp
                    ) VALUES (?, 'invalid-evidence', ?, ?, ?, 0, 1)
                """, anchor[:4])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM m06_evidence").fetchone()[0], 0)

    def test_consistent_live_wal_backup_restore_and_remigrate(self):
        old, _ = self.historical_v6()
        backup = self.root / "consistent-v6.sqlite3"
        restored = self.root / "恢复 副本"
        restored.mkdir()
        with closing(old.connect()) as source, closing(sqlite3.connect(backup)) as copy:
            self.assertEqual(source.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assert_database(source, 6)
            source.execute("PRAGMA wal_autocheckpoint=0")
            with source:
                source.execute("UPDATE study_projects SET objective='合成备份探针'")
            rows = snapshot(source)
            self.assertTrue(old.path.with_suffix(".sqlite3-wal").stat().st_size)
            source.backup(copy)
            copy.execute("PRAGMA foreign_keys=ON")
            self.assert_database(copy, 6)
            self.assertEqual(snapshot(copy), rows)

        self.assert_upgraded(old.directory, rows)
        with closing(sqlite3.connect(backup)) as copy, closing(sqlite3.connect(restored / "connectivity.sqlite3")) as db:
            copy.backup(db)
            db.execute("PRAGMA foreign_keys=ON")
            self.assert_database(db, 6)
            self.assertEqual(snapshot(db), rows)
        self.assert_upgraded(restored, rows)

    def race(self, directory):
        sync = self.root / "race-coordination"
        sync.mkdir()
        holder = self.child(directory, "holder", sync)
        self.checkpoint(holder, sync / "holder-locked")
        waiter = self.child(directory, "waiter", sync)
        self.checkpoint(waiter, sync / "waiter-attempting-lock")
        self.assertIsNone(waiter.poll())
        (sync / "release").touch()
        for process in (holder, waiter):
            out, error = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(out.strip(), str(V7))
        self.assertTrue((sync / "holder-ran-v7").exists())
        self.assertFalse((sync / "waiter-ran-v7").exists())

    def test_two_processes_initialize_one_empty_database(self):
        self.race(self.root)
        self.assert_upgraded(self.root)

    def test_two_processes_compete_to_enable_wal_in_fresh_database(self):
        processes = [
            self.child(self.root, role, self.root) for role in ("fresh-first", "fresh-second")
        ]
        for role, process in zip(("fresh-first", "fresh-second"), processes):
            self.checkpoint(process, self.root / role)
        (self.root / "release").touch()
        for process in processes:
            out, error = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(out.strip(), str(V7))
        self.assertEqual(len(list(self.root.glob("fresh-*-ran-v7"))), 1)
        self.assert_upgraded(self.root)

    def test_two_processes_upgrade_v6_and_recheck_version_under_lock(self):
        old, rows = self.historical_v6()
        self.race(old.directory)
        self.assert_upgraded(old.directory, rows)

    def test_failing_script_rolls_back_ddl_data_and_user_version(self):
        old, rows = self.historical_v6()
        injected = self.root / storage.MIGRATIONS[-1]
        injected.write_text(
            "CREATE TABLE m06_partial (id); PRAGMA user_version=7;"
            "UPDATE study_projects SET name='changed'; SELECT * FROM no_such_table;",
            encoding="utf-8",
        )
        with patch.object(storage, "MIGRATION_DIRECTORY", self.root):
            with self.assertRaisesRegex(sqlite3.OperationalError, "no such table"):
                storage.Store(old.directory)
        with closing(old.connect()) as db:
            self.assert_database(db, 6)
            self.assertEqual(snapshot(db), rows)
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_schema WHERE name='m06_partial'").fetchone())
        self.assert_upgraded(old.directory, rows)

    def test_terminated_migration_rolls_back_and_restarts(self):
        old, rows = self.historical_v6()
        process = self.child(old.directory, "interrupt", self.root)
        self.checkpoint(process, self.root / "ddl-staged")
        process.kill()
        process.communicate(timeout=15)
        self.assertNotEqual(process.returncode, 0)
        with closing(old.connect()) as db:
            self.assert_database(db, 6)
            self.assertEqual(snapshot(db), rows)
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_schema WHERE name GLOB 'm06_*'").fetchone())
        self.assert_upgraded(old.directory, rows)
