"""Browser regression for offline source acquisition and its formal gate."""

from urllib.parse import urljoin
from uuid import uuid4

from playwright.sync_api import expect


def acquisition_browser_checks(browser, base, output):
    page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN")
    errors, outbound, calls = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    def track_acquisition(request):
        if "/api/acquisition/" in request.url:
            calls.append((request.method, request.url, request.post_data_json))

    page.on("request", track_acquisition)

    def only_local(route):
        if route.request.url.startswith(base):
            route.continue_()
        else:
            outbound.append(route.request.url)
            route.abort()

    page.route("**/*", only_local)
    headers = {"Origin": base.rstrip("/"), "X-VOC-Action": "connectivity"}
    create = page.request.post(urljoin(base, "api/studies"), headers=headers, data={
        "name": "合成采集项目", "request_key": str(uuid4()),
        "scope": {"mode": "single_category", "topic": "合成厨具采集验证", "product_category_ids": ["paper-cups"]},
    })
    expect(create).to_be_ok()
    project = create.json()
    project_id = project["study_id"]
    scope_id = project["scope"]["scope_id"]
    freeze = page.request.post(urljoin(base, f"api/studies/{project_id}/scopes/{scope_id}/freeze"), headers=headers)
    expect(freeze).to_be_ok()

    page.goto(base + "#acquisition")
    wizard = page.get_by_role("dialog")
    expect(wizard.get_by_role("heading", name="首次配置 API")).to_be_visible()
    wizard.get_by_role("button", name="关闭侧栏").click()
    expect(wizard).to_be_hidden()
    expect(page.get_by_role("heading", name="来源采集", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="来源采集", exact=True)).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("button", name="正式采集", exact=True)).to_be_disabled()
    expect(page.locator("#acquisition-gate")).to_contain_text("G-1 BLOCKED")
    expect(page.get_by_role("heading", name="Tavily", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="Brave Search", exact=True)).to_be_visible()
    tavily = page.get_by_role("article", name="Tavily", exact=True)
    expect(tavily.locator(".acquisition-hint")).to_contain_text("离线合成夹具")
    for permission in ("搜索发现", "原文访问", "原文存储", "研究使用", "外部模型传输"):
        expect(tavily.locator("dt", has_text=permission)).to_be_visible()
    expect(page.get_by_role("button", name="预览查询", exact=True)).to_be_disabled()
    page.get_by_label("研究项目", exact=True).select_option(project_id)
    expect(page.get_by_label("冻结范围", exact=True)).to_have_value(scope_id)
    page.get_by_label("产品品类", exact=True).select_option("paper-cups")
    page.get_by_label("研究产品或竞品对象", exact=True).fill("合成纸杯")
    page.get_by_label("研究目标", exact=True).fill("核验合成查询与回源")
    page.get_by_label("搜索关键词", exact=True).fill("synthetic, paper cups")
    page.get_by_label("包含词", exact=True).fill("fictional")
    page.get_by_label("排除词", exact=True).fill("commercial")

    preview = page.get_by_role("button", name="预览查询", exact=True)
    expect(preview).to_be_enabled()
    preview.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="查询预览", exact=True)).to_be_focused()
    expect(page.locator("#acquisition-result-body")).to_contain_text("v1")
    expect(page.locator("#acquisition-result-body")).to_contain_text("paper-cups")
    expect(page.get_by_role("heading", name="供应商查询", exact=True)).to_be_visible()
    expect(page.get_by_text('"synthetic" "paper cups" "fictional"', exact=False).first).to_be_visible()
    expect(page.get_by_role("heading", name="发现与回源回执")).to_have_count(0)

    page.get_by_label("研究产品或竞品对象", exact=True).clear()
    page.get_by_role("button", name="运行离线演示").click()
    expect(page.get_by_role("heading", name="离线工程结果")).to_be_focused()
    expect(page.get_by_text("真实研究 API 请求 0 次", exact=True)).to_be_visible()
    funnel = page.locator(".acquisition-section").filter(has=page.get_by_role("heading", name="合成采集漏斗"))
    expect(funnel.get_by_text("2", exact=True)).to_be_visible()
    expect(funnel.get_by_text("1", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="正式研究分母")).to_be_visible()
    expect(page.get_by_text("未取得正式台账").first).to_be_visible()
    expect(page.get_by_role("heading", name="搜索请求与用量")).to_be_visible()
    expect(page.get_by_text("实际费用", exact=True).first).to_be_visible()
    expect(page.get_by_text("估算费用", exact=True).first).to_be_visible()
    receipts = page.locator(".acquisition-receipts summary")
    expect(receipts).to_have_count(2)
    duplicate = receipts.filter(has_text="2 条发现")
    missing = receipts.filter(has_text="1 条发现 · 不可访问")
    expect(duplicate).to_be_visible()
    expect(missing).to_be_visible()
    duplicate.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_text("原始 URL", exact=True)).to_have_count(3)
    expect(page.get_by_text("原始 URL", exact=True).first).to_be_visible()
    expect(page.get_by_text("规范 URL", exact=True).first).to_be_visible()
    expect(page.get_by_text("最终 URL", exact=True).first).to_be_visible()
    expect(page.get_by_text("回源时间", exact=True).first).to_be_visible()
    expect(duplicate.locator("..").get_by_text("待核验", exact=True)).to_be_visible()
    page.evaluate('window.scrollTo({top: 0, behavior: "instant"})')
    page.screenshot(path=str(output / "m08-acquisition.png"), full_page=True)

    for width in (320, 390):
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
        missing.focus()
        missing.press("Enter")
        expect(page.get_by_text("页面未找到", exact=True)).to_be_visible()
        missing.press("Enter")
        expect(page.get_by_text("页面未找到", exact=True)).to_be_hidden()
    page.evaluate('window.scrollTo({top: 0, behavior: "instant"})')
    page.screenshot(path=str(output / "m08-acquisition-mobile.png"), full_page=True)
    assert [method for method, _, _ in calls] == ["GET", "POST", "POST"], calls
    assert calls[-2][1].endswith("/preview") and calls[-1][1].endswith("/demo"), calls
    for _, _, payload in calls[1:]:
        assert payload["scope_id"] == scope_id
        assert payload["scope_version"] == "v1" and payload["data_class"] == "synthetic"
    assert set(calls[-2][2]) - set(calls[-1][2]) == {
        "research_object", "research_goal", "keywords", "include_terms", "exclude_terms",
    }
    assert not errors, errors
    assert not outbound, outbound
    page.close()
    print("M08 acquisition E2E passed: frozen scope, preview, offline receipts, formal gate and keyboard at 320/390.")
