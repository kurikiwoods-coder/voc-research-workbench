import { mountRegistryDrafts } from "./registry-drafts.js";

const lifecycle = {
  candidate: "候选待审", pending_parent: "候选缺主任务", confirmed: "已确认",
  rejected: "已驳回", retired: "已停用", merged: "已合并",
};
const survey = { unvalidated: "未验证", validating: "验证中", validated: "已验证", failed: "验证失败" };
const changes = { added: "新增", modified: "修改", retired: "停用", removed: "移除", merged: "合并",
  split: "拆分", unchanged: "无变更" };
const fields = {
  name: "名称", definition: "定义", inclusion_criteria: "纳入标准", exclusion_criteria: "排除标准",
  primary_category_id: "主任务大类", secondary_category_ids: "次任务大类",
  lifecycle_status: "生命周期", survey_validation_status: "问卷验证状态",
  approved_shared_examples: "获准共享示例", version: "定义版本",
};

function registryQuery(path, query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== "" && value != null) params.set(key, value);
  }
  return params.size ? `${path}?${params}` : path;
}

export function mountRegistry(root, _route, { api, esc }) {
  const escapeOption = ([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`;
  const btn = (action, text) => `<button class="btn" type="button" data-registry-action="${action}">${text}</button>`;
  const status = text => `<p class="state-box" role="status">${esc(text)}</p>`;
  const failure = (error, retry) => `<p role="alert">${esc(error.message)}</p>${btn(retry, "重试")}`;
  const list = rows => `<ul class="relation-list">${rows.map(row => `<li>${row}</li>`).join("")}</ul>`;
  const valueOf = value => Array.isArray(value) ? value.map(item =>
    typeof item === "object" ? JSON.stringify(item) : item).join("、") : value;
  const fieldValue = (field, value) => esc(
    (field === "lifecycle_status" ? lifecycle[value] : field === "survey_validation_status" ? survey[value] : null)
    || valueOf(value) || "—"
  );
  const changeFields = diff => diff.length ? `<dl class="registry-pairs">${diff.map(({ field, before, after }) =>
    `<div><dt>${esc(fields[field] || field)}</dt><dd>${fieldValue(field, before)} → ${fieldValue(field, after)}</dd></div>`
  ).join("")}</dl>` : "";
  const lineage = rows => rows.map(edge =>
    `<p>${esc(changes[edge.action] || ({ merge: "合并", split: "拆分", retire: "停用" })[edge.action] || edge.action)}
    ${esc(edge.from_id || "—")} → ${esc(edge.to_id || "—")} · ${esc(edge.registry_version)}</p>`
  ).join("");
  const taskSummary = item => {
    const tasks = item.task_categories || [];
    const primary = tasks.find(task => task.role === "primary")?.name || "待确认";
    const secondary = tasks.filter(task => task.role === "secondary").map(task => task.name).join("、") || "无";
    return `<p>主任务大类 ${esc(primary)} · 次任务大类 ${esc(secondary)}</p>`;
  };

  root.innerHTML = `<header class="page-head"><div><h1>意图注册表</h1>
      <p id="registry-current" role="status">正在读取当前版本…</p></div></header>
    <section class="panel relation-panel" aria-labelledby="registry-browse-title">
      <h2 id="registry-browse-title">意图知识库</h2>
      <form id="registry-search">
        <div class="relation-filters">
          <label>注册表版本<select class="field" aria-label="注册表版本" name="registry_version" disabled></select></label>
          <label>搜索意图<input class="field" type="search" name="q" maxlength="120" placeholder="名称、定义或意图 ID"></label>
          <label>生命周期<select class="field" aria-label="生命周期" name="lifecycle_status"><option value="">全部</option>${Object.entries(lifecycle).map(escapeOption).join("")}</select></label>
          <label>主任务大类<select class="field" aria-label="主任务大类" name="primary_category_id"><option value="">全部</option></select></label>
          <label>问卷验证状态<select class="field" aria-label="问卷验证状态" name="survey_validation_status"><option value="">全部</option>${Object.entries(survey).map(escapeOption).join("")}</select></label>
        </div>
        <div class="actions registry-actions"><button class="btn primary" type="submit">查询意图</button>${btn("versions", "刷新版本")}</div>
      </form>
      <div id="registry-items" aria-live="polite"></div>
      <div class="actions registry-actions" id="registry-pages"></div>
      <section id="registry-detail" class="registry-subsection" tabindex="-1" aria-live="polite" hidden></section>
    </section>
    <details class="panel relation-panel" id="registry-comparison">
      <summary>历史版本与差异</summary>
      <div id="registry-versions"></div>
      <form id="registry-compare">
        <div class="relation-filters">
          <label>起始版本<select class="field" aria-label="起始版本" name="from_version" required></select></label>
          <label>对比版本<select class="field" aria-label="对比版本" name="to_version" required></select></label>
        </div>
        <div class="actions registry-actions"><button class="btn primary" type="submit">比较版本</button></div>
      </form>
      <div id="registry-diff" aria-live="polite"></div>
      <div class="actions registry-actions" id="registry-diff-pages"></div>
    </details>
    <section class="panel relation-panel" id="registry-drafts" aria-labelledby="registry-draft-title"></section>`;

  const get = id => root.querySelector(`#registry-${id}`);
  const search = get("search");
  const compare = get("compare");
  const versionSelect = search.elements.registry_version;
  const primarySelect = search.elements.primary_category_id;
  const current = get("current");
  const catalog = get("items");
  const detail = get("detail");
  const diff = get("diff");
  let versions = [];
  let currentVersion;
  let catalogQuery = {};
  let diffQuery = {};
  let selectedIntent;
  let catalogOffset = 0;
  let diffOffset = 0;
  let catalogSequence = 0;
  let detailSequence = 0;
  let diffSequence = 0;
  let versionSequence = 0;
  let taskSequence = 0;

  const drafts = mountRegistryDrafts(get("drafts"), { api, esc, registryQuery, getCurrent: () => currentVersion });

  function filterData() {
    return Object.fromEntries(new FormData(search));
  }

  function paging(view, offset, next, pageName) {
    view.innerHTML = `${offset ? btn(`${pageName}-prev`, "上一页") : ""}${next != null ? btn(`${pageName}-next`, "下一页") : ""}`;
  }

  function dismissDetail() {
    detailSequence += 1;
    selectedIntent = null;
    detail.replaceChildren();
    detail.hidden = true;
  }

  async function loadCatalog(offset = 0) {
    const sequence = ++catalogSequence;
    catalogOffset = offset;
    dismissDetail();
    get("pages").replaceChildren();
    if (!catalogQuery.registry_version) {
      catalog.innerHTML = status("暂无已封版的注册表。");
      return;
    }
    catalog.innerHTML = status("正在读取意图…");
    try {
      const page = await api(registryQuery("/api/registry/intents", { ...catalogQuery, offset, limit: 25 }));
      if (!root.isConnected || sequence !== catalogSequence) return;
      catalog.innerHTML = page.items.length ? list(page.items.map(item =>
        `<h3><button class="btn" type="button" data-registry-intent="${esc(item.intent_id)}">${esc(item.name)}</button></h3>
        <p>${esc(item.intent_id)} · ${esc(lifecycle[item.lifecycle_status])} · ${esc(survey[item.survey_validation_status])}
        · ${esc(item.registry_version)}</p>${taskSummary(item)}
        ${item.recent_change ? `<p>最近变更 ${esc(item.recent_change.registry_version)} · ${esc(item.recent_change.created_at)}</p>` : ""}`
      )) : status("没有符合条件的意图。");
      paging(get("pages"), offset, page.next_offset, "catalog");
    } catch (error) {
      if (root.isConnected && sequence === catalogSequence) catalog.innerHTML = failure(error, "catalog-retry");
    }
  }

  async function loadTasks(version) {
    const items = [];
    let cursor;
    if (!version) return items;
    do {
      const page = await api(registryQuery("/api/categories", { registry_version: version, limit: 100, cursor }));
      items.push(...page.items);
      cursor = page.next_cursor;
    } while (cursor && root.isConnected);
    return items;
  }

  async function selectVersion() {
    const version = versionSelect.value;
    const sequence = ++taskSequence;
    catalogQuery = { ...filterData(), primary_category_id: "" };
    primarySelect.innerHTML = '<option value="">全部</option>';
    current.textContent = currentVersion
      ? `当前版本 ${currentVersion}${version !== currentVersion ? ` · 历史只读 ${version}` : ""}`
      : "暂无已封版的注册表";
    loadCatalog();
    try {
      const tasks = await loadTasks(version);
      if (!root.isConnected || sequence !== taskSequence) return;
      primarySelect.insertAdjacentHTML("beforeend", tasks.map(({ category_id: id, name }) => escapeOption([id, name])).join(""));
    } catch (error) {
      if (root.isConnected && sequence === taskSequence) {
        current.textContent += ` · 任务筛选暂不可用。${error.message}`;
      }
    }
  }

  async function loadVersions() {
    const sequence = ++versionSequence;
    const previous = versionSelect.value;
    current.textContent = "正在读取当前版本…";
    try {
      let offset = 0;
      let version;
      const items = [];
      do {
        const page = await api(registryQuery("/api/registry/versions", { limit: 100, offset }));
        if (!root.isConnected || sequence !== versionSequence) return;
        if (!items.length) version = page.current_registry_version;
        if (page.current_registry_version !== version) throw new Error("读取期间版本已变化，请刷新版本。");
        items.push(...page.items);
        offset = page.next_offset;
      } while (offset != null);
      versions = items;
      currentVersion = version;
      const options = versions.map(item => escapeOption([item.registry_version, item.registry_version])).join("");
      versionSelect.innerHTML = options;
      versionSelect.disabled = !versions.length;
      if (versions.some(item => item.registry_version === previous)) versionSelect.value = previous;
      compare.elements.from_version.innerHTML = options;
      compare.elements.to_version.innerHTML = options;
      if (versions.length > 1) compare.elements.from_version.value = versions[1].registry_version;
      compare.querySelector("button").disabled = !versions.length;
      get("versions").innerHTML = versions.length ? list(versions.map(item =>
        `<h3>${esc(item.registry_version)}${item.registry_version === currentVersion ? " · 当前版本" : ""}</h3>
        <p><time>${esc(item.created_at)}</time> · ${item.parent_version ? `前序 ${esc(item.parent_version)}` : "初始版本"}</p>`
      )) : status("暂无历史版本。");
      selectVersion();
    } catch (error) {
      if (root.isConnected && sequence === versionSequence) current.textContent = error.message;
    }
  }

  async function showIntent(id) {
    const sequence = ++detailSequence;
    const version = catalogQuery.registry_version;
    detail.hidden = false;
    detail.innerHTML = status("正在读取意图定义…");
    detail.focus();
    try {
      const item = await api(registryQuery(`/api/registry/intents/${encodeURIComponent(id)}`, { registry_version: version }));
      if (!root.isConnected || sequence !== detailSequence) return;
      selectedIntent = item;
      const definitions = ["definition", "inclusion_criteria", "exclusion_criteria"].map(field =>
        `<dt>${fields[field]}</dt><dd>${esc(item[field] || "待补充")}</dd>`).join("");
      const recent = item.change_log.map(change =>
        `<h4>${esc(change.registry_version)} · ${esc(changes[change.status])}</h4><p>${esc(change.created_at)}</p>${changeFields(change.changes)}`
      );
      detail.innerHTML = `<h3>${esc(item.name)}</h3><p>${esc(item.intent_id)} · 定义版本 ${esc(item.version)}</p>
        ${taskSummary(item)}<dl class="registry-definition">${definitions}</dl>
        <h4>获准共享示例</h4>${item.approved_shared_examples?.length
          ? list(item.approved_shared_examples.map(example =>
            `<p>${example.kind === "positive" ? "正例" : "反例"} · ${esc(example.text)}</p>`
          )) : "<p>暂无获准共享示例。</p>"}
        <h4>历史变更</h4>${recent.length ? list(recent) : "<p>暂无历史变更。</p>"}
        <h4>合并及拆分谱系</h4>${lineage(item.lineage) || "<p>暂无谱系记录。</p>"}
        <div class="actions registry-actions">${version === currentVersion
          ? `${btn("amend", "起草修订")}${btn("merge", "起草合并")}${btn("split", "起草拆分")}${btn("retire", "起草停用")}`
          : btn("restore", "从历史版本起草")}</div>`;
    } catch (error) {
      if (root.isConnected && sequence === detailSequence) {
        detail.innerHTML = `<p role="alert">${esc(error.message)}</p><button type="button" class="btn" data-registry-intent="${esc(id)}">重试</button>`;
      }
    }
  }

  async function loadDiff(offset = 0) {
    const sequence = ++diffSequence;
    diffOffset = offset;
    diff.innerHTML = status("正在比较版本…");
    get("diff-pages").replaceChildren();
    try {
      const page = await api(registryQuery("/api/registry/diff", { ...diffQuery, offset, limit: 25 }));
      if (!root.isConnected || sequence !== diffSequence) return;
      diff.innerHTML = page.items.length ? list(page.items.map(item =>
        `<h3>${esc(item.intent_id)} · ${esc(changes[item.status] || item.status)}</h3>${changeFields(item.changes)}${lineage(item.lineage)}`
      )) : status("这两个版本没有意图记录。");
      paging(get("diff-pages"), offset, page.next_offset, "diff");
    } catch (error) {
      if (root.isConnected && sequence === diffSequence) diff.innerHTML = failure(error, "diff-retry");
    }
  }

  compare.querySelector("button").disabled = true;
  search.addEventListener("submit", event => {
    event.preventDefault();
    catalogQuery = filterData();
    loadCatalog();
  });
  versionSelect.addEventListener("change", selectVersion);
  compare.addEventListener("submit", event => {
    event.preventDefault();
    diffQuery = Object.fromEntries(new FormData(compare));
    loadDiff();
  });
  root.addEventListener("click", event => {
    const intent = event.target.closest("[data-registry-intent]");
    if (intent) {
      showIntent(intent.dataset.registryIntent);
      return;
    }
    const action = event.target.closest("[data-registry-action]")?.dataset.registryAction;
    if (action === "versions") loadVersions();
    if (action === "catalog-prev") loadCatalog(catalogOffset - 25);
    if (action === "catalog-next") loadCatalog(catalogOffset + 25);
    if (action === "catalog-retry") loadCatalog(catalogOffset);
    if (action === "diff-prev") loadDiff(diffOffset - 25);
    if (action === "diff-next") loadDiff(diffOffset + 25);
    if (action === "diff-retry") loadDiff(diffOffset);
    if (selectedIntent && ["amend", "merge", "split", "retire", "restore"].includes(action)) {
      drafts.prepare(action, selectedIntent, catalogQuery.registry_version);
    }
  });

  loadVersions();
}
