"""Offline checks against a committed, real, redacted acceptance receipt."""
import json
from pathlib import Path
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

from src.execution.transport import Response
from src.outputs.audit_receipt import verify, verify_public_source

DIRECTORY = Path(__file__).resolve().parents[1] / "docs/evidence/p0-0"


class ReceiptTests(unittest.TestCase):
    def test_sqlite_and_json_agree_on_observed_outcome(self):
        receipt = verify(DIRECTORY)
        self.assertEqual(receipt["checks"]["G-1"], "BLOCKED")
        self.assertEqual(receipt["checks"]["C0-6"], "PASS")
        self.assertEqual(receipt["sqlite_integrity"], "ok")

    def test_real_discovery_and_followup_have_source_and_matching_id(self):
        report = json.loads((DIRECTORY / "run.json").read_text("utf-8"))
        for attempt in report["attempts"]:
            rows = [e for e in report["evidence"] if e["attempt_id"] == attempt["id"]]
            search = next(e for e in rows if e["name"] == "forum_search")
            post = next(e for e in rows if e["name"] == "forum_post")
            self.assertEqual((search["status_code"], post["status_code"]), (200, 200))
            self.assertIn(post["response"]["post_id"], {hit["id"] for hit in search["response"]["hits"]})
            self.assertTrue(post["response"]["verified"])
            self.assertIn("by-sa", post["response"]["license_url"])
            self.assertEqual(len(post["response"]["quote_utf8_sha256"]), 64)

    def test_unset_credentials_do_not_create_metered_requests(self):
        uri = (DIRECTORY / "audit.sqlite3").resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM usage_ledger").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM evidence WHERE name='jev_shard'").fetchone()[0], 0)
            status = db.execute("SELECT DISTINCT status_code FROM evidence WHERE mode='configuration'").fetchall()
            self.assertEqual(status, [(None,)])

    def test_independent_source_checks_match_the_preserved_quote_hash(self):
        batch = json.loads((DIRECTORY / "run.json").read_text("utf-8"))
        post = next(e["response"] for e in batch["evidence"] if e["name"] == "forum_post")
        attempts = [
            json.loads((DIRECTORY / name).read_text("utf-8"))
            for name in ("source-verification-01.json", "source-verification-02.json")
        ]
        self.assertTrue(all(a["run"] == batch["run"]["id"] for a in attempts))
        unavailable, verified = [a["observations"][0] for a in attempts]
        self.assertEqual((unavailable["http_status"], unavailable["status"]), (503, "BLOCKED"))
        self.assertIsNone(unavailable["observed_quote_utf8_sha256"])
        self.assertEqual((verified["http_status"], verified["status"]), (200, "PASS"))
        self.assertEqual(verified["observed_quote_utf8_sha256"], post["quote_utf8_sha256"])
        self.assertEqual(verified["license"], post["license"])

    def test_recheck_distinguishes_changed_content_from_unavailable_content(self):
        batch = json.loads((DIRECTORY / "run.json").read_text("utf-8"))
        post = next(e["response"] for e in batch["evidence"] if e["name"] == "forum_post")
        changed = {
            "question_id": int(post["post_id"]),
            "link": post["url"],
            "content_license": post["license"],
            "body": "This sentence is a synthetic edit in an offline unit test.",
        }
        for expected, reply in (
            ("FAIL", Response(200, {"items": [changed]})),
            ("BLOCKED", Response(200, {"items": []})),
            ("BLOCKED", Response(503, {})),
        ):
            with self.subTest(expected=expected, http=reply.status):
                with patch("src.outputs.audit_receipt.outbound", return_value=reply):
                    self.assertEqual(verify_public_source(DIRECTORY)["status"], expected)
