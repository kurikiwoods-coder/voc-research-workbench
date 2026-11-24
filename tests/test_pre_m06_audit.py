"""Independent Pre-M06 journeys on synthetic, isolated project databases."""

from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import IncompleteRead
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from src.execution.checks import run_checks
from src.execution.transport import Response, network
from src.raw_store.store import Store
from test_api_setup import review_pair
from test_imports import BASE, HEADERS, MIGRATIONS, ORIGIN, make_csv, make_xlsx


TEXT = "合成访谈：预约社区阅览室时，我希望在提交前确认无障碍入口。"
SOURCE = "https://community.example.test/feedback/18"
ONE = "audit-credential-fixture-one"
TWO = "audit-credential-fixture-two"
UTC = datetime.now(timezone.utc).date()


def row(text=TEXT, source=SOURCE, license_note="本机登记的合成许可材料", privacy="public"):
    return [text, "forum", source, "2026-10-18", license_note, privacy]


class CrossModuleAudit(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory(prefix="voc-pre-m06 审计 "))
        self.settings = Settings(Path(folder))
        # A mistaken research request must fail without opening any remote socket.
        self.enterContext(patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("audit egress")))
        self.app, self.client = self.enterContext(self.open())

    @contextmanager
    def open(self, peer="127.0.0.1"):
        app = create_app(self.settings)
        with TestClient(app, base_url=ORIGIN, client=(peer, 27112), headers=HEADERS) as client:
            yield app, client

    def new_project(self, name="合成研究项目"):
        form = {
            "name": name, "request_key": str(uuid4()),
            "scope": {"mode": "open", "topic": "社区阅览设施的预约体验",
                      "date_window": {"start": "2026-10-01", "end": "2026-10-31"}},
        }
        project = self.client.post("/api/studies", json=form).raise_for_status().json()
        return form, self.freeze(project)

    def freeze(self, project):
        path = f"/api/studies/{project['study_id']}/scopes/{project['scope']['scope_id']}/freeze"
        return self.client.post(path).raise_for_status().json()

    def upload(self, project, data, filename, index=0):
        study, scope = project["study_id"], project["scope"]["scope_id"]
        root = f"/api/imports/{study}"
        response = self.client.post(
            f"{root}/scopes/{scope}/uploads", content=data,
            headers={"Content-Type": "application/octet-stream", "X-VOC-Filename": quote(filename)},
        )
        uploaded = response.raise_for_status().json()
        return f"{root}/uploads/{uploaded['file_id']}"

    def staged(self, project, data, filename, index=0):
        url = self.upload(project, data, filename, index)
        sheet = self.client.get(url, params={"sheet_index": index}).raise_for_status().json()
        plan = {"sheet_index": index, "mapping": sheet["suggested_mapping"], "privacy": "unknown"}
        preview = self.client.post(url + "/preview", json=plan).raise_for_status().json()
        return url, {**plan, "preview_token": preview["preview_token"]}

    def imported(self, project, rows=None, filename="合成语料.csv"):
        url, plan = self.staged(project, make_csv(rows=rows or [row()]), filename)
        batch = self.client.post(url + "/confirm", json=plan).raise_for_status().json()
        return batch, self.record(project, batch)

    @staticmethod
    def record(project, batch, line=2):
        return f"/api/corpus/{project['study_id']}/records/{batch['batch_id']}:{line}"

    def review(self, path, **overrides):
        data = {
            "decision": "verified", "role": "user_quote", "reason": "人工核对合成来源",
            "basis": "已核对签发方、适用范围和原文",
            "license_status": "authorized", "license_evidence_ref": "local:audit-assent",
            "retention_until": (UTC + timedelta(days=14)).isoformat(),
        }
        return self.client.post(path + "/review", json=data | overrides)

    def withdraw(self, path, note="复核：授权已撤销"):
        return self.review(path, decision="excluded", reason=note, license_status=None,
                           license_evidence_ref=None, retention_until=None).raise_for_status().json()

    def test_runtime_and_run_evidence_require_a_loopback_peer(self):
        db = self.app.state.store
        run, attempt = db.begin("audit-local-history", self.settings)
        db.record(attempt, "private-fixture", "local_sqlite", {}, {"value": TEXT})
        db.finish(run, attempt, False)
        with self.open(peer="192.0.2.12") as (_, nonlocal_client):
            for path in ("/api/workspace", f"/api/runs/{run}/evidence"):
                with self.subTest(path=path):
                    result = nonlocal_client.get(path)
                    self.assertEqual(result.status_code, 403)
                    self.assertNotIn(TEXT, result.text)
            result = nonlocal_client.post(f"/api/runs/{run}/resume")
            self.assertEqual(result.status_code, 403)
        self.assertEqual(len(db.audit(run)["attempts"]), 1)

    def test_jev_approval_cannot_follow_type_safe_key_rotation(self):
        path = "/api/setup/typesafe"
        self.client.put(path + "/key", json={"key": ONE}).raise_for_status()
        self.client.put(path + "/review", json=review_pair("typesafe")).raise_for_status()
        self.client.put("/api/setup/jev/typesafe").raise_for_status()
        self.client.put("/api/setup/jevmodel/key", json={"key": ONE}).raise_for_status()
        self.client.put("/api/setup/jevmodel/review", json=review_pair("jevmodel")).raise_for_status()
        self.client.put(path + "/key", json={"key": TWO}).raise_for_status()
        with self.open() as (_, restarted):
            reply = restarted.get("/api/workspace").raise_for_status()
            providers = {p["id"]: p for p in reply.json()["setup"]["providers"]}
            self.assertEqual(providers["typesafe"]["status"], "REVIEW_REQUIRED")
            self.assertTrue(providers["jevmodel"]["review"]["approved"])
            self.assertNotIn(ONE, reply.text)
            self.assertNotIn(TWO, reply.text)
            check = restarted.post(path + "/diagnostics", json={"request_key": str(uuid4())})
            self.assertEqual(check.raise_for_status().json()["status"], "REVIEW_REQUIRED")

    def test_same_file_renamed_reuses_confirmed_batch_without_spending_draft_slots(self):
        _, project = self.new_project()
        original, _ = self.imported(project)
        for index in range(9):
            url, plan = self.staged(project, make_csv(rows=[row()]), f"不同文件名-{index}.csv")
            duplicate = self.client.post(url + "/confirm", json=plan).raise_for_status().json()
            self.assertEqual(duplicate["batch_id"], original["batch_id"])
        history = self.client.get(f"/api/imports/{project['study_id']}/batches").raise_for_status().json()
        self.assertEqual(len(history["batches"]), 1)
        self.assertEqual(history["drafts"], [])
        self.upload(project, make_csv(rows=[row(text=TEXT + " 修订版")]), "独立新稿.csv")

    def test_staging_duplicates_respect_privacy_and_corpus_role(self):
        _, project = self.new_project()
        internal = row(privacy="internal")
        public = row()
        headers = [*BASE, "content_role"]
        rows = [[*internal, "internal"], [*public, "background"],
                [*public, "user_quote"], [*public, "user_quote"]]
        url, plan = self.staged(project, make_csv(headers, rows), "角色隔离.csv")
        receipt = self.client.post(url + "/confirm", json=plan).raise_for_status().json()
        detail = self.client.get(f"/api/imports/{project['study_id']}/batches/{receipt['batch_id']}")
        self.assertEqual(
            [record["status"] for record in detail.raise_for_status().json()["rows"]],
            ["pending_review", "pending_review", "staged", "duplicate"],
        )

    def test_r2_known_cases_and_independent_license_variants(self):
        _, project = self.new_project()
        variants = (
            ("未授权，等待书面审批", "denied"),
            ("尚未取得原作者的書面收錄許可。", "denied"),
            ("稿件已提供，授權仍在審批流程中。", "pending"),
            ("Reuse permission has not yet been granted.", "denied"),
            ("A licence was available, but it has since been cancelled.", "revoked"),
            ("许可原已授予，现已失效。", "expired"),
            ("Granted for viewing only. Reuse consent has yet to be granted.", "pending"),
        )
        for index, (statement, expected) in enumerate(variants):
            with self.subTest(variant=index):
                _, path = self.imported(project, [row(source=SOURCE + f"/{index}", license_note=statement)])
                self.assertEqual(self.review(path).status_code, 422)
                record = self.client.get(path).raise_for_status().json()
                self.assertEqual(record["license_status"], expected)
                self.assertIsNone(record["raw_text"])
                self.assertEqual(self.client.get(path + "/eligible").status_code, 409)
        _, valid = self.imported(project, [row(source=SOURCE + "/legitimate", license_note="已明確授權；許可尚未撤銷。")])
        self.review(valid).raise_for_status()
        self.assertTrue(self.withdraw(valid)["source_permission_revoked"])
        self.assertEqual(self.review(valid).status_code, 409)
        self.assertIsNone(self.client.get(valid).raise_for_status().json()["raw_text"])

    def test_source_fragment_copies_remain_restricted_after_restart_and_reimport(self):
        _, project = self.new_project()
        first_batch, first = self.imported(project)
        second_batch, second = self.imported(project, [row(source=SOURCE + "#comment-9")])
        spare_batch, spare = self.imported(project, [row(source=SOURCE + "/independent")])
        for path in (first, second, spare):
            self.review(path).raise_for_status()
        self.assertEqual(self.client.get(spare).json()["duplicate"]["record_count"], 3)
        self.withdraw(first, "复核文件：授权已撤销")
        with self.open() as (app, restarted):
            for batch, path in ((first_batch, first), (second_batch, second)):
                detail = restarted.get(f"/api/imports/{project['study_id']}/batches/{batch['batch_id']}")
                self.assertEqual(restarted.get(path + "/eligible").status_code, 409)
                self.assertIsNone(restarted.get(path).json()["raw_text"])
                self.assertIsNone(detail.raise_for_status().json()["rows"][0]["raw_text"])
                self.assertNotIn(TEXT, restarted.get(str(detail.request.url) + "/errors.csv").text)
            self.assertEqual(restarted.get(spare).json()["duplicate"]["record_count"], 1)
            self.assertEqual(app.state.store.one("SELECT raw_text FROM import_candidates WHERE record_id=?",
                                                 (second.rsplit("/", 1)[-1],))["raw_text"], None)
        alias = self.upload(project, make_csv(rows=[row(source=SOURCE + "#comment-12")]), "来源副本.csv")
        self.assertEqual(self.client.get(alias).status_code, 409)

    def test_fragment_of_old_evidence_cannot_become_a_new_grant(self):
        _, project = self.new_project()
        _, path = self.imported(project)
        proof = "https://licensing.example.test/written-grant"
        self.review(path, license_evidence_ref=proof).raise_for_status()
        self.withdraw(path)
        new = dict(reauthorize=True, license_issued_on=UTC.isoformat())
        self.assertEqual(self.review(path, license_evidence_ref=proof + "#appendix", **new).status_code, 422)
        self.review(path, license_evidence_ref="local:separately-issued-permit", **new).raise_for_status()
        self.assertEqual(self.client.get(path + "/eligible").json()["raw_text"], TEXT)

    def test_preexisting_approval_with_now_recognized_denial_is_no_longer_eligible(self):
        _, project = self.new_project()
        batch, path = self.imported(project, [
            row(license_note="Reuse permission has not yet been granted."),
        ])
        # Keep the same persisted approval an older policy could write for this note.
        with patch("src.raw_store.corpus.license_note_state", return_value="unknown"):
            self.review(path).raise_for_status()
        with self.open() as (_, restarted):
            self.assertEqual(restarted.get(path + "/eligible").status_code, 409)
            record = restarted.get(path).raise_for_status().json()
            self.assertEqual(record["license_status"], "denied")
            self.assertIsNone(record["raw_text"])
            root = f"/api/imports/{project['study_id']}/batches/{batch['batch_id']}"
            self.assertIsNone(restarted.get(root).raise_for_status().json()["rows"][0]["raw_text"])

    def test_preexisting_unclassified_withdrawal_restricts_the_source_after_upgrade(self):
        _, project = self.new_project()
        _, original = self.imported(project)
        _, alias = self.imported(project, [row(source=SOURCE + "#alias")])
        for path in original, alias:
            self.review(path).raise_for_status()
        # Older builds saved this exclusion without a structured revoked state.
        with patch("src.raw_store.corpus.source_permission_revoked", return_value=False):
            self.withdraw(original, "The reuse licence was subsequently cancelled.")
        old_view = (MIGRATIONS / "005_corpus_licenses.sql").read_text(encoding="utf-8")
        old_view = old_view[old_view.index("CREATE VIEW IF NOT EXISTS corpus_withdrawals"):].split(";", 1)[0]
        with self.app.state.store.db() as db:
            db.execute("DROP VIEW corpus_withdrawals")
            db.execute(old_view)
            db.execute("PRAGMA user_version=5")
        with self.open() as (app, restarted):
            self.assertEqual(app.state.store.one("PRAGMA user_version"), {"user_version": 6})
            self.assertEqual(app.state.store.rows("PRAGMA foreign_key_check"), [])
            self.assertEqual(restarted.get(alias + "/eligible").status_code, 409)
            self.assertTrue(restarted.get(alias).raise_for_status().json()["source_permission_revoked"])

    def test_corrupt_workspace_startup_fails_without_overwriting_database(self):
        directory = Path(self.enterContext(TemporaryDirectory(prefix="voc-audit damaged workspace ")))
        original = b"synthetic damaged SQLite header"
        archive = directory / "connectivity.sqlite3"
        archive.write_bytes(original)
        with self.assertRaisesRegex(sqlite3.DatabaseError, "not a database"):
            with TestClient(create_app(Settings(directory)), base_url=ORIGIN, client=("127.0.0.1", 27113)):
                self.fail("An unreadable database must not produce a healthy workspace.")
        self.assertEqual(archive.read_bytes(), original)

    def test_csv_xlsx_scope_history_project_isolation_and_m06_contract(self):
        form, project = self.new_project("场景 A／C")
        _, other = self.new_project("场景 B")
        csv, first = self.imported(project)
        other_batch, other_record = self.imported(other)
        change = {key: value for key, value in form.items() if key != "request_key"}
        change["scope"] = {**form["scope"], "date_window": {"start": "2026-10-16", "end": "2026-11-30"}}
        response = self.client.put(
            f"/api/studies/{project['study_id']}", json={**change, "revision": project["revision"]},
        )
        revised = self.freeze(response.raise_for_status().json())
        target = f"/api/studies/{other['study_id']}/select"
        self.client.post(target).raise_for_status()
        url, plan = self.staged(revised, make_xlsx(rows=[row()]), "合成跨版本.xlsx", 1)
        workbook = self.client.post(url + "/confirm", json=plan).raise_for_status().json()
        second = self.record(revised, workbook)
        for path in (first, second, other_record):
            self.review(path).raise_for_status()
        with self.open() as (app, client):
            details = [client.get(path + "/eligible").raise_for_status().json() for path in (first, second, other_record)]
            for expected, record, scope, batch in zip(
                (first, second, other_record), details, (project, revised, other), (csv, workbook, other_batch),
            ):
                trace = record["trace"]
                self.assertEqual(record["record_id"], expected.rsplit("/", 1)[-1])
                self.assertEqual((trace["study_id"], trace["scope_id"], trace["scope_version"]),
                                 (scope["study_id"], scope["scope"]["scope_id"], scope["scope"]["scope_version"]))
                self.assertEqual((trace["batch_id"], trace["file_id"], trace["line_number"]),
                                 (batch["batch_id"], batch["file_id"], 2))
                self.assertEqual(record["raw_sha256"], hashlib.sha256(TEXT.encode("utf-8")).hexdigest())
                self.assertEqual((record["raw_text"], record["metadata"]["source_url"]), (TEXT, SOURCE))
                self.assertEqual((record["status"], record["license_status"], record["privacy"], record["role"]),
                                 ("verified", "authorized", "public", "user_quote"))
                self.assertTrue(record["engineering_eligible"])
                self.assertIs(record["source_permission_revoked"], False)
                self.assertFalse(record["research_eligible"] or record["outbound_allowed"])
            self.assertEqual(details[0]["duplicate"]["group_id"], details[1]["duplicate"]["group_id"])
            self.assertNotEqual(details[0]["duplicate"]["group_id"], details[2]["duplicate"]["group_id"])
            self.assertEqual(details[0]["duplicate"]["record_count"], 2)
            self.assertEqual(details[2]["duplicate"]["record_count"], 1)
            self.assertEqual(client.get(first.replace(project["study_id"], other["study_id"])).status_code, 404)
            self.assertEqual(app.state.store.rows("PRAGMA foreign_key_check"), [])

    def test_internal_material_stays_out_of_run_diagnostics_and_eligible_records(self):
        _, project = self.new_project()
        internal = "合成内部 CX：隔离记录，不外发。"
        _, path = self.imported(project, [row(text=internal, privacy="internal")])
        self.review(path, role="internal").raise_for_status()
        self.assertEqual(self.client.get(path + "/eligible").status_code, 409)
        self.client.put("/api/setup/jevmodel/key", json={"key": ONE}).raise_for_status()
        probe = self.client.post("/api/setup/jevmodel/diagnostics", json={"request_key": str(uuid4())})
        self.assertEqual(probe.raise_for_status().json()["status"], "REVIEW_REQUIRED")
        self.assertNotIn(internal, probe.text)
        workspace = self.client.get("/api/workspace").raise_for_status()
        self.assertEqual(workspace.json()["history"], [])
        self.assertNotIn(internal, workspace.text)
        self.assertEqual(self.app.state.diagnostics.rows("PRAGMA user_version"), [{"user_version": 1}])
        tables = self.app.state.diagnostics.rows("SELECT name FROM sqlite_master WHERE type='table'")
        self.assertFalse({"import_rows", "corpus_reviews", "study_projects"} & {table["name"] for table in tables})

    def test_process_kill_rolls_back_local_write_and_preserves_committed_research(self):
        _, project = self.new_project()
        batch, path = self.imported(project)
        self.review(path).raise_for_status()
        ready = self.settings.directory / "transaction-open"
        worker = (
            "import sqlite3,sys,time\n"
            "from pathlib import Path\n"
            "db=sqlite3.connect(sys.argv[1]); db.execute('BEGIN IMMEDIATE')\n"
            "db.execute('UPDATE import_batches SET revoked_at=? WHERE batch_id=?', ('uncommitted', sys.argv[2]))\n"
            "Path(sys.argv[3]).touch(); time.sleep(60)\n"
        )
        proc = subprocess.Popen([sys.executable, "-c", worker, str(self.app.state.store.path),
                                 batch["batch_id"], str(ready)])
        try:
            deadline = time.monotonic() + 12
            while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready.exists(), "Worker failed to acquire transaction.")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=12)
        with self.open() as (app, restarted):
            self.assertEqual(restarted.get(path + "/eligible").raise_for_status().json()["raw_text"], TEXT)
            self.assertEqual(app.state.store.rows("PRAGMA integrity_check"), [{"integrity_check": "ok"}])
            self.assertEqual(app.state.store.rows("PRAGMA foreign_key_check"), [])
            root = f"/api/imports/{project['study_id']}/batches/{batch['batch_id']}"
            self.assertEqual(restarted.get(root).json()["batch"]["status"], "imported")

    def test_v1_run_records_survive_incremental_upgrade_and_signed_history_reads(self):
        directory = Path(self.enterContext(TemporaryDirectory(prefix="voc-audit v1 迁移 ")))
        path = directory / "connectivity.sqlite3"
        run = str(uuid4())
        ts = "2026-10-01T12:00:00+00:00"
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript((MIGRATIONS / "001_connectivity.sql").read_text(encoding="utf-8"))
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,'paused')", (run, "old-audit", "jevmodel", "fixture", ts, ts))
            db.execute("INSERT INTO attempts VALUES (1,?,?,?)", (run, ts, ts))
            db.execute("INSERT INTO evidence VALUES (1,1,'audit','local_sqlite',?,NULL,'{}','{}')", (ts,))
        migrated = Store(directory)
        self.assertEqual(migrated.one("PRAGMA user_version"), {"user_version": 6})
        self.assertEqual(migrated.audit(run)["attempts"][0]["evidence"][0]["id"], 1)
        self.assertEqual(migrated.rows("PRAGMA foreign_key_check"), [])
        self.assertEqual(Store(directory).audit(run), migrated.audit(run))


class FixtureStorageAudit(unittest.TestCase):
    def test_connection_fixture_cannot_enter_live_acceptance_or_create_workbench_db(self):
        root = Path(self.enterContext(TemporaryDirectory(prefix="voc-audit fixture storage ")))
        cfg = Settings(root)
        fixture = Store(root, fixture=True)
        with self.assertRaises(ValueError):
            run_checks(cfg, fixture, "fixture-readback", transport=lambda *args: Response(None, {}))
        self.assertEqual(fixture.history(), [])
        self.assertFalse((root / "connectivity.sqlite3").exists())
        self.assertEqual(fixture.rows("PRAGMA foreign_key_check"), [])


class TransportAudit(unittest.TestCase):
    def test_truncated_provider_response_enters_offline_failure_handling(self):
        with patch("src.execution.transport.build_opener") as builder:
            builder.return_value.open.side_effect = IncompleteRead(b"fixture", 12)
            reply = network("GET", "https://example.invalid", None, {})
        self.assertIsNone(reply.status)
        self.assertEqual(reply.body, {"error": "connection_interrupted"})
