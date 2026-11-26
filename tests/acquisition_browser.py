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
    preview_calls = [item for item in calls if "/tasks" not in item[1]]
    assert [method for method, _, _ in preview_calls] == ["GET", "POST", "POST"], preview_calls
    assert preview_calls[-2][1].endswith("/preview") and preview_calls[-1][1].endswith("/demo"), preview_calls
    for _, _, payload in preview_calls[1:]:
        assert payload["scope_id"] == scope_id
        assert payload["scope_version"] == "v1" and payload["data_class"] == "synthetic"
    assert set(preview_calls[-2][2]) - set(preview_calls[-1][2]) == {
        "research_object", "research_goal", "keywords", "include_terms", "exclude_terms",
    }
    acquisition_task_checks(page, project_id, scope_id, output)
    task_calls = [(method, url, payload) for method, url, payload in calls if "/tasks" in url]
    assert [payload["fallback_format"] for method, url, payload in task_calls
            if method == "POST" and url.endswith("/tasks")] == ["none", "xlsx"]
    request_keys = [payload["request_key"] for method, url, payload in task_calls if url.endswith("/step")]
    assert len(request_keys) == len(set(request_keys)) and len(request_keys) >= 5
    assert not errors, errors
    assert not outbound, outbound
    page.close()
    print("M08 acquisition E2E passed: frozen scope, preview, offline receipts, recoverable tasks, Excel fallback and keyboard at 320/390.")


def acquisition_task_checks(page, project_id, scope_id, output):
    detail = page.locator("#acquisition-task-detail")
    state = detail.get_by_text("状态", exact=True).first.locator("..").locator("dd")
    task_list = page.locator("#acquisition-task-list")
    preview_panel = page.locator("#acquisition-task-preview")

    def click_button(name):
        page.get_by_role("button", name=name, exact=True).click()

    def step_to_end():
        step = detail.get_by_role("button", name="执行下一检查点")
        for _ in range(12):
            if not step.is_visible():
                break
            with page.expect_response(lambda response: response.url.endswith("/step") and response.request.method == "POST") as result:
                step.click()
            assert result.value.ok, result.value.text()
            expect(detail.get_by_role("heading", name="合成任务详情")).to_be_focused()
            expect(page.get_by_role("button", name="刷新任务")).to_be_enabled()
        expect(state).to_have_text("已完成")

    reddit = page.get_by_role("article", name="Reddit", exact=True)
    expect(reddit.get_by_text("候选 · 受阻", exact=False).first).to_be_visible()
    youtube = page.get_by_role("article", name="YouTube", exact=True)
    youtube.get_by_text("许可、留存和接口详情").press("Enter")
    expect(youtube.get_by_text("字幕文本", exact=True)).to_be_visible()
    expect(youtube.get_by_text("须视频权利人授权", exact=True)).to_be_visible()

    page.get_by_label("搜索策略", exact=True).select_option("tavily_first")
    page.get_by_label("合成故障场景").select_option("primary_unavailable")
    page.get_by_label("目标语义片段数").fill("4")
    preview = page.get_by_role("button", name="预览合成任务", exact=True)
    preview.press("Enter")
    expect(preview_panel.get_by_role("heading", name="合成任务预览", exact=True)).to_be_focused()
    expect(preview_panel).to_contain_text(scope_id)
    expect(preview_panel).to_contain_text("双路故障切换")
    expect(preview_panel).to_contain_text("主搜索引擎故障")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    page.keyboard.press("Tab")
    expect(page.get_by_role("button", name="创建合成任务")).to_be_focused()
    with page.expect_response(lambda response: response.url.endswith("/tasks") and response.request.method == "POST") as created:
        page.keyboard.press("Enter")
    assert created.value.ok, created.value.text()
    task_id = created.value.json()["acquisition_task_id"]
    expect(state).to_have_text("草稿")
    expect(task_list.get_by_role("button", name=task_id)).to_be_visible()
    click_button("加入队列")
    expect(state).to_have_text("待执行")
    click_button("执行下一检查点")
    expect(detail.get_by_text("查询与来源回执", exact=True)).to_be_visible()
    click_button("暂停任务")
    expect(state).to_have_text("已暂停")

    page.reload()
    wizard = page.get_by_role("dialog")
    expect(wizard.get_by_role("heading", name="首次配置 API")).to_be_visible()
    wizard.get_by_role("button", name="关闭侧栏").click()
    expect(wizard).to_be_hidden()
    page.get_by_label("研究项目", exact=True).select_option(project_id)
    reopen = task_list.get_by_role("button", name=task_id)
    expect(reopen).to_be_enabled()
    reopen.press("Enter")
    expect(state).to_have_text("已暂停")
    resume = page.get_by_role("button", name="恢复任务", exact=True)
    resume.press("Enter")
    expect(state).to_have_text("待执行")
    step_to_end()
    expect(detail.get_by_text("批次与质量检查", exact=True)).to_be_visible()
    detail.get_by_text("第 2 步 · 搜索发现 · Brave Search", exact=True).press("Enter")
    expect(detail.get_by_text("Tavily → Brave Search · 上游服务异常", exact=True)).to_be_visible()
    expect(detail.get_by_text("未取得正式台账", exact=True)).to_have_count(5)
    expect(detail.get_by_text("0 次", exact=True)).to_be_visible()

    page.get_by_label("搜索策略", exact=True).select_option("tavily")
    page.get_by_label("合成故障场景").select_option("source_unavailable")
    page.get_by_label("文件兜底").select_option("xlsx")
    page.get_by_label("目标语义片段数").fill("4")
    click_button("预览合成任务")
    expect(preview_panel).to_contain_text("合成 Excel")
    click_button("创建合成任务")
    expect(state).to_have_text("草稿")
    click_button("加入队列")
    expect(state).to_have_text("待执行")
    step_to_end()
    expect(detail.get_by_text("合成 Excel", exact=True)).to_be_visible()
    batch = detail.locator(".acquisition-section").filter(has=page.get_by_role("heading", name="批次与质量检查", exact=True)).last
    batch.locator("summary").first.press("Enter")
    expect(batch.get_by_text("Excel", exact=True)).to_be_visible()
    batch.get_by_text("片段 1 · ", exact=False).first.press("Enter")
    evidence = batch.get_by_role("button", name="核验并读取片段").first
    evidence.press("Enter")
    expect(batch.get_by_text("合成原话", exact=True)).to_be_visible()
    expect(batch.get_by_text("正式研究资格", exact=True).locator("..").locator("dd")).to_have_text("否")
    expect(page.get_by_role("button", name="正式采集", exact=True)).to_be_disabled()
    for width in (320, 390):
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
    page.screenshot(path=str(output / "m08-cd-tasks-mobile.png"), full_page=True)
