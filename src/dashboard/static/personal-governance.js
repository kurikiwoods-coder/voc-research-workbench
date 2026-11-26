const provider = "packycode";
const model = "jev-1.14.0";

const labels = {
  ACCOUNT_API_RIGHTS: "账户及 API 使用权",
  PROVIDER_TERMS: "服务条款及允许用途",
  SOURCE_RIGHTS: "逐源采集、处理及外发许可",
  DATA_PROTECTION: "脱敏、输入最小化及内部数据隔离",
  BUDGET_CONTROL: "预算及计量控制",
  PROJECT_AUTHORIZATION: "项目及用途授权",
  ENTERPRISE_DPA: "企业级 DPA",
  ZDR: "ZDR 资格",
  UPSTREAM_PROVIDERS: "完整上游供应商名单",
  PROCESSING_REGION: "精确处理地区",
  PROCUREMENT: "企业采购程序",
  MULTI_PARTY_APPROVAL: "多人组织审批",
  ACTIVE: "当前有效",
  PENDING: "待批准",
  EXPIRED: "已到期",
  INVALIDATED: "已失效",
  REVOKED: "已撤销",
  SUPERSEDED: "已由后续事件替代",
  VERIFIED: "已核验",
  UNKNOWN: "未知",
  PROHIBITED: "明确禁止",
  submitted: "提交",
  approved: "批准",
  revoked: "撤销",
  APPROVAL_EXPIRED: "审批已到期",
  AUTHORIZATION_CHANGED: "项目或用途授权已变化",
  CREDENTIAL_CHANGED: "当前凭证与审批绑定不一致",
  EVIDENCE_CHANGED: "审批证据已变化",
  EVIDENCE_NOT_CURRENT: "证据与当前绑定不匹配或已失效",
  PURPOSE_PROHIBITED: "供应商条款禁止此用途",
  TERMS_VERSION_MISMATCH: "所选材料的条款版本不一致",
  BUDGET_OUTSIDE_VERIFIED_LIMIT: "预算超过已核验限额",
  MANDATORY_RISK_REQUIRES_EVIDENCE: "必要条件需要补充证据",
  RISK_REVIEW_REQUIRED: "风险责任人或复核时间需要修正",
  NO_CURRENT_ACTIVE_APPROVAL: "缺少当前有效的审批",
};

const terms = (value) => labels[value] ?? value;
const reasonLabel = (value) => value.startsWith("MISSING_") ? "缺少" + terms(value.slice(8)) : terms(value);
const endpoint = (studyId) => "/api/personal/governance/" + encodeURIComponent(studyId);

export function mountGovernance(root, { api, esc }) {
  const showDate = (value) => value ? esc(value) : "—";
  const textField = (name, label, value = "") => `<label>${label}
    <input class="field" name="${name}" value="${esc(value)}" required maxlength="160"></label>`;
  const expiryField = (name) => `<label>UTC 到期时间
    <input class="field" name="${name}" type="datetime-local" required></label>`;
  const button = (action, label, extra = "") =>
    `<button type="button" class="secondary" data-governance-action="${action}" ${extra}>${label}</button>`;
  const readRefs = (form) => ({
    provider,
    channel_ref: form.elements.channel_ref.value.trim(),
    account_ref: form.elements.account_ref.value.trim(),
  });
  const asUtc = (value) => new Date(value + "Z").toISOString();
  const pendingCommands = new Map();
  let projects = [];
  let studyId = "";
  let busy = false;

  root.classList.add("governance");
  root.innerHTML = `<section class="panel" aria-labelledby="governance-title">
    <div class="panel-head"><h2 id="governance-title">个人供应商审批中心</h2></div>
    <div class="body">
      ${button("projects", "读取获准项目")}
      <label hidden>审批研究项目<select id="governance-project" class="field"></select></label>
      <p id="governance-status" role="status" tabindex="-1" hidden></p>
      <p id="governance-error" class="warning" role="alert" tabindex="-1" hidden></p>
      <div class="governance-data"></div>
    </div>
  </section>`;

  const picker = root.querySelector("#governance-project");
  const status = root.querySelector("#governance-status");
  const alert = root.querySelector("#governance-error");
  const body = root.querySelector(".governance-data");

  function feedback(node, message) {
    node.textContent = message;
    node.hidden = !message;
  }

  function details(rows) {
    return `<dl class="governance-grid governance-binding">${rows.map(([label, value]) =>
      `<div><dt>${label}</dt><dd>${value}</dd></div>`).join("")}</dl>`;
  }

  function evidenceRows(required, evidence) {
    return `<fieldset><legend>必要证据</legend>${required.map((kind) => {
      const records = evidence.filter((item) => item.kind === kind);
      if (!records.length) return `<p>${esc(terms(kind))} · 缺少可核证据</p>`;
      return `<div><p>${esc(terms(kind))}</p>${records.map((item) =>
        `<label class="governance-choice"><input type="checkbox" name="evidence_ref" value="${esc(item.evidence_ref)}"
          ${item.status === "VERIFIED" ? "" : "disabled"}>
          <span>${esc(item.evidence_ref)} · ${esc(terms(item.status))} · ${showDate(item.expires_at)}</span></label>`).join("")}</div>`;
    }).join("")}</fieldset>`;
  }

  function risksRows(risks, ownerRef) {
    return `<fieldset><legend>可登记的非强制未知风险</legend>${risks.map((kind) =>
      `<details><summary>${esc(terms(kind))}</summary>
        <fieldset data-governance-risk="${esc(kind)}" disabled>
          <legend>风险接受记录</legend>
          <div class="governance-grid">
            ${textField("reason", "未知原因")}${textField("impact", "实际影响")}
            ${textField("safeguards", "保护措施")}${textField("responsible_ref", "责任人引用", ownerRef)}
            ${textField("review_basis", "复核依据")}${expiryField("risk_expires_at")}
          </div>
        </fieldset>
        <label class="governance-choice"><input type="checkbox" data-governance-risk-toggle>登记该项 UNKNOWN</label>
      </details>`).join("")}</fieldset>`;
  }

  function approvalHistory(events, writable) {
    if (!events.length) return '<p class="state-box">暂无审批记录。</p>';
    return `<ol class="governance-history">${events.map((event) => {
      const state = esc(terms(event.status));
      const eventId = esc(event.event_id);
      let actions = "";
      if (writable && event.status === "PENDING" && !event.reasons?.length) {
        actions += button("approve", "确认批准", `data-event="${eventId}"`);
      }
      if (writable && ["PENDING", "ACTIVE"].includes(event.status)) actions += button("revoke", "撤销审批", `data-event="${eventId}"`);
      return `<li><article>
        <h4>${state} · ${esc(event.provider)} · ${esc(event.model)}</h4>
        ${details([
          ["事件", `${esc(terms(event.kind))} · ${eventId}`],
          ["冻结范围版本", esc(event.scope_version)], ["用途", esc(event.purpose)],
          ["通道", esc(event.channel_ref)], ["账户", esc(event.account_ref)],
          ["生效时间", showDate(event.effective_at)], ["UTC 到期时间", showDate(event.expires_at)],
          ["预算上限", `${esc(event.budget_limit)} ${esc(event.budget_unit)}`],
        ])}
        ${(event.reasons || []).length ? `<p>${event.reasons.map(reasonLabel).map(esc).join("、")}</p>` : ""}
        <div class="actions">${actions}</div>
      </article></li>`;
    }).join("")}</ol>`;
  }

  function display(data) {
    const binding = data.credential;
    const project = projects.find((entry) => entry.scope.study_id === studyId);
    const permissions = data.permissions || {};
    const writable = permissions.write_personal_approvals === true;
    const manage = permissions.manage_personal_credentials === true;
    const readiness = data.readiness;
    const refs = `<div class="governance-grid">
      ${textField("channel_ref", "通道引用", binding.channel_ref)}
      ${textField("account_ref", "账户引用", binding.account_ref)}
    </div>`;
    const evidence = evidenceRows(data.required_evidence, data.evidence);
    body.innerHTML = `<section>
      <h3>当前项目、账户与凭证</h3>
      ${details([
        ["冻结范围", `${esc(project.scope.scope_version)} · ${esc(project.scope.scope_id)}`],
        ["用途", esc(project.purpose)], ["供应商与模型", "PackyCode · jev-1.14.0"],
        ["本机凭证", binding.configured ? "已配置" : "未配置"],
        ["当前通道", esc(binding.channel_ref || "—")], ["当前账户", esc(binding.account_ref || "—")],
      ])}
    </section>
    ${manage ? `<form class="governance-form" data-governance-form="credential">
      <h3>保存或轮换本机凭证</h3>
      ${refs}
      <label>个人 API Key<input class="field" name="api_key" type="password" autocomplete="off" required></label>
      <div class="actions"><button type="submit" class="secondary">保存个人凭证</button>
        ${binding.configured ? button("delete", "删除个人凭证") : ""}</div>
    </form>` : ""}
    <section>
      <h3>审批及材料</h3>
      ${writable ? `<form class="governance-form" data-governance-form="submit">${refs}
        <div class="governance-grid">
          <label>预算上限（Tokens）<input class="field" name="budget_limit" type="number" min="1" step="1" required></label>
          ${expiryField("expires_at")}
        </div>
        ${evidence}${risksRows(data.optional_risks, project.owner_ref)}
        <button type="submit" class="primary">提交审批申请</button>
      </form>` : `<p>当前授权仅可查看审批。</p><div inert>${evidence}</div>`}
    </section>
    <section>
      <h3>后续 G-1-P-D 验收准备</h3>
      <p class="state-box">${readiness?.ready === true ? "当前服务端审批条件已齐备。" : "仍有审批条件待处理。"}
        ${(readiness?.reasons || []).map(reasonLabel).map(esc).join("、")}
        ${readiness?.ready === true ? "实际供应商验证需要单独授权。" : ""}</p>
    </section>
    <section><h3>当前及历史审批事件</h3>${approvalHistory(data.approvals, writable)}</section>`;
  }

  async function loadApproval() {
    body.replaceChildren();
    if (studyId) display(await api(endpoint(studyId) + "/approvals"));
  }

  async function perform(task, { credential = false, mutation = false, focusTarget } = {}) {
    if (busy) return;
    busy = true;
    root.setAttribute("aria-busy", "true");
    picker.disabled = true;
    feedback(alert, "");
    feedback(status, "正在核对本机审批记录…");
    try {
      feedback(status, await task());
    } catch (error) {
      if (mutation && error.status !== 422 && studyId) {
        try {
          await loadApproval();
        } catch {
          body.replaceChildren();
        }
      }
      feedback(status, "");
      feedback(alert, credential
        ? "凭证操作未能完成。请核对当前权限、账户、通道及本机凭证库。"
        : error.message);
      alert.focus();
    } finally {
      busy = false;
      root.removeAttribute("aria-busy");
      picker.disabled = false;
      if (alert.hidden && focusTarget?.offsetParent) focusTarget.focus();
    }
  }

  async function send(path, method, payload) {
    return api(path, {
      method,
      headers: { "X-VOC-Action": "connectivity", "Content-Type": "application/json" },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    });
  }

  async function sendApproval(path, payload, message) {
    const serialized = JSON.stringify(payload);
    const pending = pendingCommands.get(path);
    const requestKey = pending?.serialized === serialized ? pending.requestKey : crypto.randomUUID();
    pendingCommands.set(path, { serialized, requestKey });
    await send(path, "POST", { ...payload, request_key: requestKey });
    pendingCommands.delete(path);
    await loadApproval();
    return message;
  }

  root.addEventListener("change", (event) => {
    if (event.target === picker) {
      studyId = picker.value;
      pendingCommands.clear();
      perform(async () => { await loadApproval(); return ""; });
    }
    if (event.target.matches("[data-governance-risk-toggle]")) {
      event.target.closest("details").querySelector("fieldset").disabled = !event.target.checked;
    }
  });

  root.addEventListener("click", (event) => {
    const control = event.target.closest("[data-governance-action]");
    if (!control || busy) return;
    const { governanceAction: action, event: eventId } = control.dataset;
    if (action === "projects") {
      perform(async () => {
        studyId = "";
        pendingCommands.clear();
        body.replaceChildren();
        picker.closest("label").hidden = true;
        projects = (await api("/api/edition/projects")).projects.filter((project) => project.scope);
        if (!projects.length) return "暂无获准项目。";
        picker.innerHTML = '<option value="">请选择已获准项目</option>' + projects.map(({ scope }) =>
          `<option value="${esc(scope.study_id)}">${esc(scope.study_id)} · ${esc(scope.scope_version)}</option>`).join("");
        picker.closest("label").hidden = false;
        return "已读取获准项目。";
      }, { focusTarget: picker });
      return;
    }
    const base = endpoint(studyId);
    if (action === "delete" && window.confirm("删除个人凭证会使相关批准失效。确定删除？")) {
      perform(async () => {
        await send(base + "/credential", "DELETE");
        await loadApproval();
        return "已删除个人凭证。";
      }, { credential: true, mutation: true });
    }
    if (action === "approve" || action === "revoke") {
      const approval = action === "approve";
      if (!window.confirm(approval ? "确认使用当前凭证和材料批准此申请？" : "确定撤销此审批？")) return;
      perform(() => sendApproval(`${base}/approvals/${encodeURIComponent(eventId)}/${action}`, {},
        approval ? "已记录批准事件。" : "已记录撤销事件。"), { mutation: true });
    }
  });

  root.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form.matches("[data-governance-form]")) return;
    event.preventDefault();
    if (busy) return;
    const base = endpoint(studyId);
    if (form.dataset.governanceForm === "credential") {
      const payload = { ...readRefs(form), api_key: form.elements.api_key.value };
      form.elements.api_key.value = "";
      perform(async () => {
        await send(base + "/credential", "PUT", payload);
        await loadApproval();
        return "已保存个人凭证。";
      }, { credential: true, mutation: true });
      return;
    }
    perform(() => {
      const data = new FormData(form);
      const budget = Number(data.get("budget_limit"));
      if (!Number.isSafeInteger(budget) || budget < 1) {
        throw Object.assign(new Error("请填写有效的整数预算上限。"), { status: 422 });
      }
      const risks = [...form.querySelectorAll("[data-governance-risk]:enabled")].map((fields) => {
        const get = (name) => fields.querySelector(`[name=${name}]`).value;
        return {
          kind: fields.dataset.governanceRisk,
          reason: get("reason"), impact: get("impact"), safeguards: get("safeguards"),
          responsible_ref: get("responsible_ref"), expires_at: asUtc(get("risk_expires_at")),
          review_basis: get("review_basis"),
        };
      });
      return sendApproval(base + "/approvals", {
        ...readRefs(form), model, expires_at: asUtc(data.get("expires_at")), budget_unit: "TOKENS",
        budget_limit: budget, evidence_refs: data.getAll("evidence_ref"), risks,
      }, "已提交审批申请。");
    }, { mutation: true });
  });
}
