"""Synthetic permission and access regressions for M05-R2."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from threading import Barrier
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.dashboard.app import create_app
import test_corpus as fixtures
from test_imports import HEADERS, ORIGIN, discard_empty_registry_fixture_schema


class CorpusLicenseTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.CorpusTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.db = self.case.app.state.store
        self.today = datetime.now(timezone.utc).date()

    def add(self, name="quote", license_note="CC BY-SA 4.0", *, address=None, privacy="unknown"):
        row = [*fixtures.ROW[:2], address or f"https://source.example.test/{name}",
               fixtures.ROW[3], license_note, "public"]
        batch, records = self.case.import_rows([row], filename=f"{name}.csv", privacy=privacy)
        return batch, records[0]

    def eligible(self, record):
        return self.case.client.get(f"{self.case.root}/records/{record}/eligible")

    def revoke(self, record, **kwargs):
        return self.case.verify(record, decision="excluded", reason="管控状态更新",
                                license_status="revoked", retention_until=None, **kwargs)

    def restoration(self, **kwargs):
        return {
            "reauthorize": True, "license_evidence_ref": "local:new-written-permit", "reason": "复核本机新材料",
            "basis": "核对新签署材料的签发方与研究范围",
            "license_issued_on": self.today.isoformat(),
        } | kwargs

    def test_denied_pending_expired_and_conflicting_notes_never_count_as_grants(self):
        cases = (
            ("未授权，等待书面审批", "denied"),
            ("授权尚未取得", "denied"),
            ("许可审批中", "pending"),
            ("许可状态未知", "pending"),
            ("許可狀態：尚未取得授權。", "denied"),
            ("已获许可，但随后撤销", "revoked"),
            ("授權說明：已获许可；其後已撤回。", "revoked"),
            ("License review: permission was not granted.", "denied"),
            ("Notice: LICENSE REVOKED.", "revoked"),
            ("License approved, but withdrawn by owner.", "revoked"),
            ("License pending written approval.", "pending"),
            ("许可已过期。", "expired"),
        )
        for index, (note, state) in enumerate(cases):
            with self.subTest(note=note):
                _, record = self.add(f"note-{index}", note)
                self.assertEqual(self.case.get(record)["license_status"], state)
                blocked = self.case.review(record)
                self.assertEqual(blocked.status_code, 422, blocked.text)
                self.assertIsNone(self.case.get(record)["raw_text"])
                self.assertEqual(self.eligible(record).status_code, 409)
        self.assertEqual(self.db.rows("SELECT * FROM corpus_licenses"), [])

    def test_approval_needs_explicit_state_and_reference_with_review_basis(self):
        _, record = self.add(license_note="已获明确授权，许可尚未撤销")
        for invalid in (
            {"license_status": None}, {"license_status": "pending"}, {"license_status": "unknown"},
            {"license_evidence_ref": None}, {"license_evidence_ref": "已同意"},
            {"license_evidence_ref": "https://source.example.test/quote"}, {"basis": ""},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.case.review(record, **invalid).status_code, 422)
        self.assertEqual(self.eligible(record).status_code, 409)
        reviewed = self.case.verify(record, license_evidence_ref="https://licensing.example.test/written-grant")
        self.assertEqual(reviewed["license_status"], "authorized")
        found = self.eligible(record).json()
        self.assertEqual(found["raw_text"], fixtures.QUOTE)
        self.assertTrue(found["engineering_eligible"])
        self.assertFalse(found["research_eligible"])
        self.assertFalse(found["outbound_allowed"])
        self.assertNotIn("history", found)

    def test_prefixed_withdrawal_is_recorded_and_old_grant_stays_blocked(self):
        for index, note in enumerate((
            "复核：授权已撤销", "複核：授權已撤銷！", "Source review: the license has been withdrawn.",
        )):
            with self.subTest(note=note):
                _, record = self.add(f"withdrawal-{index}")
                self.case.verify(record)
                stopped = self.case.verify(record, decision="excluded", reason=note, retention_until=None)
                self.assertEqual(stopped["license_status"], "revoked")
                self.assertTrue(stopped["source_permission_revoked"])
                self.assertIsNone(stopped["raw_text"])
                self.assertEqual(self.case.review(record).status_code, 409)
                self.assertEqual(self.eligible(record).status_code, 409)
        states = self.db.rows("SELECT state FROM corpus_licenses WHERE state='revoked'")
        self.assertEqual(len(states), 3)

    def test_reauthorization_needs_new_dated_evidence_and_keeps_other_copies_restricted(self):
        address = "https://source.example.test/library"
        _, record = self.add("original", address=address)
        _, alias = self.add("alias", address=address, privacy="public")
        _, independent = self.add("independent")
        self.case.verify(record)
        self.case.verify(alias, license_evidence_ref="local:other-old-permit")
        self.assertEqual(self.case.verify(independent)["duplicate"]["record_count"], 3)
        first = self.revoke(record)
        self.assertTrue(first["can_reauthorize"])
        self.assertEqual(first["license_status"], "revoked")
        self.assertEqual(self.case.get(independent)["duplicate"]["record_count"], 1)
        old = (self.today - timedelta(days=1)).isoformat()
        for invalid in (
            {"license_evidence_ref": "local:fixture-license"},
            {"license_evidence_ref": "local:OTHER-OLD-PERMIT"},
            {"license_issued_on": old}, {"license_issued_on": None},
            {"license_issued_on": (self.today + timedelta(days=1)).isoformat()},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.case.review(record, **self.restoration(**invalid)).status_code, 422)
                self.assertIsNone(self.case.get(record)["raw_text"])
        reopened = self.case.verify(record, **self.restoration())
        self.assertEqual(reopened["raw_text"], fixtures.QUOTE)
        self.assertEqual(reopened["duplicate"]["record_count"], 2)
        self.assertEqual(len(reopened["history"]), 3)
        self.assertEqual(self.case.verify(record, **self.restoration()), reopened)
        self.assertEqual(self.eligible(alias).status_code, 409)
        self.assertEqual(self.case.review(alias).status_code, 409)
        self.assertEqual(self.case.verify(record, reason="补充研究范围说明",
                                         license_evidence_ref="local:new-written-permit")["status"], "verified")
        self.revoke(record)
        self.assertEqual(self.case.review(record, **self.restoration()).status_code, 422)
        self.assertEqual(self.eligible(record).status_code, 409)

    def test_legacy_audit_reference_cannot_be_reused_as_the_new_grant(self):
        _, record = self.add()
        self.case.verify(record)
        with self.db.db() as db:
            # Recreate a v4 style approval with a reference embedded in a historical basis.
            db.execute("""INSERT INTO corpus_reviews
                          (record_id, decision, role, reason, basis, retention_until, dedupe_group, reviewed_at)
                          SELECT record_id, decision, role, reason, ?, retention_until, dedupe_group, reviewed_at
                          FROM corpus_reviews WHERE record_id=?""", ("旧授权证明 local:archived-licence。", record))
        self.revoke(record)
        denied = self.case.review(record, **self.restoration(license_evidence_ref="local:archived-licence"))
        self.assertEqual(denied.status_code, 422)
        self.assertEqual(self.eligible(record).status_code, 409)
        self.assertEqual(self.case.verify(record, **self.restoration())["license_status"], "authorized")

    def test_staging_and_history_hide_raw_for_pending_excluded_revoked_and_expired(self):
        for name in ("pending", "excluded", "revoked", "expired"):
            with self.subTest(state=name):
                batch, record = self.add(name)
                if name != "pending":
                    self.case.verify(record)
                if name == "excluded":
                    self.case.verify(record, decision="excluded", reason="范围之外", retention_until=None)
                if name == "revoked":
                    self.revoke(record)
                now = self.today + timedelta(days=40 if name == "expired" else 0)
                with patch("src.raw_store.corpus.now", return_value=now.isoformat()), \
                        patch("src.raw_store.imports.now", return_value=now.isoformat()):
                    history_path = f"/api/imports/{self.case.study}/batches/{batch}"
                    reply = self.case.client.get(history_path)
                    self.assertTrue(reply.is_success, reply.status_code)
                    row = reply.json()["rows"][0]
                    self.assertIsNone(row["raw_text"])
                    self.assertEqual(row["fields"], {})
                    self.assertEqual(row["originals"], [])
                    self.assertEqual(self.eligible(record).status_code, 409)
                    self.assertNotIn("图书馆预约座位", self.case.client.get(history_path + "/errors.csv").text)
                candidate = self.db.one("SELECT raw_text, fields_json, originals_json FROM import_candidates WHERE record_id=?",
                                        (record,))
                self.assertEqual(candidate, {"raw_text": None, "fields_json": "{}", "originals_json": "[]"})
                self.assertEqual(self.db.one("SELECT raw_text FROM import_rows WHERE record_id=?", (record,))["raw_text"],
                                 fixtures.QUOTE)

    def test_revocation_and_review_concurrency_has_one_effective_result(self):
        _, record = self.add()
        self.case.verify(record)
        start = Barrier(2, timeout=5)

        def review(**kwargs):
            start.wait()
            return self.case.review(record, **kwargs)

        with ThreadPoolExecutor(max_workers=2) as pool:
            withdrawal = pool.submit(review, decision="excluded", license_status="revoked",
                                     reason="研究来源状态改变", retention_until=None)
            stale = pool.submit(review, reason="再次引用原来的材料")
            self.assertEqual(withdrawal.result().status_code, 200)
            self.assertIn(stale.result().status_code, {200, 409})
        self.assertEqual(self.case.get(record)["license_status"], "revoked")
        self.assertEqual(self.eligible(record).status_code, 409)
        retry = self.case.verify(record, decision="excluded", license_status="revoked",
                                 reason="研究来源状态改变", retention_until=None)
        self.assertTrue(retry["source_permission_revoked"])
        self.assertEqual(len(self.db.rows("SELECT * FROM corpus_licenses WHERE state='revoked'")), 1)

    def test_failed_structured_event_insert_rolls_back_snapshot_and_review(self):
        _, record = self.add()
        with self.db.db() as db:
            db.execute("""CREATE TRIGGER test_license_failure BEFORE INSERT ON corpus_licenses
                       BEGIN SELECT RAISE(ABORT, 'synthetic permission write fault'); END""")
        response = self.case.review(record)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.db.rows("SELECT * FROM corpus_reviews"), [])
        self.assertEqual(self.db.rows("SELECT * FROM corpus_snapshots"), [])
        self.assertEqual(self.db.rows("SELECT * FROM corpus_licenses"), [])
        self.assertEqual(self.eligible(record).status_code, 409)
        with self.db.db() as db:
            db.execute("DROP TRIGGER test_license_failure")
        self.assertEqual(self.case.verify(record)["license_status"], "authorized")

    def test_legacy_copies_awaiting_proof_do_not_prevent_fresh_review(self):
        source = "https://source.example.test/shared"
        _, first = self.add("old-a", address=source)
        _, second = self.add("old-b", address=source, privacy="public")
        _, donor = self.add("legacy-review-fixture")
        self.assertNotEqual(first, second)
        self.case.verify(donor)
        for record in (first, second):
            self.case.insert_legacy_approval(record, donor)
        for record in (first, second):
            before = self.case.get(record)
            self.assertEqual((before["status"], before["license_status"]), ("pending_review", "pending"))
            self.assertTrue(before["can_review"])
            self.assertIsNone(before["raw_text"])
            self.assertEqual(self.eligible(record).status_code, 409)
        self.case.verify(first, license_evidence_ref="local:checked-original-permit")
        self.assertEqual(self.eligible(first).json()["raw_text"], fixtures.QUOTE)
        self.assertEqual(self.eligible(second).status_code, 409)
        verified = self.case.verify(second, license_evidence_ref="local:checked-original-permit")
        self.assertEqual(verified["duplicate"]["record_count"], 3)

    def test_v4_migration_preserves_history_and_leaves_unproven_approvals_pending(self):
        _, old_record = self.add("legacy")
        self.case.verify(old_record)
        # Simulate the v4 schema in this synthetic temporary database only.
        with closing(sqlite3.connect(self.db.path)) as db, db:
            discard_empty_registry_fixture_schema(db)
            db.executescript("""
                DROP VIEW corpus_withdrawals;
                DROP TABLE corpus_licenses;
                PRAGMA user_version=4;
            """)
        read = Path.read_text

        def broken(path, *args, **kwargs):
            text = read(path, *args, **kwargs)
            return text + "\nINSERT INTO missing_table VALUES (1);" if path.name == "005_corpus_licenses.sql" else text

        with patch.object(Path, "read_text", broken), self.assertRaises(sqlite3.Error):
            with TestClient(create_app(self.case.settings), base_url=ORIGIN, client=("127.0.0.1", 29206)):
                pass
        with closing(sqlite3.connect(self.db.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT count(*) FROM corpus_reviews").fetchone()[0], 1)
        with TestClient(create_app(self.case.settings), base_url=ORIGIN, client=("127.0.0.1", 29206), headers=HEADERS) as fresh:
            self.assertEqual(fresh.get("/api/health").json()["schema_version"], 8)
            record = fresh.get(f"{self.case.root}/records/{old_record}").json()
            self.assertEqual((record["status"], record["license_status"]), ("pending_review", "pending"))
            self.assertIsNone(record["raw_text"])
            self.assertEqual(len(record["history"]), 1)
            self.assertTrue(record["can_review"])
            self.assertEqual(self.eligible(old_record).status_code, 409)
            self.assertEqual(self.case.verify(old_record)["status"], "verified")
        self.assertEqual(self.db.rows("PRAGMA foreign_key_check"), [])
