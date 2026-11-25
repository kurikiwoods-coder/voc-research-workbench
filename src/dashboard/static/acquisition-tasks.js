const taskStates = {
  draft: "草稿", queued: "待执行", running: "执行中", paused: "已暂停",
  partial: "部分完成", completed: "已完成", failed: "已失败", cancelled: "已取消",
  permission_blocked: "权限受阻", budget_blocked: "额度受阻",
};
const stepStates = {
  not_sent: "尚未发送", reserved: "已预约 · 发送结果未知", received: "已收到回执",
  persisted: "已持久化", reconciled: "已完成对账",
};
const actionLabels = { queue: "加入队列", step: "执行下一检查点", pause: "暂停任务", resume: "恢复任务", cancel: "取消任务" };
const actionsFor = {
  draft: ["queue", "cancel"], queued: ["step", "pause", "cancel"], running: ["step", "pause", "cancel"],
  paused: ["resume", "cancel"], partial: ["step", "pause", "cancel"],
  budget_blocked: ["resume", "cancel"], permission_blocked: ["resume", "cancel"],
};
const scenarios = {
  normal: "正常运行", primary_unavailable: "主搜索引擎故障", source_unavailable: "原文回源故障",
};
const formats = { none: "不使用文件兜底", csv: "合成 CSV", xlsx: "合成 Excel" };
const budgetUnits = {
  tavily_credit: "Tavily Credit", brave_request: "Brave 请求",
  stackexchange_request: "Stack Exchange 请求", youtube_quota_unit: "YouTube 配额单位",
};
const checkpointKinds = { query: "搜索发现", page: "原文回源", import: "导入批次" };
const receiptStates = {
  accessed: "可访问", no_discovery: "无搜索发现", segments_extracted: "已抽取片段",
  source_unavailable: "回源中断", skipped_by_fallback_policy: "按备用策略跳过",
  imported: "已导入", no_extractable_records: "没有可提取原文",
};
const fileFormats = { csv: "CSV", xlsx: "Excel" };
const limits = [
  ["sample_target", "目标语义片段数", 120, 12], ["per_source_limit", "单来源片段上限", 60, 12],
  ["query_limit", "搜索请求上限", 6, 2], ["page_limit", "任务页面上限", 60, 12],
  ["batch_count", "目标批次数", 3, 1],
];

export function mountAcquisitionTasks(root, {
  api, esc, pairs, message, funnel, queryPreview, nameOf, statusOf, reasonOf, selection, onReceipts,
}) {
  root.innerHTML = `
    <section class="panel acquisition-panel" aria-labelledby="acquisition-task-heading">
      <h2 id="acquisition-task-heading">创建合成采样任务</h2>
      <p class="acquisition-hint">沿用上方选定的项目、冻结范围和搜索策略。每路合成查询最多返回 20 条，搜索域名由所选平台决定。</p>
      <form id="acquisition-task-form">
        <fieldset id="acquisition-task-config" disabled>
          <fieldset class="acquisition-domains">
            <legend>合成回源平台</legend>
            <div>
              <label><input name="source_id" type="checkbox" value="m08-stackexchange" checked> Stack Exchange</label>
              <label><input name="source_id" type="checkbox" value="m08-youtube"> YouTube</label>
            </div>
          </fieldset>
          <div class="acquisition-grid">
            ${limits.map(([key, label, max, value]) => `<label>${label}<input class="field" name="${key}" type="number"
              min="1" max="${max}" value="${value}" required></label>`).join("")}
            <label>合成故障场景<select name="fixture_scenario" class="field">
              ${Object.entries(scenarios).map(([key, label]) => `<option value="${key}">${label}</option>`).join("")}
            </select></label>
            <label>文件兜底<select name="fallback_format" class="field" disabled>
              ${Object.entries(formats).map(([key, label]) => `<option value="${key}">${label}</option>`).join("")}
            </select></label>
          </div>
          <fieldset class="acquisition-domains">
            <legend>模拟用量预算</legend>
            <div class="acquisition-grid acquisition-budgets">
              ${Object.entries(budgetUnits).map(([unit, label]) => `<label>${label}<input class="field" name="${unit}" type="number"
                min="0" max="2000" value="200" required></label>`).join("")}
            </div>
          </fieldset>
          <div class="actions acquisition-actions">
            <button type="submit" class="secondary">预览合成任务</button>
          </div>
          <div id="acquisition-task-preview" hidden></div>
          <div class="actions acquisition-actions">
            <button type="button" class="primary" data-task-action="create" disabled>创建合成任务</button>
          </div>
        </fieldset>
      </form>
    </section>
    <section class="panel acquisition-panel" aria-labelledby="acquisition-task-list-heading">
      <div class="acquisition-task-heading">
        <h2 id="acquisition-task-list-heading">合成采样任务</h2>
        <button class="secondary" type="button" data-task-action="refresh" disabled>刷新任务</button>
      </div>
      <p class="study-error" id="acquisition-task-error" role="alert" hidden></p>
      <p class="acquisition-hint" id="acquisition-task-status" role="status"></p>
      <div id="acquisition-task-list">${message("选择研究项目后查看合成任务。")}</div>
      <div id="acquisition-task-detail" hidden></div>
    </section>`;

  const get = id => root.querySelector("#acquisition-task-" + id);
  const form = get("form");
  const fields = form.elements;
  let studyId = "", studyName = "", tasks = [], activeTask = null, preview = null;
  let generation = 0, previewRevision = 0, busy = false;
  const stepKeys = new Map();
  const action = name => root.querySelector('[data-task-action="' + name + '"]');
  const route = () => "/api/acquisition/" + encodeURIComponent(studyId) + "/tasks";
  const detailRoute = id => route() + "/" + encodeURIComponent(id);
  const sourceName = id => nameOf(id.replace(/^m08-/, ""));
  const taskName = state => taskStates[state] || state;
  const listOf = (items, renderer) => items?.length ? items.map(renderer).join("") : message("暂无记录。");
  function errorText(error) {
    const line = get("error");
    line.textContent = error.message;
    line.hidden = false;
  }

  function setControls() {
    const backup = fields.namedItem("fallback_format");
    backup.disabled = fields.namedItem("fixture_scenario").value !== "source_unavailable";
    if (backup.disabled) backup.value = "none";
    get("config").disabled = busy || !selection();
    action("create").disabled = busy || !preview;
    action("refresh").disabled = busy || !studyId;
    get("list").querySelectorAll("button").forEach(button => { button.disabled = busy; });
    get("detail").querySelectorAll("button").forEach(button => { button.disabled = busy; });
  }

  function invalidatePreview() {
    previewRevision += 1;
    preview = null;
    get("preview").hidden = true;
    get("preview").replaceChildren();
    setControls();
  }

  function configPairs(config, projectName) {
    const plan = config.query_plan.inputs;
    return pairs([
      ["项目", projectName], ["范围 ID", config.scope_id], ["冻结版本", config.scope_version],
      ["查询计划版本", config.query_plan.version], ["研究目标", config.research_goal],
      ["搜索关键词", plan.keywords], ["搜索引擎", plan.providers.map(nameOf)],
      ["回源平台", config.source_ids.map(sourceName)], ["白名单", plan.allowed_domains],
      ["语言", plan.language], ["地区", plan.country], ["日期范围", config.window_start + " 至 " + config.window_end],
      ["搜索策略", { independent: "独立搜索", merge: "双路合并", fallback: "双路故障切换" }[plan.mode]],
      ...limits.map(([key, label]) => [label, config[key]]),
      ["每路最大结果数", plan.limit], ["合成场景", scenarios[config.fixture_scenario]],
      ["文件兜底", formats[config.fallback_format]],
      ...Object.entries(config.budgets || {}).map(([unit, value]) =>
        [budgetUnits[unit] || unit, typeof value === "object" ? value.authorized : value]),
    ]);
  }

  function post(path, data) {
    const headers = { "X-VOC-Action": "connectivity" };
    if (data) headers["Content-Type"] = "application/json";
    return api(path, { method: "POST", headers, body: data && JSON.stringify(data) });
  }

  async function perform(label, operation, onComplete) {
    if (busy) return;
    const token = generation;
    busy = true;
    setControls();
    get("error").hidden = true;
    get("status").textContent = label;
    try {
      const value = await operation();
      if (root.isConnected && token === generation) onComplete(value);
    } catch (error) {
      if (root.isConnected && token === generation) {
        if ([401, 403, 404].includes(error.status)) {
          activeTask = null;
          get("detail").replaceChildren();
          get("detail").hidden = true;
        }
        errorText(error);
      }
    } finally {
      if (root.isConnected && token === generation) {
        busy = false;
        setControls();
        get("status").textContent = "";
      }
    }
  }

  function renderList() {
    get("list").innerHTML = tasks.length ? `<div class="acquisition-task-cards">${tasks.map(task => {
      const counts = task.engineering_funnel || {};
      const id = task.acquisition_task_id;
      return `<article class="acquisition-source">
        <div class="acquisition-task-heading">
          <button class="secondary acquisition-task-id" type="button" data-task-action="open" data-task-id="${esc(id)}">${esc(id)}</button>
          <span class="acquisition-task-state">${esc(taskName(task.state))}</span>
        </div>
        ${pairs([
          ["项目", studyName], ["来源", (task.source_ids || task.config?.source_ids)?.map(sourceName)],
          ["已发现 URL", counts.N_discovered_urls], ["已访问页面", counts.N_accessible_pages],
          ["已抽取片段", counts.N_extracted_mentions], ["失败数量", task.failure_count],
          ["模拟用量", usageValues(task.usage)], ["操作时间", task.updated_at ?? task.created_at],
        ])}
      </article>`;
    }).join("")}</div>` : message(studyId ? "该项目暂无合成采样任务。" : "选择研究项目后查看合成任务。");
  }

  function usageValues(usage) {
    return Object.entries(usage || {}).map(([unit, value]) =>
      `${budgetUnits[unit] || unit} · 已使用 ${value.used} / 获授权 ${value.authorized} · 已预约 ${value.reserved}`);
  }

  function section(title, content) {
    return `<section class="acquisition-section"><h4>${title}</h4>${content}</section>`;
  }

  function details(summary, content) {
    return `<details><summary>${esc(summary)}</summary>${content}</details>`;
  }

  function renderDetail(task, focus) {
    activeTask = task;
    const controls = (actionsFor[task.state] || []).filter(name =>
      !task.reconciliation_required || !["resume", "step"].includes(name));
    if (task.local_recovery_available && !controls.includes("step")) controls.unshift("step");
    const attempts = task.attempts || [];
    const history = task.history || [];
    onReceipts(attempts);
    get("detail").innerHTML = `<section class="acquisition-section" aria-labelledby="acquisition-task-detail-heading">
      <h3 id="acquisition-task-detail-heading" tabindex="-1">合成任务详情</h3>
      ${pairs([
        ["任务 ID", task.acquisition_task_id], ["状态", taskName(task.state)], ["状态原因", reasonOf(task.reason)],
        ["检查点进度", `${task.next_checkpoint} / ${task.checkpoint_count}`], ["创建时间", task.created_at], ["开始时间", task.started_at],
        ["完成时间", task.completed_at], ["最近操作时间", task.updated_at], ["操作者", task.actor],
        ["真实研究 API 调用", `${task.real_api_calls} 次`],
        ["请求核对", task.local_recovery_available ? "本机回执已保存，可继续对账" :
          task.reconciliation_required ? "发送结果未知，须先核对" : "无待核对请求"],
        ["模拟用量", usageValues(task.usage)],
      ])}
      <div class="actions acquisition-actions">${controls.map(name =>
        `<button type="button" class="${name === "step" ? "primary" : "secondary"}" data-task-action="${name}">
          ${name === "step" && task.local_recovery_available ? "恢复本机回执" : actionLabels[name]}</button>`
      ).join("")}</div>
      ${section("任务配置", configPairs(task.config, studyName))}
      ${queryPreview(task.config.query_plan.queries)}
      ${funnel("任务合成漏斗", task.engineering_funnel || {}, "台账未核定")}
      ${funnel("任务正式研究分母", task.formal_funnel || {}, "未取得正式台账")}
      ${section("查询与来源回执", `<div class="acquisition-receipts">${listOf(attempts, renderReceipt)}</div>`)}
      ${section("批次与质量检查", renderBatches(attempts))}
      ${section("任务审计日志", `<div class="acquisition-receipts">${listOf(history, row => details(
        taskName(row.state ?? row.to_state), pairs([
          ["事件", row.event], ["原因", reasonOf(row.reason)], ["操作者", row.actor],
          ["请求 ID", row.request_id], ["操作时间", row.event_at],
        ])
      ))}</div>`)}
    </section>`;
    get("detail").hidden = false;
    if (focus) get("detail-heading").focus();
  }

  function renderReceipt(attempt) {
    const checkpoint = attempt.checkpoint;
    const receipt = attempt.receipt;
    const source = sourceName(checkpoint.source_id);
    return details(`第 ${attempt.checkpoint_index + 1} 步 · ${checkpointKinds[checkpoint.kind] || checkpoint.kind} · ${source}`, pairs([
      ["请求 ID", attempt.request_id], ["来源", source],
      ["请求状态", stepStates[attempt.state] || attempt.state], ["限制原因", reasonOf(attempt.reason)],
      ["计量单位", budgetUnits[attempt.unit] || statusOf(attempt.unit)], ["预约用量", attempt.reserved_units],
      ["实际模拟用量", attempt.used_units], ["执行结果", taskName(attempt.outcome)],
      ["预约时间", attempt.reserved_at], ["回执时间", attempt.received_at], ["持久化时间", attempt.persisted_at],
      ["对账时间", attempt.reconciled_at], ["批次序号", checkpoint.input.batch],
      ["回执状态", receiptStates[receipt?.status] || receipt?.status],
    ]) + (receipt && checkpoint.kind === "query" ? renderSearchReceipt(receipt) : "") +
      (receipt && checkpoint.kind === "page" ? renderPageReceipt(receipt.records) : ""));
  }

  function renderSearchReceipt(receipt) {
    return pairs([
      ["搜索错误", reasonOf(receipt.error)], ["返回结果", receipt.result_count],
      ["故障切换", receipt.switch && `${nameOf(receipt.switch.from)} → ${nameOf(receipt.switch.to)} · ${reasonOf(receipt.switch.reason)}`],
    ]) + listOf(receipt.hits, hit => details(`排名 ${hit.rank} · ${hit.canonical_url}`, pairs([
      ["原始 URL", hit.url], ["规范 URL", hit.canonical_url], ["发现时间", hit.discovered_at],
    ])));
  }

  function renderPageReceipt(records) {
    return listOf(records, record => details(record.source_locator, pairs([
      ["原文获取状态", receiptStates[record.status] || statusOf(record.status)], ["HTTP 状态", record.http_status],
      ["可访问", record.accessible], ["标题", record.title], ["原始 URL", record.original_url],
      ["规范 URL", record.canonical_url], ["发布时间", record.published_at], ["最近修改", record.modified_at],
      ["采集时间", record.fetched_at], ["采集接口", record.method], ["内容角色", statusOf(record.role)],
      ["许可引用", record.license_reference], ["署名", record.attribution], ["原文 SHA-256", record.raw_sha256],
      ["抽取片段数", record.segments.length], ["抽取失败原因", reasonOf(record.extraction_reason)],
    ])));
  }

  function renderBatches(attempts) {
    const batches = attempts.filter(item => item.state === "reconciled" && item.receipt?.batch_id);
    let evidenceIndex = 0;
    return `<div class="acquisition-receipts">${listOf(batches, ({ receipt }) => details(receipt.batch_id, pairs([
      ["批次 ID", receipt.batch_id], ["格式", fileFormats[receipt.format]], ["文件兜底", receipt.fallback],
      ["记录总数", receipt.summary.total], ["结构合格", receipt.summary.staged],
      ["待审核", receipt.summary.pending_review], ["疑似重复", receipt.summary.duplicate],
      ["异常拒收", receipt.summary.rejected], ["抽取片段", receipt.evidence.length],
    ]) + listOf(receipt.evidence, item => {
      const index = evidenceIndex++;
      return details(`片段 ${index + 1} · ${item.source_locator}`, pairs([
        ["原文记录 ID", item.record_id], ["来源", sourceName(item.source_id)], ["范围版本", item.scope_version],
        ["采集方式", item.method], ["发布日期", item.published_at], ["原文 SHA-256", item.raw_sha256],
        ["Unicode 区间", `[${item.start_cp}, ${item.end_cp})`], ["抽取版本", item.extraction_version],
      ]) + `<button class="secondary" type="button" data-task-action="evidence" data-evidence-index="${index}">核验并读取片段</button>
        <div data-evidence-result role="status"></div>`);
    })))}</div>`;
  }

  function showTask(task) {
    tasks = [task, ...tasks.filter(item => item.acquisition_task_id !== task.acquisition_task_id)];
    renderList();
    renderDetail(task, true);
  }

  function refresh() {
    const currentId = activeTask?.acquisition_task_id;
    perform("正在读取合成任务…", () => Promise.all([
      api(route()), currentId ? api(detailRoute(currentId)) : null,
    ]), ([result, detail]) => {
      tasks = result.tasks;
      renderList();
      if (detail) renderDetail(detail, false);
    });
  }

  function setStudy(id, name) {
    if (id === studyId) return;
    generation += 1;
    studyId = id;
    studyName = name;
    tasks = [];
    activeTask = null;
    busy = false;
    get("detail").hidden = true;
    get("detail").replaceChildren();
    get("error").hidden = true;
    get("status").textContent = "";
    invalidatePreview();
    renderList();
    if (id) refresh();
  }

  form.addEventListener("input", invalidatePreview);
  form.addEventListener("submit", event => {
    event.preventDefault();
    const current = selection();
    if (!current || busy) return;
    const input = new FormData(form);
    const sources = input.getAll("source_id");
    if (!sources.length || !current.plan.allowed_domains.length) {
      errorText(new Error("请选择至少一个合成回源平台和一个来源白名单域名。"));
      return;
    }
    if (!Number.isInteger(current.plan.limit) || current.plan.limit < 1 || current.plan.limit > 20) {
      errorText(new Error("每路最大结果数须为 1 至 20。"));
      return;
    }
    const start = current.plan.date_from || current.dateWindow.start;
    const end = current.plan.date_to || current.dateWindow.end;
    if ((start && current.dateWindow.start && start < current.dateWindow.start) ||
        (end && current.dateWindow.end && end > current.dateWindow.end) || (start && end && start > end)) {
      errorText(new Error("查询日期须在冻结范围的时间窗内。"));
      return;
    }
    const data = {
      ...current.plan, request_key: crypto.randomUUID(), source_ids: sources,
      ...Object.fromEntries(limits.map(([key]) => [key, Number(input.get(key))])),
      budgets: Object.fromEntries(Object.keys(budgetUnits).map(unit => [unit, Number(input.get(unit))])),
      fixture_scenario: input.get("fixture_scenario"), fallback_format: input.get("fallback_format") || "none",
    };
    const revision = previewRevision;
    perform("正在核对合成任务配置…", () => post(route() + "/preview", data), ({ config }) => {
      if (revision !== previewRevision) return;
      preview = data;
      get("preview").innerHTML = `<section class="acquisition-section"><h3 id="acquisition-task-preview-heading" tabindex="-1">
        合成任务预览</h3>${configPairs(config, current.projectName)}${queryPreview(config.query_plan.queries)}</section>`;
      get("preview").hidden = false;
      get("preview-heading").focus();
    });
  });

  root.addEventListener("click", event => {
    const button = event.target.closest("button[data-task-action]");
    if (!button || busy) return;
    const name = button.dataset.taskAction;
    if (name === "create" && preview) {
      perform("正在保存合成任务…", () => post(route(), preview), task => {
        invalidatePreview();
        showTask(task);
      });
    }
    if (name === "open") perform("正在读取任务详情…", () => api(detailRoute(button.dataset.taskId)), task => renderDetail(task, true));
    if (name === "refresh") refresh();
    if (name === "evidence" && activeTask) {
      const result = button.parentElement.querySelector("[data-evidence-result]");
      result.replaceChildren();
      perform("正在核验原文许可和区间…",
        () => api(detailRoute(activeTask.acquisition_task_id) + "/evidence/" + button.dataset.evidenceIndex),
        item => {
          result.innerHTML = pairs([
            ["合成原话", item.text], ["工程资格", item.engineering_eligible],
            ["正式研究资格", item.research_eligible], ["外发许可", item.outbound_allowed],
          ]);
          button.disabled = false;
          button.focus();
        }
      );
    }
    if (Object.hasOwn(actionLabels, name) && activeTask) {
      const id = activeTask.acquisition_task_id;
      if (name === "step" && !stepKeys.has(id)) stepKeys.set(id, crypto.randomUUID());
      const payload = name === "step" ? { request_key: stepKeys.get(id) } : undefined;
      perform("正在处理任务检查点…", () => post(detailRoute(id) + "/" + name, payload), task => {
        if (name === "step") stepKeys.delete(id);
        showTask(task);
      });
    }
  });
  return { setStudy, invalidatePreview };
}
