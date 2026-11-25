"""C2 only: real WAL connections, isolated synthetic M03/M04/M05 records, reference-only writes."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from threading import Event
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_corpus as fixtures
from src.raw_store.store import Conflict


class EligibilityTransactions(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.CorpusTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.store = self.case.app.state.store
        self.corpus = self.case.app.state.corpus
        self.study = self.case.study
        with self.store.db() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            db.execute("CREATE TABLE c2_test_refs(record_id TEXT PRIMARY KEY)")
        self.addCleanup(self.check_integrity)

    def check_integrity(self):
        with self.store.db() as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def add(self, suffix="", **options):
        row = list(fixtures.ROW)
        row[2] += suffix
        batch, [record] = self.case.import_rows([row], **options)
        return batch, record

    def accepted(self, suffix="", **options):
        _, record = self.add(suffix, **options)
        self.case.verify(record)
        return record

    def revoke(self, record):
        self.case.verify(record, decision="excluded", reason="复核：授权已撤销", retention_until=None)

    def get(self, record, study=None):
        return self.case.client.get(f"/api/corpus/{study or self.study}/records/{record}/eligible")

    @contextmanager
    def writer(self):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def consume(self, db, *records):
        return self.corpus.qualified_write_inputs(db, self.study, records)

    def refs(self):
        return [r["record_id"] for r in self.store.rows("SELECT record_id FROM c2_test_refs")]

    def test_same_file_row_obeys_revoked_batch_even_if_original_never_reviewed(self):
        batch, _ = self.add()
        _, alias = self.add(privacy="public")
        self.case.verify(alias)
        self.assertEqual(self.get(alias).status_code, 200)
        self.case.client.post(f"/api/imports/{self.study}/batches/{batch}/revoke").raise_for_status()
        self.assertEqual(self.get(alias).status_code, 409)
        self.assertIsNone(self.case.get(alias)["raw_text"])
        detail = self.case.client.get(f"/api/imports/{self.study}/batches/{alias.split(':')[0]}")
        self.assertIsNone(detail.raise_for_status().json()["rows"][0]["raw_text"])
        with self.writer() as db, self.assertRaises(Conflict), self.consume(db, alias):
            self.fail("withdrawn file row reached consumer")

    def test_same_file_row_withdrawal_survives_unmapped_source_and_new_grant(self):
        _, alias = self.add()
        self.case.verify(alias)
        file_id = self.case.get(alias)["trace"]["file_id"]
        url = f"/api/imports/{self.study}/uploads/{file_id}"
        mapping = self.case.client.get(url).json()["suggested_mapping"]
        del mapping["source_url"]
        plan = {"sheet_index": 0, "privacy": "public", "mapping": mapping}
        preview = self.case.client.post(url + "/preview", json=plan).raise_for_status().json()
        other = self.case.client.post(url + "/confirm", json={**plan, "preview_token": preview["preview_token"]})
        withdrawal_row = other.raise_for_status().json()["batch_id"] + ":2"
        self.revoke(withdrawal_row)
        self.assertEqual(self.get(alias).status_code, 409)
        self.assertIsNone(self.case.get(alias)["raw_text"])
        self.assertEqual(self.case.review(alias).status_code, 409)
        self.case.verify(alias, reauthorize=True, license_evidence_ref="local:renewed-file-row",
                         license_issued_on=self.case.get(withdrawal_row)["history"][0]["reviewed_at"][:10])
        self.assertEqual(self.get(alias).status_code, 200)
        self.assertEqual(self.get(withdrawal_row).status_code, 409)
        self.assertEqual(self.case.client.get(url).status_code, 409)

    def test_revoked_staging_retry_reads_no_file_and_never_grants_eligibility(self):
        batch, record = self.add()
        url = f"/api/imports/{self.study}/uploads/{self.case.get(record)['trace']['file_id']}"
        mapping = self.case.client.get(url).json()["suggested_mapping"]
        plan = {"sheet_index": 0, "privacy": "unknown", "mapping": mapping}
        before = self.case.client.post(url + "/preview", json=plan).raise_for_status().json()
        self.case.client.post(f"/api/imports/{self.study}/batches/{batch}/revoke").raise_for_status()
        with patch("src.dashboard.import_api.read_sheet", side_effect=AssertionError("reopened file")):
            replay = self.case.client.post(url + "/preview", json=plan).raise_for_status().json()
            self.assertEqual(replay["preview_token"], before["preview_token"])
            self.assertEqual((replay["status"], replay["sample_rows"], replay["issue_rows"]), ("revoked", [], []))
            self.assertEqual(replay["summary"]["source_types"], {})
            self.assertNotIn(fixtures.ROW[2], str(replay))
            receipt = self.case.client.post(url + "/confirm", json={**plan, "preview_token": replay["preview_token"]})
            self.assertEqual(receipt.raise_for_status().json()["batch_id"], batch)
            self.assertEqual(self.case.client.post(url + "/preview", json={**plan, "privacy": "public"}).status_code, 409)
            self.assertEqual(self.case.client.get(url).status_code, 409)
        self.assertEqual(self.get(record).status_code, 409)
        self.assertEqual(self.store.one("SELECT count(*) AS n FROM import_batches")["n"], 1)

    def test_withdrawal_commits_while_prechecked_consumer_waits(self):
        record = self.accepted()
        cached = self.get(record).raise_for_status().json()
        before_commit = Event()
        release = Event()
        connect = self.store.connect

        def trace(statement):
            # Hold B at the actual SQLite COMMIT after the real M05 review has written its event.
            if statement == "COMMIT":
                before_commit.set()
                release.wait(10)

        def traced_connection():
            db = connect()
            db.set_trace_callback(trace)
            return db

        with ThreadPoolExecutor(1) as workers, closing(connect()) as db:
            db.execute("BEGIN")
            today = datetime.now(timezone.utc).date().isoformat()
            self.assertEqual(self.corpus.qualified_record_in_transaction(db, self.study, record, today=today), cached)
            db.commit()
            db.execute("PRAGMA busy_timeout=0")
            with patch.object(self.store, "connect", side_effect=traced_connection):
                worker = workers.submit(self.revoke, record)
                try:
                    self.assertTrue(before_commit.wait(10))
                    with self.assertRaises(sqlite3.OperationalError) as err:
                        db.execute("BEGIN IMMEDIATE")
                    self.assertEqual(err.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
                finally:
                    release.set()
                worker.result()
            with db, self.assertRaises(Conflict):
                db.execute("BEGIN IMMEDIATE")
                with self.consume(db, cached["record_id"]):
                    db.execute("INSERT INTO c2_test_refs VALUES (?)", (record,))
        self.assertEqual(self.refs(), [])
        self.assertEqual(self.get(record).status_code, 409)

    def test_writer_holds_wal_lock_until_reference_commits_then_withdrawal_masks_reads(self):
        record = self.accepted()
        contended = Event()

        def revoke_after_writer():
            # A failed immediate lock (timeout=0) proves concurrent contention before A commits.
            with closing(self.store.connect()) as other:
                other.execute("PRAGMA busy_timeout=0")
                with self.assertRaises(sqlite3.OperationalError) as err:
                    other.execute("BEGIN IMMEDIATE")
                self.assertEqual(err.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
            contended.set()
            self.revoke(record)

        with ThreadPoolExecutor(1) as workers:
            with self.writer() as db:
                with self.consume(db, record) as records:
                    worker = workers.submit(revoke_after_writer)
                    self.assertTrue(contended.wait(10))
                    self.assertEqual(records[record]["record_id"], record)
                    db.execute("INSERT INTO c2_test_refs VALUES (?)", (record,))
                self.assertTrue(db.in_transaction)
                self.assertEqual(self.refs(), [])
            worker.result()
        self.assertEqual(self.refs(), [record])
        self.assertEqual(self.get(record).status_code, 409)
        self.assertIsNone(self.case.get(record)["raw_text"])

    def test_stale_wal_read_snapshot_cannot_be_used_for_a_write(self):
        record = self.accepted()
        with closing(self.store.connect()) as db:
            db.execute("BEGIN")
            db.execute("SELECT count(*) FROM corpus_reviews").fetchone()
            self.revoke(record)
            with self.assertRaises(sqlite3.OperationalError) as err, self.consume(db, record):
                self.fail("stale snapshot reached writer")
            self.assertEqual(err.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY_SNAPSHOT)
            self.assertTrue(db.in_transaction)
            db.rollback()
            db.execute("BEGIN IMMEDIATE")
            with self.assertRaises(Conflict), self.consume(db, record):
                self.fail("withdrawn after snapshot restart")

    def test_python_http_and_locked_projection_match_including_frozen_trace(self):
        record = self.accepted()
        ordinary = self.corpus.qualified_record(self.study, record)
        reply = self.get(record)
        self.assertEqual(reply.headers["cache-control"], "no-store")
        self.assertEqual(reply.raise_for_status().json(), ordinary)
        with self.writer() as db, patch.object(self.store, "connect", side_effect=AssertionError("second connection")):
            with self.consume(db, record) as data:
                self.assertEqual(data, {record: ordinary})
        self.assertEqual((ordinary["trace"]["study_id"], ordinary["trace"]["scope_id"],
                          ordinary["trace"]["scope_version"]), (self.study, self.case.scope, "v1"))
        self.assertEqual(ordinary["license_status"], "authorized")
        self.assertTrue(ordinary["engineering_eligible"])
        self.assertFalse(ordinary["outbound_allowed"] or ordinary["research_eligible"])

    def test_own_connection_required_and_caller_retains_transaction_ownership(self):
        rec = self.accepted()
        with self.store.db() as db:
            with self.assertRaises(ValueError), self.consume(db, rec):
                self.fail("no transaction")
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO c2_test_refs VALUES ('before')")
            with self.assertRaises(RuntimeError):
                with self.consume(db, rec):
                    db.execute("INSERT INTO c2_test_refs VALUES (?)", (rec,))
                    raise RuntimeError("controlled write failure")
            self.assertTrue(db.in_transaction)
            self.assertEqual([r[0] for r in db.execute("SELECT * FROM c2_test_refs")], ["before"])
            self.assertEqual(self.refs(), [])
            db.rollback()
        self.assertEqual(self.refs(), [])

    def test_independent_source_and_record_scoped_new_grant(self):
        original = self.accepted()
        alias = self.accepted("#copy", privacy="public")
        independent = self.accepted("/separate")
        self.revoke(original)
        with self.writer() as db:
            with self.consume(db, independent) as data:
                self.assertEqual(data[independent]["duplicate"]["record_count"], 1)
            with self.assertRaises(Conflict), self.consume(db, independent, alias):
                self.fail("dependent context withdrawn")
        self.assertEqual(self.case.review(original).status_code, 409)
        self.case.verify(original, reauthorize=True, license_evidence_ref="local:new-c2-grant",
                         license_issued_on=self.case.get(original)["history"][0]["reviewed_at"][:10])
        with self.writer() as db:
            with self.consume(db, original, independent) as records:
                self.assertEqual(set(records), {original, independent})
            with self.assertRaises(Conflict), self.consume(db, alias):
                self.fail("other copy was not reauthorized")
        self.assertEqual(len(self.case.get(original)["history"]), 3)
        self.assertEqual(self.refs(), [])

    def test_utc_midnight_discards_whole_write_and_retry_recomputes(self):
        _, record = self.add()
        last = "2090-01-31T23:59:59.999+00:00"
        midnight = "2090-02-01T00:00:00.000+00:00"
        self.case.verify(record, retention_until=last[:10])
        with patch("src.raw_store.corpus.now", return_value=last) as clock:
            self.assertEqual(self.get(record).status_code, 200)
            with self.writer() as db:
                with self.assertRaises(Conflict):
                    with self.consume(db, record):
                        db.execute("INSERT INTO c2_test_refs VALUES (?)", (record,))
                        clock.return_value = midnight
                self.assertTrue(db.in_transaction)
                self.assertEqual(db.execute("SELECT count(*) FROM c2_test_refs").fetchone()[0], 0)
            for time in (midnight, "2090-02-01T12:00:00.000+00:00"):
                clock.return_value = time
                self.assertEqual(self.get(record).status_code, 409)
                with self.writer() as db, self.assertRaises(Conflict), self.consume(db, record):
                    self.fail("expired input reached writer")
        self.assertEqual(self.refs(), [])

    def test_new_grant_cannot_reopen_retained_row_after_its_deadline(self):
        _, record = self.add()
        self.case.verify(record, retention_until="2090-01-31")
        self.revoke(record)
        with patch("src.raw_store.corpus.now", return_value="2090-02-01T00:00:00.000+00:00"):
            reply = self.case.review(record, reauthorize=True, license_evidence_ref="local:late-c2-grant",
                                     retention_until="2090-12-31", license_issued_on="2090-02-01")
            self.assertEqual(reply.status_code, 409)
            self.assertFalse(self.case.get(record)["can_reauthorize"])
            self.assertEqual(self.get(record).status_code, 409)

    def test_file_row_deadline_survives_withdrawal_without_a_new_deadline(self):
        _, origin = self.add()
        _, alias = self.add(privacy="public")
        self.case.verify(origin, retention_until="2090-01-31")
        self.case.verify(alias, retention_until="2090-12-31")
        self.revoke(origin)
        with patch("src.raw_store.corpus.now", return_value="2090-02-01T00:00:00+00:00"):
            reply = self.case.review(alias, reauthorize=True, license_evidence_ref="local:new-copy-grant",
                                     license_issued_on="2090-02-01", retention_until="2090-12-31")
            self.assertEqual(reply.status_code, 409)
            self.assertEqual(self.get(alias).status_code, 409)

    def test_day_change_requires_retry_even_when_grant_remains_valid(self):
        _, record = self.add()
        self.case.verify(record, retention_until="2090-12-31")
        with patch("src.raw_store.corpus.now", return_value="2090-01-31T23:59:59.999+00:00") as clock:
            with self.assertRaises(Conflict), self.writer() as db, self.consume(db, record):
                db.execute("INSERT INTO c2_test_refs VALUES (?)", (record,))
                clock.return_value = "2090-02-01T00:00:00.000+00:00"
            self.assertEqual(self.refs(), [])
            with self.writer() as db, self.consume(db, record):
                db.execute("INSERT INTO c2_test_refs VALUES (?)", (record,))
            self.assertEqual(self.refs(), [record])

    def test_final_check_sees_changes_made_on_callers_connection(self):
        record = self.accepted()
        with self.writer() as db:
            with self.assertRaises(Conflict):
                with self.consume(db, record):
                    db.execute("INSERT INTO c2_test_refs VALUES (?)", (record,))
                    db.execute("UPDATE import_batches SET revoked_at='2090-01-01' WHERE batch_id=?",
                               (record.split(":")[0],))
            self.assertTrue(db.in_transaction)
        self.assertEqual(self.refs(), [])
        self.assertEqual(self.get(record).status_code, 200)

    def test_wrong_database_and_empty_dependency_set_do_not_reach_consumer(self):
        record = self.accepted()
        with sqlite3.connect(":memory:") as foreign:
            self.addCleanup(foreign.close)
            foreign.execute("BEGIN IMMEDIATE")
            with self.assertRaises(ValueError), self.consume(foreign, record):
                self.fail("wrong database")
            self.assertTrue(foreign.in_transaction)
        with self.writer() as db, self.assertRaises(ValueError), self.consume(db):
            self.fail("no source dependencies")

    def test_committed_reference_survives_expiry_but_content_does_not(self):
        _, record = self.add()
        self.case.verify(record, retention_until="2090-06-30")
        with patch("src.raw_store.corpus.now", return_value="2090-06-30T23:59:59.999+00:00"):
            with self.writer() as db, self.consume(db, record):
                db.execute("INSERT INTO c2_test_refs VALUES (?)", (record,))
        with patch("src.raw_store.corpus.now", return_value="2090-07-01T00:00:00.000+00:00"):
            self.assertEqual(self.refs(), [record])
            self.assertEqual(self.get(record).status_code, 409)
            self.assertIsNone(self.case.get(record)["raw_text"])

    def test_foreign_project_and_missing_record_have_same_public_response(self):
        record = self.accepted()
        other, _ = self.case.project()
        missing = f"{uuid4()}:2"
        foreign = self.get(record, other)
        absent = self.get(missing, other)
        self.assertEqual((foreign.status_code, foreign.content), (404, absent.content))
        self.assertEqual(absent.status_code, 404)
        self.assertNotIn(record, foreign.text)
        with self.writer() as db:
            for ident in (record, missing):
                with self.assertRaises(KeyError), self.corpus.qualified_write_inputs(db, other, [ident]):
                    self.fail("wrong study")
