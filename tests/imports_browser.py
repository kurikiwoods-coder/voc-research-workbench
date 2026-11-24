"""Browser import flows against real local routes and a temporary SQLite database."""

import csv
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from openpyxl import Workbook
from playwright.sync_api import expect


def create_target(page, base, name):
    origin = base.rstrip("/")
    response = page.request.post(urljoin(base, "/api/studies"), headers={
        "Origin": origin, "X-VOC-Action": "connectivity",
    }, data={"name": name, "request_key": str(uuid4()), "scope": {"mode": "open", "topic": "如何优化预约？"}})
    assert response.ok
    data = response.json()
    created = page.request.post(urljoin(base, f"/api/studies/{data['study_id']}/scopes/{data['scope']['scope_id']}/freeze"),
                                headers={"Origin": origin, "X-VOC-Action": "connectivity"})
    assert created.ok
    return data["study_id"]


def imports_browser_checks(browser, base, output):
    page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN", accept_downloads=True)
    events, external = [], []
    page.on("pageerror", lambda event: events.append(str(event)))
    page.on("request", lambda event: external.append(event.url)
            if urlsplit(event.url).netloc != urlsplit(base).netloc else None)
    button = lambda label: page.get_by_role("button", name=label, exact=True)
    heading = lambda label: page.get_by_role("heading", name=label, exact=True)
    link = lambda label: page.get_by_role("link", name=label, exact=True)

    page.goto(base + "#imports")
    expect(heading("数据导入中心")).to_be_visible()
    wizard = page.get_by_role("dialog")
    if wizard.is_visible():
        wizard.get_by_role("button", name="稍后配置").click()
    origin = base.rstrip("/")
    current = page.request.get(urljoin(base, "/api/studies")).json()["current"]
    project = "社区设施预约"
    other = "跨服务导入对照"
    target = create_target(page, base, project)
    other_id = create_target(page, base, other)
    page.goto(base + "#studies/" + target)
    link("查看数据导入").click()
    expect(heading("数据导入中心")).to_be_visible()
    expect(page.get_by_label("范围版本")).not_to_have_value("")
    for fmt in ("CSV", "XLSX"):
        with page.expect_download() as event:
            link(f"下载 {fmt} 模板").click()
        assert event.value.suggested_filename == f"voc-import-template.{fmt.lower()}"

    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["记录内容", "来源类型", "原文链接", "发布时间", "来源许可", "隐私等级", "频道"])
    writer.writerows([
        ["我希望提前查看可预约的时段。", "forum", "https://example.org/1", "2026-11-01", "有待核验的授权", "公开", "图书馆"],
        ["我希望提前查看可预约的时段。", "forum", "https://example.org/1", "2026-11-01", "有待核验的授权", "公开", "图书馆"],
        ["还希望补一个电话预约入口。", "内部 CX", "", "2026-11-11", "", "内部", "社区活动"],
        ["", "forum", "https://example.org/2", "2026-11-24", "有待核验的授权", "公开", "预约"],
    ])
    # Use Chromium's drag-and-drop event with an in-memory synthetic file.
    page.locator("#import-drop").evaluate("""(node, text) => {
        const transfer = new DataTransfer();
        transfer.items.add(new File([text], '设施预约 合成数据.csv', {type: 'text/csv'}));
        node.dispatchEvent(new DragEvent('drop', {bubbles: true, dataTransfer: transfer}));
    }""", stream.getvalue())
    expect(button("上传并解析")).to_be_enabled()
    page.screenshot(path=str(output / "m04-upload.png"), full_page=True)
    button("上传并解析").click()
    expect(heading("字段映射")).to_be_visible()
    expect(page.get_by_label("来源类型 第 2 列")).to_have_value("source_type")
    button("检查数据质量").click()
    expect(page.get_by_role("alert")).to_contain_text("对应到用户原话")
    page.get_by_label("记录内容 第 1 列").select_option("raw_text")
    page.screenshot(path=str(output / "m04-mapping.png"), full_page=True)
    button("检查数据质量").click()
    expect(heading("数据质量检查")).to_be_visible()
    expect(page.get_by_text("用户原话为空", exact=True).first).to_be_visible()
    counts = page.locator(".import-counts dd")
    expect(counts).to_have_text(["4", "1", "1", "1", "1"])
    button("返回修改映射").click()
    expect(page.get_by_label("记录内容 第 1 列")).to_have_value("raw_text")
    button("检查数据质量").click()
    expect(heading("数据质量检查")).to_be_visible()
    page.screenshot(path=str(output / "m04-quality.png"), full_page=True)

    # Switch the M03 selection via another client while keeping the upload target pinned.
    switch = page.request.post(urljoin(base, f"/api/studies/{other_id}/select"), headers={
        "Origin": base.rstrip("/"), "X-VOC-Action": "connectivity",
    })
    assert switch.ok
    button("确认导入").click()
    expect(heading("导入结果")).to_be_visible()
    expect(page.get_by_text(project + " · v1", exact=False)).to_be_visible()
    result_hash = urlsplit(page.url).fragment
    expect(page.locator(".import-counts dd")).to_have_text(["4", "1", "1", "1", "1"])
    page.get_by_label("记录状态").select_option("pending_review")
    expect(page.get_by_text("第 4 行", exact=True)).to_be_visible()
    expect(page.get_by_text("第 5 行", exact=True)).to_have_count(0)
    with page.expect_download() as event:
        link("下载错误报告").click()
    report = Path(event.value.path()).read_text(encoding="utf-8-sig")
    assert "missing_permission" in report and "blank_text" in report and "电话预约" not in report

    for width in (390, 320):
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        link("返回导入首页").click()
        expect(heading("数据导入中心")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        link("设施预约 合成数据.csv").click()
        expect(heading("导入结果")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(output / "m04-mobile-result.png"))
    page.once("dialog", lambda dialog: dialog.accept())
    button("撤销批次").click()
    expect(page.get_by_text("已撤销", exact=True)).to_be_visible()

    link("返回导入首页").click()
    page.get_by_label("研究项目").select_option(other_id)
    expect(page.get_by_text("这个项目还没有导入批次。")).to_be_visible()
    workbook = Workbook()
    workbook.active.title = "填写说明"
    workbook.active.append(["选择下一张表"])
    sheet = workbook.create_sheet("访谈 01")
    sheet.append(["raw_text", "source_type", "published_at", "privacy"])
    sheet.append(["请让我用母语预约。", "访谈", "2026-11-24", "非公开"])
    data = BytesIO()
    workbook.save(data)
    workbook.close()
    page.locator("#import-file").set_input_files({
        "name": "访谈 测试.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "buffer": data.getvalue(),
    })
    button("上传并解析").click()
    expect(page.get_by_role("alert")).to_contain_text("没有可导入的数据")
    page.locator("#import-sheet").select_option("1")
    expect(page.get_by_text("请让我用母语预约。", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    button("检查数据质量").click()
    expect(page.locator(".import-counts dd")).to_have_text(["1", "0", "1", "0", "0"])
    button("确认导入").click()
    expect(heading("导入结果")).to_be_visible()
    second_hash = urlsplit(page.url).fragment
    if current:
        restored = page.request.post(urljoin(base, f"/api/studies/{current['study_id']}/select"),
                                    headers={"Origin": origin, "X-VOC-Action": "connectivity"})
        assert restored.ok
    assert not events, events
    assert not external, external
    page.close()
    print("M04 import E2E passed: drag/drop CSV, XLSX sheet selection, mapping, quality, project isolation, report and 320/390px layouts.")
    return result_hash, second_hash


def imports_restart_checks(browser, base, routes):
    page = browser.new_page(locale="zh-CN")
    page.goto(base + "#" + routes[0])
    expect(page.get_by_role("heading", name="导入结果", exact=True)).to_be_visible()
    expect(page.get_by_text("已撤销", exact=True)).to_be_visible()
    expect(page.locator(".import-counts dd")).to_have_text(["4", "1", "1", "1", "1"])
    page.goto(base + "#" + routes[1])
    expect(page.get_by_text("访谈 测试.xlsx · 访谈 01", exact=False)).to_be_visible()
    expect(page.locator(".import-counts dd")).to_have_text(["1", "0", "1", "0", "0"])
    page.close()
    print("M04 restart E2E passed: original batch state and XLSX staged rows survived a fresh service process.")
