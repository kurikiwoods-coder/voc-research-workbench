"""Local browser review and withdrawal with a synthetic CSV and temporary SQLite."""

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from urllib.parse import quote, urlsplit
from uuid import uuid4

from playwright.sync_api import expect


FIXTURE_TEXT = "我希望能提前选择预约时段，并在临近日期时收到提醒。<b>合成测试片段</b>"
FILENAME = "语料审核 合成数据.csv"


def add_batch(page, base, project, filename, source_url, *, text=FIXTURE_TEXT):
    columns = ["raw_text", "source_type", "source_url", "published_at",
               "access_policy", "privacy", "content_role"]
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(columns)
    writer.writerow([text, "forum", source_url, "2026-11-01",
                     "仅供隔离工程测试的合成许可", "public", "user_quote"])
    headers = {"Origin": base.rstrip("/"), "X-VOC-Action": "connectivity"}
    target = f"{base}/api/imports/{project['study_id']}"
    response = page.request.post(f"{target}/scopes/{project['scope']['scope_id']}/uploads",
                                 headers={**headers, "Content-Type": "application/octet-stream",
                                          "X-VOC-Filename": quote(filename)}, data=stream.getvalue().encode())
    assert response.ok
    upload = f"{target}/uploads/{response.json()['file_id']}"
    plan = {"sheet_index": 0, "mapping": {name: idx for idx, name in enumerate(columns)}, "privacy": "public"}
    response = page.request.post(upload + "/preview", headers=headers, data=plan)
    assert response.ok
    response = page.request.post(upload + "/confirm", headers=headers,
                                 data={**plan, "preview_token": response.json()["preview_token"]})
    assert response.ok
    return response.json()["batch_id"]


def open_record(page, filename):
    page.get_by_role("link", name=filename, exact=True).click()
    page.get_by_role("link", name="第 2 行", exact=True).click()
    expect(page.get_by_role("heading", name="原文溯源", exact=True)).to_be_visible()
    expect(page.locator("blockquote.corpus-quote")).to_have_count(0)
    expect(page.locator("blockquote.corpus-quote b")).to_have_count(0)


def verify_quote(page, text=FIXTURE_TEXT):
    page.get_by_label("审核结论").select_option("verified")
    page.get_by_label("语料角色").select_option("user_quote")
    page.get_by_label("许可状态").select_option("authorized")
    page.get_by_label("授权证据引用").fill("local:browser-fixture-license")
    page.get_by_label("审核原因").fill("隔离环境中的合成审核")
    page.get_by_label("核验依据").fill("已对照合成原文、来源许可、隐私等级和冻结范围。")
    date = datetime.now(timezone.utc).date() + timedelta(days=30)
    page.get_by_label("保留至（UTC）").fill(date.isoformat())
    page.get_by_role("button", name="保存审核", exact=True).click()
    expect(page.locator(".corpus-record-state")).to_contain_text("已核验")
    expect(page.locator("blockquote.corpus-quote")).to_have_text(text)
    expect(page.locator("blockquote.corpus-quote b")).to_have_count(0)


def corpus_browser_checks(browser, base, output):
    base = base.rstrip("/")
    page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN")
    local = urlsplit(base).netloc
    errors, external = [], []

    def local_only(route):
        if urlsplit(route.request.url).netloc == local:
            route.continue_()
        else:
            external.append(route.request.url)
            route.abort()

    page.route("**/*", local_only)
    page.on("pageerror", lambda error: errors.append(str(error)))
    headers = {"Origin": base.rstrip("/"), "X-VOC-Action": "connectivity"}
    response = page.request.post(base + "/api/studies", headers=headers, data={
        "name": "语料治理浏览器回归", "request_key": str(uuid4()),
        "scope": {"mode": "open", "topic": "合成预约场景"},
    })
    assert response.ok
    project = response.json()
    study = project["study_id"]
    freeze = f"{base}/api/studies/{study}/scopes/{project['scope']['scope_id']}/freeze"
    assert page.request.post(freeze, headers=headers).ok
    first_url = "https://forum-one.example.test/thread/1"
    first = add_batch(page, base, project, FILENAME, first_url)
    second_name = "跨来源 合成数据.csv"
    add_batch(page, base, project, second_name, "https://forum-two.example.test/thread/2")
    page.goto(f"{base}/#corpus/{study}")
    expect(page.get_by_role("heading", name="原始语料库", exact=True)).to_be_visible()
    wizard = page.get_by_role("dialog")
    if wizard.is_visible():
        wizard.get_by_role("button", name="稍后配置").click()
    open_record(page, FILENAME)
    original = page.url
    expect(page.get_by_text(first_url, exact=True)).to_have_count(0)
    verify_quote(page)
    expect(page.get_by_text(first_url, exact=True)).to_be_visible()
    expect(page.get_by_role("link", name=first_url, exact=True)).to_have_count(0)
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(output / "m05-record.png"))

    page.get_by_role("link", name="返回批次语料", exact=True).click()
    page.get_by_role("link", name="返回语料批次", exact=True).click()
    open_record(page, second_name)
    verify_quote(page)
    second = page.url
    expect(page.get_by_text("重复记录", exact=True)).to_be_visible()
    page.get_by_role("link", name="查看主记录", exact=True).click()
    expect(page).to_have_url(original)
    expect(page.get_by_text("主记录", exact=True)).to_be_visible()
    assert page.request.post(
        f"{base}/api/imports/{study}/batches/{first}/revoke", headers=headers,
    ).ok
    page.reload()
    expect(page.locator(".corpus-record-state")).to_contain_text("已撤销")
    expect(page.get_by_role("button", name="保存审核")).to_have_count(0)
    page.goto(second)
    expect(page.get_by_text("主记录", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="查看主记录", exact=True)).to_have_count(0)

    page.get_by_label("审核结论").select_option("excluded")
    page.get_by_label("许可状态").select_option("revoked")
    page.get_by_label("审核原因").fill("测试记录来源状态改变")
    page.get_by_role("button", name="保存审核", exact=True).click()
    expect(page.locator(".corpus-record-state")).to_contain_text("许可 已撤销")
    expect(page.locator("blockquote.corpus-quote")).to_have_count(0)
    page.get_by_label("许可状态").select_option("authorized")
    page.get_by_label("授权证据引用").fill("local:browser-fixture-license")
    page.get_by_label("审核原因").fill("合成新许可复核")
    page.get_by_label("核验依据").fill("查看隔离夹具中的新材料并核对研究范围。")
    today = datetime.now(timezone.utc).date()
    page.get_by_label("新授权签发日期（UTC）").fill(today.isoformat())
    page.get_by_label("保留至（UTC）").fill((today + timedelta(days=30)).isoformat())
    page.get_by_role("button", name="保存审核", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("撤销前的授权证据不可复用")
    page.get_by_label("授权证据引用").fill("local:browser-fixture-new-license")
    page.get_by_role("button", name="保存审核", exact=True).click()
    expect(page.locator(".corpus-record-state")).to_contain_text("已明确授权")
    expect(page.locator("blockquote.corpus-quote")).to_have_text(FIXTURE_TEXT)
    for width in (390, 320):
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(output / "m05-mobile-review.png"))
    assert not errors, errors
    assert not external, external
    page.close()
    print("M05 corpus E2E passed: review, trace, duplicates, withdrawal, fresh authorization, and 320/390px layouts.")
    return urlsplit(second).fragment


def corpus_restart_checks(browser, base, record_hash):
    page = browser.new_page(locale="zh-CN")
    page.goto(f"{base.rstrip('/')}/#{record_hash}")
    expect(page.locator("blockquote.corpus-quote")).to_have_text(FIXTURE_TEXT)
    expect(page.locator(".corpus-record-state")).to_contain_text("已核验")
    expect(page.get_by_text("隔离环境中的合成审核", exact=True)).to_be_visible()
    page.close()
    print("M05 corpus restart E2E passed: original text and local review persisted.")
