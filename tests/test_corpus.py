from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from test_imports import BASE, HEADERS, ORIGIN, make_csv


QUOTE = "  我希望公共图书馆预约座位时能提前看到靠窗的位置还有没有空位。\n第二天也可以查。  "
ROW = [QUOTE, "forum", "https://source-a.invalid/post/1", "2026-11-11", "合成许可夹具", "public"]


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory(prefix="voc-corpus-研究-")))
        self.settings = Settings(self.directory)
        self.app = create_app(self.settings)
        self.client = self.enterContext(TestClient(
            self.app, base_url=ORIGIN, client=("127.0.0.1", 29205), headers=HEADERS,
        ))
        self.study, self.scope = self.project()
        self.root = f"/api/corpus/{self.study}"
        self.retain = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

    def project(self):
        response = self.client.post("/api/studies", json={
            "request_key": str(uuid4()), "name": "合成语料项目",
            "scope": {"mode": "open", "topic": "合成范围"},
        })
        response.raise_for_status()
        project = response.json()
        study, scope = project["study_id"], project["scope"]["scope_id"]
        self.client.post(f"/api/studies/{study}/scopes/{scope}/freeze").raise_for_status()
        return study, scope

    def import_rows(self, rows, *, study=None, scope=None, columns=BASE, privacy="unknown", filename="语料夹具.csv"):
        study, scope = study or self.study, scope or self.scope
        root = f"/api/imports/{study}"
        uploaded = self.client.post(
            f"{root}/scopes/{scope}/uploads", content=make_csv(columns, rows), headers={
                "Content-Type": "application/octet-stream", "X-VOC-Filename": quote(filename),
            },
        )
        uploaded.raise_for_status()
        url = f"{root}/uploads/{uploaded.json()['file_id']}"
        sheet = self.client.get(url).json()
        plan = {"sheet_index": 0, "mapping": sheet["suggested_mapping"], "privacy": privacy}
        preview = self.client.post(url + "/preview", json=plan)
        preview.raise_for_status()
        saved = self.client.post(url + "/confirm", json={**plan, "preview_token": preview.json()["preview_token"]})
        saved.raise_for_status()
        batch = saved.json()["batch_id"]
        records = self.client.get(f"/api/corpus/{study}/batches/{batch}").json()["records"]
        return batch, [row["record_id"] for row in records]

    def review(self, record, **changes):
        data = {"decision": "verified", "role": "user_quote", "basis": "已核对合成来源、许可、范围和原文",
                "reason": "测试本机审核", "retention_until": self.retain} | changes
        return self.client.post(f"{self.root}/records/{record}/review", json=data)

    def get(self, record):
        reply = self.client.get(f"{self.root}/records/{record}")
        reply.raise_for_status()
        self.assertEqual(reply.headers["Cache-Control"], "no-store")
        return reply.json()

    def verify(self, record, **changes):
        reply = self.review(record, **changes)
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()

    def test_snapshot_replays_exact_text_and_scope_after_reopen(self):
        batch, [record] = self.import_rows([ROW])
        before = self.get(record)
        self.assertEqual(before["status"], "pending_review")
        saved = self.verify(record)
        self.assertEqual(saved["raw_text"], QUOTE)
        self.assertEqual(saved["raw_sha256"], hashlib.sha256(QUOTE.encode()).hexdigest())
        self.assertEqual(saved["trace"]["batch_id"], batch)
        self.assertEqual(saved["trace"]["scope_id"], self.scope)
        self.assertEqual(saved["trace"]["scope_version"], "v1")
        self.assertEqual(saved["trace"]["line_number"], 2)
        self.assertEqual(saved["metadata"]["source_url"], ROW[2])
        self.assertFalse(saved["research_eligible"])
        self.assertFalse(saved["outbound_allowed"])
        with TestClient(create_app(self.settings), base_url=ORIGIN, client=("127.0.0.1", 29205)) as fresh:
            self.assertEqual(fresh.get(f"{self.root}/records/{record}").json(), saved)
        batches = self.client.get(f"{self.root}/batches").json()["batches"]
        self.assertEqual((batches[0]["candidate_count"], batches[0]["reviewed_count"]), (1, 1))

    def test_cross_source_dedupe_with_revocation_and_no_cross_project_join(self):
        first_batch, [first] = self.import_rows([ROW])
        alternate = [QUOTE.strip(), ROW[1], "https://source-b.invalid/post/2", *ROW[3:]]
        _, [second] = self.import_rows([alternate])
        self.verify(first)
        duplicate = self.verify(second)["duplicate"]
        self.assertEqual(duplicate["canonical_record_id"], first)
        self.assertTrue(duplicate["is_duplicate"])
        other, other_scope = self.project()
        other_batch, [third] = self.import_rows([alternate], study=other, scope=other_scope)
        self.assertEqual(self.client.get(f"{self.root}/records/{third}").status_code, 404)
        self.assertEqual(self.client.get(f"{self.root}/batches/{other_batch}").status_code, 404)
        removed = self.client.post(f"/api/imports/{self.study}/batches/{first_batch}/revoke")
        removed.raise_for_status()
        self.assertEqual(self.get(first)["status"], "revoked")
        self.assertIsNone(self.get(first)["raw_text"])
        self.assertEqual(self.review(first).status_code, 409)
        remaining = self.get(second)["duplicate"]
        self.assertEqual(remaining["group_id"], duplicate["group_id"])
        self.assertEqual(remaining["canonical_record_id"], second)
        self.assertFalse(remaining["is_duplicate"])

    def test_review_retry_is_idempotent_and_audit_is_immutable(self):
        _, [record] = self.import_rows([ROW])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.review(record), range(2)))
        self.assertEqual([reply.status_code for reply in results], [200, 200])
        self.assertEqual(len(self.get(record)["history"]), 1)
        excluded = self.verify(record, decision="excluded", reason="许可已撤销", retention_until=None)
        self.assertEqual(excluded["status"], "excluded")
        self.assertIsNone(excluded["raw_text"])
        self.assertEqual(len(excluded["history"]), 2)
        db = self.app.state.store
        for sql in ("DELETE FROM corpus_snapshots", "DELETE FROM corpus_reviews"):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), db.db() as conn:
                conn.execute(sql)
        self.assertEqual(db.rows("PRAGMA foreign_key_check"), [])

    def test_retention_expiry_masks_original_and_propagates_to_groups(self):
        _, [record] = self.import_rows([ROW])
        self.verify(record)
        next_day = (datetime.fromisoformat(self.retain) + timedelta(days=1)).date().isoformat()
        with patch("src.raw_store.corpus.now", return_value=next_day + "T00:00:00+00:00"):
            detail = self.get(record)
            self.assertEqual(detail["status"], "retention_expired")
            self.assertIsNone(detail["raw_text"])
            self.assertIsNone(detail["duplicate"])
            self.assertEqual(self.review(record, retention_until="2099-01-01").status_code, 409)

    def test_restriction_applies_to_same_file_aliases_but_not_independent_sources(self):
        _, [original] = self.import_rows([ROW])
        alias_batch, [alias] = self.import_rows([ROW], privacy="public", filename="换名的语料夹具.csv")
        _, [independent] = self.import_rows([[QUOTE, ROW[1], "https://another.invalid/post/2", *ROW[3:]]])
        self.verify(original)
        self.verify(alias, retention_until="2099-01-01")
        self.assertEqual(self.verify(independent, retention_until="2099-01-01")["duplicate"]["record_count"], 3)

        def assert_alias_restriction():
            alias_detail = self.get(alias)
            self.assertEqual(alias_detail["status"], "source_restricted")
            self.assertIsNone(alias_detail["raw_text"])
            self.assertEqual(alias_detail["metadata"], {})
            self.assertIsNone(alias_detail["duplicate"])
            rows = self.client.get(f"{self.root}/batches/{alias_batch}").json()["records"]
            self.assertEqual(rows[0]["status"], "source_restricted")
            self.assertEqual(self.review(alias, retention_until="2099-01-01").status_code, 409)
            separate = self.get(independent)
            self.assertEqual(separate["raw_text"], QUOTE)
            self.assertEqual(separate["duplicate"]["record_count"], 1)
            self.assertEqual(separate["duplicate"]["canonical_record_id"], independent)

        self.verify(original, decision="excluded", reason="暂时排除该源", retention_until=None)
        assert_alias_restriction()
        self.verify(original, reason="重新核验同一个源")
        self.assertEqual(self.get(alias)["status"], "verified")
        next_day = (datetime.fromisoformat(self.retain) + timedelta(days=1)).date().isoformat()
        with patch("src.raw_store.corpus.now", return_value=next_day + "T00:00:00+00:00"):
            self.assertEqual(self.get(original)["status"], "retention_expired")
            assert_alias_restriction()

    def test_role_and_source_policy_reject_unqualified_user_quotes(self):
        rows = [
            ["内部合成记录", "internal_cx", "", "", "本地权限夹具", "internal"],
            ["背景合成记录", "journal", "https://source-b.invalid/paper", ROW[3], ROW[4], "public"],
            ["只有发现摘要", "search_discovery", "https://source-b.invalid/snippet", ROW[3], ROW[4], "public"],
            ["缺少发布日期", "forum", ROW[2], "", ROW[4], "public"],
            ["缺少许可", "forum", ROW[2], ROW[3], "", "public"],
            ["来源需保密", "forum", "https://source-b.invalid/post?token=fixture", ROW[3], ROW[4], "public"],
        ]
        _, records = self.import_rows(rows)
        self.assertEqual(len(records), len(rows))
        for record in records:
            with self.subTest(record=record):
                self.assertEqual(self.review(record).status_code, 422)
        self.assertIsNone(self.get(records[0])["raw_text"])
        self.assertIsNone(self.get(records[-1])["metadata"].get("source_url"))
        for record, role in zip(records, ("internal", "background", "synthetic")):
            data = self.verify(record, role=role)
            self.assertEqual(data["role"], role)
            self.assertIsNone(data["duplicate"])
            self.assertFalse(data["research_eligible"])
            self.assertFalse(data["outbound_allowed"])

    def test_review_requires_same_origin_and_does_not_echo_invalid_body(self):
        _, [record] = self.import_rows([ROW])
        url = f"{self.root}/records/{record}/review"
        forbidden = self.client.post(url, json={}, headers={"Origin": "https://outside.invalid"})
        self.assertEqual(forbidden.status_code, 403)
        invalid = self.client.post(url, json={"decision": "unexpected-fixture-text"})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("unexpected-fixture-text", invalid.text)
        with TestClient(create_app(self.settings), base_url=ORIGIN, client=("192.0.2.1", 29205)) as other:
            self.assertEqual(other.get(f"{self.root}/records/{record}").status_code, 403)

    def test_v3_upgrade_keeps_unreviewed_candidates_available(self):
        batch, [record] = self.import_rows([ROW])
        # Reset only the empty M05 tables to get the same layout as the M04 database.
        with closing(sqlite3.connect(self.directory / "connectivity.sqlite3")) as db, db:
            db.executescript("""
                DROP TABLE corpus_reviews;
                DROP TABLE corpus_snapshots;
                PRAGMA user_version=3;
            """)
        read_text = Path.read_text

        def broken(path, *args, **kwargs):
            text = read_text(path, *args, **kwargs)
            return text + "\nINSERT INTO missing_table VALUES (1);" if path.name == "004_corpus.sql" else text

        with patch.object(Path, "read_text", broken), self.assertRaises(sqlite3.OperationalError):
            with TestClient(create_app(self.settings), base_url=ORIGIN, client=("127.0.0.1", 29205)):
                pass
        with closing(sqlite3.connect(self.directory / "connectivity.sqlite3")) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
        with TestClient(create_app(self.settings), base_url=ORIGIN, client=("127.0.0.1", 29205)) as fresh:
            self.assertEqual(fresh.get("/api/health").json()["schema_version"], 4)
            rows = fresh.get(f"{self.root}/batches/{batch}").json()["records"]
            self.assertEqual([(row["record_id"], row["status"]) for row in rows], [(record, "pending_review")])


if __name__ == "__main__":
    unittest.main()
