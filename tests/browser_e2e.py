"""Browser regression using the actual localhost service and blocked provider transport."""

from base64 import b64decode
from pathlib import Path
import argparse
from contextlib import contextmanager
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler
from urllib.error import URLError
from urllib.parse import urljoin
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright
from corpus_browser import corpus_browser_checks, corpus_restart_checks
from imports_browser import imports_browser_checks, imports_restart_checks
from studies_browser import study_browser_checks, study_restart_checks

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import Settings
from src.dashboard.app import create_app
from test_api_setup import review_pair
from relations_browser import relation_fixture_grants, relations_browser_checks
from registry_browser import registry_browser_checks, registry_fixture_grants


def serve(data, port):
    import uvicorn

    # Keep the real service and SQLite, and exercise the unavailable-source path without egress.
    with patch("src.execution.transport.build_opener", side_effect=URLError("offline browser regression")):
        app = create_app(Settings(Path(data)), relation_grants=lambda: (
            *relation_fixture_grants(data), *registry_fixture_grants(data),
        ))
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", use_colors=False,
                    proxy_headers=False)


def api_setup_checks(page, output):
    initial_key = "browser-offline-fixture-first"
    rotated_key = "browser-offline-fixture-rotated"
    wizard = page.get_by_role("dialog")
    expect(wizard.get_by_role("heading", name="首次配置 API")).to_be_visible()
    page.screenshot(path=str(output / "api-wizard.png"))
    wizard.get_by_label("API Key", exact=True).fill(initial_key)
    wizard.get_by_role("button", name="保存密钥").click()
    expect(wizard.get_by_text("凭证 已配置", exact=False)).to_be_visible()
    wizard.get_by_role("button", name="检查连接").click()
    expect(wizard.get_by_role("status").get_by_text("请先导入此供应商", exact=False)).to_be_visible()
    wizard.get_by_role("button", name="下一步").click()
    expect(wizard.get_by_role("heading", name="配置一个搜索引擎")).to_be_visible()
    tavily = wizard.get_by_role("article", name="Tavily")
    tavily.get_by_role("button", name="检查连接").click()
    expect(tavily.get_by_role("status").get_by_text("请先在本机工作台保存", exact=False)).to_be_visible()
    wizard.get_by_role("button", name="下一步").click()
    expect(wizard.get_by_role("heading", name="核对验收准备")).to_be_visible()
    wizard.get_by_role("button", name="打开 API 接入").click()
    expect(page.get_by_role("heading", name="API 接入", exact=True)).to_be_visible()
    # The route changes before the wizard finishes refreshing the workspace.
    expect(page.locator("#toast")).to_have_text("配置向导已完成。")
    for name in ("TypeSafe", "JevModel", "PackyCode", "Tavily", "Brave", "YouTube", "Google Forms"):
        expect(page.get_by_role("article", name=name)).to_be_visible()
    for name in ("YouTube", "Google Forms"):
        expect(page.get_by_role("article", name=name).get_by_text("待开发", exact=True)).to_be_visible()
        expect(page.get_by_role("article", name=name).get_by_role("button")).to_have_count(0)
    jev = page.get_by_role("article", name="JevModel")
    jev.get_by_text("导入留存审核", exact=True).click()
    pair = review_pair("jevmodel")
    jev.get_by_label("审查 JSON").set_input_files(
        {"name": "offline-review.json", "mimeType": "application/json", "buffer": b64decode(pair["record"])},
    )
    jev.get_by_label("证明附件").set_input_files(
        {"name": "offline-proof.txt", "mimeType": "text/plain", "buffer": b64decode(pair["attachment"])},
    )
    jev.get_by_role("button", name="导入审查材料").click()
    expect(page.locator("#toast")).to_have_text("留存审查材料已核验并保存在本机。")
    expect(jev.get_by_text("未测试", exact=True)).to_be_visible()
    jev.get_by_text("更换密钥", exact=True).click()
    jev.get_by_label("API Key", exact=True).fill(rotated_key)
    jev.get_by_role("button", name="保存密钥").click()
    expect(page.locator("#toast")).to_have_text("密钥已保存并生效。")
    page.reload()
    expect(wizard).to_be_hidden()
    expect(jev.get_by_text("凭证 已配置", exact=False)).to_be_visible()
    expect(jev.get_by_text("审核未完成", exact=True)).to_be_visible()
    expect(jev.get_by_role("status").get_by_text("尚无当前凭证", exact=False)).to_be_visible()
    response = page.request.get(urljoin(page.url, "/api/workspace"))
    assert response.ok
    workspace = response.text()
    assert initial_key not in workspace and rotated_key not in workspace
    assert initial_key not in page.content() and rotated_key not in page.content()
    stored = page.evaluate("JSON.stringify([localStorage, sessionStorage])")
    assert initial_key not in stored and rotated_key not in stored
    page.screenshot(path=str(output / "connection-settings.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(output / "mobile-api-setup.png"))
    page.set_viewport_size({"width": 320, "height": 740})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1440, "height": 960})
    page.once("dialog", lambda dialog: dialog.accept())
    jev.get_by_role("button", name="删除密钥").click()
    expect(jev.get_by_text("凭证 未配置", exact=False)).to_be_visible()
    print("API setup E2E passed: wizard, local key save/rotation/delete, preflight evidence, and 320/390 layouts.")


def packycode_checks(page, output, *, restart=False):
    initial = "packycode-browser-synthetic-first"
    rotated = "packycode-browser-synthetic-rotated"
    card = page.get_by_role("article", name="PackyCode", exact=True)
    if not restart:
        wizard = page.get_by_role("dialog")
        expect(wizard.get_by_role("heading", name="首次配置 API")).to_be_visible()
        wizard.get_by_role("button", name="稍后配置").click()
        expect(wizard).to_be_hidden()
        expect(page.locator("#toast")).to_have_text("可随时从 API 接入继续配置。")
        expect(card.get_by_text("typesafe-officially", exact=True)).to_be_visible()
        expect(card.get_by_text("jev-1.14.0", exact=True)).to_be_visible()
        expect(card.get_by_text("https://cf.api.fan/v1/systemone", exact=True)).to_be_visible()
        expect(card.get_by_text("输入 $0.294 / 百万 Token", exact=False)).to_be_visible()
        expect(card.get_by_text("最近测试 未实测。", exact=True)).to_be_visible()
        expect(card.get_by_role("link", name="注册入口", exact=False)).to_have_attribute(
            "href", "https://www.packyapi.ai/register",
        )
        expect(card.get_by_role("link", name="供应商计费页", exact=False)).to_have_attribute(
            "href", "https://www.packyapi.ai/pricing",
        )
        expect(card.get_by_role("button", name="检查连接")).to_be_disabled()
        card.get_by_role("button", name="选为 Jev 通道").click()
        expect(card.get_by_text("当前 Jev 通道", exact=True)).to_be_visible()
        expect(page.locator("#toast")).to_have_text("已切换 Jev 通道。")
        expect(page.get_by_role("button", name="运行正式验收")).to_be_disabled()
        card.get_by_label("API Key", exact=True).fill(initial)
        card.get_by_role("button", name="保存密钥").click()
        expect(page.locator("#toast")).to_have_text("密钥已保存并生效。")
        expect(card.get_by_text("凭证 已配置", exact=False)).to_be_visible()
        expect(card.get_by_text("审核未完成", exact=True)).to_be_visible()
        card.get_by_text("更换密钥", exact=True).click()
        card.get_by_label("API Key", exact=True).fill(rotated)
        card.get_by_role("button", name="保存密钥").click()
        expect(card.get_by_label("API Key", exact=True)).to_be_hidden()
        page.reload()
        expect(card.get_by_text("凭证 已配置", exact=False)).to_be_visible()
        expect(card.get_by_role("button", name="检查连接")).to_be_disabled()
        for width in (320, 390):
            page.set_viewport_size({"width": width, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
        page.set_viewport_size({"width": 1440, "height": 960})
        card.screenshot(path=str(output / "packycode-candidate.png"))
        page.get_by_role("button", name="查看 Jev Token Center").click()
        expect(page.get_by_role("heading", name="用量及计费")).to_be_visible()
        expect(page.get_by_text("按候选报价估算", exact=True)).to_be_visible()
        expect(page.get_by_text("无请求记录", exact=True)).to_be_visible()
        expect(page.get_by_text("未同步", exact=True)).to_be_visible()
        return

    expect(card.get_by_text("凭证 已配置", exact=False)).to_be_visible()
    expect(card.get_by_role("button", name="检查连接")).to_be_disabled()
    response = page.request.get(urljoin(page.url, "/api/workspace"))
    expect(response).to_be_ok()
    public = response.text() + page.content() + page.evaluate("JSON.stringify([localStorage, sessionStorage])")
    assert initial not in public and rotated not in public
    page.once("dialog", lambda dialog: dialog.accept())
    card.get_by_role("button", name="删除密钥").click()
    expect(card.get_by_text("凭证 未配置", exact=False)).to_be_visible()
    print("PackyCode Chromium E2E passed: contract, credential lifecycle/restart, disabled live actions, billing, and 320/390 layouts.")


def browser_checks(base, output, directory, studies_only=False, relations_only=False):
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("VOC_CHROMIUM") or None)
        if relations_only:
            return relations_browser_checks(browser, base, output, directory)
        page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN")
        if studies_only:
            page.goto(base)
            wizard = page.get_by_role("dialog")
            wizard.get_by_role("button", name="稍后配置").click()
            expect(wizard).to_be_hidden()
            page.close()
            return study_browser_checks(browser, base, output)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base)
        button = lambda name: page.get_by_role("button", name=name, exact=True)
        heading = lambda name: page.get_by_role("heading", name=name, exact=True)
        link = lambda name: page.get_by_role("link", name=name, exact=True)
        api_setup_checks(page, output)
        link("连通性检查").click()
        expect(heading("等待首次运行")).to_be_visible()
        expect(page.get_by_text("Jev 未连接 · 未同步", exact=True)).to_be_visible()
        progress = page.get_by_role("progressbar", name="Jev 余额进度")
        expect(progress).to_have_attribute("aria-valuetext", "额度未同步")
        button("查看 Jev Token Center").click()
        expect(heading("额度中心")).to_be_visible()
        link("跳至主要内容").press("Enter")
        expect(heading("额度中心")).to_be_visible()
        expect(page.locator("main")).to_be_focused()
        assert page.url.endswith("#tokens")
        expect(link("补充额度 ↗").first).to_have_attribute("href", "https://jevmodel.org/zh/pricing/")
        button("连接配置").click()
        expect(heading("API 接入")).to_be_visible()
        expect(page.get_by_role("article", name="TypeSafe").get_by_role("link", name="官方控制台 ↗")).to_have_attribute(
            "href", "https://console.typesafe.ai/login"
        )
        button("运行正式验收").click()
        button("开始运行").click()
        expect(heading("P0 准入暂缓")).to_be_visible(timeout=120_000)
        expect(button("C0-5 通过")).to_be_visible()
        expect(button("C0-6 通过")).to_be_visible()
        page.screenshot(path=str(output / "connectivity.png"), full_page=True)
        button("通过 2").click()
        expect(page.locator("tbody tr")).to_have_count(2)
        button("全部 6").click()
        button("查看 C0-3 证据").click()
        expect(heading("搜索与公开原话")).to_be_visible()
        page.screenshot(path=str(output / "evidence.png"))
        page.keyboard.press("Escape")
        link("验收矩阵").click()
        page.get_by_label("搜索验收项").fill("CAT-10")
        expect(page.get_by_role("cell", name="CAT-10", exact=True)).to_be_visible()
        page.get_by_label("搜索验收项").fill("no-such-requirement")
        expect(page.get_by_text("没有匹配的需求", exact=True)).to_be_visible()
        page.get_by_label("搜索验收项").fill("C0-3")
        page.get_by_role("row").filter(has_text="C0-3").get_by_role("button", name="查看 ›").click()
        expect(heading("搜索与公开原话")).to_be_visible()
        page.go_back()
        expect(heading("连通性检查")).to_be_visible()
        expect(page.get_by_role("dialog")).to_be_hidden()
        link("运行记录").click()
        button("查看批次 ›").click()
        with page.expect_download() as event:
            button("导出证据").click()
        payload = json.loads(Path(event.value.path()).read_text("utf-8"))
        assert len(payload["attempts"][0]["checks"]) == 7
        button("恢复此批次").click()
        button("恢复执行").click()
        expect(heading("P0 准入暂缓")).to_be_visible(timeout=120_000)
        link("运行记录").click()
        button("查看批次 ›").click()
        with page.expect_download() as event:
            button("导出证据").click()
        recovered = json.loads(Path(event.value.path()).read_text("utf-8"))
        assert recovered["run"]["id"] == payload["run"]["id"]
        assert len(recovered["attempts"]) == 2
        button("关闭侧栏").click()
        button("查看 Jev Token Center").click()
        expect(heading("额度中心")).to_be_visible()
        expect(page.get_by_text("本机账本暂无分片")).to_be_visible()
        count = 0

        def count_post(request):
            nonlocal count
            if request.method == "POST":
                count += 1

        page.on("request", count_post)
        button("刷新状态").click()
        expect(page.get_by_text("已刷新本地记录")).to_be_visible()
        assert count == 0
        page.set_viewport_size({"width": 390, "height": 844})
        button("打开导航").click()
        link("连通性检查").click()
        expect(heading("连通性检查")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(output / "mobile.png"))
        page.set_viewport_size({"width": 320, "height": 740})
        button("查看 Jev Token Center").click()
        expect(heading("额度中心")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.goto(base + "#constructor")
        expect(heading("连通性检查")).to_be_visible()
        failing = browser.new_page()
        failing.route("**/api/workspace", lambda route: route.abort())
        failing.goto(base)
        expect(failing.get_by_text("无法连接本机服务。请启动工作台后重新读取。")).to_be_visible()
        failing.unroute("**/api/workspace")
        failing.get_by_role("button", name="重新读取", exact=True).click()
        expect(failing.get_by_role("heading", name="P0 准入暂缓")).to_be_visible()
        assert not errors, errors
        print("M01 connectivity E2E passed: navigation, batch evidence and recovery, Token Center, and 320/390 layouts.")
        study_ids = study_browser_checks(browser, base, output)
        import_ids = imports_browser_checks(browser, base, output)
        corpus_ids = corpus_browser_checks(browser, base, output)
        relations_browser_checks(browser, base, output, directory)
        return study_ids, import_ids, corpus_ids


@contextmanager
def server(directory, port):
    process = subprocess.Popen([sys.executable, __file__, "--serve", directory, str(port)], cwd=ROOT)
    base = f"http://127.0.0.1:{port}/"
    try:
        opener = build_opener(ProxyHandler({}))
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError("Local E2E server stopped")
            try:
                with opener.open(base + "api/health", timeout=1):
                    break
            except (URLError, OSError):
                time.sleep(0.2)
        else:
            raise TimeoutError("No local E2E server")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=15)


def run_registry_browser(output):
    with tempfile.TemporaryDirectory(prefix="voc-registry-browser-") as directory:
        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]
        with server(directory, port) as base, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("VOC_CHROMIUM") or None)
            registry_browser_checks(browser, base, output, directory)
            browser.close()


def run_packycode_browser(output):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="voc-packycode-browser-") as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("VOC_CHROMIUM") or None)
        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]
        for restart in (False, True):
            with server(directory, port) as base:
                page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN")
                errors, outbound = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: outbound.append(request.url)
                        if not request.url.startswith(base) else None)
                page.route("**/*", lambda route: route.continue_()
                           if route.request.url.startswith(base) else route.abort())
                page.goto(base + "#setup")
                packycode_checks(page, output, restart=restart)
                assert not errors, errors
                assert not outbound, outbound
                page.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", nargs=2, metavar=("DIR", "PORT"))
    parser.add_argument("--studies-only", action="store_true")
    parser.add_argument("--relations-only", action="store_true")
    parser.add_argument("--registry-only", action="store_true")
    parser.add_argument("--packycode-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/browser")
    args = parser.parse_args()
    if args.serve:
        return serve(args.serve[0], int(args.serve[1]))
    if args.registry_only:
        run_registry_browser(args.output)
        return
    if args.packycode_only:
        run_packycode_browser(args.output)
        return
    with tempfile.TemporaryDirectory(prefix="voc-browser-") as directory:
        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]
        with server(directory, port) as base:
            result = browser_checks(base, args.output, directory, args.studies_only, args.relations_only)
        if args.relations_only:
            print("Chromium E2E passed. Screenshots:", args.output)
            return
        with server(directory, port) as base, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("VOC_CHROMIUM") or None)
            if args.studies_only:
                study_restart_checks(browser, base, result)
            else:
                study_ids, import_ids, corpus_ids = result
                study_restart_checks(browser, base, study_ids)
                imports_restart_checks(browser, base, import_ids)
                corpus_restart_checks(browser, base, corpus_ids)
            browser.close()
    if not args.studies_only:
        run_registry_browser(args.output)
        run_packycode_browser(args.output)
    print("Chromium E2E passed. Screenshots:", args.output)


if __name__ == "__main__":
    main()
