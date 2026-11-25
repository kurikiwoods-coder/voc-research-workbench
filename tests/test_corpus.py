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
from test_imports import BASE, HEADERS, ORIGIN, discard_empty_registry_fixture_schema, make_csv


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
        if data["decision"] == "verified":
            data.setdefault("license_status", "authorized")
            data.setdefault("license_evidence_ref", "local:fixture-license")
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
        self.assertEqual(self.review(record).status_code, 409)
        self.assertEqual(excluded["status"], "policy_restricted")
        self.assertIsNone(excluded["raw_text"])
        self.assertEqual(len(excluded["history"]), 2)
        self.assertFalse(excluded["can_review"])
        self.assertTrue(excluded["source_permission_revoked"])
        self.assertEqual(self.verify(record, decision="excluded", reason="许可已撤销", retention_until=None), excluded)
        self.assertEqual(self.review(record, decision="excluded", reason="暂时排除").status_code, 409)
        db = self.app.state.store
        self.assertEqual(db.one("SELECT reason FROM corpus_reviews WHERE decision='excluded'")["reason"], "许可已撤销")
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

    def test_exclusion_does_not_erase_or_extend_the_prior_retention_limit(self):
        rows = [[f"合成原话 {index}", *ROW[1:]] for index in range(2)]
        _, records = self.import_rows(rows)
        for record, limit in zip(records, (None, "2099-01-01")):
            self.verify(record)
            self.verify(record, decision="excluded", reason="暂时排除该源", retention_until=limit)

        next_day = (datetime.fromisoformat(self.retain) + timedelta(days=1)).date().isoformat()
        with patch("src.raw_store.corpus.now", return_value=next_day + "T00:00:00+00:00"):
            for record in records:
                with self.subTest(record=record):
                    self.assertEqual(self.get(record)["status"], "retention_expired")
                    self.assertEqual(self.review(record, retention_until="2099-01-01").status_code, 409)

    def test_restricted_record_masks_source_cells_and_free_form_review_text(self):
        quote_text = "合成原话可能在来源列和审核记录重复出现"
        row = [quote_text, quote_text, *ROW[2:]]
        batch, [record] = self.import_rows([row])
        self.verify(record, role="background", basis=quote_text)
        excluded = self.verify(record, decision="excluded", role="background",
                               reason="原话中的合成摘录", retention_until=None)

        self.assertIsNone(excluded["raw_text"])
        self.assertEqual(excluded["metadata"], {})
        self.assertIsNone(excluded["source_type"])
        self.assertIsNone(excluded["history"][0]["reason"])
        self.assertIsNone(excluded["history"][1]["basis"])
        self.assertEqual([event["decision"] for event in excluded["history"]], ["excluded", "verified"])
        self.assertEqual(excluded["trace"]["batch_id"], batch)
        rows = self.client.get(f"{self.root}/batches/{batch}").json()["records"]
        self.assertIsNone(rows[0]["source_type"])
        saved = self.app.state.store.one("SELECT basis FROM corpus_reviews WHERE decision='verified'")
        self.assertEqual(saved["basis"], quote_text)

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
        for index, record in enumerate(records):
            with self.subTest(record=record):
                fields = {"license_evidence_ref": None} if index == 4 else {}
                self.assertEqual(self.review(record, **fields).status_code, 422)
        self.assertIsNone(self.get(records[0])["raw_text"])
        self.assertIsNone(self.get(records[-1])["metadata"].get("source_url"))
        for record, role in zip(records, ("internal", "background", "synthetic")):
            data = self.verify(record, role=role)
            self.assertEqual(data["role"], role)
            self.assertIsNone(data["duplicate"])
            self.assertFalse(data["research_eligible"])
            self.assertFalse(data["outbound_allowed"])

    def test_amazon_market_and_review_fields_are_required_by_source_address(self):
        columns = BASE + ["rating", "verified", "product_model", "market"]
        rows = [
            ["缺少评价字段", "forum", "https://www.amazon.com/review/1", *ROW[3:], "", "yes", "", "US"],
            ["未验证的评价", "forum", "https://www.amazon.com./review/2", *ROW[3:], "4", "no", "合成型号", "US"],
            ["完整的美国评价", "amazon", "https://www.amazon.com/review/3", *ROW[3:], "5", "yes", "合成型号", "US"],
        ]
        _, records = self.import_rows(rows, columns=columns)
        for record in records[:2]:
            with self.subTest(record=record):
                self.assertEqual(self.review(record).status_code, 422)
        self.assertEqual(self.verify(records[2])["metadata"]["rating"], 5)

    def test_explicitly_unconfirmed_permission_masks_pending_quote_and_blocks_verification(self):
        permissions = ["No permission", "Permission denied by source", "未获授权，禁止保存",
                       "License revoked", "授权已撤销"]
        rows = [[f"合成原话 {index}", ROW[1], ROW[2], ROW[3], permission, "public"]
                for index, permission in enumerate(permissions)]
        _, records = self.import_rows(rows)
        for record in records:
            with self.subTest(record=record):
                self.assertIsNone(self.get(record)["raw_text"])
                self.assertEqual(self.review(record).status_code, 422)

    def test_source_metadata_omits_encoded_sensitive_fields(self):
        urls = ["https://source-a.invalid/post/contact%40example.invalid",
                "https://source-a.invalid/post#contact%40example.invalid"]
        rows = [[f"合成原话 {index}", ROW[1], url, *ROW[3:], f"fixture\u007fvalue{index}"]
                for index, url in enumerate(urls)]
        _, records = self.import_rows(rows, columns=BASE + ["external_id"])
        self.assertEqual(len(records), len(urls))
        for record in records:
            with self.subTest(record=record):
                metadata = self.get(record)["metadata"]
                self.assertNotIn("source_url", metadata)
                self.assertNotIn("external_id", metadata)
                self.assertEqual(self.review(record).status_code, 422)

    def insert_legacy_approval(self, record, donor):
        with self.app.state.store.db() as db:
            db.execute("INSERT INTO corpus_snapshots SELECT ?, study_id, scope_id, raw_sha256, created_at "
                       "FROM corpus_snapshots WHERE record_id=?", (record, donor))
            db.execute("""INSERT INTO corpus_reviews
                          (record_id, decision, role, reason, basis, retention_until, dedupe_group, reviewed_at)
                          SELECT ?, decision, role, reason, basis, retention_until, dedupe_group, reviewed_at
                          FROM corpus_reviews WHERE record_id=? AND decision='verified'""", (record, donor))

    def test_legacy_approvals_are_rechecked_before_display_and_deduplication(self):
        _, [valid] = self.import_rows([ROW])
        self.verify(valid)
        denied = [*ROW[:4], "No permission", "public"]
        encoded = [*ROW[:2], "https://source-b.invalid/post/contact%40example.invalid", *ROW[3:]]
        import_root = f"/api/imports/{self.study}"
        legacy = []
        for index, row in enumerate((denied, encoded)):
            batch, [record] = self.import_rows([row])
            alias_batch, [alias] = self.import_rows([row], privacy="public", filename=f"同源副本-{index}.csv")
            file_url = f"{import_root}/uploads/{self.get(record)['trace']['file_id']}"
            alias_url = f"{import_root}/uploads/{self.get(alias)['trace']['file_id']}"
            mapping = self.client.get(file_url).json()["suggested_mapping"]
            plan = {"sheet_index": 0, "mapping": mapping, "privacy": "unknown"}
            preview = self.client.post(file_url + "/preview", json=plan)
            preview.raise_for_status()
            confirm = {**plan, "preview_token": preview.json()["preview_token"]}
            legacy.append((batch, record, alias_batch, alias, file_url, alias_url, confirm))
        for _, record, *_ in legacy:
            self.insert_legacy_approval(record, valid)
        for batch, record, alias_batch, alias, file_url, alias_url, confirm in legacy:
            with self.subTest(record=record):
                detail = self.get(record)
                self.assertEqual(detail["status"], "policy_restricted")
                self.assertEqual(detail["decision"], "verified")
                self.assertIsNone(detail["raw_text"])
                self.assertEqual(detail["metadata"], {})
                self.assertIsNone(detail["duplicate"])
                self.assertEqual(self.review(record, role="synthetic").status_code, 409)
                records = self.client.get(f"{self.root}/batches/{batch}").json()["records"]
                self.assertEqual(records[0]["status"], "policy_restricted")
            with self.subTest(alias=alias):
                self.assertEqual(self.get(alias)["status"], "source_restricted")
            for ident in (batch, alias_batch):
                with self.subTest(batch=ident):
                    result = self.client.get(f"{import_root}/batches/{ident}")
                    result.raise_for_status()
                    row = result.json()["rows"][0]
                    self.assertIsNone(row["raw_text"])
                    self.assertEqual(row["originals"], [])
                    self.assertEqual(row["fields"], {})
            for url in (file_url, alias_url):
                with self.subTest(file=url):
                    self.assertEqual(self.client.get(url).status_code, 409)
                    self.assertEqual(self.client.post(url + "/preview", json={
                        field: confirm[field] for field in ("sheet_index", "mapping", "privacy")
                    }).status_code, 409)
                with self.subTest(replay=url), patch("src.dashboard.import_api.read_sheet",
                                                       side_effect=AssertionError("unexpected source read")):
                    receipt = self.client.post(url + "/confirm", json=confirm)
                    self.assertEqual(receipt.status_code, 201)
                    self.assertEqual(receipt.json()["batch_id"], batch)
                    self.assertEqual(receipt.json()["summary"]["source_types"], {})
        self.assertEqual(self.get(valid)["duplicate"]["record_count"], 1)

    def test_legacy_approval_cannot_restore_a_withdrawn_license(self):
        batch, [record] = self.import_rows([ROW])
        alias_batch, [alias] = self.import_rows([ROW], privacy="public", filename="许可副本.csv")
        authorized_row = [*ROW[:2], "https://authorized-source.invalid/post/2", *ROW[3:]]
        _, [authorized] = self.import_rows([authorized_row])
        self.verify(record)
        self.verify(authorized)
        self.verify(record, decision="excluded", reason="License revoked", retention_until=None)

        # Emulate a v4 workbench that accepted another verification after withdrawal.
        with self.app.state.store.db() as db:
            db.execute("""INSERT INTO corpus_reviews
                          (record_id, decision, role, reason, basis, retention_until, dedupe_group, reviewed_at)
                          SELECT record_id, decision, role, reason, basis, retention_until, dedupe_group, reviewed_at
                          FROM corpus_reviews WHERE record_id=? AND decision='verified'""", (record,))
        status = self.get(record)
        self.assertEqual(status["decision"], "verified")
        self.assertEqual(status["status"], "policy_restricted")
        self.assertTrue(status["source_permission_revoked"])
        self.assertIsNone(status["raw_text"])
        self.assertEqual(self.get(alias)["status"], "source_restricted")
        self.assertEqual(self.get(authorized)["duplicate"]["record_count"], 1)
        for ident in (batch, alias_batch):
            with self.subTest(batch=ident):
                result = self.client.get(f"/api/imports/{self.study}/batches/{ident}")
                result.raise_for_status()
                self.assertIsNone(result.json()["rows"][0]["raw_text"])
        self.assertEqual(self.client.get(
            f"/api/imports/{self.study}/uploads/{status['trace']['file_id']}"
        ).status_code, 409)

    def test_withdrawn_source_remains_restricted_when_csv_content_and_line_change(self):
        _, [original] = self.import_rows([ROW])
        filler = ["合成补充记录", "forum", "https://unrelated.invalid/post", *ROW[3:]]
        alias_batch, [_, alias] = self.import_rows([filler, ROW], filename="换行副本.csv")
        self.verify(original)
        self.assertEqual(self.verify(alias)["duplicate"]["record_count"], 2)
        independent_row = [*ROW[:2], "https://independent.invalid/post", *ROW[3:]]
        _, [independent] = self.import_rows([independent_row])
        self.assertEqual(self.verify(independent)["duplicate"]["record_count"], 3)

        root = f"/api/imports/{self.study}"
        path = f"{root}/scopes/{self.scope}/uploads"
        rows = [filler, independent_row, ROW]

        def upload(filename):
            response = self.client.post(path, content=make_csv(rows=rows), headers={
                "Content-Type": "application/octet-stream", "X-VOC-Filename": filename,
            })
            response.raise_for_status()
            return f"{root}/uploads/{response.json()['file_id']}"

        draft = upload("before-withdrawal.csv")
        mapping = self.client.get(draft).json()["suggested_mapping"]
        plan = {"sheet_index": 0, "mapping": mapping, "privacy": "unknown"}
        preview = self.client.post(draft + "/preview", json=plan)
        preview.raise_for_status()
        confirm = {**plan, "preview_token": preview.json()["preview_token"]}
        self.verify(original, decision="excluded", reason="许可已撤销", retention_until=None)

        for url in (draft, upload("after-withdrawal.csv")):
            for endpoint, method, payload in (
                ("", "GET", None), ("/preview", "POST", plan), ("/confirm", "POST", confirm),
            ):
                with self.subTest(url=url, endpoint=endpoint):
                    response = self.client.request(method, url + endpoint, json=payload)
                    self.assertEqual(response.status_code, 409)
                    self.assertNotIn(QUOTE.strip().splitlines()[0], response.text)
        with self.subTest(view="existing corpus"):
            detail = self.get(alias)
            self.assertEqual(detail["status"], "source_restricted")
            self.assertIsNone(detail["raw_text"])
            self.assertIsNone(detail["duplicate"])
            self.assertEqual(self.review(alias).status_code, 409)
        with self.subTest(view="existing import"):
            reply = self.client.get(f"{root}/batches/{alias_batch}")
            reply.raise_for_status()
            records = reply.json()["rows"]
            self.assertIsNone(records[0]["raw_text"])
            self.assertFalse(records[0]["license_status"] == "authorized")
            self.assertIsNone(records[1]["raw_text"])
            self.assertEqual(records[1]["originals"], [])
            self.assertEqual(records[1]["fields"], {})
        self.assertEqual(self.get(independent)["duplicate"]["record_count"], 1)
        other_study, other_scope = self.project()
        _, [other] = self.import_rows([ROW], study=other_study, scope=other_scope)
        response = self.client.get(f"/api/corpus/{other_study}/records/{other}")
        response.raise_for_status()
        self.assertIsNone(response.json()["raw_text"])
        self.assertEqual(response.json()["status"], "pending_review")
        approved = self.client.post(f"/api/corpus/{other_study}/records/{other}/review", json={
            "decision": "verified", "role": "user_quote", "reason": "独立项目核验",
            "basis": "核对这个项目的许可与研究范围", "retention_until": self.retain,
            "license_status": "authorized", "license_evidence_ref": "local:independent-scope-permit",
        })
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["raw_text"], QUOTE)

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
        # Reset only the temporary test database to the M04 layout.
        with closing(sqlite3.connect(self.directory / "connectivity.sqlite3")) as db, db:
            discard_empty_registry_fixture_schema(db)
            db.executescript("""
                DROP VIEW corpus_withdrawals;
                DROP TABLE corpus_licenses;
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
            self.assertEqual(fresh.get("/api/health").json()["schema_version"], 8)
            rows = fresh.get(f"{self.root}/batches/{batch}").json()["records"]
            self.assertEqual([(row["record_id"], row["status"]) for row in rows], [(record, "pending_review")])


if __name__ == "__main__":
    unittest.main()
