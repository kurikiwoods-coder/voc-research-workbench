"""Verify personal approval storage on isolated native SQLite databases."""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.dashboard.personal_workspace import provision
from src.edition_policy import Edition
from src.raw_store import store as storage
from src.raw_store.runtime_binding import APPLICATION_IDS, MARKER
from test_m06_constraints import insert
from test_m07_migration import append_registry_version


EVENTS = "personal_provider_approval_events"
EVIDENCE = "personal_approval_evidence"
START = "2026-11-01T00:00:00+00:00"
END = "2026-12-01T00:00:00+00:00"


def snapshot(db):
    schema = {
        tuple(row) for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE tbl_name NOT GLOB 'personal_*'"
        )
    }
    rows = {
        name: {tuple(row) for row in db.execute(f'SELECT * FROM "{name}"')}
        for kind, name, _, _ in schema if kind == "table"
    }
    return schema, rows


class PersonalApprovalMigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(
            prefix="voc-personal-migration-", dir=os.environ.get("LOCALAPPDATA") if os.name == "nt" else None,
        ))).resolve()
        self.path = self.root / "个人审批"

    def open(self):
        return storage.Store(self.path, edition=Edition.PERSONAL)

    def provision(self):
        binding = provision(self.path, "合成审批核验", "仅限迁移夹具", uuid4())
        return {key: binding[key] for key in ("study_id", "scope_id", "scope_version")}

    def assert_healthy(self, db, version):
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], version)
        self.assertEqual(db.execute("PRAGMA application_id").fetchone()[0], APPLICATION_IDS[Edition.PERSONAL])
        self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        tables = {name for (name,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name GLOB 'personal_*'"
        )}
        self.assertEqual(tables, {EVENTS, EVIDENCE, "personal_credential_binding"} if version == 9 else set())

    def historical(self):
        with patch.object(storage, "MIGRATIONS", storage.MIGRATIONS[:8]):
            binding = self.provision()
            store = self.open()
        with store.db() as db:
            append_registry_version(db, "1.0.0")
        return store, binding

    def event(self, db, binding, *, event_id="submission", kind="submitted", prior_event_id=None, **changes):
        values = {
            "edition": "PERSONAL", "purpose": "personal_research", "provider": "synthetic-provider",
            "channel_ref": "channel-a", "model": "synthetic-model", "account_ref": "synthetic-account",
            "credential_revision": "revision-1", "policy_version": "fixture-policy",
            "actor_ref": "fixture-actor", "owner_ref": "fixture-owner", "authorization_ref": "local:fixture-grant",
            "effective_at": START, "expires_at": END, "budget_unit": "request", "budget_limit": 5, "risks": "[]",
            "request_sha256": "a" * 64, "request_key": event_id, "evidence_count": 1,
        }
        insert(db, EVENTS, event_id=event_id, kind=kind, prior_event_id=prior_event_id,
               **(values | binding | changes))

    def evidence(self, db, event_id="submission"):
        insert(db, EVIDENCE, event_id=event_id, evidence_ref="local:fixture-evidence",
               kind="fixture-terms", sha256="b" * 64, terms_version="fixture-v1", verified_at=START, expires_at=END)

    def test_v8_wal_snapshot_and_live_differences_survive_migration_and_reopen(self):
        old, binding = self.historical()
        copy = self.root / "恢复备份"
        copy.mkdir(mode=0o700)
        (copy / MARKER).write_bytes((old.directory / MARKER).read_bytes())
        with closing(old.connect()) as source, closing(sqlite3.connect(copy / old.path.name)) as target:
            source.execute("PRAGMA wal_autocheckpoint=0")
            with source:
                append_registry_version(source, "1.1.0", "1.0.0")
            self.assertGreater(old.path.with_suffix(".sqlite3-wal").stat().st_size, 0)
            self.assert_healthy(source, 8)
            archived = snapshot(source)
            source.backup(target)
            with source:
                append_registry_version(source, "1.2.0", "1.1.0")
            live = snapshot(source)
        self.assertNotEqual(live, archived)
        for directory, expected in ((self.path, live), (copy, archived)):
            for _ in range(2):
                with self.subTest(directory=directory), storage.Store(directory, edition=Edition.PERSONAL).db() as db:
                    self.assert_healthy(db, 9)
                    self.assertEqual(snapshot(db), expected)
                    self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {EVENTS}").fetchone()[0], 0)
        with self.open().db() as db:
            self.event(db, binding)
            self.evidence(db)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "retained"):
                insert(db, EVIDENCE, event_id="submission", evidence_ref="local:late-evidence",
                       kind="fixture-terms", sha256="c" * 64, terms_version="fixture-v1",
                       verified_at=START, expires_at=END)

    def test_failed_migration_rolls_back_ddl_and_version(self):
        old, binding = self.historical()
        with old.db() as db:
            before = snapshot(db)
        failing = self.root / storage.MIGRATIONS[-1]
        migration = (storage.MIGRATION_DIRECTORY / failing.name).read_text(encoding="utf-8")
        failing.write_text(migration + "\nSELECT * FROM nonexistent;\n", encoding="utf-8")
        with patch.object(storage, "MIGRATION_DIRECTORY", self.root):
            with self.assertRaisesRegex(sqlite3.OperationalError, "no such table"):
                self.open()
        with old.db() as db:
            self.assert_healthy(db, 8)
            self.assertEqual(snapshot(db), before)
        with self.open().db() as db:
            self.assert_healthy(db, 9)
            self.assertEqual(snapshot(db), before)
            self.event(db, binding)

    def test_lineage_scope_and_idempotency_protect_history(self):
        binding = self.provision()
        other = self.provision()
        with self.open().db() as db:
            self.event(db, binding)
            self.event(db, other, event_id="other", request_key="submission")
            self.evidence(db)
            for changes in (
                {"scope_id": other["scope_id"]}, {"scope_version": "v2"}, {"edition": "BUSINESS"},
                {"credential_revision": "revision-2"}, {"account_ref": "other-account"},
                {"effective_at": "2026-10-01T00:00:00+00:00"},
            ):
                with self.subTest(changes=changes), self.assertRaises(sqlite3.IntegrityError):
                    self.event(db, binding, event_id="invalid", kind="approved", prior_event_id="submission", **changes)
            self.event(db, binding, event_id="approval", kind="approved", prior_event_id="submission")
            self.event(db, binding, event_id="withdrawn", kind="revoked", prior_event_id="approval",
                       effective_at="2026-12-02T00:00:00+00:00")
            self.assert_healthy(db, 9)
            for statement in (
                f"UPDATE {EVENTS} SET request_key='rewritten'",
                f"DELETE FROM {EVENTS}",
                f"INSERT OR REPLACE INTO {EVENTS} SELECT * FROM {EVENTS} WHERE event_id='submission'",
                f"UPDATE {EVIDENCE} SET evidence_ref='rewritten'",
                f"DELETE FROM {EVIDENCE}",
                f"INSERT OR REPLACE INTO {EVIDENCE} SELECT * FROM {EVIDENCE}",
            ):
                with self.subTest(statement=statement), self.assertRaisesRegex(sqlite3.IntegrityError, "retained"):
                    db.execute(statement)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "retained"):
                self.event(db, binding, event_id="reused", request_key="submission")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "retained"):
                self.event(db, binding, event_id="fork", kind="revoked", prior_event_id="submission")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "lineage"):
                self.event(db, binding, event_id="invalid", kind="revoked", prior_event_id="withdrawn",
                           effective_at="2026-12-03T00:00:00+00:00")
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {EVENTS}").fetchone()[0], 4)
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {EVIDENCE}").fetchone()[0], 1)

    def test_business_and_diagnostics_cannot_write_personal_approvals(self):
        binding = self.provision()
        business = storage.Store(self.root / "business")
        with business.db() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 9)
            self.assertEqual(db.execute("PRAGMA application_id").fetchone()[0], 0)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "personal workspace"):
                self.event(db, binding)
        for role in ({"diagnostic": True}, {"fixture": True}):
            store = storage.Store(self.root / "isolated", **role)
            with store.db() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_schema WHERE name = ?", (EVENTS,)).fetchone())
