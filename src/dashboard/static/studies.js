const endpoint = "/api/studies";
const modes = {
  single_product: "单一产品研究",
  single_category: "单一品类研究",
  multi_product_category: "多产品、多品类研究",
  cross_category: "跨品类用户需求研究",
  open: "开放式研究",
};
const modeHelp = {
  single_product: "填写一个产品 ID，可选填一个品类 ID。",
  single_category: "填写一个品类 ID。范围涵盖该品类中的产品或服务。",
  multi_product_category: "至少填写两个产品 ID 或两个品类 ID。",
  cross_category: "填写至少两个品类 ID，并用同一个核心研究问题界定需求。",
  open: "以研究问题划定范围，产品与品类均不设限。",
};
const states = { draft: "草稿", active: "研究中", archived: "已归档" };
const tone = { draft: "NOT_TESTED", active: "PASS", archived: "NOT_TESTED" };
const scopeLabels = {
  mode: "研究模式", topic: "核心研究问题", market: "目标市场",
  language: "研究语言", date_window: "研究时间范围",
  product_ids: "产品引用", product_category_ids: "品类引用",
  user_tasks: "用户任务", audience: "目标用户群体", source_preferences: "数据来源偏好",
  inclusion_criteria: "纳入标准", exclusion_criteria: "排除标准",
};
const dateTime = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium", timeStyle: "short",
});

const when = (value) => dateTime.format(new Date(value));
const projectHref = (id) => "#studies/" + id;
const statusBadge = (status) => '<span class="status ' + tone[status] + '">' + states[status] + '</span>';
const scopeBadge = (scope) => scope.frozen_at
  ? '<span class="status PASS">已冻结</span>'
  : '<span class="status NOT_TESTED">待冻结</span>';
const note = '<p class="study-error" role="alert" hidden></p>';
const action = (kind, label, style = "secondary", attributes = "") =>
  '<button type="button" class="' + style + '" data-study-action="' + kind + '" ' + attributes + '>' + label + '</button>';

export function mountStudies(root, route, { api, esc, ic, choices, tell }) {
  const [, id, view, scopeId] = route.split("/");
  const url = endpoint + (id && id !== "new" ? "/" + id : "");
  let project, busy = false, listSequence = 0, requestKey;
  let filters = { query: "", status: "open", sort: "updated" };

  function request(path, method, data) {
    return api(path, {
      method,
      headers: { "Content-Type": "application/json", "X-VOC-Action": "connectivity" },
      ...(data ? { body: JSON.stringify(data) } : {}),
    });
  }

  const href = (to, title, style = "secondary") =>
    '<a class="' + style + '" href="' + esc(to) + '">' + title + '</a>';
  const time = (value) => '<time datetime="' + esc(value) + '">' + esc(when(value)) + '</time>';
  const head = (title, summary, buttons = "") =>
    '<header class="page-head study-head"><div><h1>' + esc(title) + '</h1><p>' + summary +
    '</p></div><div class="actions">' + buttons + '</div></header>';
  const datum = (label, value, className = "") =>
    '<div class="' + className + '"><dt>' + label + '</dt><dd>' + value + '</dd></div>';
  const textValue = (value) => value ? esc(value) : '<span class="study-muted">未填写</span>';

  function errorMessage(error, host = root) {
    const line = host.querySelector(".study-error");
    if (!line) return;
    line.textContent = error.message;
    line.hidden = false;
  }

  function showList() {
    root.innerHTML = head(
      "研究项目", "管理本机课题、抽样范围与历史版本。",
      href("#studies/new", ic("file") + "新建项目", "primary")
    ) + `
      <section class="study-current panel" aria-label="当前研究项目"></section>
      <section class="panel study-list" aria-label="项目列表">
        <form class="study-filters" data-study-form="search" method="post">
          <label>搜索项目<input class="field" name="query" type="search" maxlength="240" placeholder="项目、对象或研究问题"></label>
          <label>项目状态<select class="field" name="status">${choices(
            [["open", "未归档"], ["all", "全部项目"], ...Object.entries(states)], filters.status
          )}</select></label>
          <label>排序<select class="field" name="sort">${choices(
            [["updated", "最近更新"], ["created", "最近创建"], ["name", "项目名称"]], filters.sort
          )}</select></label>
          <button class="secondary" type="submit">查询</button>
        </form>
        ${note}
        <div class="study-results"></div>
      </section>`;
    const field = root.querySelector('[name="query"]');
    field.value = filters.query;
  }

  async function readList() {
    const sequence = ++listSequence;
    const results = root.querySelector(".study-results");
    const currentBox = root.querySelector(".study-current");
    root.querySelector(".study-error").hidden = true;
    results.setAttribute("aria-busy", "true");
    results.innerHTML = '<p class="state-box" role="status">正在读取研究项目…</p>';
    try {
      const data = await request(endpoint + "/search", "POST", filters);
      if (!root.isConnected || sequence !== listSequence) return;
      const current = data.current;
      currentBox.innerHTML = '<span>当前研究项目</span><div>' +
        (current ? href(projectHref(current.study_id), esc(current.name), "study-inline-link") +
          '<small>' + esc(modes[current.mode]) + ' / ' + esc(current.scope_version) + '</small>'
          : '<strong>尚未选择</strong><small>可从项目列表设置当前项目。</small>') + '</div>' +
        (current ? scopeBadge(current) : "");
      if (!data.projects.length) {
        const filtered = filters.query || !["all", "open"].includes(filters.status);
        results.innerHTML = '<div class="state-box"><b>' +
          (filtered ? "没有符合条件的项目" : "暂无可显示的项目") +
          '</b><p>' + (filtered ? "尝试更换搜索词或项目状态。"
            : "新建项目以记录第一个研究问题与抽样范围。") + '</p></div>';
        return;
      }
      results.innerHTML = '<p class="study-result-count" role="status">共 ' + data.projects.length +
        ' 个项目</p><ul class="study-rows">' + data.projects.map(row => `
          <li class="study-row">
            <div class="study-row-main">
              <h2>${href(projectHref(row.study_id), esc(row.name), "study-inline-link")}</h2>
              <p>${textValue(row.subject || row.topic)}</p>
              ${row.objective ? '<p class="study-objective">' + esc(row.objective) + '</p>' : ""}
            </div>
            <div class="study-row-scope"><b>${esc(modes[row.mode])}</b><span>${esc(row.scope_version)} ${scopeBadge(row)}</span></div>
            <div class="study-row-status">${statusBadge(row.status)}<small>更新于 ${time(row.updated_at)}</small></div>
            <div class="study-row-action">${current?.study_id === row.study_id
              ? '<span class="study-selected">当前项目</span>'
              : row.status !== "archived"
                ? action("select", "设为当前", "secondary", 'data-study-id="' + esc(row.study_id) + '"') : ""}</div>
          </li>`).join("") + '</ul>';
    } catch (error) {
      if (!root.isConnected || sequence !== listSequence) return;
      results.innerHTML = '<p class="state-box">读取失败。请查询重试。</p>';
      errorMessage(error);
    } finally {
      if (sequence === listSequence) results.removeAttribute("aria-busy");
    }
  }

  const fields = {
    name: ["项目名称", 120], description: ["项目描述", 4000], background: ["研究背景", 4000],
    objective: ["研究目标", 4000], subject: ["研究对象", 4000],
    topic: [scopeLabels.topic, 1000], market: [scopeLabels.market, 240],
    language: [scopeLabels.language, 240], audience: [scopeLabels.audience, 4000],
    product_ids: ["产品引用 ID（每行一个）", 3000],
    product_category_ids: ["品类引用 ID（每行一个）", 3000],
    user_tasks: ["用户任务（每行一项）", 6000],
    source_preferences: ["数据来源偏好（每行一项）", 6000],
    inclusion_criteria: ["纳入标准（每行一项）", 6000],
    exclusion_criteria: ["排除标准（每行一项）", 6000],
    change_note: ["范围变更说明", 240],
  };

  function field(name, value, { rows = 0, required = false, full = false, hint = "" } = {}) {
    const [label, limit] = fields[name];
    const common = 'class="field" id="study-' + name + '" name="' + name + '" maxlength="' + limit + '"' +
      (required ? ' required' : '') + (hint ? ' aria-describedby="study-' + name + '-hint"' : '');
    const control = rows ? '<textarea ' + common + ' rows="' + rows + '">' + esc(value) + '</textarea>'
      : '<input ' + common + ' value="' + esc(value) + '">';
    return '<div class="study-field' + (full ? ' study-full' : '') + '" data-field="' + name +
      '"><label for="study-' + name + '">' + label + (required ? '（必填）' : '') + '</label>' + control +
      (hint ? '<small id="study-' + name + '-hint">' + hint + '</small>' : '') + '</div>';
  }

  function showForm() {
    const s = project?.scope || {};
    const to = project ? projectHref(project.study_id) : "#studies";
    const title = project ? "编辑研究项目" : "新建研究项目";
    root.innerHTML = href(to, project ? "返回项目详情" : "返回项目列表", "study-back") +
      head(title, "项目与研究范围保存在本机。修改范围后，旧版本仍可查看。") + `
      <form class="study-form" data-study-form="save" method="post" autocomplete="off">
        <section class="panel study-form-part">
          <header><h2>项目资料</h2></header>
          <div class="study-form-grid">
            ${field("name", project?.name, { required: true })}
            <div class="study-field"><label for="study-status">项目状态</label>
              <select class="field" id="study-status" name="status">${choices(
                Object.entries(states).filter(([key]) => key !== "archived"), project?.status || "draft"
              )}</select>
            </div>
            ${field("subject", project?.subject, { rows: 2 })}
            ${field("objective", project?.objective, { rows: 2 })}
            ${field("description", project?.description, { rows: 2 })}
            ${field("background", project?.background, { rows: 2 })}
          </div>
        </section>
        <section class="panel study-form-part">
          <header><h2>研究范围</h2></header>
          <div class="study-form-grid">
            <div class="study-field study-full"><label for="study-mode">研究模式</label>
              <select class="field" id="study-mode" name="mode" aria-describedby="study-mode-help">${choices(
                Object.entries(modes), s.mode || "open"
              )}</select>
              <small id="study-mode-help"></small>
            </div>
            ${field("topic", s.topic, { rows: 2, required: true, full: true })}
            ${field("product_ids", s.product_ids?.join("\n"), { rows: 2 })}
            ${field("product_category_ids", s.product_category_ids?.join("\n"), {
              rows: 2, hint: "使用已知的稳定品类 ID。范围标签不会给语料自动分配品类。",
            })}
            ${field("market", s.market)}
            ${field("language", s.language)}
            <div class="study-field"><label for="study-start">开始日期</label>
              <input class="field" id="study-start" name="start" type="date" value="${esc(s.date_window?.start)}"></div>
            <div class="study-field"><label for="study-end">结束日期</label>
              <input class="field" id="study-end" name="end" type="date" value="${esc(s.date_window?.end)}"></div>
            ${field("audience", s.audience, { rows: 2 })}
            ${field("user_tasks", s.user_tasks?.join("\n"), { rows: 2 })}
            ${field("source_preferences", s.source_preferences?.join("\n"), { rows: 2, full: true })}
            ${field("inclusion_criteria", s.inclusion_criteria?.join("\n"), { rows: 2 })}
            ${field("exclusion_criteria", s.exclusion_criteria?.join("\n"), { rows: 2 })}
            ${project ? field("change_note", "", {
              full: true, hint: "有范围变更时，说明会随新版本保存。",
            }) : ""}
          </div>
        </section>
        ${note}
        <div class="actions study-form-actions">
          <button type="submit" class="primary">保存项目</button>${href(to, "取消")}
        </div>
      </form>`;
    updateMode(root.querySelector(".study-form"));
  }

  function updateMode(form) {
    const mode = form.elements.mode.value;
    const controls = [
      ["product_ids", !["open", "single_category"].includes(mode), mode === "single_product"],
      ["product_category_ids", mode !== "open", ["single_category", "cross_category"].includes(mode)],
    ];
    for (const [key, visible, required] of controls) {
      form.querySelector('[data-field="' + key + '"]').hidden = !visible;
      form.elements[key].disabled = !visible;
      form.elements[key].required = required;
    }
    form.querySelector("#study-mode-help").textContent = modeHelp[mode];
  }

  function formData(form) {
    const values = new FormData(form);
    const value = (key) => String(values.get(key) || "").trim();
    const lines = (key) => value(key).split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const date = Object.fromEntries(["start", "end"].filter(key => value(key)).map(key => [key, value(key)]));
    return {
      name: value("name"), description: value("description"), background: value("background"),
      objective: value("objective"), subject: value("subject"), status: value("status"),
      change_note: value("change_note"),
      scope: {
        mode: value("mode"), topic: value("topic"), market: value("market"),
        language: value("language"), date_window: date,
        product_ids: lines("product_ids"), product_category_ids: lines("product_category_ids"),
        audience: value("audience"), user_tasks: lines("user_tasks"), source_preferences: lines("source_preferences"),
        inclusion_criteria: lines("inclusion_criteria"), exclusion_criteria: lines("exclusion_criteria"),
      },
    };
  }

  function scopeContents(s) {
    const { start, end } = s.date_window;
    const dateRange = start && end ? start + " 至 " + end
      : start ? "自 " + start : end ? "截至 " + end : "";
    const list = (items) => items.length
      ? '<ul>' + items.map(item => '<li>' + esc(item) + '</li>').join("") + '</ul>'
      : textValue("");
    return '<dl class="study-data">' +
      datum(scopeLabels.mode, esc(modes[s.mode])) +
      datum(scopeLabels.date_window, textValue(dateRange)) +
      datum(scopeLabels.market, textValue(s.market)) +
      datum(scopeLabels.language, textValue(s.language)) +
      datum(scopeLabels.audience, textValue(s.audience), "study-full") +
      (s.mode === "open" ? "" : datum(scopeLabels.product_category_ids, list(s.product_category_ids)) +
        datum(scopeLabels.product_ids, list(s.product_ids))) +
      datum(scopeLabels.user_tasks, list(s.user_tasks)) +
      datum(scopeLabels.source_preferences, list(s.source_preferences)) +
      datum(scopeLabels.inclusion_criteria, list(s.inclusion_criteria)) +
      datum(scopeLabels.exclusion_criteria, list(s.exclusion_criteria)) + '</dl>';
  }

  function scopeChanges(s) {
    return s.changed_fields.length
      ? "变更 " + s.changed_fields.map(key => scopeLabels[key] || key).join("、")
      : "初始范围";
  }

  function scopePanel(s, historical = false) {
    return '<section class="panel study-section study-scope"><header><div><h2>' +
      (historical ? '范围快照' : '当前研究范围') + '</h2><p>' +
      esc(s.scope_version) + ' / 创建于 ' + time(s.created_at) + '</p></div>' + scopeBadge(s) +
      '</header><p class="study-scope-topic">' + esc(s.topic) + '</p>' +
      (historical ? '<p class="study-muted">' + esc(scopeChanges(s)) + '</p>' : "") +
      (s.change_note ? '<p class="study-version-note">' + esc(s.change_note) + '</p>' : "") +
      scopeContents(s) +
      '<dl class="study-data study-ids">' +
      datum("范围版本 ID", '<code>' + esc(s.scope_id) + '</code>') +
      datum("冻结时间", s.frozen_at ? time(s.frozen_at) : "待冻结") + '</dl></section>';
  }

  function showDetail(p) {
    project = p;
    const active = p.status !== "archived";
    const base = projectHref(p.study_id);
    const actions = active
      ? href(base + "/edit", "编辑项目", "primary") +
        (p.is_current ? "" : action("select", "设为当前")) + action("archive", "归档项目")
      : action("restore", "恢复项目", "primary");
    root.innerHTML = href("#studies", "返回项目列表", "study-back") + head(
      p.name, statusBadge(p.status) + (p.is_current ? ' <span class="study-selected">当前项目</span>' : ''), actions
    ) + note + `
      <div class="study-detail">
        <div>
          <section class="panel study-section">
            <header><h2>项目概况</h2></header>
            <dl class="study-data">
              ${datum("研究对象", textValue(p.subject))}
              ${datum("研究目标", textValue(p.objective))}
              ${datum("项目描述", textValue(p.description))}
              ${datum("研究背景", textValue(p.background))}
              ${datum("创建时间", time(p.created_at))}
              ${datum("最后更新", time(p.updated_at))}
              ${datum("项目 ID", '<code>' + esc(p.study_id) + '</code>', "study-full")}
            </dl>
          </section>
          ${scopePanel(p.scope)}
        </div>
        <aside>
          <section class="panel study-section">
            <header><h2>范围版本历史</h2></header>
            <ol class="study-history">${p.scope_history.map(s => `<li><div>
              ${href(base + "/scopes/" + s.scope_id, "查看 " + esc(s.scope_version), "study-inline-link")}
              ${s.scope_id === p.scope.scope_id ? '<span class="study-muted">当前版本</span>' : ""}
              ${scopeBadge(s)}</div><small>${time(s.created_at)}</small>
              <p>${esc(scopeChanges(s))}</p>${s.change_note ? '<p>' + esc(s.change_note) + '</p>' : ""}</li>`).join("")}</ol>
            ${active && !p.scope.frozen_at
              ? '<div class="actions">' + action("freeze", "冻结当前范围") + '</div>' : ""}
          </section>
          <section class="panel study-section">
            <header><h2>研究记录</h2></header>
            <p>范围版本 <strong>${p.scope_history.length}</strong> 个，已冻结 <strong>${p.scope_history.filter(s => s.frozen_at).length}</strong> 个。</p>
            <div class="actions">${href("#imports/" + p.study_id, "查看数据导入")}</div>
            <p class="study-muted">采集与分析记录将在对应模块接入后显示。</p>
          </section>
        </aside>
      </div>`;
  }

  async function load() {
    if (!id) {
      showList();
      await readList();
      return;
    }
    if (id === "new") {
      showForm();
      return;
    }
    try {
      const record = await api(scopeId ? url + "/scopes/" + scopeId : url);
      if (!root.isConnected) return;
      if (scopeId) {
        root.innerHTML = href(projectHref(id), "返回项目详情", "study-back") +
          head("范围版本 " + record.scope_version, "查看该版本保存时使用的研究边界。") + scopePanel(record, true);
      } else if (view === "edit" && record.status !== "archived") {
        project = record;
        showForm();
      } else {
        showDetail(record);
      }
    } catch (error) {
      if (root.isConnected) {
        root.innerHTML = href("#studies", "返回项目列表", "study-back") +
          head("无法读取研究项目", esc(error.message), action("retry", "重新读取"));
      }
    }
  }

  async function perform(button, operation, message, errorHost) {
    if (busy) return;
    busy = true;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    const label = button.textContent;
    if (button.type === "submit") button.textContent = "正在保存…";
    errorHost.querySelector(".study-error").hidden = true;
    try {
      await operation();
      if (root.isConnected) tell(message);
    } catch (error) {
      if (root.isConnected) errorMessage(error, errorHost);
    } finally {
      busy = false;
      button.disabled = false;
      button.removeAttribute("aria-busy");
      if (button.type === "submit") button.textContent = label;
    }
  }

  root.addEventListener("input", event => {
    const alert = event.target.closest(".study-form")?.querySelector(".study-error");
    if (alert) alert.hidden = true;
  });

  root.addEventListener("change", event => {
    if (event.target.id === "study-mode") updateMode(event.target.form);
    if (event.target.matches(".study-filters select")) event.target.form.requestSubmit();
  });

  root.addEventListener("submit", async event => {
    const form = event.target;
    if (!form.dataset.studyForm) return;
    event.preventDefault();
    if (form.dataset.studyForm === "search") {
      filters = Object.fromEntries(new FormData(form));
      await readList();
      return;
    }
    const data = formData(form);
    await perform(form.querySelector('[type="submit"]'), async () => {
      if (project) data.revision = project.revision;
      else {
        requestKey ??= crypto.randomUUID();
        data.request_key = requestKey;
      }
      const saved = await request(url, project ? "PUT" : "POST", data);
      if (root.isConnected) location.hash = projectHref(saved.study_id);
    }, "项目已保存。", form);
  });

  root.addEventListener("click", async event => {
    const button = event.target.closest("[data-study-action]");
    if (!button || busy) return;
    const kind = button.dataset.studyAction;
    if (kind === "retry") {
      await load();
      return;
    }
    if (kind === "archive" && !window.confirm("归档此项目？所有范围版本与关联记录会保留。当前项目如为此项目，将取消选择。")) return;
    if (kind === "freeze" && !window.confirm("冻结当前范围供后续批次引用？之后调整范围会创建新的待冻结版本。")) return;
    const suffix = {
      select: "/select", archive: "?revision=" + project?.revision, restore: "/restore",
      freeze: "/scopes/" + project?.scope.scope_id + "/freeze",
    }[kind];
    const message = {
      select: "已切换当前研究项目。", archive: "项目已归档。", restore: "项目已恢复。", freeze: "当前范围已冻结。",
    }[kind];
    const target = button.dataset.studyId ? endpoint + "/" + button.dataset.studyId : url;
    await perform(button, async () => {
      const result = await request(target + suffix, kind === "archive" ? "DELETE" : "POST",
        kind === "restore" ? { revision: project.revision } : null);
      if (!root.isConnected) return;
      if (id) showDetail(result);
      else await readList();
    }, message, root);
  });

  load();
}
