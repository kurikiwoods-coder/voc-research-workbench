const runStates = {
  clustered: "已聚类", no_clusters: "全部离群", empty: "无输入", insufficient_samples: "样本不足",
  empty_vocabulary: "无可用主题词",
};
const decisions = { pending: "待审核", retained: "保留供审核", rejected: "已排除" };
const parameters = [
  ["random_seed", "随机种子", 42, 0, 4294967295],
  ["n_neighbors", "UMAP 邻居数", 10, 2, 1000],
  ["n_components", "UMAP 维数", 2, 1, 100],
  ["min_dist", "UMAP 最小距离", 0.05, 0, 1, "any"],
  ["min_cluster_size", "最小簇大小", 5, 2, 1000],
  ["min_samples", "HDBSCAN 最小样本数", 3, 1, 1000],
  ["top_n_words", "每主题关键词数", 10, 1, 100],
];
const topicLabel = id => id === -1 ? "离群样本" : id == null ? "无" : "主题 " + id;
const runLabel = run => [run.finished_at?.slice(0, 19).replace("T", " "),
  runStates[run.status] || run.status, run.run_id.slice(0, 8)].filter(Boolean).join(" · ");
const decimal = value => typeof value === "number" ? value.toLocaleString("zh-CN", { maximumFractionDigits: 4 }) : "—";

export function mountDiscovery(root, _route, { api, esc, personal = false }) {
  root.innerHTML = `<header class="page-head"><div><h1>主题发现</h1>
      <p>查看冻结研究范围内的离线聚类、候选与原话证据。</p></div></header>
    <section class="panel discovery-panel" aria-labelledby="discovery-scope-heading">
      <h2 id="discovery-scope-heading">运行范围</h2>
      <div class="discovery-fields">
        <label>研究项目<select class="field" id="discovery-study" disabled></select></label>
        <label>冻结范围<select class="field" id="discovery-scope" disabled></select></label>
        <label>已保存运行<select class="field" id="discovery-run" disabled></select></label>
      </div>
      <p class="discovery-note" id="discovery-status" role="status"></p>
      <p class="study-error" id="discovery-error" role="alert" hidden></p>
    </section>
    <div id="discovery-create"></div>
    <div id="discovery-result"></div>`;

  const get = name => root.querySelector("#discovery-" + name);
  const study = get("study"), scope = get("scope"), selectRun = get("run");
  const selectedInputIds = () => [...get("create").querySelectorAll("[name=evidence_ids]:checked")]
    .map(input => input.value);
  const showStatus = message => { get("status").textContent = message; };
  const showError = error => {
    get("error").textContent = error.message;
    get("error").hidden = false;
  };
  const pathPart = encodeURIComponent;
  const scopePath = () => "/api/discovery/" + [study.value, scope.value, scope.selectedOptions[0]?.dataset.version]
    .map(pathPart).join("/");
  const runsPath = () => scopePath() + "/runs";
  const runPath = id => runsPath() + "/" + pathPart(id);
  const option = (value, label) => `<option value="${esc(value)}">${esc(label)}</option>`;
  const empty = message => `<p class="state-box">${esc(message)}</p>`;
  const hiddenError = () => { get("error").hidden = true; };
  const specs = (values = {}) => `<div class="discovery-fields">${parameters.map(
    ([key, label, fallback, min, max, step = 1]) => `<label>${label}<input class="field" name="${key}"
      type="number" value="${esc(values[key] ?? fallback)}" min="${min}" max="${max}" step="${step}" required></label>`
  ).join("")}</div>`;
  const definition = pairs => `<dl class="discovery-data">${pairs.map(([name, value]) =>
    `<div><dt>${esc(name)}</dt><dd>${esc(value ?? "—")}</dd></div>`).join("")}</dl>`;
  const json = value => `<pre class="discovery-json">${esc(JSON.stringify(value, null, 2))}</pre>`;
  const topicButton = (id, text, options = "") =>
    `<button type="button" class="secondary" data-discovery-topic="${esc(id)}" ${options}>${esc(text)}</button>`;
  const evidenceButton = documentId => `<button type="button" class="secondary"
    data-discovery-document="${esc(documentId)}">查看原话与证据</button>`;
  let generation = 0;
  let mutationPending = false;
  let savedRuns = [];
  let inputs = [];
  let modelAvailable = false;
  let reviewAvailable = false;
  let view = null;
  let activeTopic = null;
  let evidenceRequest = 0;
  let comparisonRequest = 0;
  const requestKeys = new Map();
  let personalProjects = [];

  function active(token) {
    return root.isConnected && token === generation;
  }

  function clearResult() {
    evidenceRequest++;
    comparisonRequest++;
    view = null;
    activeTopic = null;
    get("result").replaceChildren();
  }

  function beginWork(message) {
    hiddenError();
    showStatus(message);
    return ++generation;
  }

  function scopeTitle(item) {
    return [item.scope_version, item.topic || item.scope_id.slice(0, 8)].join(" · ");
  }

  function setRunOptions(preferred = "") {
    selectRun.innerHTML = option("", "选择已保存运行") +
      savedRuns.map(run => option(run.run_id, runLabel(run))).join("");
    selectRun.disabled = !savedRuns.length;
    selectRun.value = savedRuns.some(run => run.run_id === preferred) ? preferred : "";
  }

  async function readProjects() {
    const token = beginWork("正在读取研究项目…");
    try {
      const data = await api(personal ? "/api/edition/projects" : "/api/studies");
      if (!active(token)) return;
      const projects = personal ? data.projects.map(({ scope: grant }) => ({
        study_id: grant.study_id, name: grant.study_id, grant,
      })) : data.projects.filter(item => item.status !== "archived");
      if (personal) personalProjects = projects;
      study.innerHTML = option("", "选择研究项目") +
        projects.map(item => option(item.study_id, item.name)).join("");
      study.disabled = !projects.length;
      if (projects.some(item => item.study_id === data.current?.study_id)) {
        study.value = data.current.study_id;
        await readScopes();
      } else {
        showStatus(projects.length ? "选择研究项目和冻结范围。" : personal
          ? "请在版本与研究准入页核对项目及冻结范围授权。" : "请先在研究项目页建立项目并冻结范围。");
      }
    } catch (error) {
      if (active(token)) {
        showStatus("");
        showError(error);
      }
    }
  }

  async function readScopes() {
    const token = beginWork(study.value ? "正在读取冻结范围…" : "选择研究项目和冻结范围。");
    scope.disabled = true;
    scope.innerHTML = option("", "选择冻结范围");
    resetScope();
    if (!study.value) return;
    try {
      const base = "/api/studies/" + pathPart(study.value) + "/scopes";
      const grant = personalProjects.find(project => project.study_id === study.value)?.grant;
      const rows = personal ? [await api(base + "/" + pathPart(grant.scope_id))] : await api(base);
      if (!active(token)) return;
      const frozen = rows.filter(item => item.frozen_at && item.scope_version && (!grant ||
        (item.scope_id === grant.scope_id && item.scope_version === grant.scope_version)));
      scope.innerHTML += frozen.map(item =>
        `<option value="${esc(item.scope_id)}" data-version="${esc(item.scope_version)}">${esc(scopeTitle(item))}</option>`
      ).join("");
      scope.disabled = !frozen.length;
      if (frozen.length === 1) {
        scope.value = frozen[0].scope_id;
        await readScope();
      } else {
        showStatus(frozen.length ? "选择冻结范围。" : "该项目尚无冻结范围。");
      }
    } catch (error) {
      if (active(token)) {
        showStatus("");
        showError(error);
      }
    }
  }

  function resetScope() {
    savedRuns = [];
    inputs = [];
    modelAvailable = false;
    reviewAvailable = false;
    requestKeys.clear();
    setRunOptions();
    clearResult();
    get("create").replaceChildren();
  }

  async function readScope() {
    const token = beginWork(scope.value ? "正在读取主题运行与合格输入…" : "选择冻结范围。");
    resetScope();
    if (!scope.value) return;
    const [runs, qualified] = await Promise.allSettled([api(runsPath()), api(scopePath() + "/inputs")]);
    if (!active(token)) return;
    showStatus("");
    if (runs.status === "rejected") {
      showError(runs.reason);
      return;
    }
    savedRuns = runs.value.runs;
    modelAvailable = runs.value.model_available;
    reviewAvailable = runs.value.review_available;
    setRunOptions(savedRuns[0]?.run_id);
    if (qualified.status === "fulfilled") {
      inputs = qualified.value.inputs;
      renderCreate(qualified.value.registry_version);
    } else {
      get("create").textContent = qualified.reason.message;
    }
    if (selectRun.value) await readRun();
    else showStatus("此冻结范围尚无已保存的主题运行。");
  }

  function renderCreate(registryVersion) {
    const content = inputs.length ? `<form id="discovery-create-form">
      <fieldset class="discovery-inputs" ${modelAvailable ? "" : "disabled"}>
        <legend>合格语义片段（${inputs.length}）</legend>
        <div class="actions discovery-actions">
          <button type="button" class="secondary" data-discovery-inputs="all">全选</button>
          <button type="button" class="secondary" data-discovery-inputs="none">取消全选</button>
        </div>
        <div class="discovery-input-list">${inputs.map((item, index) => `<label>
          <input type="checkbox" name="evidence_ids" value="${esc(item.document_id)}">
          <span>片段 ${index + 1} · ${esc(item.original_language)} <small>${esc(item.mention_id || item.document_id)}</small></span>
        </label>`).join("")}</div>
      </fieldset>
      <div class="discovery-fields">
        <label>分析语言<input class="field" name="analysis_language" value="zh-CN" maxlength="35" required></label>
        <label>输出语言<input class="field" name="output_language" value="zh-CN" maxlength="35" required></label>
      </div>
      <details class="discovery-fold"><summary>聚类参数</summary>${specs()}</details>
      <div class="actions discovery-actions"><button type="submit" class="primary" disabled>运行离线聚类</button></div>
    </form>` : empty("此范围暂无可用的离线语义片段。");
    get("create").innerHTML = `<details class="panel discovery-panel">
      <summary>新建主题运行</summary>
      <p class="discovery-note">注册表版本 ${esc(registryVersion ?? "未配置")} · 本机模型 ${modelAvailable ? "可用" : "未配置"}</p>
      ${content}</details>`;
  }

  async function readRun(revision) {
    const runId = selectRun.value;
    const token = beginWork(runId ? "正在读取已保存的快照…" : "选择已保存运行。");
    clearResult();
    if (!runId) return;
    const query = revision == null ? "" : "?revision=" + pathPart(revision);
    try {
      const data = await api(runPath(runId) + query);
      if (!active(token)) return;
      renderResult(data);
      showStatus(revision == null ? "" : "已重载历史快照。");
      if (revision != null) get("result-heading").focus();
    } catch (error) {
      if (active(token)) {
        showStatus("");
        showError(error);
      }
    }
  }

  function renderResult(data) {
    evidenceRequest++;
    comparisonRequest++;
    view = data;
    const { run, coverage } = data;
    activeTopic = run.topics.some(topic => topic.topic_id === activeTopic)
      ? activeTopic : run.topics.find(topic => topic.topic_id >= 0)?.topic_id ?? run.topics[0]?.topic_id;
    const metadata = run.metadata;
    const warnings = run.quality.m09_b_synthetic_purity.map(pair => pair.join("/")).join("、");
    get("result").innerHTML = `<section class="panel discovery-panel" aria-labelledby="discovery-result-heading">
      <h2 tabindex="-1" id="discovery-result-heading">主题分布</h2>
      <div class="discovery-stats">${[
        ["输入片段", coverage.input_count], ["当前合格", coverage.eligible_count],
        ["候选主题", coverage.candidate_count], ["候选覆盖片段", coverage.candidate_document_count],
        ["离群片段", coverage.outlier_count],
      ].map(([label, count]) => `<div><strong>${esc(count)}</strong><span>${label}</span></div>`).join("")}</div>
      <p class="discovery-note">图表按本次运行的片段数统计。正式研究分母 ${esc(metadata.research_denominator)}。</p>
      <p class="discovery-quality">${esc(runStates[run.status] || run.status)} · ${esc(run.quality.diagnostic)}
        · ${esc(run.quality.g3)} · M09-B 合成纯度 ${esc(warnings)}</p>
      <div id="discovery-distribution"></div>
      <div id="discovery-topic-details"></div>
      <section class="discovery-subsection" id="discovery-evidence" tabindex="-1" hidden></section>
    </section>
    <details class="panel discovery-panel" id="discovery-relationships"><summary>主题关系</summary>
      <p class="discovery-note">关键词集合的交集数除以并集数，用于检查主题间的词汇重叠。</p>
      ${relationships(data.topic_relationships)}
    </details>
    <details class="panel discovery-panel"><summary>研究范围、模型与复现记录</summary>
      <p class="discovery-note">运行级标识与参数随快照保存。</p>
      ${definition([
        ["运行 ID", run.run_id], ["项目", study.selectedOptions[0]?.textContent], ["冻结范围 ID", run.scope_id],
        ["冻结版本", run.scope_version], ["注册表版本", metadata.registry_version], ["研究方式", metadata.mode],
        ["开始时间", run.started_at], ["封存时间", run.finished_at], ["Embedding 运行", metadata.embedding_run_id],
        ["输入摘要", metadata.input_sha256], ["向量摘要", metadata.vector_sha256],
        ["预处理版本", metadata.preprocessing_version], ["分词版本", metadata.tokenizer_version],
        ["发现管线", metadata.pipeline_version], ["分析语言", metadata.analysis_language],
        ["输出语言", metadata.output_language], ["候选输出版本", data.output_version],
        ["审核修订", data.revision], ["复跑或重算来源", run.replay_of],
      ])}
      <h3>模型配置</h3>${json(metadata.model)}
      <h3>实际聚类参数</h3>${json(metadata.effective_config)}
      <h3>请求参数及运行时版本</h3>${json({ requested: metadata.requested_config, runtime: metadata.runtime_versions })}
    </details>
    <section class="panel discovery-panel" aria-labelledby="discovery-replay-heading">
      <h2 id="discovery-replay-heading">复跑与比较</h2>
      <form id="discovery-replay-form">
        <div class="discovery-fields"><label>历史审核修订<input class="field" type="number" name="revision"
          value="${esc(data.revision)}" min="0" max="${esc(data.latest_revision)}" step="1" required></label></div>
        <div class="actions discovery-actions"><button type="submit" class="secondary">重载已保存快照</button></div>
      </form>
      <details class="discovery-fold"><summary>重新计算聚类</summary>
        <p class="discovery-note">使用相同输入、所选参数和本机模型创建新运行。</p>
        <form id="discovery-recalculate-form">
          ${specs(metadata.requested_config)}
          <div class="actions discovery-actions"><button type="submit" class="primary"
            ${modelAvailable ? "" : "disabled"}>重新计算并比较</button></div>
        </form>
      </details>
      <form id="discovery-compare-form">
        <div class="discovery-fields"><label>对比运行<select class="field" name="other_run_id" required>
          ${option("", "选择同范围的历史运行")}${savedRuns.filter(item => item.run_id !== run.run_id)
            .map(item => option(item.run_id, runLabel(item))).join("")}</select></label></div>
        <div class="actions discovery-actions"><button type="submit" class="secondary"
            ${savedRuns.length < 2 ? "disabled" : ""}>比较运行</button></div>
      </form>
      <section class="discovery-subsection" id="discovery-comparison" tabindex="-1" hidden></section>
    </section>`;
    paintTopic();
  }

  function relationships(rows) {
    if (!rows.length) return empty("暂无可比较的主题关系。");
    return `<ul class="discovery-list">${rows.map(row => `<li><div class="discovery-row">
      <span>${esc(topicLabel(row.left_topic_id))} ↔ ${esc(topicLabel(row.right_topic_id))}
        · ${esc(decimal(row.similarity))}</span>
      <span>重叠词 ${esc(row.shared_terms.join("、") || "—")}</span>
      <div class="actions">${topicButton(row.left_topic_id, "查看" + topicLabel(row.left_topic_id))}
        ${topicButton(row.right_topic_id, "查看" + topicLabel(row.right_topic_id))}</div>
    </div></li>`).join("")}</ul>`;
  }

  function paintTopic(focus = false) {
    const { run } = view;
    const counts = new Map(run.topics.map(topic => [topic.topic_id, 0]));
    for (const member of run.members) counts.set(member.topic_id, counts.get(member.topic_id) + 1);
    const maximum = Math.max(1, ...counts.values());
    get("distribution").innerHTML = counts.size ? `<ul class="discovery-distribution">${[...counts].map(([id, total]) =>
      `<li><button type="button" class="discovery-bar" data-discovery-topic="${esc(id)}"
        aria-pressed="${id === activeTopic}"><span>${esc(topicLabel(id))}</span>
        <span class="discovery-bar-track" aria-hidden="true"><span class="discovery-bar-fill"
          style="width:${100 * total / maximum}%"></span></span>
        <strong>${esc(total)} 条</strong></button></li>`
    ).join("")}</ul>` : empty("本次运行没有成员。");
    if (activeTopic == null) return;
    const topic = run.topics.find(item => item.topic_id === activeTopic);
    const candidate = view.candidates.find(item => item.topic_id === activeTopic);
    const members = run.members.filter(item => item.topic_id === activeTopic);
    const representatives = topic.representative_document_ids.map(id => members.find(member => member.document_id === id))
      .filter(member => member?.evidence_eligible);
    get("topic-details").innerHTML = `<section class="discovery-subsection" aria-labelledby="discovery-topic-heading">
      <h3 id="discovery-topic-heading" tabindex="-1">${esc(topicLabel(activeTopic))}</h3>
      ${candidate ? candidatePanel(candidate) : "<p>保留在本次运行的离群结果中。</p>"}
      ${topic.keywords.length ? `<p>关键词 ${esc(topic.keywords.map(item => item.term).join("、"))}</p>` : ""}
      <h4>代表性原话</h4>
      ${representatives.length ? `<ul class="discovery-list">${representatives.map((member, index) =>
        `<li><div class="discovery-row"><span>代表片段 ${index + 1}</span>${evidenceButton(member.document_id)}</div></li>`
      ).join("")}</ul>` : empty(topic.evidence_eligible ? "暂无代表片段。" : "当前证据资格不足，代表片段已隐藏。")}
      <h4>成员与聚类诊断（${members.length}）</h4>
      <ul class="discovery-list">${members.map((member, index) => `<li>${memberCard(member, index)}</li>`).join("")}</ul>
    </section>`;
    if (focus) get("topic-heading").focus();
  }

  function candidatePanel(candidate) {
    const historical = view.revision !== view.latest_revision;
    return `<div class="discovery-candidate">
      <p><strong>候选描述</strong> ${esc(candidate.description || (candidate.evidence_eligible
        ? "暂无可用关键词" : "当前证据资格不足"))}</p>
      <p>${esc(decisions[candidate.decision] || candidate.decision)} · 审核修订 ${esc(view.revision)}
        · ${esc(candidate.member_count)} 个成员</p>
      <small>候选 ID ${esc(candidate.candidate_id)}</small>
      ${historical ? "<p>正在查看历史审核修订。</p>" : ""}
      ${reviewAvailable ? "" : "<p>当前角色可查看候选。</p>"}
      <form id="discovery-review-form" data-topic-id="${esc(candidate.topic_id)}">
        <div class="discovery-fields"><label>候选审核决定<select class="field" name="decision"
          ${historical || !reviewAvailable || !candidate.evidence_eligible ? "disabled" : ""}>
          ${Object.entries(decisions).map(([value, label]) => `<option value="${value}"
            ${value === candidate.decision ? "selected" : ""} ${value === "pending" ? "disabled" : ""}>${label}</option>`).join("")}</select></label></div>
        <div class="actions discovery-actions"><button type="submit" class="secondary"
          ${historical || !reviewAvailable || !candidate.evidence_eligible || candidate.decision === "pending" ? "disabled" : ""}>
          保存候选审核</button></div>
      </form>
    </div>`;
  }

  function memberCard(member, index) {
    const title = `<span>片段 ${index + 1}${member.original_language ? " · " + esc(member.original_language) : ""}</span>`;
    if (!member.evidence_eligible) return `<div class="discovery-row">${title}<span>证据当前不可用</span></div>`;
    return `<div class="discovery-row">${title}<span>成员概率 ${esc(decimal(member.membership_probability))}
      · 离群分数 ${esc(decimal(member.outlier_score))} · 质心相似度 ${esc(decimal(member.centroid_similarity))}</span>
      ${evidenceButton(member.document_id)}</div>`;
  }

  async function readEvidence(documentId) {
    const container = get("evidence");
    const token = ++evidenceRequest;
    const stillActive = () => root.isConnected && container.isConnected && evidenceRequest === token;
    container.hidden = false;
    container.innerHTML = empty("正在复核证据资格并读取原话…");
    try {
      const item = await api(runPath(view.run.run_id) + "/evidence/" + pathPart(documentId));
      if (!stillActive()) return;
      const lineage = item.lineage;
      container.innerHTML = `<h4>原话与证据</h4><blockquote lang="${esc(item.original_language)}">${esc(item.original_text)}</blockquote>
        ${definition([
          ["文档 ID", documentId], ["记录 ID", lineage.record_id], ["批次 ID", lineage.batch_id],
          ["Mention ID", lineage.mention_id], ["证据 ID", lineage.evidence_id],
          ["片段修订", lineage.segment_revision], ["原文区间", lineage.start_cp + "–" + lineage.end_cp],
          ["来源定位", lineage.source_locator], ["来源许可", lineage.license_status],
          ["提取版本", lineage.extraction_version], ["原文摘要", lineage.raw_sha256],
        ])}`;
    } catch (error) {
      if (!stillActive()) return;
      container.innerHTML = `<p class="study-error" role="alert">${esc(error.message)}</p>`;
    }
    container.focus();
  }

  function configOf(form) {
    return Object.fromEntries(parameters.map(([key]) => [key, form.elements.namedItem(key).valueAsNumber]));
  }

  async function mutate(path, data, label, complete) {
    if (mutationPending) return;
    const token = generation;
    const fingerprint = JSON.stringify([path, data]);
    if (!requestKeys.has(fingerprint)) requestKeys.set(fingerprint, crypto.randomUUID());
    const requestId = requestKeys.get(fingerprint);
    mutationPending = true;
    hiddenError();
    showStatus(label);
    try {
      const response = await api(path, {
        method: "POST", headers: { "Content-Type": "application/json", "X-VOC-Action": "connectivity" },
        body: JSON.stringify({ ...data, request_id: requestId }),
      });
      requestKeys.delete(fingerprint);
      if (active(token)) complete(response);
    } catch (error) {
      if (active(token)) {
        showStatus("");
        showError(error);
      }
    } finally {
      mutationPending = false;
    }
  }

  function openNewRun(data) {
    if (!savedRuns.some(item => item.run_id === data.run.run_id)) savedRuns.unshift(data.run);
    setRunOptions(data.run.run_id);
    renderResult(data);
    get("result-heading").focus();
  }

  async function compareRuns(leftId, rightId, leftRevision) {
    const container = get("comparison");
    const token = ++comparisonRequest;
    const stillActive = () => root.isConnected && container.isConnected && comparisonRequest === token;
    container.hidden = false;
    container.innerHTML = empty("正在读取运行差异…");
    try {
      const query = leftRevision == null ? "" : "?left_revision=" + pathPart(leftRevision);
      const diff = await api(runPath(leftId) + "/compare/" + pathPart(rightId) + query);
      if (!stillActive()) return;
      const topicMatches = diff.topic_matches.map(row => [
        topicLabel(row.left_topic_id) + " ↔ " + topicLabel(row.right_topic_id),
        row.shared_documents + " 个共同片段 / " + row.union_documents + " 个并集片段",
      ]);
      const changes = {
        "运行参数": diff.metadata_changes, "成员变化": diff.membership_changes, "离群变化": diff.outlier_changes,
        "关键词变化": diff.keyword_changes, "证据映射变化": diff.evidence_changes, "诊断变化": diff.diagnostic_changes,
        "候选匹配": diff.candidate_matches, "未匹配候选": diff.unmatched_candidate_topics,
      };
      container.innerHTML = `<h3>运行比较结果</h3>
        <p>${diff.same_result ? "聚类与成员结果一致。" : "聚类或成员结果存在差异。"}</p>
        ${definition([["原运行", diff.left_run_id], ["对比运行", diff.right_run_id], ...topicMatches,
          ["原候选覆盖片段", diff.candidate_coverage?.left.candidate_document_count],
          ["对比候选覆盖片段", diff.candidate_coverage?.right.candidate_document_count],
          ["候选覆盖片段变化", diff.candidate_coverage?.delta.candidate_document_count]])}
        ${Object.entries(changes).filter(([, value]) => value != null).map(([name, value]) =>
          `<details class="discovery-fold"><summary>${name}（${value === diff.unmatched_candidate_topics
            ? value.left.length + value.right.length : Object.keys(value).length}）</summary>${json(value)}</details>`
        ).join("")}`;
    } catch (error) {
      if (!stillActive()) return;
      container.innerHTML = `<p class="study-error" role="alert">${esc(error.message)}</p>`;
    }
    container.focus();
  }

  study.addEventListener("change", readScopes);
  scope.addEventListener("change", readScope);
  selectRun.addEventListener("change", () => readRun());
  root.addEventListener("change", event => {
    if (event.target.name === "evidence_ids") get("create-form").querySelector("[type=submit]").disabled =
      !modelAvailable || !selectedInputIds().length;
    if (event.target.name === "decision") get("review-form").querySelector("[type=submit]").disabled =
      event.target.value === "pending";
  });
  root.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (!button) return;
    if (Object.hasOwn(button.dataset, "discoveryTopic")) {
      activeTopic = Number(button.dataset.discoveryTopic);
      evidenceRequest++;
      get("evidence").hidden = true;
      get("evidence").replaceChildren();
      paintTopic(true);
    } else if (button.dataset.discoveryDocument) {
      readEvidence(button.dataset.discoveryDocument);
    } else if (button.dataset.discoveryInputs) {
      const checked = button.dataset.discoveryInputs === "all";
      get("create-form").querySelectorAll("[name=evidence_ids]").forEach(input => { input.checked = checked; });
      get("create-form").querySelector("[type=submit]").disabled = !modelAvailable || !checked;
    }
  });
  root.addEventListener("submit", event => {
    const form = event.target;
    event.preventDefault();
    if (form === get("create-form")) {
      const evidenceIds = selectedInputIds();
      if (!modelAvailable || !evidenceIds.length) return;
      mutate(runsPath(), {
        evidence_ids: evidenceIds, analysis_language: form.elements.namedItem("analysis_language").value,
        output_language: form.elements.namedItem("output_language").value, config: configOf(form),
      }, "正在执行本机聚类…", data => {
        openNewRun(data);
        showStatus("已封存主题运行。");
      });
    } else if (form === get("replay-form")) {
      readRun(form.elements.namedItem("revision").value);
    } else if (form === get("recalculate-form") && modelAvailable) {
      const baseId = view.run.run_id;
      const baseRevision = view.revision;
      mutate(runPath(baseId) + "/recalculate", { config: configOf(form) }, "正在本机重新计算…", data => {
        openNewRun(data);
        showStatus("已封存重算运行。");
        compareRuns(baseId, data.run.run_id, baseRevision);
      });
    } else if (form === get("compare-form")) {
      compareRuns(view.run.run_id, form.elements.namedItem("other_run_id").value, view.revision);
    } else if (form === get("review-form") && reviewAvailable && view.revision === view.latest_revision) {
      const topicId = Number(form.dataset.topicId);
      const decision = form.elements.namedItem("decision").value;
      if (decision === "pending" || !view.candidates.some(item => item.topic_id === topicId && item.evidence_eligible)) return;
      mutate(runPath(view.run.run_id) + "/candidates/" + topicId + "/review",
        { decision, expected_revision: view.latest_revision }, "正在保存候选审核…", data => {
          renderResult(data);
          showStatus("已保存候选审核。");
          get("topic-heading").focus();
        });
    }
  });
  readProjects();
}
