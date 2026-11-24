from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from src.raw_store.store import Store


ORIGIN = "http://127.0.0.1:8765"
HEADERS = {"Origin": ORIGIN, "X-VOC-Action": "connectivity"}
ROOT = "/api/studies"
MIGRATIONS = Path(__file__).resolve().parents[1] / "src/raw_store/migrations"


def draft(name="社区服务体验", **scope_fields):
    return {
        "request_key": str(uuid4()),
        "name": name, "description": "本地测试研究说明", "background": "社区活动常以线下报名为主。",
        "objective": "了解家长的报名体验", "subject": "社区课后服务", "status": "active",
        "scope": {
            "mode": "open", "topic": "家长如何为孩子寻找课后活动？",
            "market": "中国大陆与新加坡", "language": "zh、en",
            "date_window": {"start": "2026-03-01", "end": "2026-08-01"},
            "audience": "有学龄儿童的家庭", "user_tasks": ["寻找活动", "安排接送"],
            "source_preferences": ["公开社区论坛", "本地访谈"],
            "inclusion_criteria": ["公开且有权限的原话"], "exclusion_criteria": ["广告与匿名转载"],
            **scope_fields,
        },
    }


class StudiesTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory(prefix="voc-study-研究 "))
        self.settings = Settings(Path(directory))
        self.app, self.client = self.open_client()

    def open_client(self, peer="127.0.0.1"):
        app = create_app(self.settings)
        client = self.enterContext(TestClient(app, base_url=ORIGIN, client=(peer, 23000), headers=HEADERS))
        return app, client

    @property
    def store(self):
        return self.app.state.store

    def create(self, form=None):
        response = self.client.post(ROOT, json=draft() if form is None else form)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @staticmethod
    def edit(form, project, **fields):
        result = {key: deepcopy(value) for key, value in form.items() if key != "request_key"}
        return {**result, **fields, "revision": project["revision"]}

    def test_create_and_read_pdt_study_scope(self):
        form = draft()
        created = self.create(form)
        self.assertEqual(created["study_id"], created["scope"]["study_id"])
        self.assertEqual(created["scope"]["scope_version"], "v1")
        self.assertFalse(created["is_current"])
        for key in ("name", "description", "background", "objective", "subject", "status"):
            self.assertEqual(created[key], form[key])
        for key, value in form["scope"].items():
            self.assertEqual(created["scope"][key], value)
        self.assertEqual(created["scope"]["product_category_ids"], [])
        self.assertEqual(created["created_at"], created["updated_at"])
        self.assertNotIn("request_key", created)
        result = self.client.get(ROOT + "/" + created["study_id"])
        self.assertEqual(result.json(), created)
        self.assertEqual(result.headers["cache-control"], "no-store")

    def test_metadata_edit_and_unchanged_scope(self):
        form = draft(mode="cross_category", product_category_ids=["SVC_B", "SVC_A"])
        project = self.create(form)
        form["scope"]["product_category_ids"].reverse()
        path = ROOT + "/" + project["study_id"]
        edited = self.client.put(path, json=self.edit(form, project, name="社区服务复盘", status="draft"))
        self.assertEqual(edited.status_code, 200, edited.text)
        data = edited.json()
        self.assertEqual((data["name"], data["status"]), ("社区服务复盘", "draft"))
        self.assertEqual(data["revision"], 2)
        self.assertEqual(data["created_at"], project["created_at"])
        self.assertGreaterEqual(data["updated_at"], project["updated_at"])
        self.assertEqual(data["scope"], project["scope"])
        self.assertEqual(len(data["scope_history"]), 1)
        noop = self.client.put(path, json=self.edit(form, data, name=data["name"], status=data["status"])).json()
        self.assertEqual(noop["revision"], data["revision"])

    def test_immutable_history_freeze_and_new_current_version(self):
        form = draft()
        project = self.create(form)
        path = ROOT + "/" + project["study_id"]
        first = project["scope"]["scope_id"]
        frozen = self.client.post(path + "/scopes/" + first + "/freeze")
        self.assertEqual(frozen.status_code, 200, frozen.text)
        frozen = frozen.json()
        self.assertIsNotNone(frozen["scope"]["frozen_at"])
        self.assertEqual(self.client.post(path + "/scopes/" + first + "/freeze").json(), frozen)
        edited = self.edit(form, frozen, change_note="纳入更多地区")
        edited["scope"]["market"] = "中国大陆、日本"
        edited["scope"]["date_window"]["end"] = "2026-09-01"
        updated = self.client.put(path, json=edited)
        self.assertEqual(updated.status_code, 200, updated.text)
        newest = updated.json()["scope"]
        self.assertEqual(newest["scope_version"], "v2")
        self.assertNotEqual(newest["scope_id"], first)
        self.assertIsNone(newest["frozen_at"])
        self.assertEqual(set(newest["changed_fields"]), {"market", "date_window"})
        self.assertEqual(newest["change_note"], "纳入更多地区")
        history = self.client.get(path + "/scopes").json()
        self.assertEqual([version["scope_version"] for version in history], ["v2", "v1"])
        self.assertEqual(self.client.get(path + "/scopes/" + first).json(), frozen["scope"])
        for query in ("UPDATE study_scopes SET content_json='{}'", "DELETE FROM study_scopes",
                      "UPDATE study_scope_freezes SET frozen_at='changed'", "DELETE FROM study_scope_freezes",
                      "DELETE FROM study_projects"):
            with self.subTest(query=query), self.assertRaises(sqlite3.IntegrityError), self.store.db() as db:
                db.execute(query)

    def test_unfrozen_historical_scope_cannot_be_frozen(self):
        form = draft()
        created = self.create(form)
        path = ROOT + "/" + created["study_id"]
        edit = self.edit(form, created)
        edit["scope"]["topic"] = "怎样安排接送？"
        self.assertEqual(self.client.put(path, json=edit).status_code, 200)
        self.assertEqual(self.client.post(path + "/scopes/" + created["scope"]["scope_id"] + "/freeze").status_code, 409)

    def test_search_filters_sort_and_select_project_context(self):
        first = self.create(draft("A 咖啡店体验"))
        second = self.create({**draft("Z CAFÉ 服务", topic="跨地点任务"), "status": "draft"})
        self.assertEqual(self.client.post(ROOT + "/" + first["study_id"] + "/select").status_code, 200)
        searched = self.client.post(ROOT + "/search", json={"query": "café", "status": "draft"}).json()
        self.assertEqual([p["name"] for p in searched["projects"]], [second["name"]])
        self.assertEqual(searched["current"]["study_id"], first["study_id"])
        self.assertEqual(searched["current"]["scope_id"], first["scope"]["scope_id"])
        for sort in ("name", "created", "updated"):
            listed = self.client.post(ROOT + "/search", json={"sort": sort}).json()["projects"]
            expected = [first, second] if sort == "name" else [second, first]
            self.assertEqual([p["study_id"] for p in listed], [p["study_id"] for p in expected])
        self.assertEqual(len(self.client.post(ROOT + "/search", json={"query": "跨地点"}).json()["projects"]), 1)
        self.assertEqual(self.client.post(ROOT + "/search", json={"query": "' OR 1=1 --"}).json()["projects"], [])
        path = ROOT + "/" + second["study_id"]
        self.assertTrue(self.client.post(path + "/select").json()["is_current"])
        self.assertFalse(self.client.get(ROOT + "/" + first["study_id"]).json()["is_current"])
        self.assertEqual(self.client.get(ROOT).json()["current"]["study_id"], second["study_id"])

    def test_all_five_scope_modes(self):
        cases = [
            ("single_product", ["门禁终端-A"], ["CAT_ACCESS"]),
            ("single_category", [], ["CAT_EDUCATION"]),
            ("multi_product_category", ["服务-A", "服务-B"], ["CAT_TRANSIT", "CAT_ACCESS"]),
            ("cross_category", [], ["CAT_TRANSIT", "CAT_ACCESS"]),
            ("open", [], []),
        ]
        for mode, products, categories in cases:
            with self.subTest(mode=mode):
                project = self.create(draft(mode=mode, product_ids=products, product_category_ids=categories))
                self.assertEqual(project["scope"]["mode"], mode)
                self.assertEqual(project["scope"]["product_ids"], sorted(products))
                self.assertEqual(project["scope"]["product_category_ids"], sorted(categories))

    def test_required_validation_invalid_input_and_no_echo(self):
        invalid_forms = [
            {**draft(), "name": "  "}, draft(topic=" "), draft(mode="unsupported"),
            draft(mode="single_product"), draft(mode="single_category", product_category_ids=["A", "B"]),
            draft(mode="multi_product_category", product_ids=["P"], product_category_ids=["A"]),
            draft(mode="cross_category", product_category_ids=["A", "A"]), draft(product_ids=["P"]),
            draft(date_window={"start": "2026-09-01", "end": "2026-08-01"}),
            draft(date_window={"start": "2026-02-30"}), draft(date_window={"end": 1790000000}),
            {**draft(), "status": "archived"},
            {**draft(), "private_unknown": "仅限本地的字段内容"},
        ]
        for form in invalid_forms:
            with self.subTest(case=invalid_forms.index(form)):
                response = self.client.post(ROOT, json=form)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("仅限本地的字段内容", response.text)
                self.assertIsInstance(response.json()["detail"], str)
        self.assertEqual(self.client.post(ROOT, content="a" * 200_000, headers={
            **HEADERS, "Content-Type": "application/json",
        }).status_code, 413)
        self.assertEqual(self.client.post(ROOT, data={"bad": "type"}).status_code, 415)
        self.assertEqual(self.client.get(ROOT).json(), {"projects": [], "current": None})

    def test_project_isolation_and_composite_foreign_keys(self):
        first, second = (self.create(draft(name)) for name in ("公共交通", "社区支持"))
        p, q = first["study_id"], second["study_id"]
        scope_id = first["scope"]["scope_id"]
        self.assertEqual(self.client.get(f"{ROOT}/{q}/scopes/{scope_id}").status_code, 404)
        self.assertEqual(self.client.post(f"{ROOT}/{q}/scopes/{scope_id}/freeze").status_code, 404)
        self.assertEqual(self.client.post(f"{ROOT}/{p}/scopes/{scope_id}/freeze").status_code, 200)
        self.assertIsNone(self.client.get(f"{ROOT}/{q}").json()["scope"]["frozen_at"])
        with self.assertRaises(sqlite3.IntegrityError), self.store.db() as db:
            db.execute("CREATE TABLE test_refs(study_id,scope_id, FOREIGN KEY(study_id,scope_id) "
                       "REFERENCES study_scope_freezes(study_id,scope_id))")
            db.execute("INSERT INTO test_refs VALUES (?,?)", (p, scope_id))
            db.execute("INSERT INTO test_refs VALUES (?,?)", (q, scope_id))
        with self.store.db() as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_archive_restore_and_existing_selection(self):
        form = draft()
        data = self.create(form)
        path = ROOT + "/" + data["study_id"]
        self.client.post(path + "/select").raise_for_status()
        archived = self.client.delete(path, params={"revision": data["revision"]}).json()
        self.assertEqual(archived["status"], "archived")
        self.assertFalse(archived["is_current"])
        self.assertEqual(self.client.get(ROOT).json(), {"projects": [], "current": None})
        self.assertEqual(self.client.post(ROOT + "/search", json={"status": "archived"}).json()["projects"][0]["study_id"],
                         data["study_id"])
        self.assertEqual(self.client.post(path + "/select").status_code, 409)
        self.assertEqual(self.client.put(path, json=self.edit(form, archived)).status_code, 409)
        restored = self.client.post(path + "/restore", json={"revision": archived["revision"]}).json()
        self.assertEqual(restored["status"], "active")
        self.assertFalse(restored["is_current"])
        self.assertEqual(restored["scope"], data["scope"])
        self.assertEqual(restored["scope_history"], data["scope_history"])

    def test_concurrent_create_retry_does_not_duplicate(self):
        form = draft()
        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(pool.map(lambda _: self.client.post(ROOT, json=form), range(3)))
        self.assertEqual({r.status_code for r in responses}, {201})
        self.assertEqual(len({r.json()["study_id"] for r in responses}), 1)
        self.assertEqual(self.store.one("SELECT count(*) AS n FROM study_scopes")["n"], 1)
        self.assertEqual(self.client.post(ROOT, json={**form, "name": "另一项目"}).status_code, 409)

    def test_stale_edit_and_archive_conflicts(self):
        form = draft()
        data = self.create(form)
        path = ROOT + "/" + data["study_id"]
        self.assertEqual(self.client.put(path, json=self.edit(form, data, name="当前名称")).status_code, 200)
        self.assertEqual(self.client.put(path, json=self.edit(form, data, name="过期表单")).status_code, 409)
        self.assertEqual(self.client.delete(path, params={"revision": data["revision"]}).status_code, 409)
        self.assertEqual(self.client.get(path).json()["name"], "当前名称")

    def test_restart_preserves_local_project_and_selection(self):
        data = self.create()
        path = ROOT + "/" + data["study_id"]
        self.client.post(path + "/select").raise_for_status()
        _, restarted = self.open_client()
        self.assertEqual(restarted.get(path).json()["scope"], data["scope"])
        self.assertEqual(restarted.get(ROOT).json()["current"]["study_id"], data["study_id"])

    def test_transaction_rollback_if_scope_write_fails(self):
        form = draft()
        data = self.create(form)
        path = ROOT + "/" + data["study_id"]
        with self.store.db() as db:
            db.execute("""CREATE TRIGGER reject_next_scope BEFORE INSERT ON study_scopes
                          WHEN NEW.version_no > 1 BEGIN SELECT RAISE(ABORT,'test scope fault'); END""")
        edit = self.edit(form, data, name="不应部分保存")
        edit["scope"]["topic"] = "不应产生版本"
        response = self.client.put(path, json=edit)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("test scope fault", response.text)
        self.assertEqual(self.client.get(path).json(), data)
        with self.store.db() as db:
            db.execute("DROP TRIGGER reject_next_scope")
        self.assertEqual(self.client.put(path, json=edit).json()["scope"]["scope_version"], "v2")

    def test_local_origin_and_peer_controls(self):
        _, nonlocal_client = self.open_client(peer="192.0.2.5")
        self.assertEqual(nonlocal_client.get(ROOT).status_code, 403)
        self.assertEqual(nonlocal_client.post(ROOT, json=draft()).status_code, 403)
        self.assertEqual(self.client.post(ROOT, json=draft(), headers={"Origin": "https://other.invalid"}).status_code, 403)
        self.assertEqual(self.client.post(ROOT, json=draft(), headers={"X-VOC-Action": ""}).status_code, 403)
        self.assertEqual(self.client.get(ROOT).json()["projects"], [])


class StudyMigrationTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(TemporaryDirectory(prefix="voc-v1-研究 ")))
        self.path = self.folder / "connectivity.sqlite3"
        with sqlite3.connect(self.path) as old:
            old.executescript((MIGRATIONS / "001_connectivity.sql").read_text("utf-8"))
            old.execute("INSERT INTO runs VALUES ('old-run','existing','jevmodel','public-fixture','2026-11-23',NULL,'paused')")
            old.execute("INSERT INTO attempts VALUES (1,'old-run','2026-11-23',NULL)")
            old.execute("INSERT INTO evidence VALUES (1,1,'test','contract_check','2026-11-23',NULL,'{}','{}')")
            old.execute("INSERT INTO results VALUES (1,'G-1','BLOCKED','existing',NULL,'[1]','2026-11-23')")
            old.execute("INSERT INTO shards VALUES ('fixture-shard','old-run',1,'fixture','received','{}',7,NULL,1,'2026-11-23')")

    def test_v1_upgrade_retains_ledger_and_reopens(self):
        store = Store(self.folder)
        self.assertEqual(store.one("PRAGMA user_version")["user_version"], 2)
        self.assertEqual(store.one("SELECT status FROM results")["status"], "BLOCKED")
        self.assertEqual(store.one("SELECT tokens FROM shards")["tokens"], 7)
        self.assertEqual(json.loads(store.one("SELECT response_json FROM evidence")["response_json"]), {})
        self.assertEqual(Store(self.folder).one("PRAGMA integrity_check")["integrity_check"], "ok")
        self.assertEqual(store.rows("PRAGMA foreign_key_check"), [])
        for isolated in (Store(self.folder, diagnostic=True), Store(self.folder, fixture=True)):
            self.assertEqual(isolated.one("PRAGMA user_version")["user_version"], 1)
            self.assertIsNone(isolated.one("SELECT name FROM sqlite_master WHERE name='study_projects'"))

    def test_failed_v1_upgrade_rolls_back_and_can_retry(self):
        original_read = Path.read_text

        def broken(path, *args, **kwargs):
            value = original_read(path, *args, **kwargs)
            return value + "\nINSERT INTO missing_migration_table VALUES (1);" if path.name.startswith("002_") else value

        with patch.object(Path, "read_text", broken), self.assertRaises(sqlite3.OperationalError):
            Store(self.folder)
        with sqlite3.connect(self.path) as old:
            self.assertEqual(old.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertIsNone(old.execute("SELECT name FROM sqlite_master WHERE name='study_projects'").fetchone())
            self.assertEqual(old.execute("SELECT status FROM results").fetchone()[0], "BLOCKED")
        self.assertEqual(Store(self.folder).one("PRAGMA user_version")["user_version"], 2)
