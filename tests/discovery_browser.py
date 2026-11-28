"""M09-D browser checks over real localhost routes and isolated SQLite."""

from contextlib import contextmanager, nullcontext
from dataclasses import asdict
import ipaddress
import os
from pathlib import Path
import socket
import sys
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from src.config import Settings
from src.dashboard.app import create_app
from src.dashboard.personal_workspace import provision
from src.discovery.embedding_inputs import FixtureRecord, MentionEvidence
from src.discovery.topics import CandidateTopic, TopicAssignment, TopicKeyword
from src.edition_policy import Edition, LocalOwner
from src.raw_store.relations import RelationGrant
from test_edition_policy import fixture_root, owner_environment
from test_m06_mentions import CATALOG, MentionTests, PRODUCT_A, PRODUCT_B
from test_m09_actual_topics import ApprovedTopicTest, PINNED_CONFIG
from test_m09_embeddings import FixtureBackend


def browser_clustering(batch, config, *, observe_diagnostics):
    # The CI browser checks the UI on known assignments. Fixed-model native
    # acceptance uses the approved backend and unmodified clustering pipeline.
    assignments = tuple(
        TopicAssignment(row.document_id, label, raw_topic_id=label)
        for row, label in zip(batch.rows, (0, 1, -1) if config.random_seed == 42 else (1, 0, -1), strict=True)
    )
    observe_diagnostics(assignments)
    topics = (
        CandidateTopic(0, 1, (TopicKeyword("offline", 1.0), TopicKeyword("sample", 0.5))),
        CandidateTopic(1, 1, (TopicKeyword("offline", 1.0), TopicKeyword("fixture", 0.5))),
    )
    return "clustered", tuple(row.topic_id for row in assignments), topics, config, ()


def three_documents(case):
    case.bind_products((PRODUCT_A, PRODUCT_B))
    texts = {
        "zh": ("合成产品离线恢复示例", "zh-CN", PRODUCT_A),
        "en": ("A fictional product resumes offline after a power outage.", "en-US", PRODUCT_B),
        "third": ("A third fictional product observation mentions a rainy day.", "en-US", PRODUCT_A),
    }
    records = {key: case.add_quote(key, text) for key, (text, _, _) in texts.items()}
    published = case.publish(
        [case.member(key, interval) for key, (_, interval) in records.items()],
        proposals=tuple(case.proposal(key, interval, texts[key][2]) for key, (_, interval) in records.items()),
    )
    refs = []
    for member in published["members"]:
        key = member["ref"]
        _, interval = records[key]
        record = FixtureRecord(case.study, case.scope, "v1", interval.record_id, interval.raw_sha256)
        refs.append(MentionEvidence(
            record, published["revision"], member["mention_id"], member["evidence_ids"][0], texts[key][1],
        ))
    return tuple(refs)


@contextmanager
def discovery_fixture(actual):
    fixture = ApprovedTopicTest() if actual else MentionTests()
    try:
        fixture.setUp()
        if actual:
            case, refs, backend = fixture.case, fixture.refs, fixture.backend
            cluster = nullcontext()
        else:
            case, refs, backend = fixture, three_documents(fixture), FixtureBackend()
            cluster = patch("src.discovery.topics._cluster_batch", side_effect=browser_clustering)
        scope = case.study, case.scope, "v1"
        grant = RelationGrant(
            "synthetic-reviewer", "project_reviewer", "synthetic-owner", "local:discovery-browser",
            "2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z",
            frozenset({"read", "evidence", "validate"}), case.study,
        )
        with cluster:
            yield case, scope, refs, grant, backend
    finally:
        fixture.doCleanups()


def discovery_browser_checks(browser, base, output: Path, case, scope, *, actual=False):
    page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN", service_workers="block")
    outbound, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def local_only(route):
        if route.request.url.startswith(base):
            route.continue_()
        else:
            outbound.append(route.request.url)
            route.abort()

    page.route("**/*", local_only)
    page.goto(base + "#discovery")
    wizard = page.get_by_role("dialog")
    expect(wizard.get_by_role("heading", name="首次配置 API")).to_be_visible()
    wizard.get_by_role("button", name="关闭侧栏").click()
    expect(page.get_by_role("link", name="主题发现")).to_have_attribute("aria-current", "page")
    page.get_by_label("研究项目").select_option(scope[0])
    expect(page.get_by_label("冻结范围")).to_have_value(scope[1])
    page.get_by_text("新建主题运行", exact=True).click()
    expect(page.get_by_text(f"注册表版本 {CATALOG} · 本机模型 可用")).to_be_visible()
    page.get_by_role("button", name="全选", exact=True).click()
    if actual:
        page.get_by_text("聚类参数", exact=True).click()
        for name, value in asdict(PINNED_CONFIG).items():
            page.locator(f"#discovery-create-form [name={name}]").fill(str(value))
    expect(page.get_by_role("button", name="运行离线聚类")).to_be_enabled()
    page.get_by_role("button", name="运行离线聚类").click()
    expect(page.get_by_role("heading", name="主题分布")).to_be_focused(timeout=240_000)
    expect(page.get_by_text("G3_PENDING", exact=False)).to_be_visible()
    expect(page.get_by_text("8/11、8/12、8/13", exact=False)).to_be_visible()
    expect(page.get_by_text("正式研究分母 0", exact=False)).to_be_visible()
    first_run = page.get_by_label("已保存运行").input_value()
    expect(page.locator(".discovery-bar")).not_to_have_count(0)
    expect(page.get_by_role("button", name="离群样本", exact=False)).to_be_visible()
    page.get_by_role("heading", name="主题分布").evaluate("heading => heading.scrollIntoView({block: 'start'})")
    page.screenshot(path=str(output / ("m09-d-native-topics.png" if actual else "m09-d-browser-topics.png")))
    page.get_by_role("button", name="离群样本", exact=False).focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="离群样本")).to_be_focused()
    page.locator("#discovery-distribution button[data-discovery-topic='0']").click()
    expect(page.get_by_role("heading", name="主题 0", exact=True)).to_be_focused()

    page.get_by_text("主题关系", exact=True).click()
    if not actual:
        expect(page.get_by_text("主题 0 ↔ 主题 1", exact=False)).to_be_visible()
        expect(page.get_by_text("重叠词 offline")).to_be_visible()
    evidence_button = page.get_by_role("button", name="查看原话与证据").first
    document = evidence_button.get_attribute("data-discovery-document")
    evidence_path = base + "api/discovery/" + "/".join(scope) + f"/runs/{first_run}/evidence/{document}"
    with page.expect_response(evidence_path) as fetched:
        evidence_button.click()
    evidence = fetched.value.json()
    expect(page.locator("#discovery-evidence blockquote")).to_have_text(evidence["original_text"])
    expect(page.get_by_text(evidence["lineage"]["evidence_id"], exact=True)).to_be_visible()
    expect(page.get_by_text(evidence["lineage"]["source_locator"], exact=True)).to_be_visible()
    page.screenshot(path=str(output / ("m09-d-native-evidence.png" if actual else "m09-d-browser-evidence.png")))

    page.get_by_label("候选审核决定").select_option("retained")
    page.get_by_role("button", name="保存候选审核").click()
    expect(page.get_by_text("保留供审核 · 审核修订 1", exact=False)).to_be_visible()
    expect(page.locator("#discovery-evidence")).to_be_hidden()
    page.get_by_label("历史审核修订").fill("0")
    page.get_by_role("button", name="重载已保存快照").click()
    expect(page.get_by_text("待审核 · 审核修订 0", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="保存候选审核")).to_be_disabled()
    page.get_by_label("历史审核修订").fill("1")
    page.get_by_role("button", name="重载已保存快照").click()
    expect(page.get_by_text("保留供审核 · 审核修订 1", exact=False)).to_be_visible()
    page.get_by_text("重新计算聚类", exact=True).click()
    if not actual:
        page.locator("#discovery-recalculate-form [name=random_seed]").fill("43")
    page.get_by_role("button", name="重新计算并比较").click()
    expect(page.get_by_role("heading", name="运行比较结果")).to_be_visible(timeout=240_000)
    assert page.get_by_label("已保存运行").input_value() != first_run
    expect(page.get_by_text("候选覆盖片段变化", exact=True)).to_be_visible()
    expect(page.get_by_text("未匹配候选（0）", exact=True)).to_be_visible()
    page.screenshot(path=str(output / ("m09-d-native-comparison.png" if actual else "m09-d-browser-comparison.png")))

    case.revoke_batch(evidence["lineage"]["batch_id"])
    assert page.request.get(evidence_path).status == 409
    page.get_by_label("已保存运行").select_option(first_run)
    page.locator("#discovery-distribution button[data-discovery-topic='0']").click()
    expect(page.get_by_text("证据当前不可用", exact=True).first).to_be_visible()
    assert not page.locator("blockquote").count()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(output / ("m09-d-native-mobile.png" if actual else "m09-d-browser-mobile.png")))
    assert not errors, errors
    assert not outbound, outbound
    page.close()
    mode = "fixed MiniLM and BERTopic" if actual else "deterministic visualization fixture"
    print(f"Chromium M09-D passed with {mode}: candidate versions, evidence, recalculation, mobile, 0 external requests.")


@contextmanager
def discovery_server(app):
    import uvicorn

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = monotonic() + 20
            while not server.started and thread.is_alive() and monotonic() < deadline:
                sleep(0.05)
            assert server.started, "The isolated discovery server did not start."
            yield f"http://127.0.0.1:{port}/"
        finally:
            server.should_exit = True
            thread.join(timeout=20)
            assert not thread.is_alive(), "The isolated discovery server did not stop."


@contextmanager
def loopback_only():
    attempts = []
    active = True

    def audit(event, args):
        if not active:
            return
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"}:
            target = args[0]
        elif event in {"socket.connect", "socket.sendto"}:
            target = args[1]
        else:
            return
        host = target[0] if isinstance(target, tuple) else target
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except (TypeError, ValueError):
            pass
        attempts.append(event)
        raise RuntimeError("The isolated discovery browser blocks non-loopback network operations.")

    sys.addaudithook(audit)
    try:
        yield
    finally:
        active = False
        print(f"M09-D browser non-loopback Python socket and DNS attempts: {len(attempts)}")
        assert not attempts, attempts


def run_discovery_browser(output: Path, *, actual=False):
    output.mkdir(parents=True, exist_ok=True)
    with loopback_only(), sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("VOC_CHROMIUM") or None)
        try:
            with discovery_fixture(actual) as (case, scope, refs, grant, backend):
                app = create_app(Settings(case.db.directory), relation_grants=lambda: (grant,),
                                 discovery_catalog={scope: (CATALOG, refs)}, discovery_backend=backend)
                with discovery_server(app) as base:
                    discovery_browser_checks(browser, base, output, case, scope, actual=actual)
            if not actual:
                personal_browser_check(browser, output)
        finally:
            browser.close()


def personal_browser_check(browser, output):
    with fixture_root("voc-m09-d-personal-") as directory:
        binding = provision(Path(directory), "合成主题研究", "核对个人授权范围", uuid4())
        other = provision(Path(directory), "其他合成项目", "未授予的范围", uuid4())
        environment, proof = owner_environment(binding)
        scope = tuple(binding[key] for key in ("study_id", "scope_id", "scope_version"))
        settings = Settings(Path(directory), edition=Edition.PERSONAL, personal_owner=LocalOwner.from_environment(environment))
        app = create_app(settings, discovery_catalog={scope: (CATALOG, ())})
        with discovery_server(app) as base:
            page = browser.new_page(viewport={"width": 390, "height": 844}, locale="zh-CN", service_workers="block",
                                    http_credentials={"username": "owner", "password": proof, "origin": base.rstrip("/")})
            errors, outbound = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: outbound.append(request.url) if not request.url.startswith(base) else None)
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
            try:
                page.goto(base + "#edition")
                expect(page.get_by_role("heading", name="版本与研究准入", exact=True)).to_be_visible()
                page.locator(".menu-btn").click()
                page.get_by_role("link", name="主题发现").click()
                expect(page.get_by_role("heading", name="主题发现", exact=True)).to_be_visible()
                project = page.get_by_label("研究项目")
                project.select_option(binding["study_id"])
                expect(project.locator(f'option[value="{other["study_id"]}"]')).to_have_count(0)
                expect(page.get_by_label("冻结范围")).to_have_value(binding["scope_id"])
                expect(page.get_by_text("此冻结范围尚无已保存的主题运行。", exact=True)).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / "m09-d-personal-scope.png"))
                page.locator(".menu-btn").click()
                page.get_by_role("link", name="版本与研究准入").click()
                expect(page.get_by_role("heading", name="版本与研究准入", exact=True)).to_be_visible()
                assert not errors, errors
                assert not outbound, outbound
            finally:
                page.close()
    print("Chromium M09-D Personal passed: Owner authentication, exact granted scope, mobile navigation, 0 external requests.")
