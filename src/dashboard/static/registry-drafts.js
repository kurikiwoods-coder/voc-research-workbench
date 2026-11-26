const actions = { candidate: "新建候选", amend: "修订", merge: "合并", split: "拆分", retire: "停用", restore: "从历史版本恢复" };
const states = { draft: "草稿", submitted: "待审核", withdrawn: "已撤回" };
const messages = {
  NAME_REQUIRED: "补充名称", DEFINITION_REQUIRED: "补充定义",
  INCLUSION_CRITERIA_REQUIRED: "补充纳入标准", EXCLUSION_CRITERIA_REQUIRED: "补充排除标准",
  PARENT_MISSING: "主任务待确认", PRIMARY_REQUIRED: "主任务待确认",
  REPRESENTATIVES_INSUFFICIENT: "独立代表发生不足",
};
const editorialFields = [
  ["name", "名称"], ["definition", "定义"], ["inclusion_criteria", "纳入标准"], ["exclusion_criteria", "排除标准"],
];

export function mountRegistryDrafts(root, { api, esc, registryQuery, getCurrent }) {
  const button = (action, text, dataset = "") =>
    `<button class="btn" type="button" data-draft-action="${action}" ${dataset}>${text}</button>`;
  const issues = values => values.map(value => `<li>${esc(messages[value] || value)}</li>`).join("");
  const url = (...segments) => "/api/studies/" + [study, "registry", "drafts", ...segments].map(encodeURIComponent).join("/");
  root.innerHTML = `<h2 id="registry-draft-title">项目候选草稿</h2>
    <div class="relation-filters"><label>草稿项目<select class="field" aria-label="草稿项目" id="registry-draft-project"><option value="">请选择项目</option></select></label></div>
    <div class="actions registry-actions">${button("projects", "刷新项目授权")}${button("new", "新建候选", "hidden")}</div>
    <p class="state-box" id="registry-draft-notice" role="status">正在读取项目授权…</p>
    <div id="registry-draft-list"></div>
    <div class="actions registry-actions" id="registry-draft-pages"></div>
    <section class="registry-subsection" id="registry-draft-editor" tabindex="-1" hidden></section>`;

  const projectSelect = root.querySelector("#registry-draft-project");
  const notice = root.querySelector("#registry-draft-notice");
  const list = root.querySelector("#registry-draft-list");
  const pages = root.querySelector("#registry-draft-pages");
  const editor = root.querySelector("#registry-draft-editor");
  const createButton = root.querySelector('[data-draft-action="new"]');
  let study = "";
  let projectSequence = 0;
  let studyEpoch = 0;
  let listSequence = 0;
  let editorEpoch = 0;
  let focusPoll = null;
  let offset = 0;
  let authorized = false;
  let draft = null;
  let preparation = null;
  let pending = null;
  let dirty = false;
  let visibleEvidence = null;

  function showEditorMessage(text, alert = false) {
    const status = editor.querySelector("[data-draft-status]");
    if (!status) return;
    status.setAttribute("role", alert ? "alert" : "status");
    status.textContent = text;
  }

  function clearEditor() {
    editorEpoch += 1;
    draft = null;
    preparation = null;
    pending = null;
    dirty = false;
    visibleEvidence = null;
    editor.replaceChildren();
    editor.hidden = true;
  }

  function clearPrivate(text) {
    studyEpoch += 1;
    authorized = false;
    createButton.hidden = true;
    list.replaceChildren();
    pages.replaceChildren();
    clearEditor();
    notice.textContent = text;
  }

  function denied() {
    study = "";
    clearPrivate("项目授权已撤销或当前不可用，草稿已清除。");
    projectSelect.replaceChildren(new Option("请选择项目", ""));
    loadProjects(false);
  }

  async function loadProjects(showNotice = true) {
    const sequence = ++projectSequence;
    if (showNotice) notice.textContent = "正在读取项目授权…";
    try {
      const data = await api("/api/registry/projects");
      if (sequence !== projectSequence || !root.isConnected) return;
      projectSelect.replaceChildren(new Option("请选择项目", ""),
        ...data.items.map(item => new Option(item.name, item.study_id)));
      if (study && data.items.some(item => item.study_id === study)) {
        projectSelect.value = study;
        if (showNotice) loadDrafts(offset);
      } else if (study) {
        study = "";
        clearPrivate("项目授权已撤销或当前不可用，草稿已清除。");
      } else if (showNotice) {
        notice.textContent = data.items.length ? "请选择有权编辑草稿的研究项目。" : "暂无获准编辑草稿的项目。";
      }
    } catch (error) {
      if (sequence !== projectSequence || !root.isConnected) return;
      study = "";
      projectSelect.replaceChildren(new Option("请选择项目", ""));
      clearPrivate(error.message);
    }
  }

  async function loadDrafts(nextOffset = 0) {
    if (!study) return;
    const epoch = studyEpoch;
    const sequence = ++listSequence;
    notice.textContent = "正在读取草稿…";
    try {
      const data = await api(registryQuery(url(), { limit: 25, offset: nextOffset }));
      if (!root.isConnected || epoch !== studyEpoch || sequence !== listSequence) return;
      offset = nextOffset;
      authorized = true;
      createButton.hidden = false;
      notice.textContent = data.items.length ? "" : "此项目暂无候选草稿。";
      list.innerHTML = `<ul class="relation-list">${data.items.map(item =>
        `<li><h3>${button("open", esc(item.definition.name || item.intent_id), `data-draft-id="${esc(item.draft_id)}"`)}</h3>
        <p>${esc(item.intent_id)} · ${states[item.state]} · 修订 ${esc(item.revision)}${item.lifecycle_status === "pending_parent" ? " · 主任务待确认" : ""}</p></li>`
      ).join("")}</ul>`;
      pages.innerHTML = `${offset ? button("previous", "上一页") : ""}${data.next_offset != null ? button("next", "下一页") : ""}`;
    } catch (error) {
      if (!root.isConnected || epoch !== studyEpoch || sequence !== listSequence) return;
      if ([403, 404].includes(error.status)) denied();
      else {
        clearPrivate(error.message);
        pages.innerHTML = button("reload", "重试读取草稿");
      }
    }
  }

  function values(input) {
    return input.split(/[\r\n,，]+/).map(value => value.trim()).filter(Boolean);
  }

  function renderEditor(text = "") {
    const item = draft;
    const kind = item?.kind || preparation.kind;
    const definition = item?.definition || preparation.intent || {};
    const changesAllowed = !item || item.state === "draft";
    const restoration = !item && kind === "restore";
    const meta = item ? `${states[item.state]} · 修订 ${item.revision}` : "未保存草稿";
    editor.hidden = false;
    editor.innerHTML = `<h3>${actions[kind]}${item ? " · " + esc(item.intent_id) : ""}</h3>
      <p>${meta}${item?.lifecycle_status === "pending_parent" ? " · 主任务待确认" : ""}</p>
      ${item?.reason ? `<p>最近变更理由 ${esc(item.reason)}</p>` : ""}
      <form id="registry-draft-form" autocomplete="off">
        <fieldset class="registry-editor" ${changesAllowed && !restoration ? "" : "disabled"}>
          <div class="relation-filters">
            ${editorialFields.map(([key, label]) => `<label class="registry-wide">${label}${key === "name"
              ? `<input class="field" name="${key}" maxlength="4000" value="${esc(definition[key])}">`
              : `<textarea class="field" aria-label="${label}" name="${key}" rows="2" maxlength="4000">${esc(definition[key])}</textarea>`}</label>`).join("")}
            <label>主任务大类 ID<input class="field" name="primary_category_id" maxlength="128" value="${esc(definition.primary_category_id)}"></label>
            <label>次任务大类 ID<textarea class="field" name="secondary_category_ids" rows="2" placeholder="每行一个 ID">${esc((definition.secondary_category_ids || []).join("\n"))}</textarea></label>
            ${kind === "merge" ? `<label>前序意图 ID<textarea class="field" name="source_intent_ids" rows="2" placeholder="每行一个 ID">${esc((definition.source_intent_ids || []).join("\n"))}</textarea></label>` : ""}
            ${kind === "split" ? `<label>后继意图 ID<textarea class="field" name="target_ids" rows="2" placeholder="每行一个 ID">${esc((item?.target_ids || []).join("\n"))}</textarea></label>` : ""}
          </div>
        </fieldset>
        <div class="relation-filters registry-actions">
          ${changesAllowed && !restoration ? `${item ? `<label class="registry-wide registry-check">
            <input type="checkbox" name="replace_source_refs"> 替换项目证据引用
            </label>` : ""}
            <label class="registry-wide" ${item ? 'id="registry-source-editor" hidden' : ""}>项目证据引用（可选）
            <textarea class="field" name="source_refs" rows="2" ${item ? "disabled" : ""}
              placeholder="每行一条，格式为片段版本, mention_id, evidence_id"></textarea>
            ${item ? "<small>替换会覆盖全部原引用。留空并保存可移除全部原引用。</small>" : ""}</label>` : ""}
          ${changesAllowed || item?.state === "submitted" ? '<label class="registry-wide">本次变更理由<textarea class="field" name="reason" rows="2" required maxlength="2000"></textarea></label>' : ""}
        </div>
        <div class="actions registry-actions">
          ${changesAllowed ? '<button class="btn primary" type="submit">保存草稿</button>' : ""}
          ${item?.state === "draft" ? `${button("preflight", "校验缺项")}${button("submit", "提交待审核")}` : ""}
          ${item && item.state !== "withdrawn" ? button("withdraw", "撤回提案") : ""}
          ${item ? button("history", "查看草稿历史") : ""}
          ${button("close", "关闭编辑")}
        </div>
      </form>
      <p data-draft-status role="status">${esc(text)}</p>
      ${item?.missing_fields?.length ? `<h4>当前缺项</h4><ul>${issues(item.missing_fields)}</ul>` : ""}
      <div id="registry-preflight"></div>
      ${item?.source_refs?.length ? `<h4>项目证据</h4><div class="actions registry-actions">${
        item.source_refs.map((ref, index) => button("evidence", `查看证据 ${index + 1}`, `data-ref-index="${index}"`)).join("")
      }</div><div class="registry-evidence" aria-live="polite"></div>` : ""}
      <div id="registry-draft-history" aria-live="polite"></div>`;
    dirty = false;
    visibleEvidence = null;
  }

  function prepare(kind, intent, version) {
    if (!authorized || getCurrent() === undefined) {
      projectSelect.focus();
      notice.textContent = "请先选择已获草稿授权的项目，并读取当前注册表版本。";
      return;
    }
    if (dirty && !window.confirm("放弃当前未保存的草稿修改？")) return;
    clearEditor();
    preparation = { kind, intent, version, base: getCurrent() };
    renderEditor();
    editor.focus();
  }

  async function openDraft(id) {
    if (dirty && !window.confirm("放弃当前未保存的草稿修改？")) return;
    clearEditor();
    const epoch = editorEpoch;
    editor.hidden = false;
    editor.innerHTML = '<p role="status">正在读取草稿…</p>';
    editor.focus();
    try {
      const data = await api(url(id));
      if (!root.isConnected || epoch !== editorEpoch) return;
      draft = data;
      renderEditor();
    } catch (error) {
      if (!root.isConnected || epoch !== editorEpoch) return;
      if ([403, 404].includes(error.status)) denied();
      else editor.innerHTML = `<p role="alert">${esc(error.message)}</p>${button("open", "重试", `data-draft-id="${esc(id)}"`)}`;
    }
  }

  function payload(form, operation) {
    const reason = form.elements.reason.value.trim();
    const expectedVersion = !draft ? preparation.base
      : operation === "withdraw" ? getCurrent() : draft.base_registry_version;
    const body = { reason, expected_registry_version: expectedVersion };
    if (draft) body.expected_revision = draft.revision;
    else {
      body.kind = preparation.kind;
      if (preparation.intent) body.intent_id = preparation.intent.intent_id;
      if (preparation.kind === "restore") return { ...body, origin_registry_version: preparation.version };
    }
    if (operation === "save") {
      const data = new FormData(form);
      body.definition = Object.fromEntries(editorialFields.map(([key]) => [key, data.get(key)]));
      body.definition.primary_category_id = data.get("primary_category_id").trim() || null;
      body.definition.secondary_category_ids = values(data.get("secondary_category_ids"));
      if (data.has("source_intent_ids")) body.definition.source_intent_ids = values(data.get("source_intent_ids"));
      if (data.has("target_ids")) body.target_ids = values(data.get("target_ids"));
      const references = data.get("source_refs")?.trim();
      if (data.has("replace_source_refs") || references) {
        body.source_refs = !references ? [] : references.split(/\r?\n/).map(line => {
          const [segment, mention_id, evidence_id, extra] = line.split(/[,，]/).map(part => part.trim());
          const segment_revision = Number(segment);
          if (!Number.isSafeInteger(segment_revision) || segment_revision <= 0 || !mention_id || !evidence_id || extra !== undefined) {
            throw new Error("项目证据引用每行须填写正整数片段版本、mention_id 和 evidence_id。");
          }
          return { segment_revision, mention_id, evidence_id };
        });
      }
    }
    return body;
  }

  async function command(operation) {
    const form = editor.querySelector("form");
    if (form.dataset.busy || !form.reportValidity()) return;
    if (operation === "submit" && dirty) {
      showEditorMessage("请先保存定义修改，再提交审核。", true);
      return;
    }
    const epoch = editorEpoch;
    const method = draft && operation === "save" ? "PATCH" : "POST";
    const path = !draft ? url() : operation === "save" ? url(draft.draft_id) : url(draft.draft_id, operation);
    try {
      const body = payload(form, operation);
      const signature = JSON.stringify([method, path, body]);
      if (pending?.signature !== signature) pending = { signature, key: crypto.randomUUID() };
      form.dataset.busy = "true";
      for (const control of form.querySelectorAll("button")) control.disabled = true;
      showEditorMessage(operation === "save" ? "正在保存草稿…" : "正在处理提案…");
      const data = await api(path, {
        method, headers: { "Content-Type": "application/json", "X-VOC-Action": "connectivity" },
        body: JSON.stringify({ ...body, request_key: pending.key }),
      });
      if (!root.isConnected || epoch !== editorEpoch) return;
      pending = null;
      draft = data;
      preparation = null;
      renderEditor({ save: "草稿已保存。", submit: "已提交待审核。", withdraw: "提案已撤回。" }[operation]);
      editor.focus();
      loadDrafts(offset);
    } catch (error) {
      if (!root.isConnected || epoch !== editorEpoch) return;
      if (error.status === 403) denied();
      else if (error.status === 404) {
        showEditorMessage("项目证据或提案当前不可访问，请重新读取。", true);
        verifyAccess();
      } else {
        showEditorMessage(error.status === 409 ? "草稿或注册表版本冲突。请保存需要保留的输入，再重新读取草稿或版本。" : error.message, true);
      }
    } finally {
      delete form.dataset.busy;
      for (const control of form.querySelectorAll("button")) control.disabled = false;
    }
  }

  async function preflight() {
    if (dirty) {
      showEditorMessage("请先保存定义修改，再校验缺项。", true);
      return;
    }
    const target = editor.querySelector("#registry-preflight");
    const epoch = editorEpoch;
    target.innerHTML = '<p role="status">正在校验…</p>';
    try {
      const data = await api(registryQuery(url(draft.draft_id, "preflight"), { revision: draft.revision }));
      if (!root.isConnected || epoch !== editorEpoch || !target.isConnected) return;
      target.innerHTML = `<h4>预检结果</h4><p>${data.valid ? "工程预检通过" : "仍有缺项"} · 正式发行关闭</p>
        ${data.violations.length ? `<ul>${issues(data.violations)}</ul>` : ""}`;
    } catch (error) {
      if (!root.isConnected || epoch !== editorEpoch || !target.isConnected) return;
      target.innerHTML = `<p role="alert">${esc(error.message)}</p>`;
      if ([403, 404].includes(error.status)) verifyAccess();
    }
  }

  async function history(next = 0) {
    const target = editor.querySelector("#registry-draft-history");
    const epoch = editorEpoch;
    try {
      const page = await api(registryQuery(url(draft.draft_id, "history"), { limit: 25, offset: next }));
      if (!root.isConnected || epoch !== editorEpoch || !target.isConnected) return;
      target.innerHTML = `<h4>草稿历史</h4><ul class="relation-list">${page.items.map(item =>
        `<li><p>修订 ${item.revision} · ${states[item.state]} · ${esc(item.updated_at)}</p><p>${esc(item.reason)}</p></li>`
      ).join("")}</ul><div class="actions registry-actions">${next ? button("history", "上一页", `data-offset="${next - 25}"`) : ""}
      ${page.next_offset != null ? button("history", "下一页", `data-offset="${page.next_offset}"`) : ""}</div>`;
    } catch (error) {
      if (!root.isConnected || epoch !== editorEpoch || !target.isConnected) return;
      target.innerHTML = `<p role="alert">${esc(error.message)}</p>`;
      if ([403, 404].includes(error.status)) verifyAccess();
    }
  }

  function evidencePath(ref) {
    return registryQuery("/api/" + ["studies", study, "mentions", ref.mention_id, "evidence", ref.evidence_id].map(encodeURIComponent).join("/"),
      { segment_revision: ref.segment_revision });
  }

  async function evidence(index) {
    const ref = draft.source_refs[index];
    const target = editor.querySelector(".registry-evidence");
    const epoch = editorEpoch;
    visibleEvidence = ref;
    target.innerHTML = '<p role="status">正在核验原话资格…</p>';
    try {
      const data = await api(evidencePath(ref));
      if (!root.isConnected || epoch !== editorEpoch || !target.isConnected || visibleEvidence !== ref) return;
      const record = "#corpus/" + encodeURIComponent(study) + "/records/" + encodeURIComponent(data.record_id);
      target.innerHTML = `<blockquote>${esc(data.excerpt)}</blockquote><p><a href="${record}">查看原始记录</a></p>`;
    } catch (error) {
      if (!root.isConnected || epoch !== editorEpoch || !target.isConnected || visibleEvidence !== ref) return;
      visibleEvidence = null;
      target.innerHTML = `<p role="alert">${[403, 404, 409].includes(error.status) ? "证据授权或资格已失效。" : esc(error.message)}</p>`;
      if ([403, 404].includes(error.status)) verifyAccess();
    }
  }

  async function verifyAccess() {
    if (!authorized || focusPoll || !root.isConnected) return;
    const epoch = studyEpoch;
    const ref = visibleEvidence;
    const request = api(registryQuery(url(), { offset: 0, limit: 1 }));
    focusPoll = request;
    try {
      await request;
    } catch (error) {
      if (root.isConnected && epoch === studyEpoch) {
        if ([403, 404].includes(error.status)) denied();
        else {
          clearPrivate(error.message);
          pages.innerHTML = button("reload", "重试读取草稿");
        }
      }
      return;
    } finally {
      if (focusPoll === request) focusPoll = null;
    }
    if (ref && ref === visibleEvidence && epoch === studyEpoch) {
      try {
        await api(evidencePath(ref));
      } catch {
        if (ref === visibleEvidence && epoch === studyEpoch) {
          visibleEvidence = null;
          editor.querySelector(".registry-evidence").textContent = "证据授权或资格已失效。";
        }
      }
    }
  }

  const timer = window.setInterval(() => {
    if (!root.isConnected) window.clearInterval(timer);
    else if (document.visibilityState === "visible") verifyAccess();
  }, 5000);
  projectSelect.addEventListener("change", () => {
    study = projectSelect.value;
    offset = 0;
    clearPrivate(study ? "正在读取草稿…" : "请选择研究项目。");
    if (study) loadDrafts();
  });
  root.addEventListener("input", event => {
    if (!event.target.closest("#registry-draft-form") || event.target.name === "reason") return;
    dirty = true;
    showEditorMessage("修改尚未保存。");
  });
  root.addEventListener("change", event => {
    if (event.target.name !== "replace_source_refs") return;
    const group = editor.querySelector("#registry-source-editor");
    group.hidden = !event.target.checked;
    group.querySelector("textarea").disabled = group.hidden;
  });
  root.addEventListener("submit", event => {
    if (event.target.id !== "registry-draft-form") return;
    event.preventDefault();
    command("save");
  });
  root.addEventListener("click", event => {
    const control = event.target.closest("[data-draft-action]");
    if (!control) return;
    const action = control.dataset.draftAction;
    if (action === "projects") loadProjects();
    if (action === "new") prepare("candidate", null, null);
    if (action === "previous") loadDrafts(offset - 25);
    if (action === "next") loadDrafts(offset + 25);
    if (action === "reload") loadDrafts(offset);
    if (action === "open") openDraft(control.dataset.draftId);
    if (action === "preflight") preflight();
    if (action === "submit" || action === "withdraw") command(action);
    if (action === "history") history(Number(control.dataset.offset || 0));
    if (action === "evidence") evidence(Number(control.dataset.refIndex));
    if (action === "close" && (!dirty || window.confirm("放弃当前未保存的草稿修改？"))) {
      clearEditor();
      projectSelect.focus();
    }
  });
  loadProjects();
  return { prepare };
}
