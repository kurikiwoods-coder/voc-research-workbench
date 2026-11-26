"""Exercise the v10 migration with local, synthetic SQLite workspaces."""

from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.dashboard.personal_workspace import provision
from src.edition_policy import Edition
from src.raw_store import store as storage
from src.raw_store.personal_backup import backup_personal_v9
from src.raw_store.runtime_binding import APPLICATION_IDS, MARKER
from test_m06_constraints import insert
from test_m07_migration import append_registry_version


PERSONAL_ID = APPLICATION_IDS[Edition.PERSONAL]
BATCHES = "personal_validation_batches"
APPROVALS = "personal_provider_approval_events"
CREDENTIAL = "personal_credential_binding"
ROOT = Path(__file__).resolve().parents[1]


def schema_objects(db):
    return {tuple(row) for row in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema")}


def table_rows(db, schema):
    return {
        name: {tuple(row) for row in db.execute(f'SELECT * FROM "{name}"')}
        for kind, name, _, _ in schema if kind == "table"
    }


class PreAdmissionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(
            prefix="voc-migration 个人 ", dir=os.environ.get("LOCALAPPDATA") if os.name == "nt" else None,
        ))).resolve()

    def personal(self, directory):
        return storage.Store(directory, edition=Edition.PERSONAL)

    def historical(self, directory):
        with patch.object(storage, "PERSONAL_MIGRATIONS", ()):
            binding = provision(directory, "合成迁移项目", "合成范围", uuid4())
            store = self.personal(directory)
        with store.db() as db:
            insert(db, CREDENTIAL, study_id=binding["study_id"], scope_id=binding["scope_id"],
                   credential_revision="a" * 32)
            append_registry_version(db, "1.0.0")
        return store, binding

    def approval(self, db, binding, identifier, kind, prior=None):
        insert(
            db, APPROVALS, event_id=identifier, kind=kind, prior_event_id=prior, edition="PERSONAL",
            study_id=binding["study_id"], scope_id=binding["scope_id"], scope_version=binding["scope_version"],
            purpose="personal_research", provider="synthetic-provider", channel_ref="fixture-channel",
            model="fixture-model", account_ref="fixture-account", credential_revision="a" * 32,
            policy_version="fixture-v1", actor_ref="fixture-actor", owner_ref="fixture-owner",
            authorization_ref="local:fixture-grant", effective_at="2026-11-01T00:00:00+00:00",
            expires_at="2026-12-01T00:00:00+00:00", budget_unit="requests", budget_limit=1,
            risks="[]", request_sha256="b" * 64, request_key=identifier, evidence_count=0,
        )

    def assert_database(self, store, version, application_id):
        with closing(store.connect()) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], version)
            self.assertEqual(db.execute("PRAGMA application_id").fetchone()[0], application_id)
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual([row[0] for row in db.execute("PRAGMA integrity_check")], ["ok"])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (BATCHES,)).fetchone() is not None,
                version == 10,
            )
            if version == 10:
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {BATCHES}").fetchone()[0], 0)

    def test_fresh_and_reopened_workspaces_keep_six_schema_targets(self):
        for edition, version, application_id in ((Edition.BUSINESS, 9, 0), (Edition.PERSONAL, 10, PERSONAL_ID)):
            with self.subTest(edition=edition):
                directory = self.root / edition.value
                for role, expected in (({}, version), ({"fixture": True}, 1), ({"diagnostic": True}, 1)):
                    for _ in range(2):
                        self.assert_database(storage.Store(directory, edition=edition, **role), expected, application_id)

    def test_active_wal_backup_is_exclusive_and_restores_v9_history(self):
        old, binding = self.historical(self.root / "live")
        recovered = self.root / "restored"
        recovered.mkdir(mode=0o700)
        destination = recovered / old.path.name
        with closing(old.connect()) as db:
            db.execute("PRAGMA wal_autocheckpoint=0")
            with db:
                self.approval(db, binding, "submit", "submitted")
                self.approval(db, binding, "approve", "approved", "submit")
                self.approval(db, binding, "revoke", "revoked", "approve")
                append_registry_version(db, "1.1.0", "1.0.0")
            self.assertGreater(old.path.with_suffix(".sqlite3-wal").stat().st_size, 32)
            old_schema = schema_objects(db)
            archived_rows = table_rows(db, old_schema)
            backup_personal_v9(old.path, destination)
            with self.assertRaises(FileExistsError):
                backup_personal_v9(old.path, destination)
            with db:
                append_registry_version(db, "1.2.0", "1.1.0")
            live_rows = table_rows(db, old_schema)
        self.assertNotEqual(archived_rows, live_rows)
        shutil.copyfile(old.directory / MARKER, recovered / MARKER)
        with patch.object(storage, "PERSONAL_MIGRATIONS", ()):
            self.assert_database(self.personal(recovered), 9, PERSONAL_ID)
        for directory, expected_rows in ((old.directory, live_rows), (recovered, archived_rows)):
            with self.subTest(directory=directory):
                for _ in range(2):
                    updated = self.personal(directory)
                    self.assert_database(updated, 10, PERSONAL_ID)
                    with updated.db() as db:
                        self.assertTrue(old_schema.issubset(schema_objects(db)))
                        self.assertEqual(table_rows(db, old_schema), expected_rows)
                        self.assertEqual(db.execute(
                            f"SELECT kind, prior_event_id FROM {APPROVALS} WHERE event_id='revoke'"
                        ).fetchone()[:], ("revoked", "approve"))
        with self.assertRaisesRegex(ValueError, "v9"):
            backup_personal_v9(old.path, recovered / "wrong-version.sqlite3")

    def test_mismatched_application_id_and_v1_targets_reject_workbench_files(self):
        old, _ = self.historical(self.root / "old")
        business = storage.Store(self.root / "business")
        swapped = self.root / "misbound"
        swapped.mkdir(mode=0o700)
        shutil.copyfile(old.directory / MARKER, swapped / MARKER)
        shutil.copyfile(business.path, swapped / old.path.name)
        with self.assertRaisesRegex(ValueError, "产品版本"):
            self.personal(swapped)
        with self.assertRaisesRegex(ValueError, "个人工作库"):
            backup_personal_v9(swapped / old.path.name, self.root / "failed-backup.sqlite3")
        self.assertFalse((self.root / "failed-backup.sqlite3").exists())
        updated = self.personal(old.directory)
        for role in ({"fixture": True}, {"diagnostic": True}):
            store = storage.Store(old.directory, edition=Edition.PERSONAL, **role)
            with closing(updated.connect()) as source, closing(sqlite3.connect(store.path)) as target:
                source.backup(target)
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, "数据库版本"):
                storage.Store(old.directory, edition=Edition.PERSONAL, **role)
            with self.assertRaisesRegex(ValueError, "数据库版本"):
                store.connect()

    def test_v9_gateway_rejects_v10_and_existing_store_refuses_new_connection(self):
        old, _ = self.historical(self.root / "old")
        updated = self.personal(old.directory)
        with patch.object(storage, "PERSONAL_MIGRATIONS", ()), self.assertRaisesRegex(ValueError, "数据库版本"):
            self.personal(old.directory)
        with self.assertRaisesRegex(ValueError, "数据库版本"):
            old.connect()
        self.assert_database(updated, 10, PERSONAL_ID)

    def failing_migration(self, tail):
        directory = self.root / "migration"
        directory.mkdir()
        filename = storage.PERSONAL_MIGRATIONS[0]
        original = (storage.MIGRATION_DIRECTORY / filename).read_text("utf-8")
        (directory / filename).write_text(original + tail, encoding="utf-8")
        return directory

    def assert_rolled_back(self, old, before):
        self.assert_database(old, 9, PERSONAL_ID)
        with old.db() as db:
            self.assertEqual(schema_objects(db), before)
        self.assert_database(self.personal(old.directory), 10, PERSONAL_ID)

    def test_failed_sql_rolls_back_ddl_and_user_version(self):
        old, _ = self.historical(self.root / "old")
        with old.db() as db:
            before = schema_objects(db)
        failing = self.failing_migration("\nSELECT * FROM missing_migration_fixture;\n")
        with patch.object(storage, "MIGRATION_DIRECTORY", failing), self.assertRaisesRegex(
            sqlite3.OperationalError, "no such table",
        ):
            self.personal(old.directory)
        self.assert_rolled_back(old, before)

    def launch(self, script, *arguments):
        child = subprocess.Popen(
            [sys.executable, "-c", script, *map(str, arguments)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.addCleanup(child.__exit__, None, None, None)
        self.addCleanup(self.stop_child, child)
        return child

    @staticmethod
    def stop_child(child):
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)

    def await_ready(self, child, path):
        deadline = time.monotonic() + 15
        while not path.is_file() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        if not path.is_file():
            self.stop_child(child)
            self.fail(child.communicate(timeout=10)[0].decode(errors="replace"))

    def test_process_killed_after_ddl_before_commit_leaves_v9(self):
        old, _ = self.historical(self.root / "old")
        with old.db() as db:
            before = schema_objects(db)
        migration = self.failing_migration("\nSELECT pause_before_migration_commit();\n")
        witness = self.root / "transaction-open"
        child = self.launch(
            """import sys, time
from pathlib import Path
from src.edition_policy import Edition
from src.raw_store import store as storage

original = storage.configure_workspace_connection

def pause():
    Path(sys.argv[3]).touch()
    time.sleep(120)

def configure(db):
    original(db)
    db.create_function('pause_before_migration_commit', 0, pause)

storage.configure_workspace_connection = configure
storage.MIGRATION_DIRECTORY = Path(sys.argv[2])
storage.Store(Path(sys.argv[1]), edition=Edition.PERSONAL)
""", old.directory, migration, witness,
        )
        self.await_ready(child, witness)
        self.stop_child(child)
        self.assertNotEqual(child.returncode, 0)
        self.assert_rolled_back(old, before)

    def test_parallel_processes_serialize_v9_to_v10(self):
        old, _ = self.historical(self.root / "old")
        start = self.root / "start"
        script = """import sys, time
from pathlib import Path
from src.edition_policy import Edition
from src.raw_store.store import Store

Path(sys.argv[2]).touch()
start = Path(sys.argv[3])
while not start.is_file():
    time.sleep(0.01)
store = Store(Path(sys.argv[1]), edition=Edition.PERSONAL)
assert store.one('PRAGMA user_version')['user_version'] == 10
"""
        children = []
        for index in range(2):
            ready = self.root / f"ready-{index}"
            child = self.launch(script, old.directory, ready, start)
            children.append(child)
            self.await_ready(child, ready)
        start.touch()
        for child in children:
            output, _ = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, output.decode(errors="replace"))
        self.assert_database(self.personal(old.directory), 10, PERSONAL_ID)
