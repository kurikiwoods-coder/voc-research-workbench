"""Exercise the M07 workspace against the real service and synthetic registry data."""

from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect

from relations_browser import CANDIDATE, CATALOG, FIXTURES, PRODUCT_A, project, seed
from src.raw_store.relations import RelationGrant
from src.raw_store.store import Store
from test_m06_constraints import registry, seal_registry


DRAFT_GRANT_FILE = "synthetic-m07-study.txt"
NEXT_VERSION = "8.1.0"
LATER_VERSION = "8.2.0"
DRAFT_NAME = "合成候选：在无网络时继续"
OLD_NAME = "合成待审意图"
NEW_NAME = "合成待审意图第二版"


def registry_fixture_grants(directory):
    path = Path(directory) / DRAFT_GRANT_FILE
    if not path.is_file():
        return ()
    return tuple(RelationGrant(
        "synthetic-reviewer", "project_reviewer", "synthetic-owner", "local:registry-browser-fixture",
        "2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z",
        frozenset({"registry_draft"}), study_id,
    ) for study_id in path.read_text("ascii").splitlines())


def second_version(directory):
    with Store(Path(directory)).db() as db:
        db.execute("BEGIN IMMEDIATE")
        registry(db, NEXT_VERSION, CATALOG)
        for table in ("m06_task", "m06_intent", "m06_intent_task", "m06_representative"):
            columns = ", ".join(row["name"] for row in db.execute(f"PRAGMA table_info({table})")
                                if row["name"] != "registry_version")
            db.execute(f"INSERT INTO {table} (registry_version, {columns}) "
                       f"SELECT ?, {columns} FROM {table} WHERE registry_version=?", (NEXT_VERSION, CATALOG))
        db.execute("UPDATE m06_intent SET name=? WHERE registry_version=? AND intent_id=?",
                   (NEW_NAME, NEXT_VERSION, CANDIDATE))
        seal_registry(db, NEXT_VERSION)


def registry_browser_checks(browser, base, output, directory):
    output.mkdir(parents=True, exist_ok=True)
    base = base.rstrip("/")
    headers = {"Origin": base, "X-VOC-Action": "connectivity"}
    page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN")
    page.set_default_timeout(7500)
    errors, outbound = [], []

    def local_only(route):
        if urlsplit(route.request.url).netloc == urlsplit(base).netloc:
            route.continue_()
        else:
            outbound.append(route.request.url)
            route.abort()

    page.route("**/*", local_only)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/#registry")
    expect(page.get_by_role("heading", name="意图注册表", exact=True)).to_be_visible()
    wizard = page.get_by_role("dialog")
    if wizard.is_visible():
        wizard.get_by_role("button", name="稍后配置").click()
    expect(page.get_by_text("暂无已封版的注册表。", exact=True)).to_be_visible()
    expect(page.get_by_text("暂无获准编辑草稿的项目。", exact=True)).to_be_visible()

    fixture = project(page, base, headers, "M07 合成项目")
    project(page, base, headers, "M07 无授权项目")
    quotes, members = seed(page, base, headers, directory, fixture)
    second_version(directory)
    study = fixture["study_id"]
    grant = Path(directory) / DRAFT_GRANT_FILE
    grant.write_text(study, encoding="ascii")
    page.goto(base + "/#registry")
    catalog = page.get_by_role("region", name="意图知识库")
    expect(catalog.get_by_role("button", name=NEW_NAME, exact=True)).to_be_visible()
    expect(catalog.locator("#registry-items").get_by_text("候选缺主任务", exact=False)).to_be_visible()
    search = catalog.get_by_role("searchbox", name="搜索意图")
    search.fill("不存在的合成定义")
    search.press("Enter")
    expect(catalog.get_by_text("没有符合条件的意图。")).to_be_visible()
    search.fill("")
    page.get_by_label("注册表版本", exact=True).select_option(CATALOG)
    expect(page.get_by_text(f"历史只读 {CATALOG}", exact=False)).to_be_visible()
    catalog.get_by_role("button", name=OLD_NAME, exact=True).press("Enter")
    detail = page.locator("#registry-detail")
    expect(detail.get_by_role("heading", name=OLD_NAME, exact=True)).to_be_visible()
    expect(detail.get_by_role("button", name="从历史版本起草")).to_be_visible()
    expect(detail.get_by_role("button", name="起草修订")).to_have_count(0)

    page.get_by_text("历史版本与差异", exact=True).click()
    page.get_by_role("button", name="比较版本").click()
    comparison = page.locator("#registry-diff")
    expect(comparison.get_by_text(f"{OLD_NAME} → {NEW_NAME}")).to_be_visible()
    page.screenshot(path=str(output / "m07-version-diff.png"), full_page=True)

    page.route("**/api/registry/intents?*", lambda route: route.abort(), times=1)
    page.get_by_label("注册表版本", exact=True).select_option(NEXT_VERSION)
    expect(catalog.get_by_role("alert")).to_contain_text("无法连接本机服务")
    catalog.get_by_role("button", name="重试").click()
    expect(catalog.get_by_role("button", name=NEW_NAME, exact=True)).to_be_visible()

    drafts = page.get_by_role("region", name="项目候选草稿")
    project_select = drafts.get_by_label("草稿项目")
    expect(project_select.locator("option")).to_have_count(2)
    project_select.select_option(study)
    drafts.get_by_role("button", name="新建候选").press("Enter")
    editor = page.locator("#registry-draft-editor")
    expect(editor).to_be_focused()
    expect(editor.get_by_text("未保存草稿")).to_be_visible()
    editor.get_by_label("名称", exact=True).fill(DRAFT_NAME)
    editor.get_by_label("定义", exact=True).fill("只用合成记录验证隔离流程。")
    editor.get_by_label("纳入标准", exact=True).fill("合成的断网使用请求。")
    editor.get_by_label("排除标准", exact=True).fill("合成的联网设置请求。")
    member = members[PRODUCT_A]
    editor.get_by_label("项目证据引用（可选）").fill(f"2, {member['mention_id']}, {member['evidence_ids'][0]}")
    editor.get_by_label("本次变更理由").fill("浏览器回归合成创建")
    editor.get_by_role("button", name="保存草稿").click()
    expect(editor.get_by_text("草稿已保存。")).to_be_visible()
    editor.get_by_role("button", name="校验缺项").click()
    expect(editor.get_by_text("仍有缺项 · 正式发行关闭")).to_be_visible()
    expect(editor.get_by_text("主任务待确认", exact=True).first).to_be_visible()
    editor.get_by_role("button", name="查看证据 1").click()
    expect(editor.locator("blockquote")).to_have_text(FIXTURES[PRODUCT_A][1])
    assert editor.locator("blockquote b").count() == 0
    page.screenshot(path=str(output / "m07-candidate-preflight.png"), full_page=True)

    path = f"{base}/api/studies/{study}/registry/drafts"
    draft_id = page.request.get(path).json()["items"][0]["draft_id"]
    response = page.request.patch(f"{path}/{draft_id}", headers=headers, data={
        "request_key": "registry-browser-concurrent-revision", "expected_registry_version": NEXT_VERSION,
        "expected_revision": 1, "reason": "浏览器回归并发修订",
    })
    expect(response).to_be_ok()
    expect(page.request.post(f"{base}/api/imports/{study}/batches/{quotes[PRODUCT_A][0]}/revoke",
                             headers=headers)).to_be_ok()
    editor.get_by_role("button", name="查看证据 1").click()
    expect(editor.get_by_text("证据授权或资格已失效。")).to_be_visible()
    expect(editor.locator("blockquote")).to_have_count(0)
    editor.get_by_label("本次变更理由").fill("过时的修订")
    editor.get_by_role("button", name="保存草稿").click()
    expect(editor.locator("[data-draft-status]")).to_contain_text("版本冲突")
    drafts.get_by_role("button", name=DRAFT_NAME, exact=True).click()
    expect(editor.get_by_text("草稿 · 修订 2", exact=False)).to_be_visible()
    editor.get_by_role("checkbox", name="替换项目证据引用").check()
    editor.get_by_label("本次变更理由").fill("移除失去资格的证据引用")
    editor.get_by_role("button", name="保存草稿").click()
    expect(editor.get_by_text("草稿 · 修订 3", exact=False)).to_be_visible()
    expect(editor.get_by_role("button", name="查看证据 1")).to_have_count(0)
    editor.get_by_label("本次变更理由").fill("浏览器回归合成提交")
    editor.get_by_role("button", name="提交待审核").click()
    expect(editor.get_by_text("已提交待审核。")).to_be_visible()
    expect(editor.get_by_role("button", name="保存草稿")).to_have_count(0)
    editor.get_by_role("button", name="查看草稿历史").click()
    expect(editor.get_by_text("浏览器回归并发修订", exact=True)).to_be_visible()

    for width in (320, 390):
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
        page.screenshot(path=str(output / f"m07-{width}px.png"), full_page=True)

    page.set_viewport_size({"width": 1440, "height": 960})
    with Store(Path(directory)).db() as db:
        db.execute("BEGIN IMMEDIATE")
        registry(db, LATER_VERSION, NEXT_VERSION, seal=True)
    page.get_by_role("button", name="刷新版本").click()
    expect(page.get_by_text(f"当前版本 {LATER_VERSION}", exact=False)).to_be_visible()
    editor.get_by_label("本次变更理由").fill("新版后撤回旧提案")
    editor.get_by_role("button", name="撤回提案").click()
    expect(editor.get_by_text("提案已撤回。")).to_be_visible()

    grant.write_text("", encoding="ascii")
    expect(drafts.get_by_text("项目授权已撤销", exact=False)).to_be_visible(timeout=9000)
    expect(editor).to_be_hidden()
    expect(drafts.get_by_role("button", name=DRAFT_NAME, exact=True)).to_have_count(0)
    assert DRAFT_NAME not in page.content()
    assert FIXTURES[PRODUCT_A][1] not in page.content()
    assert not errors, errors
    assert not outbound, outbound
    page.close()
    print("M07 Chromium E2E passed: empty, search, version history/diff, candidate, conflict, authorization, keyboard, 320/390px.")
