"""Local browser coverage of the Personal approval center with synthetic materials."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

from playwright.sync_api import expect

from src.dashboard.personal_governance import governance_decision
from src.edition_policy import Deployment, Domain, Edition, EditionPolicy, LocalOwner, Permission
from src.raw_store.personal_approval_evidence import REGISTRY_NAME, REQUIRED_EVIDENCE
from src.raw_store.personal_validation import BatchContext, Budget, ValidationLedger
from src.raw_store.store import Store
from test_personal_credentials import BINDING, FIRST, ROTATED


def write_synthetic_evidence(directory, scope):
    directory = Path(directory)
    with Store(directory, edition=Edition.PERSONAL).db() as db:
        revision = db.execute(
            "SELECT credential_revision FROM personal_credential_binding WHERE study_id=? AND scope_id=?",
            (scope["study_id"], scope["scope_id"]),
        ).fetchone()["credential_revision"]
    now = datetime.now(UTC)
    records = [
        {key: scope[key] for key in ("study_id", "scope_id", "scope_version")}
        | {"purpose": "personal_research", "provider": BINDING[0], "channel_ref": BINDING[1],
           "account_ref": BINDING[2], "credential_revision": revision,
           "model": "jev-1.14.0", "evidence_ref": f"local:browser-fixture-{index}", "kind": kind,
           "status": "VERIFIED", "sha256": sha256(kind.encode()).hexdigest(), "terms_version": "fixture-1",
           "verified_at": (now - timedelta(days=1)).isoformat(), "expires_at": (now + timedelta(days=2)).isoformat(),
           "budget_unit": "TOKENS", "budget_limit": 1000}
        for index, kind in enumerate(REQUIRED_EVIDENCE)
    ]
    registry = directory / REGISTRY_NAME
    registry.write_text(json.dumps(records), encoding="utf-8")
    if os.name != "nt":
        registry.chmod(0o600)
    return revision


def open_approval_center(page, base, study_id):
    if page.url == base + "#edition":
        page.reload()
    else:
        page.goto(base + "#edition")
    panel = page.locator("#personal-governance")
    expect(panel.get_by_role("heading", name="个人供应商审批中心")).to_be_visible()
    project = panel.get_by_label("审批研究项目")
    expect(project).to_be_hidden()
    panel.get_by_role("button", name="读取获准项目").click()
    expect(project).to_be_focused()
    project.select_option(study_id)
    expect(panel.get_by_role("heading", name="当前项目、账户与凭证")).to_be_visible()
    return panel


def fill_approval(form, expiry):
    form.get_by_label("预算上限（Tokens）").fill("100")
    form.locator('[name="expires_at"]').fill(expiry)


def select_evidence(form):
    evidence = form.get_by_role("group", name="必要证据").get_by_role("checkbox")
    expect(evidence).to_have_count(len(REQUIRED_EVIDENCE))
    for choice in evidence.all():
        choice.check()


def submit_and_approve(page, panel, form):
    form.get_by_role("button", name="提交审批申请").click()
    expect(panel.get_by_text("已提交审批申请。", exact=True)).to_be_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    panel.get_by_role("button", name="确认批准").click()
    expect(panel.get_by_text("已记录批准事件。", exact=True)).to_be_visible()
    expect(panel.get_by_role("article").filter(has_text="当前有效")).to_have_count(1)
    expect(panel.get_by_text("当前服务端审批条件已齐备。", exact=False)).to_be_visible()


def verify_binding(page, panel, governance_url, marker):
    form = panel.locator('[data-governance-form="credential"]')
    key = form.get_by_label("个人 API Key")
    expect(key).to_have_attribute("type", "password")
    form.get_by_label("通道引用").fill(BINDING[1])
    form.get_by_label("账户引用").fill(BINDING[2])
    key.fill(marker)
    with page.expect_response(lambda response: response.url == governance_url + "/credential"
                              and response.request.method == "PUT") as saved:
        form.get_by_role("button", name="保存个人凭证").click()
    assert saved.value.ok, f"Credential save returned HTTP {saved.value.status}"
    assert marker not in saved.value.text()
    expect(key).to_have_value("")
    expect(panel.get_by_text("已配置", exact=True)).to_be_visible()


def verify_admission_projection(page, base, scope):
    url = base + f"api/personal/pre-admission/{scope['study_id']}"
    batch_id = "a0000000-0000-4000-8000-000000000002"
    frozen_scope = {key: scope[key] for key in ("scope_id", "scope_version")}
    evidence_ref = "<em>local:synthetic-evidence</em>"
    batch = {
        "batch_id": batch_id, "status": "RUNNING", "reason": "供应商实扣待核对。",
        "can_pause": True, "can_revoke": True,
        "budget": {"requests": 3, "credits": 1, "input_tokens": 800, "output_tokens": 300,
                   "total_tokens": 1100, "units": "9007199254740993"},
        "used": {"requests": 1, "credits": 0, "input_tokens": 809, "output_tokens": 220,
                 "total_tokens": 1029, "units": "238"},
        "currency": "USD", "decimals": 6, "single_cost": "500",
        "authorizations": [{"grant_id": "synthetic-approval", "operation": "model_shard", "provider": "packycode",
                            "channel_ref": "synthetic-channel", "account_ref": "synthetic-account",
                            "credential_current": True, "status": "ACTIVE"}],
        "requests": [{"request_id": "synthetic-request", "status": "UNKNOWN", "operation": "model_shard",
                      "reconciliation_status": "待核对", "estimated_units": "238", "actual_units": None}],
        "evidence": [{"check_id": "C0-5", "kind": "SYNTHETIC", "status": "BLOCKED", "evidence_ref": evidence_ref}],
    }
    received = []

    def reply(route):
        request = route.request
        if request.method == "GET":
            received.append(("GET", request.url))
            route.fulfill(json={"mode": "synthetic_only", "formal_gate": "NOT_EVALUATED", "batches": [batch]})
            return
        action = request.url.removeprefix(f"{url}/{batch_id}/")
        received.append(("POST", action, request.post_data_json))
        if action == "pause":
            batch.update(status="PAUSED", can_pause=False)
        elif action == "revoke":
            batch.update(status="REVOKED", can_pause=False, can_revoke=False)
        route.fulfill(json={"status": batch["status"]})

    pattern = url + "**"
    page.route(pattern, reply)
    try:
        panel = open_approval_center(page, base, scope["study_id"])
        batches = panel.locator("[data-governance-admission]")
        expect(batches.get_by_text("正式研究门禁 NOT_EVALUATED", exact=False)).to_be_visible()
        expect(batches.get_by_text("0.000238 / 9007199254.740993", exact=True)).to_be_visible()
        expect(batches.get_by_text("1 / 3", exact=True)).to_be_visible()
        batches.get_by_text("操作授权与凭证", exact=True).click()
        expect(batches.get_by_text("绑定记录匹配", exact=True)).to_be_visible()
        batches.get_by_text("请求预约及对账", exact=True).click()
        expect(batches.get_by_text("待核对", exact=True)).to_be_visible()
        expect(batches.get_by_text("未核实", exact=True)).to_be_visible()
        batches.get_by_text("同批六项证据", exact=True).click()
        for index in range(1, 7):
            expect(batches.get_by_text(f"C0-{index}", exact=True)).to_be_visible()
        expect(batches.get_by_text(evidence_ref, exact=False)).to_be_visible()
        expect(batches.locator("em")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

        for action, label, confirmation, status in (
            ("pause", "暂停验收批次", "已记录批次暂停。", "PAUSED"),
            ("revoke", "撤销验收批次", "已记录批次撤销。", "REVOKED"),
        ):
            page.once("dialog", lambda dialog: dialog.accept())
            batches.get_by_role("button", name=label).click()
            expect(panel.get_by_text(confirmation, exact=True)).to_be_visible()
            expect(batches.get_by_role("heading", name=f"批次 {batch_id} · {status}")).to_be_visible()
            expect(batches.get_by_role("button", name=label)).to_have_count(0)
            assert ("POST", action, frozen_scope) in received
        assert received[0] == ("GET", f"{url}?scope_id={scope['scope_id']}&scope_version={scope['scope_version']}")
    finally:
        page.unroute(pattern, reply)


def verify_admission_controls(page, base, directory, scope, environment, secret):
    owner = LocalOwner.from_environment(environment)
    policy = EditionPolicy(Edition.PERSONAL, Deployment.LOCAL, owner)
    decision = policy.decide(Permission.WRITE_PERSONAL_APPROVALS, Domain.LOCAL_WORKSPACE,
                             study_id=scope["study_id"], proof=secret, current_scope=lambda _: True)
    assert decision.allowed
    decision = governance_decision(decision, owner)
    context = BatchContext(scope["study_id"], scope["scope_id"], scope["scope_version"], decision.actor_ref,
                           decision.owner_ref, decision.evidence_refs[0], decision.policy_version)
    store = Store(Path(directory), edition=Edition.PERSONAL)
    ledger = ValidationLedger(store)
    at = datetime.now(UTC)
    batch = ledger.draft(context, (at - timedelta(minutes=1)).isoformat(), (at + timedelta(hours=1)).isoformat(),
                         Budget(4, 1, 800, 300, 1100, 500), "USD", 6, 300, "local:browser-batch",
                         lambda db, batch, grant: True)
    panel = open_approval_center(page, base, scope["study_id"])
    batches = panel.locator("[data-governance-admission]")
    heading = f"批次 {batch['batch_id']} · "
    expect(batches.get_by_role("heading", name=heading + "草稿")).to_be_visible()
    expect(batches.get_by_text("合成验收 · 正式研究门禁 NOT_EVALUATED", exact=False)).to_be_visible()
    expect(batches.get_by_text("0.000000 / 0.000500", exact=True)).to_be_visible()
    url = base + f"api/personal/pre-admission/{scope['study_id']}/{batch['batch_id']}"
    for action, label, status in (("pause", "暂停验收批次", "已暂停"), ("revoke", "撤销验收批次", "已撤销")):
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_response(url + "/" + action) as result:
            batches.get_by_role("button", name=label).click()
        assert result.value.ok
        expect(batches.get_by_role("heading", name=heading + status)).to_be_visible()
        expect(batches.get_by_role("button", name=label)).to_have_count(0)
    with store.db() as db:
        events = db.execute("SELECT state FROM personal_validation_batch_events WHERE batch_id=? ORDER BY sequence",
                            (batch["batch_id"],))
        assert [row["state"] for row in events] == ["draft", "paused", "revoked"]


def governance_browser_checks(page, base, directory, scope, other, environment, secret, output, variant):
    study_id = scope["study_id"]
    url = base + f"api/personal/governance/{study_id}"
    headers = {"Origin": base.rstrip("/"), "X-VOC-Action": "connectivity"}
    verify_admission_projection(page, base, scope)
    verify_admission_controls(page, base, directory, scope, environment, secret)
    panel = open_approval_center(page, base, study_id)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    expect(panel.get_by_text("缺少可核证据", exact=False)).to_have_count(len(REQUIRED_EVIDENCE))
    verify_binding(page, panel, url, FIRST)

    expiry = (datetime.now(UTC) + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M")
    form = panel.locator('[data-governance-form="submit"]')
    fill_approval(form, expiry)
    form.get_by_role("button", name="提交审批申请").click()
    expect(panel.get_by_text("已提交审批申请。", exact=True)).to_be_visible()
    pending = panel.get_by_role("article").filter(has_text="待批准")
    expect(pending.get_by_text("缺少账户及 API 使用权", exact=False)).to_be_visible()
    expect(pending.get_by_role("button", name="确认批准")).to_have_count(0)
    blocked_id = pending.get_by_role("button", name="撤销审批").get_attribute("data-event")
    rejected = page.request.post(url + f"/approvals/{blocked_id}/approve", headers=headers,
                                 data={"request_key": "browser-missing-evidence"})
    assert rejected.status == 409

    revision = write_synthetic_evidence(directory, scope)
    panel = open_approval_center(page, base, study_id)
    form = panel.locator('[data-governance-form="submit"]')
    fill_approval(form, expiry)
    select_evidence(form)
    form.get_by_text("企业级 DPA", exact=True).click()
    risk = form.locator("details[open]")
    risk.get_by_role("checkbox", name="登记该项 UNKNOWN").check()
    risk.get_by_label("未知原因").fill("合成材料中未提供")
    risk.get_by_label("实际影响").fill("仅演练审批")
    risk.get_by_label("保护措施").fill("本机隔离，禁用外发")
    expect(risk.get_by_label("责任人引用")).to_have_value("project-owner")
    risk.get_by_label("复核依据").fill("local:browser-synthetic-review")
    risk.locator('[name="risk_expires_at"]').fill(expiry)
    submit_and_approve(page, panel, form)
    active = panel.get_by_role("article").filter(has_text="当前有效")

    for private in (FIRST, ROTATED, secret, revision):
        assert private not in page.content()
    assert page.evaluate("localStorage.length === 0 && sessionStorage.length === 0")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(output / f"personal-approval-{variant}.png"))

    page.once("dialog", lambda dialog: dialog.accept())
    active.get_by_role("button", name="撤销审批").click()
    expect(panel.get_by_text("已记录撤销事件。", exact=True)).to_be_visible()
    expect(panel.get_by_role("article").filter(has_text="当前有效")).to_have_count(0)
    expect(panel.get_by_role("heading", name="已撤销 · packycode · jev-1.14.0").first).to_be_visible()
    fill_approval(form, expiry)
    select_evidence(form)
    submit_and_approve(page, panel, form)
    verify_binding(page, panel, url, ROTATED)
    expect(active).to_have_count(0)
    expect(panel.get_by_role("article").filter(has_text="已失效").get_by_text(
        "当前凭证与审批绑定不一致", exact=True)).to_be_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    with page.expect_response(lambda response: response.url == url + "/credential"
                              and response.request.method == "DELETE") as deleted:
        panel.get_by_role("button", name="删除个人凭证").click()
    assert deleted.value.ok, f"Credential deletion returned HTTP {deleted.value.status}"
    expect(panel.get_by_text("已删除个人凭证。", exact=True)).to_be_visible()
    expect(panel.get_by_text("未配置", exact=True)).to_be_visible()

    denied = page.request.get(base + f"api/personal/governance/{other['study_id']}/approvals")
    assert denied.status in (403, 404)
    assert other["study_id"] not in denied.text()
    forged = page.request.get(url + "/approvals", headers={"X-VOC-Owner": "fixture-claim"})
    assert forged.status == 403
    assert FIRST not in forged.text() and ROTATED not in forged.text()
