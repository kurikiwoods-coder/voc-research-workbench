from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
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
from src.raw_store.personal_backup import backup_personal_v10, restore_personal_v10
from src.raw_store.personal_validation import BatchContext, Budget, OperationGrant, Receipt, ValidationLedger
from src.raw_store.runtime_binding import APPLICATION_IDS


START = "2026-01-01T00:00:00Z"
END = "2026-01-03T00:00:00Z"
DIGEST = "1" * 64
BUDGET = Budget(4, 4, 80, 40, 120, 100)
V11_MIGRATION = "011_personal_live_admission.sql"


def trusted(db, batch, grant):
    return True


def ledger_rows(db):
    names = db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'personal_validation_%'")
    return {row[0]: [tuple(record) for record in db.execute(f'SELECT * FROM "{row[0]}" ORDER BY rowid')]
            for row in names}


class PersonalLiveMigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.workspace = self.root / "workspace"
        with patch.object(storage, "PERSONAL_MIGRATIONS", storage.PERSONAL_MIGRATIONS[:1]):
            binding = provision(self.workspace, "合成迁移项目", "合成范围", uuid4())
            self.old = self.store()
        self.context = BatchContext(
            binding["study_id"], binding["scope_id"], binding["scope_version"], "fixture-actor",
            "fixture-owner", "fixture-authorization", "fixture.v1",
        )
        self.ledger = ValidationLedger(
            self.old, engineering_fixture=True, clock=lambda: datetime(2026, 1, 2, tzinfo=UTC),
        )

    def store(self, directory=None):
        return storage.Store(directory or self.workspace, edition=Edition.PERSONAL)

    def seed_history(self):
        self.ledger.bind_credential(
            self.context, "search", "tavily", "fixture-account", "fixture-channel", "fixture-revision",
            "fixture-credentials", trusted,
        )
        batch = self.ledger.draft(
            self.context, START, END, BUDGET, "USD", 6, 25, "fixture-batch", trusted,
        )
        batch_id = batch["batch_id"]
        grant = OperationGrant(
            "search", "tavily", "fixture-account", "fixture-channel", "fixture-revision", "", None,
            "fixture-material", "fixture-source", DIGEST, DIGEST, "", START, END, BUDGET, "fixture-grant",
        )
        saved_grant = self.ledger.authorize(batch_id, self.context, grant, trusted)
        request = self.ledger.reserve(
            batch_id, self.context, saved_grant["grant_id"], 1, DIGEST, Budget(1, 1, 0, 0, 0, 10), trusted,
        )
        request_id = request["request_id"]
        self.ledger.claim(request_id, self.context, trusted)
        self.ledger.receipt(
            request_id, self.context, Receipt(
                DIGEST, 200, "fixture-receipt", credits=1, actual_units=10, valid=True,
                reason="fixture-response", source_sha256=DIGEST,
            ), trusted,
        )
        self.ledger.add_evidence(
            batch_id, self.context, "C0-3", "synthetic_fixture", "fixture-evidence", DIGEST, "fixture", trusted,
        )
        return batch_id

    def test_v10_to_v11_preserves_history_and_separates_formal_evidence(self):
        batch_id = self.seed_history()
        with self.old.db() as db:
            before = ledger_rows(db)
        updated = self.store()
        with updated.db() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 11)
            self.assertEqual(db.execute("PRAGMA application_id").fetchone()[0], APPLICATION_IDS[Edition.PERSONAL])
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(ledger_rows(db), before)
            for kind, requirement in (("formal_live", "C0-1"), ("formal_offline", "C0-5")):
                with self.subTest(kind=kind), self.assertRaises(sqlite3.IntegrityError):
                    db.execute(
                        """INSERT INTO personal_validation_evidence
                           (batch_id,requirement,kind,evidence_ref,evidence_sha256,reason,actor_ref,occurred_at)
                           VALUES (?,?,?,'formal-evidence',?,'formal','fixture-actor',?)""",
                        (batch_id, requirement, kind, DIGEST, START),
                    )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE personal_validation_batches SET mode='formal_live' WHERE batch_id=?", (batch_id,))
        with self.assertRaisesRegex(ValueError, "数据库版本"):
            self.old.connect()

    def test_populated_v10_snapshot_captures_wal_and_restores_independently(self):
        backup = self.root / "pre-v11.sqlite3"
        restored = self.root / "restore"
        with closing(self.old.connect()) as live:
            live.execute("PRAGMA wal_autocheckpoint=0")
            self.seed_history()
            self.assertGreater(self.old.path.with_suffix(".sqlite3-wal").stat().st_size, 32)
            before = ledger_rows(live)
            backup_personal_v10(self.old.path, backup)
            with self.assertRaises(FileExistsError):
                backup_personal_v10(self.old.path, backup)
        restore_personal_v10(backup, restored)
        with self.assertRaises(FileExistsError):
            restore_personal_v10(backup, restored)
        with patch.object(storage, "PERSONAL_MIGRATIONS", storage.PERSONAL_MIGRATIONS[:1]):
            with self.store(restored).db() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 10)
                self.assertEqual(ledger_rows(db), before)
        with self.store(restored).db() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 11)
            self.assertEqual(ledger_rows(db), before)
        with self.old.db() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 10)
            self.assertEqual(ledger_rows(db), before)

    def test_failed_v11_sql_rolls_back_rebuilt_tables(self):
        self.seed_history()
        with self.old.db() as db:
            before = ledger_rows(db)
            schema = [tuple(row) for row in db.execute("SELECT * FROM sqlite_schema ORDER BY rowid")]
        migrations = self.root / "broken"
        migrations.mkdir()
        original = (storage.MIGRATION_DIRECTORY / V11_MIGRATION).read_text("utf-8")
        (migrations / V11_MIGRATION).write_text(
            original + "\nSELECT * FROM missing_fixture;\n", encoding="utf-8",
        )
        with patch.object(storage, "MIGRATION_DIRECTORY", migrations), self.assertRaisesRegex(
            sqlite3.OperationalError, "no such table",
        ):
            self.store()
        with self.old.db() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 10)
            self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM sqlite_schema ORDER BY rowid")], schema)
            self.assertEqual(ledger_rows(db), before)

    def test_two_processes_upgrade_the_same_v10_workspace(self):
        self.seed_history()
        with self.old.db() as db:
            before = ledger_rows(db)
        script = """import sys
import time
from pathlib import Path
from src.edition_policy import Edition
from src.raw_store.store import Store

Path(sys.argv[2]).touch()
while not Path(sys.argv[3]).is_file():
    time.sleep(0.01)
store = Store(Path(sys.argv[1]), edition=Edition.PERSONAL)
assert store.one('PRAGMA user_version')['user_version'] == 11
"""
        start = self.root / "start"
        processes = []
        try:
            for index in range(2):
                ready = self.root / f"ready-{index}"
                process = subprocess.Popen(
                    [sys.executable, "-c", script, str(self.workspace), str(ready), str(start)],
                    cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
                processes.append(process)
                deadline = time.monotonic() + 10
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists())
            start.touch()
            for process in processes:
                output, _ = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, output.decode(errors="replace"))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)
        with self.store().db() as db:
            self.assertEqual(ledger_rows(db), before)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
