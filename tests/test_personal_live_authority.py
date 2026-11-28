from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.raw_store.credentials import VaultError
from src.raw_store.personal_live_authority import AuthorityError, PersonalLiveAuthority, _digest


def _fixture_protection(data, *, encrypt):
    prefix = b"isolated-fixture:"
    if encrypt:
        return prefix + data[::-1]
    if not data.startswith(prefix):
        raise VaultError("not an isolated fixture")
    return data[len(prefix):][::-1]


class ProtectedAuthorityTests(unittest.TestCase):
    def setUp(self):
        parent = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
        temporary = TemporaryDirectory(prefix="voc-authority-fixture-", dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.work = self.root / "runtime"
        self.work.mkdir()
        self.authority = self.root / "authority"
        self.authority.mkdir(mode=0o700)
        self.database = self.work / "example.sqlite3"
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript("""
                CREATE TABLE personal_validation_requests(
                    request_id TEXT PRIMARY KEY, batch_id TEXT, grant_id TEXT, operation TEXT, slot INTEGER,
                    payload_sha256 TEXT, credits INTEGER
                );
                CREATE TABLE personal_validation_request_events(request_id TEXT, state TEXT);
                CREATE TABLE personal_validation_batches(batch_id TEXT PRIMARY KEY, mode TEXT);
                CREATE TABLE personal_validation_grants(batch_id TEXT, grant_id TEXT, provider TEXT, account_ref TEXT);
                CREATE TABLE personal_validation_reconciliations(
                    sequence INTEGER PRIMARY KEY, request_id TEXT, evidence_ref TEXT, actual_units INTEGER,
                    subject_ref TEXT
                );
                CREATE TABLE personal_validation_receipts(
                    request_id TEXT PRIMARY KEY, provider TEXT, account_ref TEXT, provider_request_id TEXT
                );
            """)
            db.commit()
        self.local = PersonalLiveAuthority(self.authority, database=self.database)
        protector = patch("src.raw_store.personal_live_authority._protect", _fixture_protection)
        protector.start()
        self.addCleanup(protector.stop)
        self.batch = {
            "batch_id": str(uuid4()), "mode": "formal_live", "edition": "PERSONAL",
            "purpose": "g1_personal_acceptance", "state": "draft", "owner_ref": "fixture-owner",
            "actor_ref": "fixture-actor", "study_id": "fixture-study", "scope_id": "fixture-scope",
            "scope_version": "v1", "authorization_ref": "fixture-batch-authorization", "request_limit": 4,
        }
        self.payload = {"query": "an imaginary search query"}
        shared = {
            "batch_id": self.batch["batch_id"], "grant_id": str(uuid4()), "operation": "search",
            "slot": 1, "payload_sha256": _digest(self.payload),
        }
        self.grant = shared | {"credential_revision": "one", "account_ref": "fixture-account", "credit_limit": 1}
        self.request = shared | {"request_id": str(uuid4()), "state": "claimed", "credits": 1}

    def ready(self):
        self.local.register_batch(self.batch)
        self.batch["state"] = "approved"
        self.local.authorize(self.batch, self.grant)

    def ledger_claim(self, request):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("""
                INSERT INTO personal_validation_requests VALUES(
                    :request_id, :batch_id, :grant_id, :operation, :slot, :payload_sha256, :credits)
            """, request)
            db.execute("INSERT INTO personal_validation_request_events VALUES(?, 'claimed')", (request["request_id"],))
            db.commit()

    def check(self, grant=None):
        with closing(sqlite3.connect(self.database)) as db:
            return self.local.check(db, self.batch, grant)

    def test_missing_and_changed_batch_or_grant_fail_closed(self):
        self.assertFalse(self.check())
        self.local.register_batch(self.batch)
        self.assertTrue(self.check())
        self.assertFalse(self.check(self.grant))
        self.local.authorize(self.batch, self.grant)
        self.assertTrue(self.check(self.grant))
        for mutation in (
            {"credential_revision": "two"}, {"credit_limit": 2}, {"account_ref": "other"},
            {"payload_sha256": "0" * 64},
        ):
            self.assertFalse(self.check(self.grant | mutation))
        self.batch["scope_version"] = "v2"
        self.assertFalse(self.check())

    def test_atomic_claim_allows_only_one_independent_sender(self):
        self.ready()
        self.ledger_claim(self.request)
        barrier = Barrier(5)

        def sender():
            authority = PersonalLiveAuthority(self.authority, database=self.database)
            barrier.wait(timeout=5)
            return authority.claim(self.batch, self.grant, self.request)

        with ThreadPoolExecutor(max_workers=5) as workers:
            self.assertEqual([False, False, False, False, True], sorted(workers.map(lambda _: sender(), range(5))))
        self.assertTrue(self.local.verify_claim(self.batch, self.grant, self.request))
        self.assertFalse(self.local.verify_claim(self.batch, self.grant, self.request | {"credits": 2}))
        self.assertFalse(self.local.claim(self.batch, self.grant, self.request | {"request_id": str(uuid4())}))

    def test_replacement_database_cannot_restore_unused_grant(self):
        self.ready()
        original = self.work / "original.sqlite3"
        self.database.rename(original)
        with closing(sqlite3.connect(original)) as source, closing(sqlite3.connect(self.database)) as replacement:
            sqlite3.Connection.backup(source, replacement)
        self.assertFalse(self.check(self.grant))
        with self.assertRaises(AuthorityError):
            self.local.claim(self.batch, self.grant, self.request)
        with self.assertRaises(AuthorityError):
            self.local.register_batch(self.batch)
        with self.assertRaises(AuthorityError):
            self.local.register_batch(self.batch | {"batch_id": str(uuid4())})

    def test_claim_requires_a_committed_ledger_event(self):
        self.ready()
        with self.assertRaises(AuthorityError):
            self.local.claim(self.batch, self.grant, self.request)
        self.assertFalse(self.local.verify_claim(self.batch, self.grant, self.request))

    def test_in_place_restore_before_prior_claim_blocks_directory(self):
        self.ready()
        with closing(sqlite3.connect(":memory:")) as snapshot:
            with closing(sqlite3.connect(self.database)) as source:
                source.backup(snapshot)
            self.ledger_claim(self.request)
            self.assertTrue(self.local.claim(self.batch, self.grant, self.request))
            self.assertTrue(self.check(self.grant))
            with closing(sqlite3.connect(self.database)) as destination:
                snapshot.backup(destination)
        self.assertFalse(self.check(self.grant))
        with closing(sqlite3.connect(self.database)) as db:
            new_batch = self.batch | {"batch_id": str(uuid4())}
            self.local.register_batch(new_batch)
            self.assertFalse(self.local.check(db, new_batch, None))

    def test_revocation_is_monotonic_and_preserves_claim_and_receipt_audit(self):
        self.ready()
        self.ledger_claim(self.request)
        self.assertTrue(self.local.claim(self.batch, self.grant, self.request))
        self.local.revoke(self.batch)
        self.local.revoke(self.batch)
        self.assertFalse(self.check(self.grant))
        self.assertTrue(self.local.verify_claim(self.batch, self.grant, self.request))
        response = {"request_id": "official-fixture", "status": "isolated"}
        with self.assertRaises(AuthorityError):
            self.local.archive(self.batch, self.grant, self.request, {"query": "changed"}, response)
        ref = self.local.archive(self.batch, self.grant, self.request, self.payload, response)
        reopened = PersonalLiveAuthority(self.authority, database=self.database)
        self.assertEqual(self.local.archive(self.batch, self.grant, self.request, self.payload, response), ref)
        artifact = reopened.read_archive(self.batch, self.grant, self.request, _digest(response))
        self.assertEqual(artifact["response"], response)
        self.assertFalse(reopened.has_archive(self.batch, self.grant, self.request, "0" * 64))
        self.assertNotIn(self.payload["query"].encode("utf-8"), (self.authority / f"{ref}.dpapi").read_bytes())
        with self.assertRaises(AuthorityError):
            reopened.archive(self.batch, self.grant, self.request, self.payload, {"different": True})

    def test_protected_review_is_bound_to_batch_requirement_and_digest(self):
        self.ready()
        reference, digest = self.local.archive_review(self.batch, "C0-5", {"passed": True})
        review = self.local.read_review(self.batch, "C0-5", reference, digest)
        self.assertEqual(review, {"passed": True, "batch_id": self.batch["batch_id"], "requirement": "C0-5"})
        with self.assertRaises(AuthorityError):
            self.local.read_review(self.batch, "C0-6", reference, digest)
        with self.assertRaises(AuthorityError):
            self.local.read_review(self.batch | {"batch_id": str(uuid4())}, "C0-5", reference, digest)
        with self.assertRaises(AuthorityError):
            self.local.read_review(self.batch, "C0-5", reference, "0" * 64)

    def test_revoked_batch_can_archive_only_one_claim_bound_charge(self):
        self.batch["currency"] = "USD"
        self.grant["provider"] = "tavily"
        self.ready()
        proof = {
            "request_id": self.request["request_id"], "provider": self.grant["provider"],
            "account_ref": self.grant["account_ref"], "currency": self.batch["currency"],
            "actual_units": 12, "bill_ref": "fixture-bill",
        }
        with self.assertRaises(AuthorityError):
            self.local.archive_charge(self.batch, self.grant, self.request, proof)
        self.ledger_claim(self.request)
        self.assertTrue(self.local.claim(self.batch, self.grant, self.request))
        self.local.revoke(self.batch)
        ref = self.local.archive_charge(self.batch, self.grant, self.request, proof)
        self.assertEqual(ref, self.local.archive_charge(self.batch, self.grant, self.request, proof))
        self.assertEqual(proof, self.local.read_charge(self.batch, self.grant, self.request, ref))
        with self.assertRaises(AuthorityError):
            self.local.read_charge(self.batch, self.grant, self.request, "live-charge-" + "0" * 64)
        with self.assertRaises(AuthorityError):
            self.local.archive_charge(self.batch, self.grant, self.request, proof | {"actual_units": 13})
        self.assertFalse(self.check(self.grant))

    def test_refuses_relative_repository_workspace_and_unsafe_file_paths(self):
        with self.assertRaises(AuthorityError):
            PersonalLiveAuthority("relative-authority", database=self.database)
        with self.assertRaises(AuthorityError):
            PersonalLiveAuthority(Path(__file__).resolve().parent, database=self.database)
        with self.assertRaises(AuthorityError):
            PersonalLiveAuthority(self.authority, database=self.database, workspace_roots=(self.root,))
        with self.assertRaises(AuthorityError):
            PersonalLiveAuthority(self.database, database=self.database)
        with self.assertRaises(AuthorityError):
            PersonalLiveAuthority(self.authority, database=self.database.relative_to(self.root))
        self.ready()
        path = self.authority / f"grant-{self.batch['batch_id']}-search-1.dpapi"
        os.link(path, path.with_suffix(".other"))
        self.assertFalse(self.check(self.grant))

    def test_unavailable_dpapi_does_not_persist_plaintext_or_grant_send_authority(self):
        with patch("src.raw_store.personal_live_authority._protect", side_effect=VaultError("DPAPI unavailable")):
            with self.assertRaises(AuthorityError):
                self.local.register_batch(self.batch)
            self.assertEqual(list(self.authority.iterdir()), [])
        self.ready()
        with patch("src.raw_store.personal_live_authority._protect", side_effect=VaultError("DPAPI unavailable")):
            self.assertFalse(self.check(self.grant))
            with self.assertRaises(AuthorityError):
                self.local.claim(self.batch, self.grant, self.request)


if __name__ == "__main__":
    unittest.main()
