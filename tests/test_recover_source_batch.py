"""M01 restoration regressions in a physically separate fixture database."""

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.config import ROOT, Settings
from src.execution.checks import reuse_paid_source, run_checks
from src.execution.transport import ENDPOINTS, Response
from src.outputs.audit_receipt import fingerprint, verify
from src.outputs.recover_source_batch import (
    RECEIPT_PATH, RECEIPT_SHA256, restore_public_source_batch,
)
from src.raw_store.store import Store, dump

SYNTHETIC_EXCERPT = "This synthetic fixture verifies safe public source recovery."


class SourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        workspace = TemporaryDirectory(prefix="voc-recover-")
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.archive = self.root / "archive"
        shutil.copytree(ROOT / RECEIPT_PATH, self.archive)
        receipt_file = self.archive / "run.json"
        receipt = json.loads(receipt_file.read_text("utf-8"))
        self.run_id = receipt["run"]["id"]
        post = next(row for row in receipt["evidence"] if row["name"] == "forum_post")
        self.source = post["response"]
        self.source["quote_utf8_sha256"] = sha256(SYNTHETIC_EXCERPT.encode()).hexdigest()
        receipt_file.write_text(dump(receipt), encoding="utf-8")
        with sqlite3.connect(self.archive / "audit.sqlite3") as db:
            db.execute(
                "UPDATE evidence SET response_json=? WHERE id=?",
                (dump(self.source), post["id"]),
            )
        db.close()
        self.fixture_digest = fingerprint(receipt)
        self.cfg = Settings(self.root / "data")
        self.db = Store(self.cfg.directory, fixture=True)

    def source_reply(self, **overrides):
        published = datetime.fromisoformat(self.source["published_at"])
        item = {
            "question_id": int(self.source["post_id"]), "link": self.source["url"],
            "content_license": self.source["license"], "creation_date": int(published.timestamp()),
            "owner": {"display_name": "Synthetic author"}, "body": SYNTHETIC_EXCERPT,
        }
        item.update(overrides)
        return Response(200, {"items": [item]})

    def restore(self, transport):
        with patch("src.outputs.recover_source_batch.RECEIPT_SHA256", self.fixture_digest):
            return restore_public_source_batch(self.cfg, self.db, self.archive, transport=transport)

    def test_shipped_archive_matches_pinned_digest(self):
        self.assertEqual(verify(ROOT / RECEIPT_PATH)["receipt_sha256"], RECEIPT_SHA256)

    def test_restores_same_batch_once_and_reuses_paid_evidence(self):
        _, unrelated = self.db.begin("unrelated", self.cfg)
        self.db.record(unrelated, "fixture", "synthetic_contract", {}, {})
        requests = []

        def transport(method, url, body, headers):
            requests.append(url)
            self.assertEqual(method, "GET")
            self.assertTrue(url.startswith(ENDPOINTS["stackexchange"] + self.source["post_id"] + "?"))
            self.assertFalse(headers)
            return self.source_reply()

        result = self.restore(transport)
        self.assertEqual((result["run_id"], result["status"]), (self.run_id, "RESTORED"))
        self.assertEqual(self.restore(transport)["status"], "ALREADY_PRESENT")
        self.assertEqual(len(requests), 1)
        reopened = Store(self.cfg.directory, fixture=True)
        attempts = reopened.audit(self.run_id)["attempts"]
        self.assertEqual(len(attempts), 1)
        events = attempts[0]["evidence"]
        self.assertEqual([e["mode"] for e in events], ["archived_live_http", "synthetic_contract", "archive_recovery"])
        self.assertEqual(events[0]["response"]["credits"], 1)
        self.assertEqual(events[-1]["response"]["tavily_requests"], 0)
        self.assertEqual(events[-1]["response"]["restored_search_id"], events[0]["id"])
        self.assertEqual(events[-1]["response"]["rechecked_post_id"], events[1]["id"])
        self.assertEqual(reopened.ledger(self.run_id), [])
        self.assertEqual({r["requirement_id"]: r["status"] for r in reopened.results(self.run_id)},
                         {"C0-3": "PASS", "G-1": "BLOCKED"})
        posts = reopened.rows("SELECT * FROM evidence WHERE name='forum_post'")
        quote, refs, matched, _ = reuse_paid_source(reopened, posts)
        self.assertEqual(quote["text"], SYNTHETIC_EXCERPT)
        self.assertTrue(matched)
        self.assertEqual(refs, [e["id"] for e in events])

    def test_changed_or_unavailable_source_creates_no_batch(self):
        for reply in (
            Response(503, {}), self.source_reply(body="A different licensed sentence."),
            self.source_reply(content_license="CC BY-SA 3.0"),
            self.source_reply(owner={}), self.source_reply(creation_date=0),
        ):
            with self.subTest(reply=reply):
                with self.assertRaises(ValueError):
                    self.restore(lambda *args: reply)
                self.assertEqual(self.db.history(), [])

    def test_untrusted_or_inconsistent_archive_does_not_fetch(self):
        def unexpected(*args):
            self.fail("The rejected archive must cause no external request.")
        with self.assertRaisesRegex(ValueError, "可信凭据摘要"):
            restore_public_source_batch(self.cfg, self.db, self.archive, transport=unexpected)
        receipt_file = self.archive / "run.json"
        receipt = json.loads(receipt_file.read_text("utf-8"))
        receipt["research_denominator"] = 1
        receipt_file.write_text(dump(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "数据库与 JSON"):
            self.restore(unexpected)
        self.assertEqual(self.db.history(), [])

    def test_storage_failure_rolls_back_the_run_and_all_evidence(self):
        record = self.db._record

        def fail_after_search(*args, **kwargs):
            if args[2] == "forum_post":
                raise sqlite3.OperationalError("injected evidence write error")
            return record(*args, **kwargs)

        with patch.object(self.db, "_record", side_effect=fail_after_search):
            with self.assertRaises(sqlite3.OperationalError):
                self.restore(lambda *args: self.source_reply())
        self.assertEqual(self.db.history(), [])
        self.assertEqual(self.db.rows("SELECT id FROM evidence"), [])
        self.assertEqual(self.restore(lambda *args: self.source_reply())["status"], "RESTORED")

    def test_fixture_transport_cannot_recover_an_operational_batch(self):
        actual = Store(self.cfg.directory)
        with self.assertRaises(ValueError):
            restore_public_source_batch(self.cfg, actual, self.archive, transport=lambda *args: None)
        with self.assertRaises(ValueError):
            run_checks(self.cfg, self.db, "fixture-cannot-run-formal-gate")
        self.assertEqual(actual.history(), [])
