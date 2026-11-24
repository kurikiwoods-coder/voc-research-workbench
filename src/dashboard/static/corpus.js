const pageSize = 20;
const statuses = {
  pending_review: ["待核验", "PENDING"],
  verified: ["已核验", "PASS"],
  excluded: ["已排除", "NOT_TESTED"],
  revoked: ["已撤销", "FAIL"],
  retention_expired: ["保留期限已过", "BLOCKED"],
  source_restricted: ["同源原文受限", "BLOCKED"],
};
const privacyLabels = { public: "公开", private: "非公开", internal: "内部 / CX", unknown: "未确认" };
const roles = {
  user_quote: "用户原话",
  background: "背景证据",
  internal: "内部材料",
  synthetic: "合成样本",
};
const clock = new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" });
const present = value => value !== null && value !== undefined && value !== "";
const time = value => value ? clock.format(new Date(value)) : "";
const homeFor = study => "#corpus" + (study ? "/" + encodeURIComponent(study) : "");
const routeFor = (study, type, id) => homeFor(study) + "/" + type + "/" + encodeURIComponent(id);

export function mountCorpus(root, route, { api, esc, choices, tell }) {
  const [, routeStudy, kind, itemId] = route.split("/");
  let study = routeStudy, offset = 0, loading = false;
  const endpoint = () => "/api/corpus/" + encodeURIComponent(study);
  const submit = (path, data) => api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-VOC-Action": "connectivity" },
    body: JSON.stringify(data),
  });
  const link = (href, title) => `<a class="secondary" href="${esc(href)}">${esc(title)}</a>`;
  const empty = message => `<p class="state-box">${esc(message)}</p>`;
  const badge = status => {
    const [label, modifier] = statuses[status] || ["未确认", "NOT_TESTED"];
    return `<span class="status ${modifier}">${label}</span>`;
  };
  const heading = (title, description, actions) => `<header class="page-head corpus-head">
    <div><h1 tabindex="-1">${esc(title)}</h1><p>${esc(description)}</p></div>
    <div class="actions">${actions}</div></header><p class="study-error" role="alert" tabindex="-1" hidden></p>`;
  const section = (title, body, className = "") => `<section class="panel corpus-panel ${className}">
    <h2>${esc(title)}</h2>${body}</section>`;
  function fields(values) {
    return '<dl class="study-data corpus-fields">' + values.map(([label, value]) =>
      `<div><dt>${esc(label)}</dt><dd>${esc(present(value) ? value : "—")}</dd></div>`
    ).join("") + "</dl>";
  }
  function show(html, focus = true) {
    if (!root.isConnected) return;
    root.innerHTML = html;
    if (focus) root.querySelector("h1")?.focus({ preventScroll: true });
  }
  function showError(error) {
    if (!root.isConnected) return;
    const alert = root.querySelector("[role=alert]");
    alert.textContent = error.message;
    alert.hidden = false;
    alert.focus({ preventScroll: true });
  }
  function pagination(more) {
    if (!offset && !more) return "";
    return `<div class="actions corpus-paging" aria-label="翻页">
      <button type="button" class="secondary" data-corpus-offset="${offset - pageSize}" ${offset ? "" : "disabled"}>上一页</button>
      <span>第 ${offset / pageSize + 1} 页</span>
      <button type="button" class="secondary" data-corpus-offset="${offset + pageSize}" ${more ? "" : "disabled"}>下一页</button>
      </div>`;
  }
  function batchList({ batches, more }) {
    if (!batches.length) return empty("这个项目还没有导入批次。");
    return `<ul class="corpus-list">${batches.map(batch => `<li>
      <div><a class="study-inline-link" href="${esc(routeFor(study, "batches", batch.batch_id))}">${esc(batch.filename)}</a>
        <p>${esc(batch.sheet_name)} · ${esc(batch.scope_version)} · ${esc(time(batch.collected_at))}</p></div>
      <div class="corpus-row-state"><span>${esc(batch.reviewed_count)} / ${esc(batch.candidate_count)} 已审核</span>
        ${batch.revoked_at ? badge("revoked") : ""}</div>
      </li>`).join("")}</ul>${pagination(more)}`;
  }
  async function loadHome() {
    const projects = await submit("/api/studies/search", { status: "all" });
    study = routeStudy || projects.current?.study_id || "";
    const options = projects.projects.map(project => [
      project.study_id, project.name + (project.status === "archived" ? "（已归档）" : ""),
    ]);
    if (study && !options.some(([id]) => id === study)) {
      const project = await api("/api/studies/" + encodeURIComponent(study));
      options.unshift([study, project.name]);
    }
    if (!study) options.unshift(["", "请选择项目"]);
    const body = study
      ? batchList(await api(endpoint() + "/batches?offset=" + offset))
      : empty("选择研究项目以查看语料。");
    show(heading("原始语料库", "查看本机导入原文、来源和审核记录。",
      link(study ? "#imports/" + encodeURIComponent(study) : "#imports", "进入数据导入")) +
      section("导入批次", `<label class="corpus-project">研究项目
        <select class="field" id="corpus-project">${choices(options, study)}</select></label>${body}`));
  }
  async function loadBatch() {
    const { records, more } = await api(endpoint() + "/batches/" + itemId + "?offset=" + offset);
    const body = records.length ? `<ul class="corpus-list">${records.map(record => `<li>
      <div><a class="study-inline-link" href="${esc(routeFor(study, "records", record.record_id))}">第 ${esc(record.line_number)} 行</a>
        <p>${esc(privacyLabels[record.privacy] || "未确认")} · ${esc(record.source_type || "来源未填")}</p></div>
      <div class="corpus-row-state">${record.role ? `<span>${esc(roles[record.role])}</span>` : ""}${badge(record.status)}</div>
      </li>`).join("")}</ul>${pagination(more)}` : empty("这个批次没有可回查的候选记录。");
    show(heading("批次语料", "选择文件行号，查看原文和来源。",
      link(homeFor(study), "返回语料批次") +
      link("#imports/" + encodeURIComponent(study) + "/batches/" + itemId, "查看导入结果")) +
      section("语料记录", body));
  }
  function source(record) {
    const { metadata = {}, trace } = record;
    const window = trace.time_window || {};
    const windowLabel = window.start || window.end
      ? (window.start || "不限起始") + " 至 " + (window.end || "不限结束") : "未限定";
    return fields([
      ["来源类型", record.source_type], ["原文地址", metadata.source_url],
      ["发布日期", record.published_at], ["来源许可", metadata.access_policy],
      ["标注角色", metadata.content_role], ["隐私等级", privacyLabels[record.privacy]],
      ["采样时间", time(trace.collected_at)], ["采样窗口", windowLabel],
      ["提取方式", trace.extraction_method === "csv_upload" ? "CSV 导入" : "工作簿导入"],
      ["提取规则", trace.extraction_rule],
    ]);
  }
  function duplicate(record) {
    const entry = record.duplicate;
    if (!entry) return empty("暂无同一项目内已识别的重复记录。");
    const canonical = entry.is_duplicate
      ? link(routeFor(study, "records", entry.canonical_record_id), "查看主记录")
      : "";
    return fields([
      ["组内记录", entry.record_count],
      ["归组结果", entry.is_duplicate ? "重复记录" : "主记录"],
    ]) + (canonical ? `<div class="actions corpus-paging">${canonical}</div>` : "");
  }
  function history(record) {
    if (!record.history.length) return empty("暂无审核记录。");
    return `<ol class="corpus-list corpus-history">${record.history.map(entry => `<li>
      <div class="corpus-row-state">${badge(entry.decision)}<span>${esc(roles[entry.role])}</span>
      <time datetime="${esc(entry.reviewed_at)}">${esc(time(entry.reviewed_at))}</time></div>
      ${fields([["原因", entry.reason], ["核验依据", entry.basis], ["保留至", entry.retention_until]])}
      </li>`).join("")}</ol>`;
  }
  function reviewForm(record) {
    if (!record.can_review) return empty("该记录目前只供回查。");
    const roleOptions = [["", "请选择角色"], ...Object.entries(roles)];
    const decisions = [["", "请选择结论"], ["verified", "核验通过"], ["excluded", "排除"]];
    return `<form id="corpus-review">
      <fieldset class="study-form-grid corpus-form">
        <label>审核结论<select class="field" name="decision" required>${choices(decisions, "")}</select></label>
        <label>语料角色<select class="field" name="role" required>${choices(roleOptions, record.role || "")}</select></label>
        <label class="study-full">审核原因<textarea class="field" name="reason" required maxlength="500" rows="2"></textarea></label>
        <label class="study-full">核验依据<textarea class="field" name="basis" maxlength="1000" rows="3"
          aria-describedby="corpus-basis-hint"></textarea></label>
        <p id="corpus-basis-hint" class="study-full">核验通过时，记录原文比对、来源许可、项目范围与隐私检查的依据。请避免在审核说明中复述个人资料。</p>
        <label>保留至（UTC）<input class="field" type="date" name="retention_until"
          min="${new Date().toISOString().slice(0, 10)}"></label>
        <div class="actions corpus-review-action"><button class="primary" type="submit">保存审核</button></div>
      </fieldset></form>`;
  }
  function drawRecord(record, focus = true) {
    const { trace } = record;
    const quote = record.raw_text == null
      ? empty("该记录的原文当前不供查看。")
      : `<blockquote class="corpus-quote">${esc(record.raw_text)}</blockquote>`;
    const notice = record.revoked_at ? "导入批次撤销于 " + time(record.revoked_at) + "。" : "";
    const state = `<div class="corpus-record-state">${badge(record.status)}
      <span>${esc(roles[record.role] || "角色待定")}</span>
      ${record.retention_until ? `<span>保留至 ${esc(record.retention_until)}（UTC）</span>` : ""}</div>`;
    const fileTrace = fields([
      ["原始文件", trace.filename], ["工作表", trace.sheet_name],
      ["文件行号", trace.line_number], ["冻结范围", trace.scope_version],
      ["语料 ID", record.record_id], ["文件 ID", trace.file_id],
      ["文件 SHA-256", trace.file_sha256], ["原文 SHA-256", record.raw_sha256],
    ]);
    show(heading("原文溯源", "第 " + trace.line_number + " 行 · " + trace.filename,
      link(routeFor(study, "batches", trace.batch_id), "返回批次语料")) +
      (notice ? `<p class="warning">${esc(notice)}</p>` : "") +
      section("原文", state + quote, "corpus-primary") +
      `<div class="corpus-details">${section("来源与许可", source(record))}${section("导入位置", fileTrace)}</div>` +
      section("去重记录", duplicate(record)) +
      section("本机审核", reviewForm(record)) +
      section("审核记录", history(record)), focus);
  }
  async function load() {
    if (loading) return;
    loading = true;
    const recovery = link(homeFor(study), "返回语料批次");
    show(heading("原始语料库", "正在读取本机语料。", recovery), false);
    try {
      if (kind === "records") drawRecord(await api(endpoint() + "/records/" + itemId));
      else if (kind === "batches") await loadBatch();
      else await loadHome();
    } catch (error) {
      showError(error);
    } finally {
      loading = false;
    }
  }

  root.addEventListener("click", event => {
    const button = event.target.closest("[data-corpus-offset]");
    if (!button || button.disabled || loading) return;
    offset = Number(button.dataset.corpusOffset);
    load();
  });
  root.addEventListener("change", event => {
    if (event.target.id === "corpus-project") location.hash = homeFor(event.target.value);
    if (event.target.name === "decision" && event.target.form?.id === "corpus-review") {
      const verified = event.target.value === "verified";
      event.target.form.elements.basis.required = verified;
      event.target.form.elements.retention_until.required = verified;
    }
  });
  root.addEventListener("submit", async event => {
    const form = event.target;
    if (form.id !== "corpus-review") return;
    event.preventDefault();
    const controls = form.querySelector("fieldset");
    if (controls.disabled) return;
    const data = Object.fromEntries(new FormData(form));
    data.retention_until ||= null;
    const path = endpoint() + "/records/" + itemId;
    controls.disabled = true;
    root.querySelector("[role=alert]").hidden = true;
    try {
      const reviewed = await submit(path + "/review", data);
      if (root.isConnected) tell("审核记录已保存");
      drawRecord(reviewed);
    } catch (error) {
      showError(error);
    } finally {
      controls.disabled = false;
    }
  });
  load();
}
