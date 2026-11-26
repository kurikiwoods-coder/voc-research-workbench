"use strict";
const el = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const pages = {
  studies: ["研究项目", "folder"],
  acquisition: ["来源采集", "search"],
  imports: ["数据导入中心", "download"],
  corpus: ["原始语料库", "file"],
  relations: ["三层关系", "branch"],
  registry: ["意图注册表", "branch"],
  checks: ["连通性检查", "pulse"],
  matrix: ["验收矩阵", "grid"],
  history: ["运行记录", "clock"],
  tokens: ["额度中心", "meter"],
  setup: ["API 接入", "sliders"],
};
const researchViews = {
  studies: () => import("./studies.js").then(module => module.mountStudies),
  acquisition: () => import("./acquisition.js").then(module => module.mountAcquisition),
  imports: () => import("./imports.js").then(module => module.mountImports),
  corpus: () => import("./corpus.js").then(module => module.mountCorpus),
  relations: () => import("./relations.js").then(module => module.mountRelations),
  registry: () => import("./registry.js").then(module => module.mountRegistry),
};
function pageFromLocation() {
  const page = location.hash.slice(1);
  if (/^imports\/[a-f0-9-]{36}(?:\/batches\/[a-f0-9-]{36})?$/.test(page)) return "imports";
  if (/^studies\/(?:new|[a-f0-9-]{36}(?:\/(?:edit|scopes\/[a-f0-9-]{36}))?)$/.test(page)) return "studies";
  if (/^corpus\/[a-f0-9-]{36}(?:\/batches\/[a-f0-9-]{36}|\/records\/[a-f0-9-]{36}(?:%3A|:)[1-9][0-9]{0,6})?$/i.test(page)) return "corpus";
  return Object.hasOwn(pages, page) ? page : "checks";
}
const labels = {
  PASS: "通过",
  FAIL: "失败",
  BLOCKED: "阻塞",
  PENDING: "待条件满足",
  NOT_TESTED: "未测试",
};
const modes = {
  live_http: "真实 HTTP",
  archived_live_http: "归档真实 HTTP",
  archive_recovery: "归档恢复",
  configuration: "配置核验",
  local_sqlite: "SQLite 回读",
  contract_check: "契约校验",
  local_gate: "阶段判定",
  synthetic_fault_drill: "合成故障演练",
  synthetic_smoke: "合成召回测试",
  local_error: "本地异常",
};
const sources = {
  tavily: "Tavily 搜索",
  brave: "Brave 搜索",
  forum_search: "论坛公开检索",
  forum_post: "公开原话快照",
  source_archive_recovery: "同批来源恢复",
  source_contract: "发现与原话分项核验",
  jev_admission: "Jev 调用条件",
  jev_shard: "Jev 分片响应",
  schema_gap: "响应契约缺口",
  sqlite_readback: "SQLite 持久化",
  outbound_isolation: "外发隔离演练",
  global_recall: "跨品类向量召回",
  stage_gate: "阶段准入判定",
  probe_error: "执行异常",
};
const shardStates = {
  sending: "等待响应",
  received: "已收到响应",
  retryable: "待重试",
  uncertain: "待核对",
};
const detailLabels = [
  "固定 jev-1.14.0 · 11 道判断",
  "Choice / Score / Noul",
  "发现 URL · 许可原文",
  "SQLite · 分片用量",
  "外发闸门 · 故障演练",
  "全局 Top-K · 跨品类检索",
];
const paths = {
  folder: "M3 6h7l2 3h9v10H3z M7 13h10 M7 16h7",
  search: "M15 10a5 5 0 1 0-10 0 5 5 0 0 0 10 0z M14 14l5 5",
  pulse: "M3 13h4l3-8 5 15 3-9h3",
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2",
  meter: "M3 17a9 9 0 0 1 18 0 M12 15l5-6 M5 20h14",
  play: "M7 4l13 8-13 8z",
  file: "M5 3h10l4 4v14H5z M14 3v6h5 M8 13h8 M8 16h6",
  branch:
    "M6 3v14a3 3 0 1 0 3 3 M6 11h7a5 5 0 0 0 5-5 M15 6a3 3 0 1 0 6 0 3 3 0 0 0-6 0",
  shield: "M12 3l8 3v6c0 5-4 8-8 10-4-2-8-5-8-10V6z M8 12l3 3 5-6",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  download: "M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5",
  sliders: "M3 6h9m4 0h5 M3 18h3m4 0h11 M12 3v6 M7 15v6",
};
const ic = (key) =>
  `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[key] || paths.file}"/></svg>`;
let state = null,
  current = pageFromLocation(),
  selected = null,
  audit = null,
  busy = false,
  busyLabel = "",
  checkFilter = "ALL",
  search = "",
  stage = "ALL",
  statusFilter = "ALL";
const number = (n) =>
  n == null ? "—" : new Intl.NumberFormat("zh-CN").format(n);
const ts = (value, short = false) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        ...(short ? {} : { second: "2-digit" }),
        hour12: false,
      }).format(new Date(value))
    : "未记录";
const badge = (s) =>
  `<span class="status ${esc(s)}" title="${esc(s)}">${esc(labels[s] || s)}</span>`;
const act = (a, t, kind = "secondary", attr = "") =>
  `<button class="${kind}" data-action="${a}" ${attr}>${t}</button>`;
const link = (href, label) =>
  `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
const getRows = () =>
  state.requirements.filter((r) => r.requirement_id.startsWith("C0-"));
const getRow = (id) => state.requirements.find((r) => r.requirement_id === id);
const refsFor = (r) =>
  (audit?.attempts || [])
    .flatMap((a) => a.evidence)
    .filter((e) => r?.evidence.includes(e.id));
const newestEvidence = () => (audit?.attempts || []).at(-1)?.evidence || [];
const tell = (msg) => {
  el("toast").textContent = msg;
  el("toast").classList.add("active");
  clearTimeout(tell.t);
  tell.t = setTimeout(() => el("toast").classList.remove("active"), 3500);
};
async function api(url, options) {
  let response;
  try {
    response = await fetch(url, { cache: "no-store", ...options });
  } catch {
    throw new Error("无法连接本机服务。请启动工作台后重新读取。");
  }
  if (!response.ok) {
    let message = "本地服务暂时不可用";
    let code;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      if (typeof data.message === "string") message = data.message;
      code = data.code;
    } catch {}
    throw Object.assign(new Error(message + "（" + response.status + "）"), { status: response.status, code });
  }
  try {
    return await response.json();
  } catch {
    throw new Error("本机服务返回的记录格式异常，请重新读取。");
  }
}
let refreshSequence = 0;
async function refresh(id = selected) {
  const seq = ++refreshSequence;
  try {
    const data = await api(
      "/api/workspace" + (id ? "?run_id=" + encodeURIComponent(id) : ""),
    );
    if (seq !== refreshSequence) return false;
    const evidence = data.selected
      ? await api("/api/runs/" + data.selected.id + "/evidence")
      : null;
    if (seq !== refreshSequence) return false;
    state = data;
    selected = data.selected?.id || null;
    audit = evidence;
    render();
    return true;
  } catch (error) {
    if (seq !== refreshSequence) return false;
    throw error;
  }
}
function nav() {
  el("nav").innerHTML = Object.entries(pages)
    .map(
      ([key, [name, icon]]) =>
        `${key === "setup" ? '<div class="rail-label setup-nav-label">设置</div>' : ""}<a class="navlink" href="#${key}" ${current === key ? 'aria-current="page"' : ""}>${ic(icon)}${name}</a>`,
    )
    .join("");
  el("crumb").textContent = pages[current][0];
  document.title = pages[current][0] + " · VOC 研究工作台";
}
function renderQuota() {
  const t = state.token,
    pct = Math.min(100, Math.max(0, t.percent || 0));
  const balance =
    !t.key_configured ? "Jev 未连接 · 未同步"
    : t.remaining == null ? "额度未同步"
    : number(t.remaining) + " 剩余";
  const status = t.warning ? balance + " · " + t.warning : balance;
  const sync = t.last_synced_at ? "上次同步 " + ts(t.last_synced_at, true) : "最近同步 —";
  const progress =
    t.percent == null
      ? `aria-valuetext="${t.remaining == null ? "额度未同步" : "待配置额度上限"}"`
      : `aria-valuenow="${Math.round(pct)}"`;
  const meterClass = t.percent == null ? "unknown" : pct < 5 ? "critical" : pct < 20 ? "low" : "";
  el("top-token").innerHTML =
    `<button class="token-open" data-action="token-view" aria-label="查看 Jev Token Center" aria-describedby="token-status"><span class="token-summary">${ic("meter")}<span><strong>Jev Token Center</strong><small id="token-status">${esc(status)}</small></span></span><small class="desktop-token">消耗 ${number(t.input_tokens)}<br>${esc(sync)}</small></button><span class="minibar ${meterClass}" role="progressbar" aria-label="Jev 余额进度" ${progress}><i style="width:${pct}%"></i></span>${t.purchase_url ? `<a class="small-link" href="${esc(t.purchase_url)}" target="_blank" rel="noopener noreferrer">补充额度 ↗</a>` : ""}`;
}
function head(kicker, title, subtitle, buttons = "") {
  return `<section class="page-head"><div><div class="kicker">${kicker}</div><h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${buttons}</div></section>`;
}
function shellPanel(title, subtitle, inside) {
  return `<section class="panel"><div class="panel-head"><div><h2>${title}</h2>${subtitle ? `<p>${subtitle}</p>` : ""}</div></div>${inside}</section>`;
}
function stageList() {
  return `<section class="panel side-panel"><div class="panel-head"><h3>阶段进度</h3></div><div class="body">${[
    ["P0-0", "技术连通", "本批"],
    ["P0", "核心闭环", "待准入"],
    ["P1", "完整分析", "待准入"],
    ["P2", "扩展研究", "待准入"],
  ]
    .map(
      ([id, label, s], i) =>
        `<div class="stage-line"><i class="stage-dot ${i ? "" : "current"}"></i><b>${id}</b><span>${label}</span><small class="faint">${s}</small></div>`,
    )
    .join("")}</div></section>`;
}
function recentSide() {
  const wanted = ["forum_post", "outbound_isolation", "global_recall"],
    rows = newestEvidence().filter((e) => wanted.includes(e.name));
  const items = rows
    .map(
      (e) =>
        `<button class="evi-link" data-action="one-evidence" data-id="${e.id}"><span class="tiny-icon">${ic(e.name === "forum_post" ? "file" : e.name === "global_recall" ? "branch" : "shield")}</span><span><span class="row-name">${esc(sources[e.name])}</span><span class="row-sub">${esc(modes[e.mode])} · ${e.status_code ? "HTTP " + e.status_code : ts(e.checked_at, true)}</span></span></button>`,
    )
    .join("");
  return `<aside class="side"><section class="panel side-panel"><div class="panel-head"><h3>本批证据</h3></div><div class="body">${items || '<p class="support">运行后可查看原话快照、隔离演练和召回结果。</p>'}</div></section>${stageList()}</aside>`;
}
function checks() {
  const rows = getRows(),
    gate = getRow("G-1"),
    count = (s) => rows.filter((r) => r.status === s).length;
  const options = [
    ["ALL", "全部", 6],
    ["BLOCKED", "阻塞", count("BLOCKED")],
    ["PASS", "通过", count("PASS")],
  ];
  if (count("FAIL")) options.push(["FAIL", "失败", count("FAIL")]);
  const displayed = rows.filter(
    (r) => checkFilter === "ALL" || r.status === checkFilter,
  );
  const title = busy
    ? "正在执行检查"
    : gate.status === "PASS"
      ? "P0 准入已通过"
      : gate.status === "NOT_TESTED"
        ? "等待首次运行"
        : "P0 准入暂缓";
  const desc = busy
    ? "正在运行预设探针并保存响应，可继续查看已保存的证据。"
    : gate.status === "NOT_TESTED"
      ? "运行六项前置检查，建立第一份验收记录。"
      : gate.status === "PASS"
        ? "同一批次的六项检查和供应商审查均已通过。"
        : `已通过 ${count("PASS")} 项，阻塞 ${count("BLOCKED")} 项${count("FAIL") ? "，失败 " + count("FAIL") + " 项" : ""}。可逐项查看原因与取证记录。`;
  const runButton = act(
    "run",
    ic("play") + (busy ? "执行中…" : "运行检查"),
    "primary",
    busy || jevAwaitingLiveAuthorization() ? "disabled" : "",
  );
  const hero = `<section class="hero"><div><span class="eyebrow">G-1　阶段准入</span><h2>${title}</h2><p>${desc}</p></div><div class="trackbox"><div class="tracklabel"><span>本批检查通过数</span><strong>${count("PASS")} <small>/ 6</small></strong></div><div class="segments">${rows.map((r) => `<button class="segment ${r.status}" data-action="detail" data-id="${r.requirement_id}" aria-label="${esc(r.requirement_id + " " + labels[r.status])}"></button>`).join("")}</div><div class="trackfoot"><span>C0-1</span><span>C0-6</span></div></div></section>`;
  const list = `<div class="chips" aria-label="按检查状态筛选">${options.map(([val, name, n]) => act("filter-check", name + " " + n, "chip " + (checkFilter === val ? "on" : ""), 'data-id="' + val + '" aria-pressed="' + (checkFilter === val) + '"')).join("")}</div><div class="wide-table"><table class="table workbench-table"><thead><tr><th>编号</th><th>检查项</th><th>状态</th><th>证据</th></tr></thead><tbody>${displayed.map((r) => `<tr class="check-row"><td class="id">${r.requirement_id}</td><td><span class="row-name">${esc(r.title)}</span><span class="row-sub">${esc(detailLabels[Number(r.requirement_id.at(-1)) - 1])}</span></td><td>${badge(r.status)}</td><td>${act("detail", "查看 ›", "link", 'data-id="' + r.requirement_id + '" aria-label="查看 ' + r.requirement_id + ' 证据"')}</td></tr>`).join("")}</tbody></table></div>${displayed.length ? "" : '<div class="state-box"><b>此筛选下没有检查项</b>可切换到全部检查。</div>'}`;
  return (
    head(
      "P0-0 / CONNECTIVITY",
      "连通性检查",
      "核验外部服务、数据隔离与跨品类召回。",
      act("config", ic("sliders") + "连接配置") + runButton,
    ) +
    hero +
    `<div class="workspace-grid">${shellPanel("检查清单", "同批次的技术验收与执行证据", list)}${recentSide()}</div><div class="footerline"><span>${selected ? "批次 " + esc(selected.slice(0, 8)) + " · " + esc(ts(state.selected.started_at)) : "尚无运行批次"}</span><span>验收分母 6 项 · 正式研究样本 0 条</span></div>`
  );
}
function choices(values, val) {
  return values
    .map(
      ([id, label]) =>
        `<option value="${esc(id)}" ${id === val ? "selected" : ""}>${esc(label)}</option>`,
    )
    .join("");
}
function filteredMatrix() {
  const q = search.trim().toLowerCase();
  return state.requirements.filter(
    (r) =>
      (stage === "ALL" || stage === r.stage) &&
      (statusFilter === "ALL" || statusFilter === r.status) &&
      (!q ||
        [r.requirement_id, r.title, r.description]
          .join(" ")
          .toLowerCase()
          .includes(q)),
  );
}
function matrixRows() {
  const rows = filteredMatrix();
  return `<div class="wide-table"><table class="table matrix-table"><thead><tr><th>需求编号</th><th>阶段</th><th>验收项</th><th>状态</th><th>明细</th></tr></thead><tbody>${rows.map((r) => `<tr><td class="id">${esc(r.requirement_id)}</td><td class="id">${esc(r.stage)}</td><td>${esc(r.title)}</td><td>${badge(r.status)}</td><td>${act("detail", "查看 ›", "link", 'data-id="' + esc(r.requirement_id) + '"')}</td></tr>`).join("")}</tbody></table></div>${rows.length ? "" : '<div class="state-box"><b>没有匹配的需求</b>请调整关键词或筛选条件。</div>'}`;
}
function matrix() {
  const inputs = `<div class="tools"><input class="field search" id="matrix-search" aria-label="搜索验收项" placeholder="搜索编号或关键词" value="${esc(search)}"><select class="field" id="stage-filter" aria-label="阶段筛选">${choices([["ALL", "全部阶段"], ...["P0-0", "P0", "P1", "P2"].map((s) => [s, s])], stage)}</select><select class="field" id="status-filter" aria-label="状态筛选">${choices([["ALL", "全部状态"], ...Object.entries(labels)], statusFilter)}</select></div><div id="matrix-rows">${matrixRows()}</div>`;
  return (
    head(
      "REQUIREMENTS / PDT 1.3.1",
      "验收矩阵",
      "按编号、阶段和状态查找需求，追溯实现位置、测试与证据。",
      act("export-matrix", ic("download") + "导出矩阵"),
    ) +
    shellPanel(
      "需求映射",
      "共 " + state.requirements.length + " 项 · 专案 v2.2 与 PDT v1.3.1",
      inputs,
    )
  );
}
function history() {
  const rows = state.history;
  const body = rows.length
    ? `<div class="wide-table"><table class="table matrix-table"><thead><tr><th>批次 / 开始时间</th><th>供应商</th><th>执行次数</th><th>准入结果</th><th>操作</th></tr></thead><tbody>${rows.map((r) => `<tr><td><b class="mono">${esc(r.id.slice(0, 8))}</b><span class="row-sub">${esc(ts(r.started_at))}</span></td><td>${esc(r.provider)}</td><td>${r.attempts}</td><td>${badge(r.gate || "NOT_TESTED")}</td><td>${act("open-run", "查看批次 ›", "link", 'data-id="' + r.id + '"')}</td></tr>`).join("")}</tbody></table></div>`
    : '<div class="state-box"><b>还没有运行记录</b>从连通性检查页运行第一批检查。</div>';
  return (
    head(
      "AUDIT / RUNS",
      "运行记录",
      "每次执行保存独立记录，原始证据可在离线时回看。",
      act("goto-checks", "返回检查"),
    ) + shellPanel("本地批次", "按最新开始时间排列", body)
  );
}
function tokens() {
  const t = state.token;
  const stats = [
    [
      t.unit === "input tokens" ? "供应商剩余额度" : "供应商账户余额",
      number(t.remaining),
      t.remaining == null ? "未同步" : "响应头余额",
    ],
    [
      "本机累计消耗",
      number(t.input_tokens),
      "本机验收及连接诊断 · input tokens",
    ],
    [
      "最近余额同步",
      t.last_synced_at ? ts(t.last_synced_at, true) : "—",
      t.last_synced_at
        ? t.remaining == null ? "上次成功同步 · 当前待回填" : "供应商响应头"
        : "等待可信余额记录",
    ],
  ];
  const metrics = `<div class="metrics">${stats.map(([a, b, c]) => `<div class="metric"><span>${esc(a)}</span><b>${esc(b)}</b><small>${esc(c)}</small></div>`).join("")}</div>`;
  const table = t.records.length
    ? `<div class="wide-table"><table class="table"><thead><tr><th>批次</th><th>分片</th><th>输入 tokens</th><th>状态</th><th>时间</th></tr></thead><tbody>${t.records.map((r) => `<tr><td>${act("open-run", esc(r.run_id.slice(0, 8)), "link", 'data-id="' + r.run_id + '"')}</td><td>${r.shard_no}</td><td>${number(r.tokens)}</td><td>${esc(shardStates[r.state] || r.state)} · ${r.status_code == null ? "未收到 HTTP" : "HTTP " + r.status_code}</td><td>${esc(ts(r.updated_at, true))}</td></tr>`).join("")}</tbody></table></div>`
    : '<div class="state-box"><b>本机账本暂无分片</b>真实 Jev 响应会在这里留下输入用量及同步依据。</div>';
  return (
    head(
      "JEV / TOKEN CENTER",
      "额度中心",
      esc(t.provider) + " · " + esc(t.model) + " · 账户单位 " + esc(t.unit),
      (t.key_configured ? "" : act("config", "连接配置")) +
        act("refresh", "刷新状态") + (t.purchase_url ? link(t.purchase_url, "补充额度") : ""),
    ) +
    (t.warning
      ? `<div class="warning">${esc(t.warning)} · 请核对供应商账户或查看最近分片。</div>`
      : t.key_configured ? "" : '<div class="warning">Jev 未连接。请在 API 接入页保存密钥，余额等待同步。</div>') +
    metrics + (t.billing ? shellPanel("用量及计费", t.billing.rate_source, packyBilling(t.billing)) : "") +
    shellPanel("最近验收分片", "按当前供应商与本机凭证隔离，最多 20 次。连接诊断在 API 接入页查看。", table)
  );
}
function render() {
  nav();
  renderQuota();
  const main = el("main");
  if (!Object.hasOwn(researchViews, current)) {
    main.innerHTML = { checks, matrix, history, tokens, setup }[current]();
    return;
  }
  const hash = location.hash;
  if (main.firstElementChild?.dataset.workspaceRoute === hash) return;
  const view = document.createElement("div");
  const title = pages[current][0];
  view.className = { studies: "study-root", acquisition: "acquisition-root", imports: "import-root", corpus: "corpus-root",
    relations: "relation-root", registry: "relation-root registry-root" }[current];
  view.dataset.workspaceRoute = hash;
  view.innerHTML = '<p class="panel state-box" role="status">正在读取' + title + '…</p>';
  main.replaceChildren(view);
  researchViews[current]().then(mount => {
    if (view.isConnected) mount(
      view, hash.slice(1), { api, esc, ic, choices, tell }
    );
  }).catch(() => {
    if (view.isConnected) view.textContent = "无法加载" + title + "。请刷新工作台。";
  });
}
function openDrawer(title, kicker, html) {
  el("drawer-title").textContent = title;
  el("drawer-kicker").textContent = kicker;
  el("drawer-body").innerHTML = html;
  if (!el("drawer").open) el("drawer").showModal();
  el("drawer").scrollTop = 0;
}
function evidenceCard(e, open = false) {
  const obj = e.response,
    http = e.status_code == null ? "未记录 HTTP" : "HTTP " + e.status_code;
  const citation =
    e.name === "forum_post" && obj.verified
      ? `<blockquote lang="en">${esc(obj.text)}</blockquote><p>${link(obj.url, "原文")} · ${esc(obj.author)} · ${link(obj.license_url, obj.license)}<br>原文日期 ${esc(new Date(obj.published_at).toLocaleDateString("zh-CN"))} · 采样 ${esc(ts(e.checked_at))}</p>`
      : "";
  return `<details class="evidence-card" ${open ? "open" : ""}><summary>${esc(sources[e.name] || e.name)}　<small>${esc(modes[e.mode] || e.mode)} · ${esc(http)}</small></summary>${citation}<p>记录 #${e.id} · ${esc(ts(e.checked_at))}</p><h4>脱敏请求</h4><pre>${esc(JSON.stringify(e.request, null, 2))}</pre><h4>响应或本机结果</h4><pre>${esc(JSON.stringify(obj, null, 2))}</pre></details>`;
}
function detail(id) {
  const r = getRow(id);
  if (!r) return;
  const evidence = refsFor(r);
  const content = `<section class="drawer-section">${badge(r.status)}<p>${esc(r.detail || r.description)}</p>${r.blocker ? `<div class="warning">${esc(r.blocker)}</div>` : ""}<dl><dt>研究阶段</dt><dd>${esc(r.stage)}</dd><dt>最近核验</dt><dd>${esc(ts(r.last_checked_at))}</dd><dt>实现位置</dt><dd class="mono">${esc(r.implementation)}</dd><dt>测试用例</dt><dd class="mono">${esc(r.test_case)}</dd></dl></section><section class="drawer-section"><h3>验收标准</h3><p>${esc(r.description)}</p></section><section class="drawer-section"><h3>执行证据 · ${evidence.length}</h3>${evidence.map((e) => evidenceCard(e)).join("") || "<p>此项尚无执行证据。</p>"}</section>`;
  openDrawer(r.title, id + " / 验收详情", content);
}
const connectionLabels = {
  NOT_CONFIGURED: "未配置", NOT_TESTED: "未测试", CONNECTED: "已连接",
  CAPABILITY_BLOCKED: "能力不满足", REVIEW_REQUIRED: "审核未完成",
  READY: "连接条件已核验", ERROR: "请求失败", PLANNED: "待开发",
};
const sourceLabels = { local: "本机凭证库", environment: "后端环境", disabled: "已停用环境凭证" };
const docReview = "https://github.com/kurikiwoods-coder/voc-research-workbench/blob/codex/p0-0-connectivity/docs/connectivity.md#变量与审核凭证";
let wizardStep = null, setupBusy = false, lastProbeProvider = null;
const diagnosticKeys = new Map();

function jevAwaitingLiveAuthorization() {
  return state.setup?.providers.find(provider => provider.selected)?.live_test_allowed === false;
}

function packyBilling(billing) {
  const recorded = value => value == null ? "未记录" : number(value);
  const amount = value => value == null ? "未记录" : "$" + esc(value);
  return `<dl class="setup-quota">
    <div><dt>响应输入 Token</dt><dd>${recorded(billing.input_tokens)}</dd></div>
    <div><dt>响应输出 Token</dt><dd>${recorded(billing.output_tokens)}</dd></div>
    <div><dt>按候选报价估算</dt><dd>${amount(billing.estimated_usd)}</dd></div>
    <div><dt>实际扣费</dt><dd>${billing.actual_charge_usd == null
      ? billing.charge_status === "UNKNOWN" ? "未知" : "无请求记录"
      : amount(billing.actual_charge_usd)}</dd></div>
    </dl>`;
}

function connectionBadge(status) {
  const tone = { READY: "PASS", CONNECTED: "PASS", ERROR: "FAIL",
    CAPABILITY_BLOCKED: "BLOCKED", REVIEW_REQUIRED: "BLOCKED" }[status] || "NOT_TESTED";
  return `<span class="status ${tone}" title="${esc(status)}">${esc(connectionLabels[status])}</span>`;
}
function prerequisiteStrip() {
  const p = state.setup.prerequisites;
  return `<ol class="setup-track"><li><b>Jev 密钥</b><span>${p.jev_key ? "已配置" : "请选择一个 Jev 供应商"}</span></li><li><b>搜索密钥</b><span>${p.search_key ? "已配置至少一家" : "Tavily 或 Brave 任一即可"}</span></li><li><b>留存审核</b><span>${p.jev_review ? "审查记录已核验" : "导入所选 Jev 供应商的审查记录"}</span></li></ol>`;
}
function credentialForm(p, prefix) {
  const id = prefix + "-" + p.id;
  return `<form method="post" class="setup-form" data-setup-form="key" data-provider="${p.id}" autocomplete="off"><label for="${id}">API Key</label><div class="setup-form-row"><input class="field" id="${id}" name="key" type="password" autocomplete="off" autocapitalize="none" spellcheck="false" maxlength="512" required><button type="submit" class="primary">保存密钥</button></div></form>`;
}
function reviewForm(p) {
  return `<details class="connector-detail"><summary>${p.review.approved ? "留存审核已核验" : "导入留存审核"}</summary><p>选择已审核的 JSON 记录与对应附件。工作台会核对供应商、审批字段和附件摘要。更换密钥后请核对当前账户并重新登记审批材料。</p><p>${link(docReview, "审查材料格式")} ${p.review_docs ? link(p.review_docs, "申请零数据留存") : ""}</p><form method="post" class="setup-form" data-setup-form="review" data-provider="${p.id}"><label>审查 JSON <input type="file" name="record" accept=".json,application/json" required></label><label>证明附件 <input type="file" name="attachment" required></label><button class="secondary" type="submit">导入审查材料</button></form></details>`;
}
function diagnosticEvidence(test) {
  const status = test.http_status == null ? "未收到 HTTP" : "HTTP " + test.http_status;
  const groups = test.source
    ? `<dl class="setup-evidence"><dt>搜索结果</dt><dd>${number(test.source.result_count)} 条，合规候选 ${number(test.source.eligible_links)} 条</dd><dt>原始网页</dt><dd>${test.source.original_fetched ? "已回源" : "待核验"}${test.source.source_http.length ? " · " + esc(test.source.source_http.map((x) => x == null ? "无 HTTP" : "HTTP " + x).join(" / ")) : ""}</dd><dt>许可审核</dt><dd>${test.source.license_verified ? esc(test.source.license || "识别到公开许可") : "待核验"}</dd><dt>真实引用</dt><dd>${test.source.excerpt_verified ? "已核验原句" : "暂无原句证据"}</dd></dl>`
    : "";
  const { message, ...projection } = test;
  return `<details class="connector-detail"><summary>${esc(ts(test.checked_at, true))} · ${esc(status)} · 证据 #${test.evidence_id}</summary><p>${esc(message)}</p>${groups}<p>记录范围为连接诊断，正式研究分母为 0。</p><pre>${esc(JSON.stringify(projection, null, 2))}</pre></details>`;
}
function candidateContract(p, compact) {
  const contract = p.candidate_contract;
  if (!contract) return "";
  return `<dl class="setup-evidence">
    <dt>API 分组</dt><dd><code>${esc(contract.group)}</code></dd>
    <dt>固定 Model ID</dt><dd><code>${esc(contract.model)}</code></dd>
    <dt>候选 Base URL</dt><dd><code>${esc(contract.base_url)}</code></dd>
    <dt>候选接口</dt><dd><code>${esc(contract.endpoint)}</code>${contract.endpoint_evidence === "DOCUMENTED" ? " · 文档已查证" : ""}</dd>
    <dt>接口契约</dt><dd>${esc(connectionLabels[contract.live_status] || contract.live_status)} · 待验证实际接口</dd>
    <dt>供应商审核</dt><dd>${p.review?.approved ? "本机审核记录已核验" : "未通过"}</dd>
    <dt>候选报价</dt><dd>输入 $${number(contract.input_usd_per_million)} / 百万 Token，输出 $${number(contract.output_usd_per_million)} / 百万 Token</dd>
    <dt>报价来源</dt><dd>${esc(contract.rate_source)} · 待独立核验</dd>
    </dl>${p.live_test_allowed === false ? `<p class="connector-time" id="packycode-diagnostic-policy${compact ? "-wizard" : ""}">真实连接测试及正式验收待负责人另行授权。</p>` : ""}`;
}
function providerCard(p, compact = false) {
  const report = p.recent_tests?.[0];
  const attrs = 'data-id="' + p.id + '"';
  const editing = !p.configured;
  const testHint = report
    ? `${esc(report.message)} <span class="connector-time">${esc(ts(report.checked_at, true))}${report.http_status == null ? "" : " · HTTP " + report.http_status}</span>`
    : p.candidate_contract ? "最近测试 未实测。" : "尚无当前凭证的连接诊断。";
  const guides = `<p class="connector-purpose">${esc(p.purpose)} ${p.signup ? link(p.signup, p.candidate_contract ? "注册入口" : "官方控制台") : ""} ${p.docs ? link(p.docs, "接入文档") : ""} ${p.candidate_contract && p.purchase_url ? link(p.purchase_url, "供应商计费页") : ""}</p><p class="connector-guide">${esc(p.guide)}</p>`;
  if (p.status === "PLANNED") {
    return `<article class="provider-row" aria-label="${esc(p.label)}"><header><h3>${esc(p.label)}</h3><span class="connector-time">${esc(p.stage)} 接入</span>${connectionBadge(p.status)}</header>${guides}<p class="connector-time">计量单位 ${esc(p.unit)}</p></article>`;
  }
  const useAction = p.group === "jev" && !p.selected ? act("setup-choose", "选为 Jev 通道", "secondary", attrs) : "";
  const diagnosticAttrs = p.live_test_allowed === false
    ? attrs + ` disabled aria-describedby="packycode-diagnostic-policy${compact ? "-wizard" : ""}"`
    : attrs;
  const actions = `${useAction}${act("setup-test", "检查连接", "secondary", diagnosticAttrs)}${p.configured ? act("setup-delete", "删除密钥", "quiet remove-key", attrs) : ""}`;
  const quota = `<dl class="setup-quota"><div><dt>计量单位</dt><dd>${esc(p.unit)}</dd></div><div><dt>已知余额</dt><dd>${p.remaining == null ? "未同步" : number(p.remaining)}</dd></div><div><dt>额度上限</dt><dd>${p.capacity == null ? "未提供" : number(p.capacity)}</dd></div><div><dt>${esc(p.usage_scope)}用量</dt><dd>${p.local_usage == null ? "未记录" : number(p.local_usage)}</dd></div></dl><p class="connector-time">最近余额同步 ${esc(ts(p.last_synced_at, true))}${p.warning ? " · " + esc(p.warning) : ""}</p>`;
  return `<article class="provider-row" aria-label="${esc(p.label)}"><header><h3>${esc(p.label)}</h3>${p.selected ? '<span class="connector-time">当前 Jev 通道</span>' : ""}${connectionBadge(p.status)}</header>${guides}${candidateContract(p, compact)}<p class="connector-time">凭证 ${p.configured ? "已配置" : "未配置"}${p.credential_source ? " · " + esc(sourceLabels[p.credential_source]) : ""} <code>${esc(p.env_var)}</code></p>${compact ? "" : quota + (p.billing ? packyBilling(p.billing) : "")}<div class="actions connector-actions">${actions}</div><details class="connector-detail" ${editing ? "open" : ""}><summary>${editing ? "填写密钥" : "更换密钥"}</summary>${credentialForm(p, compact ? "wizard-key" : "api-key")}</details>${p.review ? reviewForm(p) : ""}<div class="connector-result" role="status">${testHint}</div>${p.recent_tests.length ? `<details class="connector-detail" ${lastProbeProvider === p.id ? "open" : ""}><summary>最近测试证据</summary>${p.recent_tests.map(diagnosticEvidence).join("")}</details>` : ""}</article>`;
}
function setup() {
  const { providers, future, error } = state.setup;
  const gate = state.config.acceptance;
  return `<section class="page-head setup-head"><div><h1>API 接入</h1><p>在本机保存密钥，逐一检查服务，然后运行 P0-0 正式验收。</p></div><div class="actions">${act("setup-wizard", "配置向导")}</div></section>${error ? '<p class="warning" role="alert">' + esc(error) + '</p>' : ""}<section class="panel setup-summary"><div><h2>开始 P0-0 验收</h2><p>连接诊断与正式验收分别记录。当前所选批次的 G-1 ${badge(gate)}</p></div>${prerequisiteStrip()}${jevAwaitingLiveAuthorization() ? '<p>当前 Jev 通道的正式验收待负责人另行授权。</p>' : ""}<div class="actions">${act("run", "运行正式验收", "primary", busy || error || jevAwaitingLiveAuthorization() ? "disabled" : "")}${act("goto-checks", "查看连通性检查")}</div></section>${shellPanel("Jev 模型", "选一种 Jev 通道，固定使用 jev-1.14.0。各供应商独立保存密钥与审核材料。", providers.filter(p => p.group === "jev").map(p => providerCard(p)).join(""))}${shellPanel("公开搜索", "Tavily 或 Brave 任一可用于 P0-0。搜索命中会继续核对原始网页、许可和引用。", providers.filter(p => p.group === "search").map(p => providerCard(p)).join(""))}${shellPanel("后续接入", "首次设置可跳过，当前阶段无需凭证。", future.map(p => providerCard(p)).join(""))}`;
}
function showWizard(step) {
  wizardStep = step;
  const providers = state.setup.providers;
  const active = providers.find(p => p.selected);
  const caption = ["选择 Jev 通道", "配置一个搜索引擎", "核对验收准备"][step];
  const cards = step === 0
    ? `<label class="wizard-choice">当前 Jev 通道 <select id="wizard-jev" class="field">${choices(providers.filter(p => p.group === "jev").map(p => [p.id, p.label]), active.id)}</select></label>${providerCard(active, true)}`
    : step === 1
      ? providers.filter(p => p.group === "search").map(p => providerCard(p, true)).join("")
      : prerequisiteStrip();
  const next = step === 2
    ? act("wizard-finish", "打开 API 接入", "primary")
    : act("wizard-next", "下一步", "primary");
  openDrawer(
    "首次配置 API",
    "第 " + (step + 1) + " 步，共 3 步",
    `<section class="drawer-section wizard-body"><h3>${caption}</h3><p>${step === 0 ? "请选择一个 Jev 通道。每一步都可以稍后配置。" : step === 1 ? "配置其中一家即可。YouTube 和 Google Forms 等后续阶段再接入。" : "打开 API 接入页查看当前验收准备情况。"}</p>${cards}<div class="actions wizard-actions">${next}${step ? act("wizard-back", "上一步") : ""}${act("wizard-skip", "稍后配置", "quiet")}</div></section>`,
  );
}
function setupRequest(path, method, data) {
  return api("/api/setup/" + path, {
    method,
    headers: { "X-VOC-Action": "connectivity", "Content-Type": "application/json" },
    ...(data ? { body: JSON.stringify(data) } : {}),
  });
}
async function updateSetup(path, method, data, message, control, after) {
  if (setupBusy) return;
  setupBusy = true;
  const originalLabel = control?.tagName === "BUTTON" ? control.textContent : null;
  if (control) {
    control.disabled = true;
    control.setAttribute("aria-busy", "true");
    if (originalLabel && path.endsWith("/diagnostics")) control.textContent = "检查中…";
  }
  try {
    const reply = await setupRequest(path, method, data);
    if (after) after(reply);
    await refresh();
    if (wizardStep !== null && el("drawer").open) showWizard(wizardStep);
    tell(typeof message === "function" ? message(reply) : message);
  } finally {
    setupBusy = false;
    if (control) {
      control.disabled = false;
      control.removeAttribute("aria-busy");
      if (originalLabel && path.endsWith("/diagnostics")) control.textContent = originalLabel;
    }
  }
}
function setupError(error) {
  if (el("drawer").open) {
    el("drawer-body").querySelector("[role=alert]")?.remove();
    const message = document.createElement("p");
    message.className = "warning";
    message.setAttribute("role", "alert");
    message.textContent = error.message;
    el("drawer-body").prepend(message);
  } else tell(error.message);
}
async function readReviewFile(file, limit) {
  if (!file || file.size > limit) throw new Error("审查记录最多 32 KB，证明附件最多 1 MB。");
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text = "";
  for (let offset = 0; offset < bytes.length; offset += 8192) {
    text += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  }
  return btoa(text);
}
function save(name, content) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(content, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
function runDialog(resume = false) {
  if (!resume && jevAwaitingLiveAuthorization()) return;
  wizardStep = null;
  const action = resume ? "commit-resume" : "commit-run";
  openDrawer(
    resume ? "恢复此批次" : "运行六项连接检查",
    "P0-0 / 执行范围",
    `<section class="drawer-section"><h3>本次执行</h3><p>从许可来源检索一条公开原话，核验数据库，运行合成隔离与召回测试。已配置凭证并通过留存审查时，后台会向 ${esc(state.config.provider)} 发送最多两个固定分片，分别有 8 题和 3 题，产生供应商用量。重试遵守同一分片键。</p><p>${resume ? "已成功的分片从原账本读取。" : "检查记录保存在一个新批次。"} 全部诊断材料的正式研究分母为零。</p>${act(action, resume ? "恢复执行" : "开始运行", "primary")}</section>`,
  );
}
function batchInfo() {
  const info = state.selected;
  if (!info) return;
  const timeline = [...audit.attempts]
    .reverse()
    .map(
      (a) =>
        `<section class="drawer-section"><h3>执行 #${a.id} · ${esc(ts(a.started_at))}</h3>${a.evidence.map((e) => evidenceCard(e)).join("")}</section>`,
    )
    .join("");
  openDrawer(
    "批次 " + info.id.slice(0, 8),
    "运行记录",
    `<section class="drawer-section"><p class="mono">${esc(info.id)}</p><div class="actions">${act("export-audit", ic("download") + "导出证据")}${info.state !== "complete" ? act("resume", "恢复此批次", "primary", busy ? "disabled" : "") : ""}</div></section>` +
      timeline,
  );
}
async function execute(resume) {
  if (busy || (!resume && jevAwaitingLiveAuthorization())) return;
  busy = true;
  el("drawer").close();
  current = "checks";
  location.hash = "checks";
  render();
  const storeKey = "voc-pending-request";
  try {
    let key;
    if (!resume) {
      key = sessionStorage.getItem(storeKey);
      if (!key) {
        key = crypto.randomUUID();
        sessionStorage.setItem(storeKey, key);
      }
    }
    const out = await api(
      resume ? "/api/runs/" + selected + "/resume" : "/api/runs",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-VOC-Action": "connectivity",
        },
        ...(!resume ? { body: JSON.stringify({ request_key: key }) } : {}),
      },
    );
    if (!resume) sessionStorage.removeItem(storeKey);
    checkFilter = "ALL";
    await refresh(out.run_id);
    tell("检查执行记录已保存");
  } catch (error) {
    openDrawer(
      "执行遇到问题",
      "本机服务",
      `<section class="drawer-section"><p>${esc(error.message)}</p>${act("refresh", "重新读取已有记录")}</section>`,
    );
  } finally {
    busy = false;
    render();
  }
}
function gotoPage(page) {
  wizardStep = null;
  if (el("drawer").open) el("drawer").close();
  location.hash = page;
  if (current === page) render();
}
document.addEventListener("click", async (event) => {
  if (event.target.closest("a.skip")) {
    event.preventDefault();
    const main = el("main");
    main.focus({ preventScroll: true });
    main.scrollIntoView({ block: "start" });
    return;
  }
  const navLink = event.target.closest("a.navlink");
  if (navLink && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
    event.preventDefault();
    const next = navLink.getAttribute("href").slice(1);
    document.getElementById("rail").classList.remove("open");
    document.querySelector(".menu-btn").setAttribute("aria-expanded", "false");
    gotoPage(next);
    return;
  }
  const b = event.target.closest("[data-action]");
  if (!b) return;
  const a = b.dataset.action,
    id = b.dataset.id;
  try {
    if (a === "menu") {
      const open = el("rail").classList.toggle("open");
      b.setAttribute("aria-expanded", String(open));
      return;
    }
    if (a === "close") {
      wizardStep = null;
      el("drawer").close();
      return;
    }
    if (a === "retry-load") {
      await startWorkspace();
      return;
    }
    if (a === "refresh") {
      if (!(await refresh())) return;
      if (el("drawer").open) el("drawer").close();
      tell("已刷新本地记录");
      return;
    }
    if (a === "config") gotoPage("setup");
    if (a === "setup-wizard") showWizard(0);
    if (a === "wizard-next" && !setupBusy) showWizard(wizardStep + 1);
    if (a === "wizard-back" && !setupBusy) showWizard(wizardStep - 1);
    if (a === "wizard-skip" || a === "wizard-finish") {
      await updateSetup("wizard", "POST", null, a === "wizard-skip" ? "可随时从 API 接入继续配置。" : "配置向导已完成。", b, () => {
        if (a === "wizard-finish") gotoPage("setup");
        else {
          wizardStep = null;
          el("drawer").close();
        }
      });
    }
    if (a === "setup-choose") {
      await updateSetup("jev/" + id, "PUT", null, "已切换 Jev 通道。", b);
    }
    if (a === "setup-delete" && !setupBusy && window.confirm("停止在本机工作台使用此密钥？要同时撤销供应商的密钥，请前往其控制台。")) {
      await updateSetup(id + "/key", "DELETE", null, "本机已停止使用该密钥。", b, () => diagnosticKeys.delete(id));
    }
    if (a === "setup-test" && !setupBusy) {
      const key = diagnosticKeys.get(id) || crypto.randomUUID();
      diagnosticKeys.set(id, key);
      await updateSetup(id + "/diagnostics", "POST", { request_key: key }, result => result.message, b, () => {
        diagnosticKeys.delete(id);
        lastProbeProvider = id;
      });
    }
    if (a === "detail") detail(id);
    if (a === "token-view") gotoPage("tokens");
    if (a === "goto-checks") gotoPage("checks");
    if (a === "filter-check") {
      checkFilter = id;
      render();
    }
    if (a === "run" || a === "resume") runDialog(a === "resume");
    if (a === "commit-run" || a === "commit-resume")
      await execute(a === "commit-resume");
    if (a === "one-evidence") {
      const e = newestEvidence().find((x) => String(x.id) === id);
      if (e)
        openDrawer(
          sources[e.name],
          "本批证据",
          `<section class="drawer-section">${evidenceCard(e, true)}</section>`,
        );
    }
    if (a === "open-run") {
      if (await refresh(id)) batchInfo();
    }
    if (a === "export-audit" && audit)
      save("voc-evidence-" + selected + ".json", audit);
    if (a === "export-matrix") save("voc-requirements.json", filteredMatrix());
  } catch (error) {
    if (a === "retry-load") {
      loadError(error);
    } else setupError(error);
  }
});
document.addEventListener("submit", async (event) => {
  const form = event.target;
  const kind = form.dataset.setupForm;
  if (!kind) return;
  event.preventDefault();
  if (setupBusy) return;
  const provider = form.dataset.provider;
  try {
    if (kind === "key") {
      const input = form.elements.namedItem("key");
      const key = input.value;
      input.value = "";
      await updateSetup(provider + "/key", "PUT", { key }, "密钥已保存并生效。", event.submitter, () => diagnosticKeys.delete(provider));
    } else {
      const [record, attachment] = await Promise.all([
        readReviewFile(form.elements.namedItem("record").files[0], 32 * 1024),
        readReviewFile(form.elements.namedItem("attachment").files[0], 1024 * 1024),
      ]);
      form.reset();
      await updateSetup(provider + "/review", "PUT", { record, attachment }, "留存审查材料已核验并保存在本机。", event.submitter);
    }
  } catch (error) {
    setupError(error);
  }
});
document.addEventListener("cancel", (event) => {
  if (event.target.id === "drawer") wizardStep = null;
}, true);
document.addEventListener("input", (e) => {
  if (e.target.id === "matrix-search") {
    search = e.target.value;
    el("matrix-rows").innerHTML = matrixRows();
  }
});
document.addEventListener("change", async (e) => {
  if (e.target.id === "wizard-jev") {
    const old = state.setup.provider;
    if (setupBusy) {
      e.target.value = old;
      return;
    }
    try {
      await updateSetup("jev/" + e.target.value, "PUT", null, "已切换 Jev 通道。", e.target);
    } catch (error) {
      e.target.value = old;
      setupError(error);
    }
  }
  if (e.target.id === "stage-filter" || e.target.id === "status-filter") {
    stage = el("stage-filter").value;
    statusFilter = el("status-filter").value;
    el("matrix-rows").innerHTML = matrixRows();
  }
});
window.addEventListener("hashchange", () => {
  const next = pageFromLocation();
  if (next !== current && el("drawer").open) {
    wizardStep = null;
    el("drawer").close();
  }
  current = next;
  el("rail").classList.remove("open");
  document.querySelector(".menu-btn").setAttribute("aria-expanded", "false");
  if (state) render();
  window.scrollTo(0, 0);
});
function loadError(error) {
  el("main").innerHTML =
    `<div class="panel state-box"><b>无法读取本地工作台</b><p>${esc(error.message)}</p>${act("retry-load", "重新读取")}</div>`;
}
function renderEdition(data) {
  const personal = data.edition === "PERSONAL";
  const local = data.deployment === "LOCAL";
  el("nav").innerHTML = '<a class="navlink" href="#edition" aria-current="page">版本与研究准入</a>';
  el("crumb").textContent = "版本与研究准入";
  document.title = "版本与研究准入 · VOC 研究工作台";
  el("top-token").textContent = "供应商调用关闭";
  const metrics = [
    ["产品版本", personal ? "个人研究版" : "商用研究版", data.edition],
    ["部署方式", local ? "本机" : "云端", data.deployment],
    ["个人准入", data.gates.personal.id, data.gates.personal.status],
    ["商用准入", data.gates.business.id, data.gates.business.status],
  ];
  el("main").innerHTML = head("", "版本与研究准入", esc(data.reason)) +
    `<div class="metrics">${metrics.map(([label, value, detail]) =>
      `<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(detail)}</small></div>`).join("")}</div>` +
    shellPanel("本机操作权限", data.operations.scoped_local_workspace
      ? "经本机 Owner 验证后，可在授予的项目和冻结范围内读取、导入或复核。"
      : "当前部署只提供状态查询。", data.operations.scoped_local_workspace
      ? '<p><a class="btn quiet" href="/api/edition/projects">核对已授权项目</a></p>' : "") +
    '<p class="state-box">正式采集、外部模型、正式编码和发布关闭。</p>' +
    (personal && local && data.operations.scoped_local_workspace
      ? '<div id="personal-governance"></div>' : "");
  const governance = el("personal-governance");
  if (governance) import("./personal-governance.js").then(({ mountGovernance }) => {
    if (governance.isConnected) mountGovernance(governance, { api, esc });
  }).catch(() => {
    governance.textContent = "无法载入个人审批中心，请刷新工作台。";
  });
}

async function startWorkspace() {
  const edition = await api("/api/edition");
  if (edition.workspace !== "BUSINESS_LOCAL") {
    renderEdition(edition);
    return;
  }
  el("crumb").title =
    `商用研究版 · 本机 · ${edition.gates.business.id} ${edition.gates.business.status}`;
  nav();
  const loaded = await refresh(null);
  if (loaded && state?.setup && !state.setup.wizard_seen && !state.setup.error) showWizard(0);
}

startWorkspace().catch(loadError);
