"""M03 browser journeys over a real localhost server and a temporary database."""

from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect


def check_mobile(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def study_browser_checks(browser, base, output):
    page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN")
    errors = []
    external = []
    page.on("pageerror", lambda event: errors.append(str(event)))
    page.on("request", lambda event: external.append(event.url) if urlsplit(event.url).netloc != urlsplit(base).netloc else None)
    button = lambda name: page.get_by_role("button", name=name, exact=True)
    link = lambda name: page.get_by_role("link", name=name, exact=True)
    heading = lambda name: page.get_by_role("heading", name=name, exact=True)
    page.goto(base + "#studies")
    expect(heading("研究项目")).to_be_visible()
    expect(page.get_by_text("暂无可显示的项目")).to_be_visible()

    link("新建项目").click()
    expect(heading("新建研究项目")).to_be_visible()
    button("保存项目").click()
    assert page.locator("#study-name").evaluate("field => !field.validity.valid")
    name = "跨品类｜出行提醒研究"
    page.get_by_label("项目名称（必填）").fill(name)
    page.get_by_label("研究对象").fill("经常跨交通方式通勤的乘客")
    page.get_by_label("研究目标").fill("理解延误时机，识别乘客需要的提醒")
    page.get_by_label("研究背景").fill("换乘信息分散在多个出行服务中。")
    page.get_by_label("项目描述").fill("以换乘前后两个时点组织访谈。")
    page.get_by_label("项目状态").select_option("active")
    page.get_by_label("研究模式").select_option("cross_category")
    page.get_by_label("核心研究问题（必填）").fill("用户希望在什么时点得知换乘延误？")
    page.get_by_label("品类引用 ID（每行一个）").fill("TRANSIT_BUS")
    page.get_by_label("目标市场").fill("中国大陆、新加坡")
    page.get_by_label("研究语言").fill("中文、英文")
    page.get_by_label("开始日期").fill("2026-10-01")
    page.get_by_label("结束日期").fill("2026-11-21")
    page.get_by_label("目标用户群体").fill("每周三次及以上跨方式通勤的乘客")
    page.get_by_label("用户任务（每行一项）").fill("确认下一段行程\n处理延误")
    page.get_by_label("数据来源偏好（每行一项）").fill("有许可的论坛\n本地访谈")
    page.get_by_label("纳入标准（每行一项）").fill("涉及实际换乘经历")
    page.get_by_label("排除标准（每行一项）").fill("未经历的假设情景")
    button("保存项目").click()
    expect(page.get_by_role("alert")).to_have_text("跨品类用户需求研究至少填写两个不同的品类 ID。（422）")
    expect(page.get_by_label("核心研究问题（必填）")).to_have_value("用户希望在什么时点得知换乘延误？")
    page.get_by_label("品类引用 ID（每行一个）").fill("TRANSIT_BUS\nTRANSIT_RAIL")
    page.screenshot(path=str(output / "m03-project-form.png"), full_page=True)
    create_posts = []
    page.on("request", lambda req: create_posts.append(req.url) if req.method == "POST"
            and urlsplit(req.url).path == "/api/studies" else None)
    # Dispatch two valid submissions in the same turn to exercise the pending guard.
    page.locator(".study-form").evaluate("form => { form.requestSubmit(); form.requestSubmit(); }")
    expect(heading(name)).to_be_visible()
    assert len(create_posts) == 1
    expect(page.locator("#toast")).to_have_text("项目已保存。")
    project_hash = urlsplit(page.url).fragment
    study_id = project_hash.split("/")[1]
    button("设为当前").click()
    expect(page.get_by_text("当前项目", exact=True)).to_be_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    button("冻结当前范围").click()
    expect(page.get_by_text("已冻结", exact=True).first).to_be_visible()
    link("编辑项目").click()
    expect(heading("编辑研究项目")).to_be_visible()
    page.get_by_label("目标市场").fill("中国大陆、新加坡、日本")
    page.get_by_label("范围变更说明").fill("纳入日本换乘服务")
    button("保存项目").click()
    expect(heading(name)).to_be_visible()
    expect(link("查看 v2")).to_be_visible()
    expect(page.get_by_text("变更 目标市场")).to_be_visible()
    link("查看 v1").click()
    expect(heading("范围版本 v1")).to_be_visible()
    expect(page.get_by_text("中国大陆、新加坡", exact=True)).to_be_visible()
    expect(page.get_by_text("已冻结", exact=True)).to_be_visible()
    link("返回项目详情").click()
    expect(heading(name)).to_be_visible()
    expect(page.get_by_text("中国大陆、新加坡、日本", exact=True)).to_be_visible()
    page.screenshot(path=str(output / "m03-project-detail.png"), full_page=True)

    link("返回项目列表").click()
    for name_other, mode, scope_refs in [
        ("单品类｜公共图书馆", "single_category", "PUBLIC_LIBRARY"),
        ("开放式｜照护协调", "open", None),
    ]:
        link("新建项目").click()
        page.get_by_label("项目名称（必填）").fill(name_other)
        page.get_by_label("研究模式").select_option(mode)
        if scope_refs:
            page.get_by_label("品类引用 ID（每行一个）").fill(scope_refs)
        else:
            expect(page.get_by_label("品类引用 ID（每行一个）")).to_be_hidden()
        page.get_by_label("核心研究问题（必填）").fill("用户在什么条件下需要协助？")
        button("保存项目").click()
        expect(heading(name_other)).to_be_visible()
        link("返回项目列表").click()
    expect(page.get_by_role("status").get_by_text("共 3 个项目")).to_be_visible()
    page.get_by_label("排序").select_option("name")
    expect(page.locator(".study-row").first.get_by_role("link")).to_have_text("单品类｜公共图书馆")
    page.screenshot(path=str(output / "m03-project-list.png"), full_page=True)
    page.get_by_label("搜索项目").fill("不存在的研究")
    button("查询").click()
    expect(page.get_by_text("没有符合条件的项目")).to_be_visible()
    page.get_by_label("搜索项目").fill("照护")
    page.get_by_label("搜索项目").press("Enter")
    expect(page.get_by_role("status").get_by_text("共 1 个项目")).to_be_visible()
    button("设为当前").click()
    expect(page.get_by_role("region", name="当前研究项目").get_by_role("link")).to_have_text("开放式｜照护协调")
    page.get_by_label("搜索项目").fill("")
    button("查询").click()

    link(name).click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    button("归档项目").click()
    expect(button("归档项目")).to_be_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    button("归档项目").click()
    expect(button("恢复项目")).to_be_visible()
    link("返回项目列表").click()
    page.get_by_label("项目状态").select_option("archived")
    expect(page.get_by_role("status").get_by_text("共 1 个项目")).to_be_visible()
    link(name).click()
    button("恢复项目").click()
    expect(button("归档项目")).to_be_visible()
    expect(page.get_by_text("研究中", exact=True)).to_be_visible()
    button("设为当前").click()
    expect(page.get_by_text("当前项目", exact=True)).to_be_visible()

    for width in (390, 320):
        page.set_viewport_size({"width": width, "height": 844})
        check_mobile(page)
        button("打开导航").click()
        link("研究项目").click()
        expect(heading("研究项目")).to_be_visible()
        check_mobile(page)
        link("新建项目").click()
        expect(heading("新建研究项目")).to_be_visible()
        check_mobile(page)
        link("返回项目列表").click()
        link(name).click()
        expect(heading(name)).to_be_visible()
        check_mobile(page)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(output / "m03-mobile-detail.png"), full_page=True)
    page.route("**/api/studies/search", lambda route: route.abort())
    link("返回项目列表").click()
    expect(page.get_by_role("alert")).to_contain_text("无法连接本机服务")
    page.unroute("**/api/studies/search")
    button("查询").click()
    expect(page.get_by_role("region", name="当前研究项目").get_by_role("link")).to_have_text(name)
    assert not errors, errors
    assert not external, external
    detail = page.request.get(urljoin(base, "/api/studies/" + study_id)).json()
    assert len(detail["scope_history"]) == 2 and detail["scope_history"][1]["frozen_at"]
    page.close()
    print("M03 project E2E passed: create, validation, duplicate submission, history, archive/restore, search, active project, and 320/390 layouts.")
    return study_id, detail["scope"]["scope_id"]


def study_restart_checks(browser, base, ids):
    study_id, scope_id = ids
    page = browser.new_page(locale="zh-CN")
    page.goto(base + "#studies")
    wizard = page.get_by_role("dialog")
    if wizard.is_visible():
        wizard.get_by_role("button", name="稍后配置").click()
    current = page.get_by_role("region", name="当前研究项目")
    expect(current.get_by_role("link")).to_have_text("跨品类｜出行提醒研究")
    current.get_by_role("link").click()
    expect(page.get_by_role("link", name="查看 v1")).to_be_visible()
    expect(page.get_by_role("link", name="查看 v2")).to_have_attribute("href", "#studies/" + study_id + "/scopes/" + scope_id)
    page.close()
    print("M03 restart E2E passed: same SQLite database, current project, and scope versions reopened in a new process.")
