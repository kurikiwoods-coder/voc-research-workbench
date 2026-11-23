"""Browser regression using the actual localhost service. Only anonymous public-source probes run."""

from pathlib import Path
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler
from urllib.error import URLError

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import Settings
from src.dashboard.app import create_app


def serve(data, port):
    import uvicorn

    # Ignore real credentials even if the developer's personal .env exists.
    uvicorn.run(create_app(Settings(Path(data))), host="127.0.0.1", port=port, log_level="warning")


def browser_checks(base, output):
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("VOC_CHROMIUM") or None)
        page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN")
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base)
        button = lambda name: page.get_by_role("button", name=name, exact=True)
        heading = lambda name: page.get_by_role("heading", name=name, exact=True)
        link = lambda name: page.get_by_role("link", name=name, exact=True)
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
        expect(page.get_by_role("dialog").get_by_text("JEVMODEL_API_KEY", exact=True)).to_be_visible()
        button("关闭侧栏").click()
        link("连通性检查").click()
        button("运行检查").click()
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
        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", nargs=2, metavar=("DIR", "PORT"))
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/browser")
    args = parser.parse_args()
    if args.serve:
        return serve(args.serve[0], int(args.serve[1]))
    with tempfile.TemporaryDirectory(prefix="voc-browser-") as directory:
        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]
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
            browser_checks(base, args.output)
            print("Chromium E2E passed. Screenshots:", args.output)
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
