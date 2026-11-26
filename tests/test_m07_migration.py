"""Exercise the M07 migration against genuine v7 SQLite databases."""

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.raw_store import store as storage
from test_m06_constraints import insert, registry, seal_registry


V7 = 7
V9 = 9
M07_TABLES = {"m07_draft", "m07_draft_revision", "m07_draft_command", "m07_shared_example"}


def registry_history(db):
    return {
        table: {tuple(row) for row in db.execute(f"SELECT * FROM {table}")}
        for table in ("m06_registry", "m06_command", "m06_task", "m06_intent", "m06_intent_task")
    }


def append_registry_version(db, version, parent=None):
    registry(db, version, parent)
    insert(
        db, "m06_task", registry_version=version, category_id="task-seat",
        name="预约", definition="合成预约定义", inclusion_criteria="明确预约",
        exclusion_criteria="取消预约", discovery="preset",
        lifecycle_status="confirmed", version="1.0.0",
    )
    insert(
        db, "m06_intent", registry_version=version, intent_id="intent-book-seat",
        name="预约座位", definition="合成预约座位定义", inclusion_criteria="提前预留座位",
        exclusion_criteria="仅询问开门时间", lifecycle_status="candidate",
        primary_category_id="task-seat", survey_validation_status="unvalidated", version="1.0.0",
    )
    insert(
        db, "m06_intent_task", registry_version=version, intent_id="intent-book-seat",
        category_id="task-seat", is_primary=1,
    )
    seal_registry(db, version)


class M07MigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(prefix="voc-m07 迁移 ")))

    def historical_v7(self):
        with patch.object(storage, "MIGRATIONS", storage.MIGRATIONS[:V7]):
            old = storage.Store(self.root / "历史 v7")
        with old.db() as db:
            append_registry_version(db, "1.0.0")
            append_registry_version(db, "1.1.0", "1.0.0")
            self.assert_database(db, V7)
        return old

    def assert_database(self, db, version):
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], version)
        self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        m07_tables = {name for (name,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name GLOB 'm07_*'"
        )}
        self.assertEqual(m07_tables, M07_TABLES if version >= 8 else set())

    def assert_upgraded(self, directory, history, head):
        store = storage.Store(directory)
        with closing(store.connect()) as db:
            self.assert_database(db, V9)
            self.assertEqual(registry_history(db), history)
            self.assertEqual(db.execute("SELECT registry_version FROM m06_registry_head").fetchone()[0], head)
            for table in M07_TABLES:
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_v7_upgrade_preserves_exact_sealed_registry_and_stable_ids(self):
        old = self.historical_v7()
        with closing(old.connect()) as db:
            history = registry_history(db)
        self.assert_upgraded(old.directory, history, "1.1.0")
        self.assert_upgraded(old.directory, history, "1.1.0")

    def test_v7_wal_backup_can_restore_and_repeat_upgrade(self):
        old = self.historical_v7()
        backup = self.root / "consistent-v7.sqlite3"
        restored = self.root / "恢复 v7"
        restored.mkdir()
        destination = restored / old.path.name

        with closing(old.connect()) as source, closing(sqlite3.connect(backup)) as copy:
            source.execute("PRAGMA wal_autocheckpoint=0")
            with source:
                append_registry_version(source, "1.2.0", "1.1.0")
            self.assertGreater(old.path.with_suffix(".sqlite3-wal").stat().st_size, 0)
            archived_history = registry_history(source)
            source.backup(copy)
            copy.execute("PRAGMA foreign_keys=ON")
            self.assert_database(copy, V7)
            self.assertEqual(registry_history(copy), archived_history)
            with source:
                append_registry_version(source, "1.3.0", "1.2.0")
            live_history = registry_history(source)
            with closing(sqlite3.connect(destination)) as restored_db:
                copy.backup(restored_db)
                restored_db.execute("PRAGMA foreign_keys=ON")
                self.assert_database(restored_db, V7)
                self.assertEqual(registry_history(restored_db), archived_history)

        self.assert_upgraded(old.directory, live_history, "1.3.0")
        self.assert_upgraded(restored, archived_history, "1.2.0")
        self.assert_upgraded(restored, archived_history, "1.2.0")

    def test_failed_v8_upgrade_leaves_v7_schema_and_contents_recoverable(self):
        old = self.historical_v7()
        with closing(old.connect()) as db:
            history = registry_history(db)
        migration = self.root / "008_m07_registry_drafts.sql"
        migration.write_text(
            "CREATE TABLE m07_partial (id INTEGER); PRAGMA user_version=8;"
            "SELECT * FROM no_such_table;",
            encoding="utf-8",
        )
        with patch.object(storage, "MIGRATION_DIRECTORY", self.root):
            with self.assertRaisesRegex(sqlite3.OperationalError, "no such table"):
                storage.Store(old.directory)
        with closing(old.connect()) as db:
            self.assert_database(db, V7)
            self.assertEqual(registry_history(db), history)
        self.assert_upgraded(old.directory, history, "1.1.0")

    def test_fresh_workspace_reopens_current_schema_and_other_store_roles_stay_v1(self):
        workspace = storage.Store(self.root)
        fixture = storage.Store(self.root, fixture=True)
        diagnostic = storage.Store(self.root, diagnostic=True)
        self.assertEqual(workspace.path, self.root / "connectivity.sqlite3")
        self.assertEqual(fixture.path, self.root / "synthetic_contract.sqlite3")
        self.assertEqual(diagnostic.path, self.root / "api-diagnostics" / "connectivity.sqlite3")
        for store, version in (
            (storage.Store(self.root), V9),
            (storage.Store(self.root, fixture=True), 1),
            (storage.Store(self.root, diagnostic=True), 1),
        ):
            with self.subTest(path=store.path), closing(store.connect()) as db:
                self.assert_database(db, version)
