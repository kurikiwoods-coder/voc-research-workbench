const endpoint = "/api/imports";
const beforeImport = ["上传文件", "字段映射", "质量检查", "导入结果"];
const labels = {
  staged: "结构合格", pending_review: "待审核", duplicate: "疑似重复", rejected: "异常拒收",
  imported: "已暂存", revoked: "已撤销", unknown: "未确认", public: "公开",
  private: "非公开", internal: "内部 / CX", error: "错误", warning: "提醒",
};
const dateTime = new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" });
const time = value => dateTime.format(new Date(value));
const urlFor = study => endpoint + "/" + study;
const homeFor = study => "#imports/" + study;
const batchFor = (study, id) => homeFor(study) + "/batches/" + id;
const badge = state => '<span class="status ' + ({
  staged: "PASS", imported: "PASS", pending_review: "PENDING", rejected: "FAIL",
  duplicate: "PENDING",
}[state] || "NOT_TESTED") + '">' + labels[state] + '</span>';
const alert = '<p class="study-error" role="alert" hidden></p>';

export function mountImports(root, route, { api, esc, ic, choices, tell }) {
  const [, routeStudy, , routeBatch] = route.split("/");
  let project, projectChoices, history, file, targetScope, selectedFile, inspected, quality;
  let sheetIndex = 0, mapping = {}, privacy = "unknown", issueOffset = 0;
  let batchOffset = 0, rowOffset = 0, rowStatus = "all", busy = false;
  const fixed = () => urlFor(file.study_id) + "/uploads/" + file.file_id;
  const link = (href, label, kind = "secondary") =>
    '<a class="' + kind + '" href="' + esc(href) + '">' + label + '</a>';
  const button = (name, label, kind = "secondary", data = "") =>
    '<button class="' + kind + '" type="button" data-import-action="' + name + '" ' + data + '>' + label + '</button>';
  function header(title, help, step, action = "") {
    return `<header class="page-head import-head"><div><h1 tabindex="-1">${esc(title)}</h1><p>${help}</p></div>
      <div class="actions">${action}</div></header>
      <ol class="import-steps" aria-label="导入进度">${beforeImport.map((label, index) =>
        `<li ${index === step ? 'aria-current="step"' : ""}>${esc(label)}</li>`).join("")}</ol>${alert}`;
  }
  function focusStep() {
    root.querySelector(".import-head h1")?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
  function setError(error) {
    const message = root.querySelector("[role=alert]");
    if (message) {
      message.textContent = error.message;
      message.hidden = false;
    }
  }
  function request(path, method, data, filename) {
    const headers = { "X-VOC-Action": "connectivity" };
    if (filename) {
      headers["Content-Type"] = "application/octet-stream";
      headers["X-VOC-Filename"] = encodeURIComponent(filename);
    } else if (data) headers["Content-Type"] = "application/json";
    return api(path, { method, headers, ...(data ? { body: filename ? data : JSON.stringify(data) } : {}) });
  }
  async function perform(task, label = "正在读取…") {
    if (busy) return;
    busy = true;
    const controls = [...root.querySelectorAll("input, select, button")].filter(item => !item.disabled);
    controls.forEach(item => item.disabled = true);
    const message = root.querySelector("[role=alert]");
    if (message) message.hidden = true;
    const status = document.createElement("p");
    status.className = "import-busy";
    status.setAttribute("role", "status");
    status.textContent = label;
    root.querySelector(".import-steps")?.after(status);
    try {
      await task();
    } catch (error) {
      if (root.isConnected) setError(error);
    } finally {
      busy = false;
      controls.forEach(item => { if (item.isConnected) item.disabled = false; });
      status.remove();
      if (root.querySelector("#import-file")) uploadState();
    }
  }
  function bodyPanel(title, content, description = "") {
    return `<section class="panel import-panel"><header><h2>${title}</h2>
      ${description ? '<p>' + description + '</p>' : ""}</header>${content}</section>`;
  }
  const pageLink = () => link(homeFor(project.study_id), "返回导入首页");
  const studyLink = () => link("#studies/" + project.study_id, "进入研究项目");
  const valueLabel = count => new Intl.NumberFormat("zh-CN").format(count);

  function summaryCards(summary) {
    const keys = ["total", "staged", "pending_review", "duplicate", "rejected"];
    return '<dl class="import-counts">' + keys.map(key =>
      '<div><dt>' + (labels[key] || "记录总数") + '</dt><dd>' + valueLabel(summary[key]) + '</dd></div>'
    ).join("") + '</dl>';
  }
  function composition(summary) {
    const counts = (values, translate) => Object.entries(values).map(([name, count]) =>
      `<li>${esc(translate ? labels[name] : name)} <b>${valueLabel(count)}</b></li>`).join("");
    return `<dl class="import-composition"><div><dt>来源类型</dt><dd><ul>${counts(summary.source_types)}</ul></dd></div>
      <div><dt>隐私等级</dt><dd><ul>${counts(summary.privacy_levels, true)}</ul></dd></div></dl>`;
  }
  function pages(offset, more, name) {
    if (!offset && !more) return "";
    return `<div class="actions import-pagination" aria-label="翻页">
      ${button(name, "上一页", "secondary", 'data-offset="' + Math.max(0, offset - 20) + '"' + (!offset ? " disabled" : ""))}
      <span>第 ${offset / 20 + 1} 页</span>
      ${button(name, "下一页", "secondary", 'data-offset="' + (offset + 20) + '"' + (!more ? " disabled" : ""))}
      </div>`;
  }
  function uploadState() {
    const button = root.querySelector('[data-import-action="upload"]');
    if (button) button.disabled = busy || !selectedFile || !targetScope || project?.status === "archived";
    const name = root.querySelector("#import-file-name");
    if (name) name.textContent = selectedFile
      ? selectedFile.name + "（" + Math.ceil(selectedFile.size / 1024) + " KiB）" : "未选择文件";
  }

  function drawHome() {
    const chosen = project?.study_id || "";
    const archived = project?.status === "archived";
    const frozen = project?.scope_history.filter(s => s.frozen_at) || [];
    const options = projectChoices.map(p => [p.study_id, p.name + (p.status === "archived" ? "（已归档）" : "")]);
    if (!chosen) options.unshift(["", "请选择项目"]);
    const target = `<div class="import-target">
      <label>研究项目<select class="field" id="import-project">${choices(options, chosen)}</select></label>
      <label>范围版本<select class="field" id="import-scope" ${!frozen.length || archived ? "disabled" : ""}>
        ${choices([["", "请选择已冻结范围"], ...frozen.map(s =>
          [s.scope_id, s.scope_version + (s.scope_id === project.scope.scope_id ? "（当前范围）" : "")])], targetScope || "")}
      </select></label></div>`;
    const hint = !project ? "选择目标项目，或从研究项目中新建课题。"
      : archived ? "该项目已归档。恢复后可继续导入，已有批次仍可查看。"
      : !frozen.length ? "此项目还没有冻结的研究范围。请先进入研究项目冻结范围。"
      : "当前范围 " + esc(project.scope.scope_version) + "，导入将绑定上方选定的冻结版本。";
    const uploader = `<div id="import-drop" class="import-drop" ${!project || archived ? 'aria-disabled="true"' : ""}>
      ${ic("download")}<div><b>选择或拖入文件</b><p>CSV / XLSX · 8 MiB 以内 · 每表最多 5,000 条</p>
      <input type="file" id="import-file" accept=".csv,.xlsx" aria-label="选择导入文件" ${!project || archived ? "disabled" : ""}>
      <p id="import-file-name" role="status"></p></div></div>
      <div class="actions import-row-actions">${button("upload", "上传并解析", "primary", "disabled")}
      ${link(endpoint + "/templates/csv", "下载 CSV 模板")}${link(endpoint + "/templates/xlsx", "下载 XLSX 模板")}</div>`;
    const drafts = history?.drafts?.length ? `<ul class="import-history">${history.drafts.map(item =>
      `<li><div><strong>${esc(item.filename)}</strong><small>${esc(item.scope_version)} · ${esc(time(item.uploaded_at))}</small></div>
        <div class="actions">${archived ? "" : button("resume", "继续映射", "secondary", 'data-id="' + esc(item.file_id) + '"')}
        ${button("discard", "丢弃文件", "quiet", 'data-id="' + esc(item.file_id) + '"')}</div></li>`).join("")}</ul>` : "";
    const batches = history?.batches?.length ? `<ul class="import-history">${history.batches.map(b =>
      `<li><div>${link(batchFor(chosen, b.batch_id), esc(b.filename), "study-inline-link")}
        <small>${esc(b.sheet_name)} · ${esc(b.scope_version)} · ${esc(time(b.created_at))}</small></div>
        <span>${valueLabel(b.summary.total)} 条 ${badge(b.status)}</span></li>`).join("")}</ul>`
      + pages(batchOffset, history.more, "history-page") : '<p class="state-box">这个项目还没有导入批次。</p>';
    root.innerHTML = header("数据导入中心", "将研究表格导入本机，保留来源、行号和冻结范围。", 0,
      project ? studyLink() : link("#studies", "研究项目"))
      + bodyPanel("目标与文件", target + '<p class="import-hint">' + hint + '</p>' + uploader)
      + (drafts ? bodyPanel("待导入文件", drafts) : "")
      + (project ? bodyPanel("项目导入历史", batches) : "");
    uploadState();
  }

  function targetLine() {
    const version = inspected?.scope_version || project.scope_history.find(s => s.scope_id === file.scope_id)?.scope_version;
    return `<div class="import-context"><div><small>导入目标</small><b>${esc(project.name)} · ${esc(version)}</b></div>
      <div><small>原始文件</small><b>${esc(file.filename)}</b></div>
      <div><small>工作表</small><b>${esc(file.sheets[sheetIndex])}</b></div></div>`;
  }

  function drawMap() {
    const mapped = Object.fromEntries(Object.entries(mapping).map(([field, index]) => [index, field]));
    const controls = `<div class="import-target">
      <label>工作表<select id="import-sheet" class="field">${choices(file.sheets.map((name, index) => [String(index), name]), String(sheetIndex))}</select></label>
      <label>批次隐私等级<select id="import-privacy" class="field">${choices(["unknown", "public", "private", "internal"].map(v =>
        [v, labels[v]]), privacy)}</select></label></div>`;
    const definitions = inspected.standard_fields;
    const fields = [["", "保留为扩展字段"], ...definitions.map(def =>
      [def.id, def.label + (def.required ? "（必填）" : "")])];
    const pairs = `<div class="import-pair-head"><b>文件原始字段</b><b>工作台字段</b></div>
      <div>${inspected.columns.map((name, index) =>
        `<div class="import-pair"><label for="import-map-${index}">${esc(name || "空表头")} <small>第 ${index + 1} 列</small></label>
          <select id="import-map-${index}" class="field" data-map-column="${index}">${choices(fields, mapped[index] || "")}</select></div>`).join("")}</div>`;
    const sample = `<div class="import-scroll" tabindex="0" role="region" aria-label="原始文件预览">
      <table class="table"><thead><tr><th>文件行号</th>${inspected.columns.map(name => "<th>" + esc(name || "空表头") + "</th>").join("")}</tr></thead>
      <tbody>${inspected.samples.map(row => "<tr><td>" + row.line_number + "</td>" +
        inspected.columns.map((_, i) => "<td>" + ('<span class="import-muted">' + (row.populated[i] ? "有内容" : "空") + '</span>') + "</td>").join("") + "</tr>").join("")}</tbody></table></div>`;
    root.innerHTML = header("字段映射", "核对自动建议。未对应到标准字段的列会作为扩展字段保留。", 1, pageLink())
      + targetLine() + bodyPanel("工作表与隐私", controls)
      + bodyPanel("对应文件字段", pairs, "请映射一个用户原话字段。来源、时间、许可和隐私信息缺失时会提示审核。")
      + bodyPanel("原始数据结构", sample,
        "共 " + valueLabel(inspected.total) + " 条记录，表头在第 " + inspected.header_line + " 行"
        + (inspected.encoding ? "，编码 " + esc(inspected.encoding) : ""))
      + '<div class="actions import-row-actions">' + button("quality", "检查数据质量", "primary") + '</div>';
  }

  function drawFileProblem(error) {
    root.innerHTML = header("字段映射", "请选择可读取的工作表。", 1, pageLink()) + targetLine()
      + bodyPanel("工作表", `<label>选择工作表 <select id="import-sheet" class="field">${choices(
        file.sheets.map((name, index) => [String(index), name]), String(sheetIndex))}</select></label>`);
    setError(error);
  }

  async function readSheet() {
    try {
      const response = await api(fixed() + "?sheet_index=" + sheetIndex);
      if (!root.isConnected) return;
      inspected = response;
      mapping = { ...response.suggested_mapping };
      drawMap();
    } catch (error) {
      if (root.isConnected) {
        inspected = null;
        drawFileProblem(error);
      }
    }
  }

  function plan() { return { sheet_index: sheetIndex, mapping, privacy }; }

  function drawQuality() {
    const { summary, issue_rows: issueRows, sample_rows: samples } = quality;
    const issues = summary.issues.length ? `<ul class="import-issues">${summary.issues.map(issue =>
      `<li><b>${esc(labels[issue.severity])}</b> ${esc(issue.message)} <span>${issue.count} 条</span></li>`).join("")}</ul>`
      : '<p>已通过结构检查。原话与来源仍需核验。</p>';
    const lines = issueRows.length ? `<ul class="import-history">${issueRows.map(row =>
      `<li><div><b>第 ${row.line_number} 行</b> ${badge(row.status)}
        <small>${esc(row.issues.map(issue => issue.message).join("；"))}
        ${row.duplicate_of_line ? " · 与第 " + row.duplicate_of_line + " 行重复" : ""}</small></div></li>`).join("")}</ul>
        ${pages(issueOffset, quality.more_issues, "issue-page")}` : "";
    const sample = `<ul class="import-history">${samples.map(row => `<li>
      <div><b>第 ${row.line_number} 行</b> ${badge(row.status)}
      <p class="import-quote">${row.status === "rejected" ? "请查看本行质量检查结果。" : "原话待许可及人工核验后查看。"}</p></div></li>`).join("")}</ul>`;
    const canSave = summary.staged + summary.pending_review > 0;
    root.innerHTML = header("数据质量检查", "核对目标与行级结果。暂存数据需经过后续审核才能成为正式研究证据。", 2, pageLink())
      + targetLine() + bodyPanel("确认与统计", summaryCards(summary) + composition(summary))
      + bodyPanel("问题分类", issues + lines)
      + bodyPanel("已映射的行样本", sample)
      + '<div class="actions import-row-actions">' + button("map", "返回修改映射")
      + button("confirm", "确认导入", "primary", canSave ? "" : "disabled") + '</div>'
      + (canSave ? "" : '<p class="import-hint">全部记录均无法暂存。请修正源文件并重新上传。</p>');
  }

  async function checkQuality(offset) {
    const response = await request(fixed() + "/preview", "POST", { ...plan(), offset });
    if (!root.isConnected) return;
    quality = response;
    issueOffset = offset;
    drawQuality();
  }

  function drawResult({ batch: b, rows, more }) {
    const entry = urlFor(b.study_id) + "/batches/" + b.batch_id;
    const fields = b.headers.map((name, index) => [name || "空表头",
      Object.keys(b.mapping).find(field => b.mapping[field] === index) || "扩展字段"]);
    const details = `<dl class="import-composition"><div><dt>项目与范围</dt><dd>${esc(b.project_name)} · ${esc(b.scope_version)}
      <br><code>${esc(b.scope_id)}</code></dd></div>
      <div><dt>源文件与工作表</dt><dd>${esc(b.filename)} · ${esc(b.sheet_name)} · 表头在第 ${b.header_line} 行</dd></div>
      <div><dt>导入时间</dt><dd>${esc(time(b.created_at))}</dd></div>
      <div><dt>批次 ID</dt><dd><code>${esc(b.batch_id)}</code></dd></div></dl>
      <details><summary>查看字段映射</summary><dl class="import-composition">${fields.map(([name, field]) =>
        `<div><dt>${esc(name)}</dt><dd>${esc(field)}</dd></div>`).join("")}</dl></details>`;
    const list = rows.length ? '<ul class="import-history">' + rows.map(r => `<li><div>
      <b>第 ${r.line_number} 行</b> ${badge(r.status)} <small>${esc(labels[r.privacy])}</small>
      ${r.issues.length ? "<p>" + esc(r.issues.map(issue => issue.message).join("；")) + "</p>" : ""}
      ${r.content_restricted ? '<p class="import-muted">此行原文和原始字段已限制查看。</p>' :
      `<details><summary>查看本机原始字段</summary><p class="import-quote">${esc(r.raw_text) || "原话为空"}</p>
      <dl class="import-composition">${r.originals.map((value, index) =>
        `<div><dt>${esc(b.headers[index] || "第 " + (index + 1) + " 列")}</dt><dd>${esc(value) || "空"}</dd></div>`
      ).join("")}</dl></details>`}</div></li>`).join("") + '</ul>' : '<p class="state-box">没有符合所选状态的记录。</p>';
    root.innerHTML = header("导入结果", "核对本机暂存和拒收记录。", 3, pageLink() + studyLink())
      + bodyPanel("批次详情 " + badge(b.status), details + summaryCards(b.summary) + composition(b.summary)
        + '<div class="actions import-row-actions">' + link(entry + "/errors.csv", "下载错误报告")
        + (b.revoked_at ? '<span class="import-muted">撤销于 ' + esc(time(b.revoked_at)) + '</span>'
          : button("revoke", "撤销批次")) + '</div>')
      + bodyPanel("导入记录", `<label class="import-record-filter">记录状态<select id="import-status" class="field">
        ${choices([["all", "全部记录"], ...["staged", "pending_review", "duplicate", "rejected"].map(s => [s, labels[s]])], rowStatus)}
        </select></label>` + list + pages(rowOffset, more, "row-page"));
  }

  async function loadResult() {
    const data = await api(urlFor(routeStudy) + "/batches/" + routeBatch + "?status=" + rowStatus + "&offset=" + rowOffset);
    if (root.isConnected) drawResult(data);
  }

  async function loadHome() {
    const all = await request("/api/studies/search", "POST", { status: "all" });
    projectChoices = all.projects;
    const id = routeStudy || all.current?.study_id;
    if (id) {
      [project, history] = await Promise.all([
        api("/api/studies/" + id), api(urlFor(id) + "/batches?offset=" + batchOffset)
      ]);
      targetScope = project.scope.frozen_at ? project.scope.scope_id : "";
      if (routeBatch) {
        await loadResult();
        return;
      }
    }
    if (root.isConnected) drawHome();
  }

  function selectFile(picked) {
    if (busy || !project || project.status === "archived") return;
    const alertLine = root.querySelector("[role=alert]");
    if (alertLine) alertLine.hidden = true;
    selectedFile = picked;
    if (picked && (!/\.(xlsx|csv)$/i.test(picked.name) || picked.size > 8 * 1024 * 1024 || !picked.size)) {
      selectedFile = null;
      setError(new Error("请选择不超过 8 MiB 的非空 CSV 或 XLSX 文件。"));
    }
    uploadState();
  }

  root.addEventListener("change", event => {
    if (busy) return;
    const control = event.target;
    if (control.id === "import-project") {
      location.hash = control.value ? homeFor(control.value) : "#imports";
      return;
    }
    if (control.id === "import-scope") {
      targetScope = control.value;
      uploadState();
    }
    if (control.id === "import-file") selectFile(control.files[0]);
    if (control.id === "import-privacy") privacy = control.value;
    if (control.id === "import-sheet") {
      sheetIndex = Number(control.value);
      perform(readSheet, "正在解析工作表…");
    }
    if (control.id === "import-status") {
      rowStatus = control.value;
      rowOffset = 0;
      perform(loadResult);
    }
    if (control.dataset.mapColumn != null) {
      const index = Number(control.dataset.mapColumn);
      const previous = Object.keys(mapping).find(field => mapping[field] === index);
      if (previous) delete mapping[previous];
      if (control.value) {
        if (mapping[control.value] != null) {
          root.querySelector('[data-map-column="' + mapping[control.value] + '"]').value = "";
        }
        mapping[control.value] = index;
      }
    }
  });
  root.addEventListener("dragover", event => {
    if (event.target.closest("#import-drop")) event.preventDefault();
  });
  root.addEventListener("drop", event => {
    if (!event.target.closest("#import-drop")) return;
    event.preventDefault();
    if (event.dataTransfer.files.length !== 1) {
      setError(new Error("一次请选择一个导入文件。"));
      return;
    }
    selectFile(event.dataTransfer.files[0]);
  });
  root.addEventListener("click", event => {
    const control = event.target.closest("[data-import-action]");
    if (!control || busy) return;
    const { importAction: action, id, offset } = control.dataset;
    if (action === "upload") perform(async () => {
      file = await request(urlFor(project.study_id) + "/scopes/" + targetScope + "/uploads",
        "POST", selectedFile, selectedFile.name);
      sheetIndex = 0;
      privacy = "unknown";
      if (root.isConnected) {
        await readSheet();
        if (root.isConnected) focusStep();
      }
    }, "正在上传并解析文件…");
    if (action === "resume") perform(async () => {
      const draft = history.drafts.find(item => item.file_id === id);
      file = { ...draft, study_id: project.study_id };
      sheetIndex = 0;
      privacy = "unknown";
      await readSheet();
      if (root.isConnected) focusStep();
    }, "正在读取待导入文件…");
    if (action === "discard" && window.confirm("丢弃此待导入文件及本机副本？")) perform(async () => {
      await request(urlFor(project.study_id) + "/uploads/" + id, "DELETE");
      await loadHome();
      if (root.isConnected) tell("已丢弃待导入文件。");
    });
    if (action === "map") {
      drawMap();
      focusStep();
    }
    if (action === "quality") perform(async () => {
      await checkQuality(0);
      if (root.isConnected) focusStep();
    }, "正在检查数据质量…");
    if (action === "issue-page") perform(() => checkQuality(Number(offset)), "正在检查数据质量…");
    if (action === "confirm") perform(async () => {
      const result = await request(fixed() + "/confirm", "POST", { ...plan(), preview_token: quality.preview_token });
      if (root.isConnected) {
        tell("本机导入批次已保存。");
        location.hash = batchFor(result.study_id, result.batch_id);
      }
    }, "正在保存导入批次…");
    if (action === "history-page") {
      batchOffset = Number(offset);
      perform(loadHome);
    }
    if (action === "row-page") {
      rowOffset = Number(offset);
      perform(loadResult);
    }
    if (action === "revoke" && window.confirm("撤销此批次的后续使用？本机文件和审计记录将保留。")) perform(async () => {
      await request(urlFor(routeStudy) + "/batches/" + routeBatch + "/revoke", "POST");
      await loadResult();
      if (root.isConnected) tell("导入批次已撤销。");
    });
    if (action === "retry") perform(loadHome);
  });

  root.innerHTML = header(routeBatch ? "导入结果" : "数据导入中心", "", routeBatch ? 3 : 0)
    + '<div class="panel state-box">' + button("retry", "重新读取") + '</div>';
  perform(loadHome);
}
