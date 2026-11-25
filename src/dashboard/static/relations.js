import { denominatorPage } from "./denominators.js";

const paths = { products: "product-categories", tasks: "categories", intents: "intents" };
const directions = {
  "product-intent": "产品品类 → 意图",
  "intent-product": "意图 → 产品品类",
  "task-intent": "任务大类 → 意图",
  "intent-task": "意图 → 任务大类",
};
const modes = { engineering: "工程查看", synthetic: "合成演练", formal: "正式研究" };
const statuses = {
  candidate: "候选待审", pending_parent: "候选缺主任务", confirmed: "已确认",
  rejected: "已驳回", merged: "已合并", retired: "已停用",
};
const reasonLabels = {
  G1_BLOCKED: "G-1 尚未通过",
  RESEARCH_NOT_ADMITTED: "当前项目尚未准入正式研究",
  M12_RECEIPTS_MISSING: "缺少真实编码回执",
  SCOPE_MAPPING_UNRESOLVED: "冻结范围的产品映射未解析",
  REGISTRY_UNAVAILABLE: "暂无已封版的注册表",
  SEGMENT_REVISION_UNAVAILABLE: "暂无可用片段版",
  CATALOG_VERSION_UNAVAILABLE: "指定的产品目录版本不可用",
};
const enc = encodeURIComponent;
const apiPath = (...parts) => "/api/" + parts.map(enc).join("/");
const scopeKey = scope => JSON.stringify([scope.scope_id, scope.scope_version, scope.mapping_revision, scope.catalog_version]);

function withQuery(path, fields) {
  const params = new URLSearchParams();
  for (const [key, values] of Object.entries(fields)) {
    for (const value of Array.isArray(values) ? values : [values]) {
      if (value) params.append(key, value);
    }
  }
  return params.size ? path + "?" + params : path;
}

export function mountRelations(root, _route, { api, esc }) {
  const selected = { study: "", scope: "", version: "", revision: "", mode: "engineering",
    direction: "product-intent", product: "", task: "", intent: "",
    source: "", batch: "", timeField: "published_at", from: "", to: "", confidence: "", index: "" };
  const denominatorSets = { product: [], task: [], intent: [] };
  let denominatorOpened = false;
  let currentView = "relations";
  let sequence = 0;
  let evidenceSequence = 0;
  let next = null;
  let requestForPage = null;
  let projects = [];
  let mappings = [];
  let definitions = { products: [], tasks: [], intents: [] };
  let visibleRefs = [];
  let trigger = null;

  root.innerHTML = `<header class="page-head relation-head"><div><h1>三层关系</h1></div></header>
    <div class="actions relation-views" role="group" aria-label="三层关系页面">
      <button type="button" class="btn" data-relation-view="relations" aria-pressed="true">关系查看</button>
      <button type="button" class="btn" data-relation-view="denominators" aria-pressed="false">分母对账</button>
    </div>
    <section class="panel relation-panel" aria-label="关系筛选"><div class="relation-filters"></div>
      <div class="actions"><button type="button" class="btn" data-relation-action="refresh">重新查询</button></div></section>
    <section class="panel relation-panel" aria-labelledby="relation-results-title">
      <h2 id="relation-results-title">关系结果</h2><div class="relation-results" aria-live="polite"></div>
      <div class="actions"><button type="button" class="btn" hidden data-relation-action="next">下一页</button></div></section>
    <dialog class="relation-drawer" aria-labelledby="relation-evidence-title">
      <header><h2 id="relation-evidence-title">原话证据</h2>
        <button type="button" class="btn" data-relation-action="close">返回关系</button></header>
      <div class="relation-evidence" aria-live="polite"></div></dialog>`;
  const fields = root.querySelector(".relation-filters");
  const results = root.querySelector(".relation-results");
  const dialog = root.querySelector(".relation-drawer");
  const evidenceView = root.querySelector(".relation-evidence");
  const nextButton = root.querySelector('[data-relation-action="next"]');
  const resultsTitle = root.querySelector("#relation-results-title");
  const closeButton = root.querySelector('[data-relation-action="close"]');

  function options(items, value, placeholder) {
    const pairs = placeholder === null ? items : [["", placeholder], ...items];
    const current = Array.isArray(value) ? value : [value];
    return pairs.map(([id, label]) =>
      `<option value="${esc(id)}" ${current.includes(id) ? "selected" : ""}>${esc(label)}</option>`).join("");
  }

  function filters() {
    const controls = [
      ["study", "研究项目", projects.map(item => [item.study_id, item.name]), "请选择有权访问的项目"],
      ["scope", "冻结研究范围", mappings.map(item => [scopeKey(item),
        [item.scope_version, item.mapping_revision && "映射版 " + item.mapping_revision,
          item.catalog_version && "目录 " + item.catalog_version, item.scope_id].filter(Boolean).join(" · ")]), "全部可见范围"],
      ["product", "产品品类", definitions.products.map(item => [item.product_category_id, `${item.name} · ${item.product_category_id}`]), "全部产品品类"],
      ["task", "任务大类", definitions.tasks.map(item => [item.category_id, item.name]), "全部任务大类"],
      ["intent", "用户意图", definitions.intents.map(item => [item.intent_id, item.name]), "全部用户意图"],
      ["mode", "查询模式", Object.entries(modes), null],
    ];
    if (currentView === "relations") controls.splice(2, 0, ["direction", "关系方向", Object.entries(directions), null]);
    else controls.push(["timeField", "时间依据", [["published_at", "发布时间"], ["collected_at", "采集时间"]], null]);
    const focused = document.activeElement?.dataset.relationFilter;
    fields.innerHTML = controls.map(([name, label, items, placeholder]) => {
      const multi = currentView === "denominators" && Object.hasOwn(denominatorSets, name);
      return `<div class="relation-control"><label for="relation-filter-${name}">${label}</label>
        <select id="relation-filter-${name}" class="field" data-relation-filter="${name}"
          ${multi ? 'multiple size="3" aria-describedby="denominator-multiselect-help"' : ""}>
          ${options(items, multi ? denominatorSets[name] : selected[name], multi ? null : placeholder)}</select></div>`;
    }).join("") +
      `<label>注册表版本<input class="field" data-relation-filter="version" value="${esc(selected.version)}" placeholder="当前封版"></label>
       <label>片段版本<input class="field" type="number" min="1" step="1" data-relation-filter="revision"
        value="${esc(selected.revision)}" placeholder="当前封版"></label>`;
    if (currentView === "denominators") {
      fields.insertAdjacentHTML("afterbegin",
        '<p id="denominator-multiselect-help" class="relation-meta">产品品类、任务大类和用户意图可多选，未选时查询全部。</p>');
      const inputs = [
        ["source", "来源", "text", "多个来源可用逗号分隔"],
        ["batch", "批次 ID", "text", "多个批次可用逗号分隔"],
        ["from", "起始日（UTC，含）", "date", ""],
        ["to", "截止日（UTC，不含）", "date", ""],
        ["confidence", "置信度", "text", "多个置信度可用逗号分隔"],
        ["index", "编码索引版本", "text", ""],
      ];
      fields.insertAdjacentHTML("beforeend", inputs.map(([name, title, type, hint]) =>
        `<label>${title}<input class="field" type="${type}" data-relation-filter="${name}"
          value="${esc(selected[name])}"${hint ? ` placeholder="${hint}"` : ""}></label>`).join(""));
    }
    if (focused) fields.querySelector(`[data-relation-filter="${focused}"]`)?.focus({ preventScroll: true });
  }

  function status(text, retry = false) {
    results.innerHTML = `<p class="state-box">${esc(text)}</p>` +
      (retry ? '<button type="button" class="btn" data-relation-action="refresh">重试</button>' : "");
  }

  function clearEvidence(restore = false) {
    evidenceSequence += 1;
    evidenceView.replaceChildren();
    if (dialog.open) dialog.close();
    if (restore && trigger?.isConnected) trigger.focus();
    trigger = null;
  }

  dialog.addEventListener("cancel", event => {
    event.preventDefault();
    clearEvidence(true);
  });
  const detached = cleanupSignal(root, clearEvidence);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && root.isConnected) clearEvidence();
  }, { signal: detached });
  window.addEventListener("pagehide", () => clearEvidence(), { signal: detached });

  function nameOf(group, key, id) {
    return definitions[group].find(item => item[key] === id)?.name || id;
  }

  function taskNames(ids, primary) {
    const secondaries = (ids || []).filter(id => id !== primary);
    return `<p>主任务 <strong>${primary ? esc(nameOf("tasks", "category_id", primary)) : "缺主任务"}</strong></p>
      ${secondaries.length ? '<p>次任务 ' + secondaries.map(id => esc(nameOf("tasks", "category_id", id))).join("、") + "</p>" : ""}`;
  }

  function entry(title, body, refs = []) {
    const evidence = refs.map(ref => {
      const index = visibleRefs.push(ref) - 1;
      return `<button type="button" class="btn" data-relation-action="evidence" data-index="${index}">查看证据 ${index + 1}</button>`;
    }).join("");
    return `<li><h3>${esc(title)}</h3>${body}${evidence ? '<div class="actions">' + evidence + "</div>" : ""}</li>`;
  }

  function productIntentRow(row) {
    if (row.intent_id) {
      return entry(row.intent_name || row.intent_id, taskNames(row.category_ids, row.primary_category_id) +
        `<p>可核片段 ${esc(row.distinct_mention_n)}</p>`, row.evidence_refs);
    }
    return entry(row.product_name || row.product_category_id,
      `<p>${esc(row.product_category_id)} · 目录 ${esc(row.catalog_version)}</p>
       <p>可核片段 ${esc(row.distinct_mention_n)}</p>`, row.evidence_refs);
  }

  function mentionRows(items) {
    const groups = new Map();
    for (const mention of items) {
      for (const edge of mention.product_intent_edges || []) {
        const key = JSON.stringify([edge.product_category_id, edge.catalog_version, edge.intent_id]);
        if (!groups.has(key)) {
          const intent = mention.intents.find(item => item.intent_id === edge.intent_id);
          groups.set(key, { edge, intent, refs: [], mentions: new Set() });
        }
        const group = groups.get(key);
        group.mentions.add(mention.mention_id);
        group.refs.push(edge);
      }
    }
    return Array.from(groups.values(), ({ edge, intent, refs, mentions }) => {
      const product = edge.product_name || nameOf("products", "product_category_id", edge.product_category_id);
      const intentName = intent.intent_name || intent.intent_id;
      const title = selected.direction === "intent-product" ? intentName + " → " + product : product + " → " + intentName;
      return entry(title, taskNames(intent.category_ids, intent.primary_category_id) +
        "<p>" + esc(edge.product_category_id) + " · 目录 " + esc(edge.catalog_version) +
        " · 本页可核片段 " + esc(mentions.size) + "</p>", refs);
    }).join("");
  }

  function taskRows(items) {
    return items.map(row => entry(selected.direction === "task-intent" ? row.intent_name : row.category_name,
        `<p>${row.role === "primary" ? "主任务" : "次任务"} · ${esc(statuses[row.lifecycle_status])}</p>`)).join("");
  }

  function definitionRows() {
    const isIntent = selected.direction === "intent-task";
    const rows = isIntent ? definitions.intents : definitions.tasks;
    return rows.map(row => {
      const action = isIntent ? "choose-intent" : "choose-task";
      const id = isIntent ? row.intent_id : row.category_id;
      return entry(row.name, (isIntent ? taskNames(row.category_ids, row.primary_category_id) : "") +
        `<p>${esc(statuses[row.lifecycle_status])}</p><button type="button" class="btn"
        data-relation-action="${action}" data-id="${esc(id)}">查看关联</button>`);
    }).join("");
  }

  async function definitionList(resource, version) {
    const fields = { registry_version: version, limit: 100 };
    const items = [];
    let cursor;
    do {
      const page = await api(withQuery(apiPath(resource), { ...fields, cursor }));
      items.push(...page.items);
      fields.registry_version = page.resolved_versions.registry_version;
      cursor = page.next_cursor;
    } while (cursor);
    return { items, version: fields.registry_version || "" };
  }

  function projectQuery() {
    const scope = mappings.find(item => scopeKey(item) === selected.scope);
    const options = { registry_version: selected.version, segment_revision: selected.revision, mode: selected.mode,
      scope_id: scope?.scope_id, scope_version: scope?.scope_version, mapping_revision: scope?.mapping_revision,
      catalog_version: scope?.catalog_version, category_id: selected.task, intent_id: selected.intent,
      product_category_id: selected.product };
    if (currentView === "denominators") {
      const selectedValues = text => text.split(/[,，]/).map(value => value.trim()).filter(Boolean);
      return { path: apiPath("studies", selected.study, "denominators"), renderer: "denominators",
        options: { ...options, source: selectedValues(selected.source), batch_id: selectedValues(selected.batch),
          time_field: selected.timeField, from: selected.from, to: selected.to,
          confidence_band: selectedValues(selected.confidence), index_version: selected.index,
          product_category_id: denominatorSets.product, category_id: denominatorSets.task,
          intent_id: denominatorSets.intent } };
    }
    if (selected.direction === "product-intent" && selected.product) {
      return { path: apiPath(paths.products, selected.product, "intents"), options: { ...options, study_id: selected.study }, renderer: "product" };
    }
    if (selected.direction === "intent-product" && selected.intent) {
      return { path: apiPath(paths.intents, selected.intent, "product-categories"), options: { ...options, study_id: selected.study }, renderer: "product" };
    }
    return { path: apiPath("studies", selected.study, "mentions"), options, renderer: "mentions" };
  }

  function paint(page, renderer) {
    if (renderer === "denominators") {
      results.innerHTML = denominatorPage(page, {
        esc, project: projects.find(project => project.study_id === selected.study)?.name || selected.study,
        category: id => nameOf("tasks", "category_id", id),
        evidence: (title, ref) => entry(title, "", [ref]),
      });
      return true;
    }
    const versions = page.resolved_versions || {};
    const reasons = [...(page.reasons || [])];
    if (renderer === "mentions" && page.availability === "available") {
      if (!versions.registry_version) reasons.push("REGISTRY_UNAVAILABLE");
      if (versions.scope_mappings?.some(scope => scope.mapping_status === "unresolved")) {
        reasons.push("SCOPE_MAPPING_UNRESOLVED");
      }
    }
    if (page.availability === "unavailable" || reasons.length) {
      status(reasons.map(reason => reasonLabels[reason] || "当前版本缺少可核数据").join(" · ") || "当前关系不可用。");
      return false;
    }
    const rows = { product: () => page.items.map(productIntentRow).join(""), mentions: () => mentionRows(page.items),
      task: () => taskRows(page.items), definitions: definitionRows }[renderer]();
    const matchScope = mappings.find(item => scopeKey(item) === selected.scope);
    const versionLine = [versions.registry_version && "注册表 " + versions.registry_version,
      versions.segment_revision && "片段版 " + versions.segment_revision,
      matchScope?.mapping_revision && "映射版 " + matchScope.mapping_revision,
      matchScope?.catalog_version && "目录 " + matchScope.catalog_version].filter(Boolean).join(" · ");
    results.innerHTML = (versionLine ? `<p class="relation-meta">${esc(versionLine)}</p>` : "") +
      (rows ? '<ul class="relation-list">' + rows + "</ul>" : '<p class="state-box">暂无符合条件的关系。</p>');
    return true;
  }

  async function load({ cursor = null, preserveNotice = null } = {}) {
    const id = ++sequence;
    clearEvidence();
    visibleRefs = [];
    next = null;
    nextButton.hidden = true;
    status(currentView === "denominators" ? "正在核对统计分母…" : "正在核对关系…");
    try {
      if (!cursor) {
        const [list, projectList] = await Promise.all([
          definitionList(paths.products, selected.version), api(apiPath("studies", "relations", "projects")),
        ]);
        if (!root.isConnected || id !== sequence) return;
        selected.version = list.version;
        const [taskList, intentList] = await Promise.all([
          definitionList(paths.tasks, selected.version), definitionList(paths.intents, selected.version),
        ]);
        if (!root.isConnected || id !== sequence) return;
        definitions = { products: list.items, tasks: taskList.items, intents: intentList.items };
        projects = projectList.items;
        if (!selected.study) selected.study = projectList.current_study_id || projects[0]?.study_id || "";
        const global = currentView === "relations" && ["task-intent", "intent-task"].includes(selected.direction);
        if (global) {
          const taskFirst = selected.direction === "task-intent";
          const key = taskFirst ? selected.task : selected.intent;
          requestForPage = key
            ? { path: taskFirst ? apiPath(paths.tasks, key, "intents") : apiPath(paths.intents, key, "categories"),
                options: { registry_version: selected.version, category_id: selected.task, intent_id: selected.intent },
                renderer: "task" }
            : null;
          filters();
          if (selected.mode === "formal") {
            status("G-1 尚未通过，正式研究关系不可用。");
            return;
          }
          if (!requestForPage) {
            paint({ items: [], resolved_versions: { registry_version: selected.version } }, "definitions");
            return;
          }
        } else {
          if (!selected.study || !projects.some(project => project.study_id === selected.study)) {
            selected.scope = "";
            mappings = [];
            filters();
            const missing = currentView === "denominators" ? "暂无获准查询统计的项目。" : "暂无获准查询关系证据的项目。";
            status([preserveNotice, missing].filter(Boolean).join(" "));
            return;
          }
          requestForPage = projectQuery();
        }
      }
      const request = requestForPage;
      const page = await api(withQuery(request.path, { ...request.options, cursor }));
      if (!root.isConnected || id !== sequence) return;
      if (request.renderer !== "task") {
        if (!selected.scope && page.resolved_versions.scope_mappings) {
          mappings = page.resolved_versions.scope_mappings;
        }
        selected.revision = page.resolved_versions.segment_revision || selected.revision;
      }
      filters();
      const available = paint(page, request.renderer);
      if (preserveNotice) results.insertAdjacentHTML("afterbegin", `<p role="status">${esc(preserveNotice)}</p>`);
      next = available && request.renderer !== "denominators" ? page.next_cursor : null;
      nextButton.hidden = !next;
    } catch (error) {
      if (!root.isConnected || id !== sequence) return;
      if (error.status === 409 && cursor) {
        load({ preserveNotice: "关系版本或资格已变化，已从第一页重新核验。" });
        return;
      }
      if (error.status === 403 || error.status === 404) {
        selected.scope = "";
        mappings = [];
      }
      filters();
      status(error.message, true);
    }
  }

  async function openEvidence(index, button) {
    const ref = visibleRefs[index];
    if (!ref) return;
    clearEvidence();
    const id = evidenceSequence;
    trigger = button;
    evidenceView.innerHTML = '<p role="status">正在核验原话资格…</p>';
    dialog.showModal();
    try {
      const path = apiPath("studies", selected.study, "mentions", ref.mention_id, "evidence", ref.evidence_id);
      const evidence = await api(withQuery(path, { segment_revision: ref.segment_revision || selected.revision }));
      if (!root.isConnected || id !== evidenceSequence || !dialog.open) return;
      const batch = "#corpus/" + enc(selected.study) + "/batches/" + enc(evidence.batch_id);
      const record = "#corpus/" + enc(selected.study) + "/records/" + enc(evidence.record_id);
      const scope = "#studies/" + enc(selected.study) + "/scopes/" + enc(evidence.scope_id);
      evidenceView.innerHTML = `<blockquote>${esc(evidence.excerpt)}</blockquote><dl>
        <dt>原始来源</dt><dd>${esc(evidence.source_url || "暂无可展示的来源地址")}</dd>
        <dt>原始记录</dt><dd><a href="${record}">查看第 ${esc(evidence.line_number)} 行</a></dd>
        <dt>导入批次</dt><dd><a href="${batch}">查看语料批次</a> · ${esc(evidence.batch_id)}</dd>
        <dt>冻结范围</dt><dd><a href="${scope}">${esc(evidence.scope_version)}</a></dd>
        <dt>片段版本</dt><dd>${esc(evidence.segment_revision || evidence.revision)}</dd>
        <dt>许可状态</dt><dd>${evidence.license_status === "authorized" ? "已授权" : esc(evidence.license_status)}</dd>
        <dt>原文码点区间</dt><dd>${esc(evidence.start_cp)}–${esc(evidence.end_cp)}</dd></dl>`;
    } catch (error) {
      if (!root.isConnected || id !== evidenceSequence || !dialog.open) return;
      const invalid = error.status === 409 || error.status === 404 || error.status === 403;
      if (invalid) {
        clearEvidence(true);
        const target = currentView === "denominators" ? "统计" : "关系";
        load({ preserveNotice: `原话已失格或当前访问受限，已重新核验${target}。` });
      } else {
        evidenceView.innerHTML = `<p role="alert">${esc(error.message)}</p>
          <button type="button" class="btn" data-relation-action="evidence" data-index="${index}">重试核验</button>`;
      }
    }
  }

  root.addEventListener("change", event => {
    const key = event.target.dataset.relationFilter;
    if (!key) return;
    if (event.target.multiple) {
      denominatorSets[key] = Array.from(event.target.selectedOptions, option => option.value);
    } else {
      selected[key] = event.target.value;
    }
    if (key === "study" || key === "revision" || key === "version") {
      selected.scope = "";
      mappings = [];
    }
    if (key === "study" || key === "version") selected.revision = "";
    if (key === "version") {
      for (const field of Object.keys(denominatorSets)) {
        denominatorSets[field] = [];
        selected[field] = "";
      }
    }
    load();
  });
  root.addEventListener("click", event => {
    const view = event.target.closest("[data-relation-view]");
    if (view && view.dataset.relationView !== currentView) {
      currentView = view.dataset.relationView;
      if (currentView === "denominators" && !denominatorOpened) {
        for (const field of Object.keys(denominatorSets)) {
          if (selected[field]) denominatorSets[field] = [selected[field]];
        }
        denominatorOpened = true;
      }
      for (const control of root.querySelectorAll("[data-relation-view]")) {
        control.setAttribute("aria-pressed", String(control === view));
      }
      resultsTitle.textContent = currentView === "denominators" ? "分母对账" : "关系结果";
      closeButton.textContent = currentView === "denominators" ? "返回对账" : "返回关系";
      filters();
      load();
      return;
    }
    const button = event.target.closest("[data-relation-action]");
    if (!button) return;
    const action = button.dataset.relationAction;
    if (action === "close") clearEvidence(true);
    if (action === "evidence") openEvidence(Number(button.dataset.index), trigger || button);
    if (action === "next" && next) load({ cursor: next });
    if (action === "choose-intent" || action === "choose-task") {
      selected[action === "choose-intent" ? "intent" : "task"] = button.dataset.id;
      load();
    }
    if (action === "refresh") load();
  });
  filters();
  load();
}

function cleanupSignal(root, release) {
  const controller = new AbortController();
  const observer = new MutationObserver(() => {
    if (!root.isConnected) {
      release();
      controller.abort();
      observer.disconnect();
    }
  });
  observer.observe(root.parentNode, { childList: true });
  return controller.signal;
}
