from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
import json
from io import BytesIO, StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
import warnings
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from openpyxl.workbook.defined_name import DefinedName

from src.config import Settings
from src.dashboard.app import create_app
from src.ingestion.import_files import ImportProblem, MAX_ROWS, MAX_UPLOAD, read_csv, read_sheet
from src.ingestion.import_mapping import FIELDS, suggestions
from src.raw_store.store import Store


ORIGIN = "http://127.0.0.1:8765"
HEADERS = {"Origin": ORIGIN, "X-VOC-Action": "connectivity"}
BASE = ["raw_text", "source_type", "source_url", "published_at", "access_policy", "privacy"]
VALID = ["想在图书馆提前预约座位。", "forum", "https://example.org/t/3", "2026-11-11", "公开许可待核", "public"]
MIGRATIONS = Path(__file__).resolve().parents[1] / "src/raw_store/migrations"


def discard_empty_registry_fixture_schema(db):
    """Remove the v7–v8 objects before constructing disposable v3–v5 fixtures."""
    if db.in_transaction or db.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise ValueError("Use a fresh raw connection to the disposable fixture")
    objects = db.execute(
        """SELECT type, name FROM sqlite_schema
           WHERE name GLOB 'm06_*' OR name GLOB 'm07_*'
           ORDER BY type = 'table', name"""
    ).fetchall()
    if any(
        db.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone() is not None
        for kind, name in objects if kind == "table"
    ):
        raise ValueError("The fixture contains M06 or M07 rows")
    for kind, name in objects:
        db.execute(f'DROP {kind} "{name}"')


def make_csv(headers=BASE, rows=None, *, encoding="utf-8", separator=","):
    data = StringIO(newline="")
    writer = csv.writer(data, delimiter=separator)
    writer.writerow(headers)
    writer.writerows(rows if rows is not None else [VALID])
    return data.getvalue().encode(encoding)


def make_xlsx(rows=None, *, sheet_name="出行体验", private_print_area=None):
    buffer = BytesIO()
    book = Workbook()
    book.active.title = "填写说明"
    book.active.append(["单独选择数据表"])
    table = book.create_sheet(sheet_name)
    table.append(BASE)
    for row in rows if rows is not None else [VALID]:
        table.append(row)
    if private_print_area:
        book.defined_names.add(DefinedName("_xlnm.Print_Area", localSheetId=1, attr_text=private_print_area))
    book.save(buffer)
    book.close()
    return buffer.getvalue()


def custom_zip(entries):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enterContext(TemporaryDirectory(prefix="voc-import-研究 ")))
        self.settings = Settings(self.dir)
        self.client, self.app = self.open_client()
        self.study, self.scope = self.make_project()
        self.root = f"/api/imports/{self.study}"

    def open_client(self, peer="127.0.0.1"):
        app = create_app(self.settings)
        client = self.enterContext(TestClient(app, base_url=ORIGIN, client=(peer, 29204), headers=HEADERS))
        return client, app

    def make_project(self, *, frozen=True, **scope):
        project = self.client.post("/api/studies", json={
            "request_key": str(uuid4()), "name": "图书馆与社区体验",
            "scope": {"mode": "open", "topic": "用户如何预约公共设施？", **scope},
        })
        project.raise_for_status()
        data = project.json()
        sid, vid = data["study_id"], data["scope"]["scope_id"]
        if frozen:
            self.client.post(f"/api/studies/{sid}/scopes/{vid}/freeze").raise_for_status()
        return sid, vid

    def upload(self, data, name="样本 data.csv", study=None, scope=None):
        study, scope = study or self.study, scope or self.scope
        return self.client.post(f"/api/imports/{study}/scopes/{scope}/uploads", content=data,
                                headers={"Content-Type": "application/octet-stream", "X-VOC-Filename": quote(name)})

    def prepare(self, data=None, name="样本.csv", index=0):
        upload = self.upload(make_csv() if data is None else data, name)
        self.assertEqual(upload.status_code, 201, upload.text)
        url = self.root + "/uploads/" + upload.json()["file_id"]
        table = self.client.get(url, params={"sheet_index": index})
        self.assertEqual(table.status_code, 200, table.text)
        body = table.json()
        return url, body, {"sheet_index": index, "mapping": body["suggested_mapping"]}

    def check(self, url, plan):
        response = self.client.post(url + "/preview", json=plan)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm(self, url, plan):
        receipt = self.check(url, plan)
        response = self.client.post(url + "/confirm", json={**plan, "preview_token": receipt["preview_token"]})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @property
    def db(self):
        return self.app.state.store

    def test_standard_csv_and_template_downloads(self):
        url, table, plan = self.prepare()
        self.assertEqual(table["total"], 1)
        self.assertEqual(table["encoding"], "UTF-8")
        self.assertEqual(table["file"]["filename"], "样本.csv")
        receipt = self.confirm(url, plan)
        self.assertEqual(receipt["summary"]["staged"], 1)
        self.assertFalse(receipt["research_eligible"])
        csv_template = self.client.get("/api/imports/templates/csv")
        self.assertEqual(csv_template.status_code, 200)
        self.assertEqual(list(csv.reader(StringIO(csv_template.content.decode("utf-8-sig")))), [list(FIELDS)])
        xlsx_template = self.client.get("/api/imports/templates/xlsx")
        self.assertEqual(xlsx_template.status_code, 200)
        with closing(load_workbook(BytesIO(xlsx_template.content), read_only=True)) as book:
            self.assertEqual(list(book.active.values), [tuple(FIELDS)])

    def test_gb18030_and_common_delimiters(self):
        for sep in (";", "|", "\t"):
            with self.subTest(delimiter=sep):
                _, table, plan = self.prepare(make_csv(["原话", "来源", "出处", "发布时间", "来源许可", "隐私等级"],
                                                       encoding="gb18030", separator=sep))
                self.assertEqual((table["encoding"], table["delimiter"]), ("GB18030", sep))
                self.assertTrue(table["samples"][0]["populated"][0])
                self.assertNotIn(VALID[0], str(table["samples"]))
                self.assertEqual(plan["mapping"]["raw_text"], 0)

    def test_utf8_bom_preserves_header(self):
        _, table, plan = self.prepare(make_csv(encoding="utf-8-sig"))
        self.assertEqual(table["encoding"], "UTF-8 BOM")
        self.assertEqual(table["columns"], BASE)
        self.assertEqual(plan["mapping"]["raw_text"], 0)

    def test_xlsx_multi_sheet_and_native_dates(self):
        from datetime import datetime
        row = [*VALID]
        row[3] = datetime(2026, 11, 11, 13, 27)
        url, table, plan = self.prepare(make_xlsx([row]), "多表 工作簿.xlsx", index=1)
        self.assertEqual(table["file"]["sheets"], ["填写说明", "出行体验"])
        self.assertEqual(self.client.get(url).status_code, 422)
        self.assertEqual(self.client.get(url, params={"sheet_index": 8}).status_code, 422)
        receipt = self.confirm(url, plan)
        result = self.client.get(self.root + "/batches/" + receipt["batch_id"]).json()
        self.assertEqual(result["batch"]["sheet_name"], "出行体验")
        self.assertEqual(result["rows"][0]["fields"], {})
        stored = self.db.one("SELECT fields_json FROM import_rows WHERE batch_id=?", (receipt["batch_id"],))
        self.assertEqual(json.loads(stored["fields_json"])["published_at"], "2026-11-11T13:27:00")

    def test_mapping_suggestion_and_manual_revision(self):
        self.assertEqual(suggestions(["反馈内容", "来源链接", "来源许可"]), {"raw_text": 0, "source_url": 1, "access_policy": 2})
        url, _, plan = self.prepare(make_csv(["答复内容", "附加字段"], [["文字", "扩展"]]))
        response = self.client.post(url + "/preview", json=plan)
        self.assertEqual(response.status_code, 422)
        plan["mapping"] = {"raw_text": 0}
        first = self.check(url, plan)
        changed = {**plan, "mapping": {"raw_text": 1}}
        self.assertEqual(self.client.post(url + "/confirm", json={**changed, "preview_token": first["preview_token"]}).status_code, 409)
        receipt = self.confirm(url, plan)
        self.assertEqual(receipt["headers"], ["答复内容", "附加字段"])
        saved = self.client.get(self.root + "/batches/" + receipt["batch_id"]).json()["rows"][0]
        self.assertIsNone(saved["raw_text"])
        self.assertEqual(saved["originals"], [])
        exact = self.db.one("SELECT raw_text, originals_json FROM import_rows WHERE batch_id=?", (receipt["batch_id"],))
        self.assertEqual(exact["raw_text"], "文字")
        self.assertEqual(json.loads(exact["originals_json"]), ["文字", "扩展"])

    def test_required_and_invalid_mapping(self):
        url, _, plan = self.prepare()
        for mapping in ({}, {"raw_text": 90}, {"raw_text": 0, "lang": 0}, {"raw_text": 0, "fake": 1}, {"raw_text": True}):
            with self.subTest(mapping=mapping):
                self.assertEqual(self.client.post(url + "/preview", json={**plan, "mapping": mapping}).status_code, 422)

    def test_blank_text_ragged_row_date_rating_and_url_errors(self):
        rows = [
            VALID + ["4"],
            [""] + VALID[1:] + ["4"],
            ["不合法日期", "forum", "https://example.org", "2026-02-30", "许可", "public", "4"],
            ["不合法评分", "forum", "https://example.org", "2026-11-11", "许可", "public", "4.5"],
            ["不合法链接", "forum", "javascript:invalid", "2026-11-11", "许可", "public", "4"],
            ["列数错误", "forum"],
        ]
        url, _, plan = self.prepare(make_csv(BASE + ["rating"], rows))
        summary = self.check(url, plan)["summary"]
        self.assertEqual(summary["rejected"], 5)
        required = {"blank_text", "bad_date", "bad_rating", "bad_url", "row_width"}
        self.assertTrue(required <= {issue["code"] for issue in summary["issues"]})
        receipt = self.confirm(url, plan)
        data = self.client.get(self.root + "/batches/" + receipt["batch_id"], params={"status": "rejected"}).json()
        self.assertEqual(len(data["rows"]), 5)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM import_candidates")["n"], 1)

    def test_fully_rejected_file_cannot_create_batch(self):
        url, _, plan = self.prepare(make_csv(BASE, [[""] * len(BASE)]))
        first = self.check(url, plan)
        response = self.client.post(url + "/confirm", json={**plan, "preview_token": first["preview_token"]})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM import_batches")["n"], 0)

    def test_within_file_duplicates_keep_original_ordinals(self):
        rows = [
            VALID + ["aa"], ["  " + VALID[0] + "  ", *VALID[1:], "ab"],
            ["同外部编号而文案不同", *VALID[1:], "aa"],
        ]
        url, _, plan = self.prepare(make_csv(BASE + ["external_id"], rows))
        receipt = self.confirm(url, plan)
        self.assertEqual(receipt["summary"]["duplicate"], 2)
        variants = self.client.get(self.root + "/batches/" + receipt["batch_id"],
                                   params={"status": "duplicate"}).json()["rows"]
        self.assertEqual([(row["line_number"], row["duplicate_of_line"]) for row in variants], [(3, 2), (4, 2)])

    def test_unverified_source_private_data_require_local_review(self):
        rows = [["只有原话", "", "", "", "", ""], ["内部用研", "内部 CX", "", "2026-11-11", "", "public"]]
        url, _, plan = self.prepare(make_csv(BASE, rows))
        receipt = self.confirm(url, {**plan, "privacy": "public"})
        self.assertEqual(receipt["summary"]["pending_review"], 2)
        refs = self.db.rows("SELECT privacy, outbound_allowed, research_eligible FROM import_candidates ORDER BY line_number")
        self.assertEqual(refs, [{"privacy": "public", "outbound_allowed": 0, "research_eligible": 0},
                                {"privacy": "internal", "outbound_allowed": 0, "research_eligible": 0}])
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM runs")["n"], 0)

    def test_preserves_file_bytes_original_multiline_text_and_file_lines(self):
        quote_text = "  原句第一行\r\n第二行，保留标点  "
        data = make_csv(BASE + ["作者自订列"], [[quote_text, *VALID[1:], "自订"], ["下一条", *VALID[1:], "另一值"]])
        url, _, plan = self.prepare(data)
        receipt = self.confirm(url, plan)
        actual = self.db.rows("SELECT line_number, raw_text FROM import_rows ORDER BY line_number")
        self.assertEqual(actual, [{"line_number": 2, "raw_text": quote_text}, {"line_number": 4, "raw_text": "下一条"}])
        self.assertEqual(self.db.one("SELECT source_bytes FROM import_files")["source_bytes"], data)
        self.assertEqual(receipt["headers"][-1], "作者自订列")
        with self.assertRaises(sqlite3.IntegrityError), self.db.db() as db:
            db.execute("UPDATE import_rows SET raw_text='change'")

    def test_out_of_scope_and_product_label_are_candidates_only(self):
        study, scope = self.make_project(mode="single_category", product_category_ids=["CAT-TRANSIT"],
                                         date_window={"start": "2026-11-15", "end": "2026-11-30"})
        result = self.upload(make_csv(BASE + ["product_category_id"], [VALID + ["CAT-OTHER"]]), study=study, scope=scope)
        url = f"/api/imports/{study}/uploads/{result.json()['file_id']}"
        mapping = self.client.get(url).json()["suggested_mapping"]
        plan = {"sheet_index": 0, "mapping": mapping}
        preview = self.check(url, plan)
        self.assertEqual(preview["summary"]["pending_review"], 1)
        self.assertIn("outside_scope", {issue["code"] for issue in preview["summary"]["issues"]})

    def test_cross_project_reads_writes_and_frozen_scope_requirement(self):
        other, other_scope = self.make_project(frozen=False)
        url, _, plan = self.prepare()
        batch = self.confirm(url, plan)
        self.assertEqual(self.upload(make_csv(), study=other, scope=self.scope).status_code, 404)
        self.assertEqual(self.upload(make_csv(), study=other, scope=other_scope).status_code, 409)
        self.assertEqual(self.client.get(url.replace(self.study, other)).status_code, 404)
        self.assertEqual(self.client.get(f"/api/imports/{other}/batches/{batch['batch_id']}").status_code, 404)
        self.assertEqual(self.client.post(f"/api/imports/{other}/batches/{batch['batch_id']}/revoke").status_code, 404)

    def test_current_project_switch_and_scope_edit_do_not_reassign_batch(self):
        url, _, plan = self.prepare()
        next_project, _ = self.make_project()
        self.client.post(f"/api/studies/{next_project}/select").raise_for_status()
        api = f"/api/studies/{self.study}"
        before = self.client.get(api).json()
        edit = self.client.put(api, json={
            "revision": before["revision"], "name": before["name"],
            "scope": {"mode": "open", "topic": "另一个研究问题"},
        })
        edit.raise_for_status()
        batch = self.confirm(url, plan)
        self.assertEqual((batch["study_id"], batch["scope_id"], batch["scope_version"]), (self.study, self.scope, "v1"))
        self.assertNotEqual(edit.json()["scope"]["scope_id"], self.scope)
        self.assertEqual(self.client.get(f"/api/imports/{next_project}/batches").json()["batches"], [])

    def test_archiving_after_preview_blocks_confirmation(self):
        url, _, plan = self.prepare()
        preview = self.check(url, plan)
        api = f"/api/studies/{self.study}"
        revision = self.client.get(api).json()["revision"]
        archived = self.client.delete(api, params={"revision": revision})
        archived.raise_for_status()
        self.assertEqual(self.client.post(url + "/confirm", json={**plan, "preview_token": preview["preview_token"]}).status_code, 409)
        self.assertEqual(self.upload(make_csv()).status_code, 409)
        self.assertEqual(self.client.get(self.root + "/batches").json()["batches"], [])
        self.client.post(api + "/restore", json={"revision": archived.json()["revision"]}).raise_for_status()
        self.confirm(url, plan)

    def test_history_drafts_records_and_revoke_preserve_receipt(self):
        url, _, plan = self.prepare()
        self.assertEqual(len(self.client.get(self.root + "/batches").json()["drafts"]), 1)
        receipt = self.confirm(url, plan)
        path = self.root + "/batches/" + receipt["batch_id"]
        history = self.client.get(self.root + "/batches").json()
        self.assertEqual(len(history["batches"]), 1)
        self.assertEqual(history["drafts"], [])
        response = self.client.post(path + "/revoke")
        self.assertEqual(response.json()["status"], "revoked")
        self.assertEqual(self.client.post(path + "/revoke").json(), response.json())
        self.assertIsNone(self.client.get(path).json()["rows"][0]["raw_text"])
        self.assertEqual(self.db.one("SELECT raw_text FROM import_rows WHERE batch_id=?", (receipt["batch_id"],))["raw_text"], VALID[0])
        self.assertEqual(self.db.rows("SELECT * FROM import_candidates"), [])
        self.assertEqual(self.client.delete(url).status_code, 409)
        self.assertEqual(self.confirm(url, plan)["status"], "revoked")

    def test_corpus_restriction_applies_to_import_rows_and_original_file_previews(self):
        for restriction in ("excluded", "expired", "revoked"):
            with self.subTest(restriction=restriction):
                restricted = [f"这是一条需要限制浏览的合成评论 {restriction}。", *VALID[1:]]
                restricted[4] = "CC BY-SA 4.0"
                sibling = [*VALID]
                sibling[4] = "CC BY-SA 4.0"
                data = make_csv(rows=[restricted, sibling])
                url, _, plan = self.prepare(data, f"原文件-{restriction}.csv")
                preview = self.check(url, plan)
                new_plan = {**plan, "privacy": "private"}
                new_preview = self.check(url, new_plan)
                receipt = self.confirm(url, plan)
                original_path = self.root + "/batches/" + receipt["batch_id"]
                alias_url, _, alias_plan = self.prepare(data, f"同内容-{restriction}.csv")
                alias = self.confirm(alias_url, {**alias_plan, "privacy": "public"})
                alias_path = self.root + "/batches/" + alias["batch_id"]
                row = self.client.get(original_path).json()["rows"][0]
                self.assertIsNone(row["raw_text"])
                self.assertIsNone(self.client.get(alias_path).json()["rows"][0]["raw_text"])
                self.assertEqual(self.db.one("SELECT raw_text FROM import_rows WHERE record_id=?",
                                             (row["record_id"],))["raw_text"], restricted[0])
                decision = "excluded" if restriction == "excluded" else "verified"
                review = self.client.post(f"/api/corpus/{self.study}/records/{row['record_id']}/review", json={
                    "decision": decision, "role": "user_quote", "reason": "测试导入遮蔽",
                    "basis": "对照合成原文、公开许可和研究范围", "retention_until": "2090-01-01",
                    **({"license_status": "authorized", "license_evidence_ref": "local:fixture-license"}
                       if decision == "verified" else {"license_status": "pending"}),
                })
                self.assertEqual(review.status_code, 200, review.text)
                for sibling_path in (original_path, alias_path):
                    sibling_id = self.client.get(sibling_path).json()["rows"][1]["record_id"]
                    self.client.post(f"/api/corpus/{self.study}/records/{sibling_id}/review", json={
                        "decision": "verified", "role": "user_quote", "reason": "核验同批另一条",
                        "basis": "核对合成许可与范围", "retention_until": "2091-01-01",
                        "license_status": "authorized", "license_evidence_ref": "local:sibling-license",
                    }).raise_for_status()
                if restriction == "revoked":
                    self.client.post(original_path + "/revoke").raise_for_status()
                day = "2090-01-02T00:00:00+00:00" if restriction == "expired" else "2090-01-01T00:00:00+00:00"
                with patch("src.raw_store.imports.now", return_value=day):
                    for path in (original_path, alias_path):
                        detail = self.client.get(path)
                        detail.raise_for_status()
                        rows = detail.json()["rows"]
                        self.assertNotIn(restricted[0], detail.text)
                        self.assertTrue(rows[0]["content_restricted"])
                        self.assertIsNone(rows[0]["raw_text"])
                        self.assertEqual(rows[0]["originals"], [])
                        self.assertEqual(rows[0]["fields"], {})
                        expect_sibling = None if restriction == "revoked" else VALID[0]
                        self.assertEqual(rows[1]["raw_text"], expect_sibling)
                        report = self.client.get(path + "/errors.csv")
                        self.assertEqual(report.status_code, 200)
                        self.assertNotIn(restricted[0], report.content.decode("utf-8-sig"))
                    for path in (url, alias_url):
                        self.assertEqual(self.client.get(path).status_code, 409)
                        self.assertEqual(self.client.post(path + "/preview", json=plan).status_code, 409)
                    self.assertEqual(self.client.post(url + "/confirm", json={
                        **new_plan, "preview_token": new_preview["preview_token"],
                    }).status_code, 409)
                    self.assertEqual(self.client.post(url + "/confirm", json={
                        **new_plan, "preview_token": preview["preview_token"],
                    }).status_code, 409)
                    with patch("src.dashboard.import_api.read_sheet", side_effect=AssertionError("unexpected file read")):
                        for path in (url, alias_url):
                            replay = self.client.post(path + "/confirm", json={
                                **plan, "preview_token": preview["preview_token"],
                            })
                            self.assertEqual(replay.status_code, 201, replay.text)
                            self.assertEqual(replay.json()["batch_id"], receipt["batch_id"])
                            self.assertEqual(replay.json()["status"], "revoked" if restriction == "revoked" else "imported")
                            self.assertNotIn(restricted[0], replay.text)
                    self.assertEqual(self.db.one("SELECT COUNT(*) n FROM import_batches WHERE file_id IN (?, ?)",
                                                 (receipt["file_id"], alias["file_id"]))["n"], 2)

    def test_restricted_rows_cannot_appear_in_import_source_composition(self):
        protected = "这是只用于测试摘要遮蔽的合成原话。"
        row = [protected, *VALID[1:], protected]
        data = make_csv(headers=[*BASE, "extension"], rows=[row])
        url, _, plan = self.prepare(data)
        receipt = self.confirm(url, plan)
        path = self.root + "/batches/" + receipt["batch_id"]
        alias_url, _, alias_plan = self.prepare(data, "副本.csv")
        alias_plan["mapping"]["source_type"] = len(BASE)
        checked = self.check(alias_url, alias_plan)
        alias = self.confirm(alias_url, alias_plan)
        alias_path = self.root + "/batches/" + alias["batch_id"]
        self.assertNotIn(protected, str(alias["summary"]["source_types"]))
        record_id = self.client.get(path).json()["rows"][0]["record_id"]
        self.client.post(f"/api/corpus/{self.study}/records/{record_id}/review", json={
            "decision": "excluded", "role": "user_quote", "reason": "合成语料遮蔽测试",
            "basis": "合成数据保留限制", "retention_until": "2090-01-01",
        }).raise_for_status()

        for endpoint in (self.root + "/batches", alias_path):
            result = self.client.get(endpoint)
            result.raise_for_status()
            self.assertNotIn(protected, result.text)
        replay = self.client.post(alias_url + "/confirm", json={**alias_plan, "preview_token": checked["preview_token"]})
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(replay.json()["batch_id"], alias["batch_id"])
        self.assertNotIn(protected, replay.text)

    def test_error_report_download_has_no_quotes_and_prevents_spreadsheet_formulas(self):
        raw = "机密的测试句"
        data = make_xlsx([[raw, "", "", "", "", ""]], sheet_name="=待核实")
        url, _, plan = self.prepare(data, "sheets.xlsx", 1)
        receipt = self.confirm(url, plan)
        path = self.root + "/batches/" + receipt["batch_id"] + "/errors.csv"
        report = self.client.get(path)
        self.assertEqual(report.status_code, 200)
        self.assertIn("attachment;", report.headers["content-disposition"])
        text = report.content.decode("utf-8-sig")
        self.assertNotIn(raw, text)
        rows = list(csv.reader(StringIO(text)))
        self.assertGreater(len(rows), 2)
        self.assertEqual(rows[1][1], "'=待核实")
        self.assertIn("missing_source", {row[5] for row in rows[1:]})

    def test_confirmation_idempotence_and_parallel_submission(self):
        url, _, plan = self.prepare()
        preview = self.check(url, plan)
        form = {**plan, "preview_token": preview["preview_token"]}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.client.post(url + "/confirm", json=form), range(2)))
        self.assertEqual({result.status_code for result in results}, {201})
        self.assertEqual(len({result.json()["batch_id"] for result in results}), 1)
        retry_url, _, retry = self.prepare(name="重命名再试.csv")
        self.assertEqual(self.confirm(retry_url, retry)["batch_id"], results[0].json()["batch_id"])
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM import_rows")["n"], 1)

    def test_reviewed_batch_revocation_survives_concurrent_confirmation_retry(self):
        row = [*VALID]
        row[4] = "CC BY-SA 4.0"
        url, _, plan = self.prepare(make_csv(rows=[row]))
        preview = self.check(url, plan)
        form = {**plan, "preview_token": preview["preview_token"]}
        receipt = self.confirm(url, plan)
        path = self.root + "/batches/" + receipt["batch_id"]
        record_id = self.client.get(path).json()["rows"][0]["record_id"]
        self.client.post(f"/api/corpus/{self.study}/records/{record_id}/review", json={
            "decision": "verified", "role": "user_quote", "reason": "并发确认回归",
            "basis": "核对合成原话、合成许可与范围", "retention_until": "2090-01-01",
            "license_status": "authorized", "license_evidence_ref": "local:fixture-license",
        }).raise_for_status()

        start = Barrier(2, timeout=5)

        def post(endpoint, payload=None):
            start.wait()
            response = self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            retry = pool.submit(post, url + "/confirm", form)
            revocation = pool.submit(post, path + "/revoke")
            self.assertEqual(retry.result()["batch_id"], receipt["batch_id"])
            revoked = revocation.result()

        current = self.client.post(url + "/confirm", json=form)
        self.assertEqual(current.status_code, 201, current.text)
        self.assertEqual(current.json(), revoked)
        self.assertEqual(revoked["status"], "revoked")
        self.assertEqual(revoked["summary"]["total"], receipt["summary"]["total"])
        self.assertEqual(revoked["summary"]["staged"], receipt["summary"]["staged"])
        history = self.client.get(self.root + "/batches").json()
        self.assertEqual(history, {"batches": [revoked], "more": False, "drafts": []})
        self.assertIsNone(self.client.get(path).json()["rows"][0]["raw_text"])
        self.assertEqual(self.db.rows("SELECT * FROM import_candidates"), [])

    def test_failed_insert_rolls_back_entire_batch_and_can_retry(self):
        url, _, plan = self.prepare(make_csv(rows=[VALID, ["第二条", *VALID[1:]]]))
        with self.db.db() as db:
            db.execute("""CREATE TRIGGER fail_second_import_row BEFORE INSERT ON import_rows WHEN NEW.line_number=3
                          BEGIN SELECT RAISE(ABORT,'test row fault'); END""")
        preview = self.check(url, plan)
        form = {**plan, "preview_token": preview["preview_token"]}
        self.assertEqual(self.client.post(url + "/confirm", json=form).status_code, 503)
        self.assertEqual(self.db.rows("SELECT * FROM import_batches"), [])
        self.assertEqual(self.db.rows("SELECT * FROM import_rows"), [])
        self.assertEqual(len(self.client.get(self.root + "/batches").json()["drafts"]), 1)
        with self.db.db() as db:
            db.execute("DROP TRIGGER fail_second_import_row")
        self.assertEqual(self.client.post(url + "/confirm", json=form).json()["summary"]["staged"], 2)

    def test_persists_across_new_app_lifespan(self):
        url, _, plan = self.prepare()
        receipt = self.confirm(url, plan)
        client, _ = self.open_client()
        data = client.get(self.root + "/batches/" + receipt["batch_id"]).json()
        self.assertIsNone(data["rows"][0]["raw_text"])
        self.assertEqual(self.db.one("SELECT raw_text FROM import_rows WHERE batch_id=?", (receipt["batch_id"],))["raw_text"], VALID[0])
        self.assertEqual(data["batch"]["scope_id"], self.scope)
        self.assertEqual(self.db.rows("PRAGMA foreign_key_check"), [])

    def test_xlsx_diagnostic_warnings_do_not_disclose_workbook_metadata(self):
        private_marker = "fixture-private-print-area"
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter("always")
            url, _, plan = self.prepare(make_xlsx(private_print_area=private_marker), "warnings.xlsx", 1)
            receipt = self.confirm(url, plan)
        self.assertEqual(receipt["summary"]["staged"], 1)
        self.assertFalse(any(private_marker in str(warning.message) for warning in observed))

    def test_xlsx_formula_is_rejected_without_evaluation(self):
        url, _, plan = self.prepare(make_xlsx([VALID, ["=1+1", *VALID[1:]]]), "formula.xlsx", 1)
        check = self.check(url, plan)
        self.assertIn("excel_formula", {issue["code"] for issue in check["summary"]["issues"]})
        batch = self.confirm(url, plan)
        self.assertEqual(batch["summary"]["rejected"], 1)
        row = self.db.one("SELECT raw_text, status FROM import_rows WHERE line_number=3")
        self.assertEqual(row, {"raw_text": "=1+1", "status": "rejected"})

    def test_upload_draft_discard_and_wrong_project_boundaries(self):
        url, file, _ = self.prepare()
        other, _ = self.make_project()
        self.assertEqual(self.client.delete(url.replace(self.study, other)).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.db.rows("SELECT * FROM import_files"), [])
        self.assertNotIn("source_bytes", file["file"])

    def test_bad_files_archive_limits_and_upload_privacy(self):
        nonlocal_client, _ = self.open_client(peer="192.0.2.7")
        self.assertEqual(nonlocal_client.get(self.root + "/batches").status_code, 403)
        self.assertEqual(self.upload(make_csv(), "../outside.csv").status_code, 422)
        self.assertEqual(self.upload(make_csv(), "C:\\outside.csv").status_code, 422)
        self.assertEqual(self.upload(make_csv(), "docs.xlsm").status_code, 422)
        self.assertEqual(self.upload(b"broken", "docs.xlsx").status_code, 422)
        self.assertEqual(self.upload(b"", "empty.csv").status_code, 422)
        self.assertEqual(self.upload(b"\0test", "binary.csv").status_code, 422)
        self.assertEqual(self.upload(b"a" * (MAX_UPLOAD + 1)).status_code, 413)
        path = self.root + f"/scopes/{self.scope}/uploads"
        self.assertEqual(self.client.post(path, content=b"x", headers={"Origin": "https://external.invalid"}).status_code, 403)
        for entry in (
            ("../outside.xml", b"<e/>"), ("xl/vbaProject.bin", b"only a fixture"),
            ("xl/embeddings/test.bin", b"only a fixture"),
            ("xl/other.xml", b"<!DOCTYPE sheet><sheet/>"),
            ("xl/sheet.xml", b'<worksheet><c r="XFD8"/></worksheet>'),
        ):
            content = custom_zip([("[Content_Types].xml", b"<Types/>"), entry])
            self.assertEqual(self.upload(content, "guard.xlsx").status_code, 422)
        self.assertEqual(self.db.rows("SELECT * FROM import_files"), [])


class ImportMigrationTest(unittest.TestCase):
    def test_upgrade_from_v2_preserves_scope_and_rolls_back_if_interrupted(self):
        with TemporaryDirectory(prefix="进口旧库 ") as directory:
            root = Path(directory)
            with closing(sqlite3.connect(root / "connectivity.sqlite3")) as db, db:
                db.executescript((MIGRATIONS / "001_connectivity.sql").read_text("utf-8"))
                db.executescript((MIGRATIONS / "002_research_studies.sql").read_text("utf-8"))
                db.execute("""INSERT INTO study_projects VALUES
                    ('p','request','sig','旧库研究','','','','','draft',NULL,1,'t','t')""")
                db.execute("INSERT INTO study_scopes VALUES ('p','s',1,'{}','[]','','t')")
                db.execute("INSERT INTO study_scope_freezes VALUES ('p','s','t')")
            read_text = Path.read_text

            def broken(path, *args, **kwargs):
                result = read_text(path, *args, **kwargs)
                return result + "\nINSERT INTO nonexistent VALUES (1);" if path.name.startswith("003_") else result

            with patch.object(Path, "read_text", broken), self.assertRaises(sqlite3.Error):
                Store(root)
            with closing(sqlite3.connect(root / "connectivity.sqlite3")) as old:
                self.assertEqual(old.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertIsNone(old.execute("SELECT name FROM sqlite_master WHERE name='import_batches'").fetchone())
            store = Store(root)
            self.assertEqual(store.one("PRAGMA user_version")["user_version"], 8)
            self.assertEqual(store.one("SELECT study_id, scope_id FROM study_scope_freezes"), {"study_id": "p", "scope_id": "s"})
            self.assertEqual(Store(root).one("PRAGMA integrity_check")["integrity_check"], "ok")

    def test_row_column_and_expanded_size_limits(self):
        with self.assertRaises(ImportProblem):
            read_csv(b"raw_text\nx\n" + b"y\n" * MAX_ROWS)
        with self.assertRaises(ImportProblem):
            read_csv(b",".join([b"abc"] * 65) + b"\ncontents\n")
        with self.assertRaises(ImportProblem):
            read_csv(b'raw_text\n"unterminated\n')
        with patch('src.ingestion.import_files.MAX_XLSX_EXPANDED', 128), self.assertRaises(ImportProblem):
            read_sheet(custom_zip([("[Content_Types].xml", b"<Types/>"), ("xl/many.xml", b"x" * 256)]),
                       "xlsx", 0)
