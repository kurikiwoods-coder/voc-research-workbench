const endpoint = "/api/acquisition";
const providers = { tavily: "Tavily", brave: "Brave Search", stackexchange: "Stack Exchange" };
const capabilities = {
  discover: "搜索发现", access: "原文访问", store: "原文存储", research: "研究使用", transmit: "外部模型传输",
};
const statuses = {
  allowed: "已许可", approved: "已许可", denied: "禁止", unknown: "待审查", closed: "关闭", enabled: "启用",
  disabled: "停用", restricted: "受限制", revoked: "已撤销", expired: "已过期",
  offline_fixture: "离线合成夹具", pending: "待核验", background: "仅背景参考",
  background_only: "仅背景参考", internal: "内部或非公开", synthetic: "合成",
  fixture_reported: "夹具提供", unsynced: "未同步", credit: "Credit", request: "请求",
  discovered: "已发现", accessible: "可访问", inaccessible: "不可访问", permission_pending: "许可待核验",
  permission_denied: "许可拒绝", quote_extracted: "已提取原文", extraction_failed: "提取失败",
};
const sourceTypes = { search: "搜索引擎", public_forum: "公开论坛" };
const reasons = {
  missing_key: "凭证未配置", query_too_long: "查询超出接口长度限制",
  invalid_request: "请求参数无效", quota_exhausted: "额度用尽",
  invalid_schema: "供应商响应结构不符", no_valid_urls: "响应中没有可用 URL",
  offline: "连接失败或超时", invalid_key: "未通过身份验证", permission_denied: "访问被拒绝",
  insufficient_balance: "余额不足", invalid_contract: "请求与接口契约不符", upstream_error: "上游服务异常",
  not_found: "页面未找到", rate_limited: "请求受限", provider_error: "供应商服务异常",
  redirect_refused: "接口拒绝跟随重定向", unverified_page: "页面身份未核实",
  invalid_url: "URL 无效", invalid_url_configuration: "URL 核验配置无效", unsupported_scheme: "URL 协议不受支持",
  unsafe_authority: "URL 主机或端口不符合要求", unsafe_host: "URL 主机不符合安全规则",
  ip_literal_disallowed: "禁止使用 IP 地址", domain_not_allowed: "域名未获准",
  too_many_redirects: "重定向跳数超出限制", redirect_scheme_downgrade: "重定向降低连接安全性",
  redirect_cycle: "重定向循环", unapproved_source_route: "原文访问路径未获准",
  access_permission: "原文访问许可限制", fixture_transport_required: "回源仅支持离线夹具",
  excerpt_permission: "原文抽取许可待核验或受限", source_license_unknown: "原文许可未知",
  unverified_excerpt: "原文片段核验失败",
};
const strategies = {
  tavily: ["independent", ["tavily"]],
  brave: ["independent", ["brave"]],
  merge: ["merge", ["tavily", "brave"]],
  tavily_first: ["fallback", ["tavily", "brave"]],
  brave_first: ["fallback", ["brave", "tavily"]],
};
const stages = {
  N_discovered_urls: "去重后发现 URL",
  N_accessible_pages: "可访问页面",
  N_extracted_mentions: "已抽取语义片段",
  N_eligible_dedup: "合格去重片段",
  N_published_classified: "已发布且已分类",
};
const filterNames = {
  language: "语言", country: "地区", date_from: "开始日期", date_to: "结束日期",
  allowed_domains: "来源白名单", date_window: "研究时间窗", exclude_terms: "排除词",
  limit: "最大结果数", freshness: "日期时间窗", query: "查询长度",
};
const filterNotes = {
  ranking_boost_only: "仅影响搜索排序",
  local_post_filter_only: "仅在本机筛选",
  indexed_page_age_may_use_modification_date: "索引时间可能基于修改日期",
  provider_site_operators_and_local_filter: "通过站点运算符和本机白名单筛选",
  query_too_long: "超出接口长度限制",
};
const labels = {
  reported_usage: "合成回执中的供应商用量", unit: "计费单位",
  actual_requests: "实际请求数", simulated_requests: "模拟请求数", estimated_usage: "估算用量",
  remaining: "剩余额度", quota_limit: "额度上限", actual_cost: "实际费用",
  estimated_cost: "估算费用", estimated_cost_basis: "估算依据", cost_currency: "币种",
  balance_status: "余额状态",
};
const costBases = {
  tavily: "按 Tavily 即用即付价估算 1 个基础搜索 Credit，未计入套餐额度。",
  brave: "按 Brave Web Search 标价估算 1 次请求，未计入套餐额度。",
};

const nameOf = provider => providers[provider] || provider;
const statusOf = value => statuses[value] || value;
const reasonOf = value => reasons[value] || value;
const listValues = value => value.split(/[,，\n]+/).map(item => item.trim()).filter(Boolean);

export function mountAcquisition(root, _route, { api, esc }) {
  function valueItem(value) {
    if (value == null || value === "") return "未记录";
    if (typeof value === "boolean") return value ? "是" : "否";
    if (Array.isArray(value)) return value.length ? value.map(valueItem).join("、") : "无";
    if (typeof value === "object") {
      return Object.entries(value).map(([key, item]) => `${labels[key] || key} ${valueItem(item)}`).join(" · ");
    }
    return String(value);
  }

  const pairs = entries => `<dl class="acquisition-pairs">${entries.map(([label, value]) =>
    `<div><dt>${esc(label)}</dt><dd>${esc(valueItem(value))}</dd></div>`
  ).join("")}</dl>`;
  const message = text => `<p class="state-box" role="status">${esc(text)}</p>`;
  const selectOptions = (placeholder, entries) => `<option value="">${esc(placeholder)}</option>` +
    entries.map(([value, title]) => `<option value="${esc(value)}">${esc(title)}</option>`).join("");
  const queryInputs = [
    ["research_object", "研究产品或竞品对象", 160, true],
    ["research_goal", "研究目标", 240, true],
    ["keywords", "搜索关键词", 240, true],
    ["include_terms", "包含词", 240, false],
    ["exclude_terms", "排除词", 240, false],
  ];

  root.innerHTML = `
    <header class="page-head acquisition-head">
      <div><h1>来源采集</h1><p>基于冻结研究范围预览查询，查看合成发现和回源回执。</p></div>
      <button class="secondary" type="button" aria-describedby="acquisition-gate" disabled>正式采集</button>
    </header>
    <p id="acquisition-gate" class="state-box acquisition-gate" role="status">G-1 门禁 · 正式采集关闭</p>
    <section class="panel acquisition-panel" aria-labelledby="acquisition-source-heading">
      <h2 id="acquisition-source-heading">来源与权限</h2>
      <div id="acquisition-sources">${message("正在读取本机来源配置…")}</div>
    </section>
    <section class="panel acquisition-panel" aria-labelledby="acquisition-plan-heading">
      <h2 id="acquisition-plan-heading">查询计划</h2>
      <form id="acquisition-plan">
        <fieldset id="acquisition-fields" disabled>
          <div class="acquisition-grid">
            <label><span id="acquisition-study-label">研究项目</span>
              <select class="field" name="study_id" aria-labelledby="acquisition-study-label" required></select></label>
            <label><span id="acquisition-scope-label">冻结范围</span>
              <select class="field" name="scope_id" aria-labelledby="acquisition-scope-label" required disabled></select></label>
            <label><span id="acquisition-category-label">产品品类</span>
              <select class="field" name="product_category_id" aria-labelledby="acquisition-category-label" disabled></select></label>
            ${queryInputs.map(([key, label, length, required]) =>
              `<label>${label}<input class="field" name="${key}" maxlength="${length}" ${required ? "required" : ""}
                ${["keywords", "include_terms", "exclude_terms"].includes(key) ? 'aria-describedby="acquisition-keyword-help"' : ""}></label>`
            ).join("")}
            <label><span id="acquisition-strategy-label">搜索策略</span>
              <select class="field" name="strategy" aria-labelledby="acquisition-strategy-label">
              <option value="merge">合并 Tavily 和 Brave</option>
              <option value="tavily">仅 Tavily</option><option value="brave">仅 Brave Search</option>
              <option value="tavily_first">Tavily 优先，Brave 备用</option>
              <option value="brave_first">Brave 优先，Tavily 备用</option>
            </select></label>
            <label>每路最大结果数<input class="field" name="limit" type="number" min="1" max="20" value="5" required></label>
          </div>
          <p id="acquisition-keyword-help" class="acquisition-hint">预览请填写合成内容。多个词用逗号分隔。演示使用固定的合成对象、目标和关键词。</p>
          <fieldset class="acquisition-domains">
            <legend>来源白名单</legend><div id="acquisition-domains"></div>
          </fieldset>
          <details class="acquisition-filters">
            <summary>语言、地区和研究时间窗</summary>
            <div class="acquisition-grid">
              <label>语言代码<input class="field" name="language" maxlength="10" placeholder="en"></label>
              <label>地区代码<input class="field" name="country" maxlength="2" placeholder="US"></label>
              <label>开始日期<input class="field" name="date_from" type="date"></label>
              <label>结束日期<input class="field" name="date_to" type="date"></label>
            </div>
          </details>
          <div class="actions acquisition-actions">
            <button class="secondary" name="preview" value="preview" type="submit" disabled>预览查询</button>
            <button class="primary" name="demo" value="demo" type="submit" formnovalidate disabled>运行离线演示</button>
          </div>
        </fieldset>
        <p class="study-error" id="acquisition-error" role="alert" hidden></p>
        <p id="acquisition-plan-state" class="acquisition-hint" role="status"></p>
      </form>
    </section>
    <section class="panel acquisition-panel" id="acquisition-results" aria-labelledby="acquisition-result-heading" hidden>
      <h2 id="acquisition-result-heading" tabindex="-1">查询结果</h2>
      <div id="acquisition-result-body"></div>
    </section>`;

  const get = id => root.querySelector("#acquisition-" + id);
  const form = get("plan");
  const fields = form.elements;
  const study = fields.namedItem("study_id");
  const scope = fields.namedItem("scope_id");
  const category = fields.namedItem("product_category_id");
  const buttons = [fields.namedItem("preview"), fields.namedItem("demo")];
  let scopesReady = false;
  let frozenVersion = "";
  let scopeRequest = 0;
  let resultRequest = 0;
  let running = false;

  function setFormState() {
    for (const button of buttons) button.disabled = running || !scopesReady;
    form.setAttribute("aria-busy", String(running));
  }

  function invalidateResult() {
    resultRequest += 1;
    running = false;
    get("results").hidden = true;
    get("error").hidden = true;
    get("plan-state").textContent = "";
    setFormState();
  }

  function errorText(error) {
    const line = get("error");
    line.textContent = error.message;
    line.hidden = false;
  }

  function showSources(data) {
    const reason = data.formal_collection.reason;
    get("gate").textContent = `G-1 BLOCKED · ${reason}`;
    get("sources").innerHTML = `<div class="acquisition-sources">${data.sources.map(source => `
      <article class="acquisition-source" aria-label="${esc(nameOf(source.provider))}">
        <h3>${esc(nameOf(source.provider))}</h3>
        <p class="acquisition-hint">${esc(statusOf(source.capability_status))} · 正式许可${esc(statusOf(source.permission_status))}</p>
        ${pairs([
          ...Object.entries(capabilities).map(([permission, label]) =>
            [label, statusOf(source.permissions[permission] || "unknown")]
          ),
          ["离线操作", source.allowed_operations.map(operation => capabilities[operation] || operation)],
        ])}
        <details><summary>许可、留存和接口详情</summary>${pairs([
          ["来源 ID", source.source_id], ["来源类型", sourceTypes[source.source_type] || source.source_type],
          ["适配器版本", source.adapter_version], ["离线域名", source.allowed_domains],
          ["本机凭证", source.credential_status === "unavailable" ? "无法读取" :
            source.credential_configured == null ? "无需配置" : source.credential_configured ? "已配置" : "未配置"],
          ["启用状态", statusOf(source.enabled_status)],
          ["许可依据", source.license_reference], ["署名要求", source.attribution_requirement],
          ["留存", source.retention_policy], ["删除", source.deletion_policy],
          ["限流", source.rate_limit], ["计费单位", statusOf(source.usage_unit)],
        ])}
        ${source.connection_diagnostic ? pairs([
          ["本机连接诊断用量", source.connection_diagnostic.local_usage],
          ["诊断记录的剩余额度", source.connection_diagnostic.remaining ?? "未同步"],
          ["诊断记录的额度上限", source.connection_diagnostic.capacity],
          ["最近一次诊断余额同步", source.connection_diagnostic.last_synced_at ?? "未同步"],
        ]) : ""}
        </details>
      </article>
    `).join("")}</div>`;
    get("domains").innerHTML = data.offline_domains.map((domain, index) =>
      `<label><input name="domain" type="checkbox" value="${esc(domain)}" ${index === 0 ? "checked" : ""}> ${esc(domain)}</label>`
    ).join("");
  }

  async function readScope() {
    const token = ++scopeRequest;
    scopesReady = false;
    frozenVersion = "";
    category.disabled = true;
    category.innerHTML = selectOptions("不另选品类", []);
    invalidateResult();
    if (!scope.value || !study.value) return;
    const path = `/api/studies/${encodeURIComponent(study.value)}/scopes/${encodeURIComponent(scope.value)}`;
    try {
      const data = await api(path);
      if (!root.isConnected || token !== scopeRequest) return;
      category.innerHTML = selectOptions("不另选品类", (data.product_category_ids || []).map(id => [id, id]));
      category.disabled = category.options.length < 2;
      frozenVersion = data.scope_version;
      scopesReady = Boolean(data.frozen_at && frozenVersion);
      setFormState();
    } catch (error) {
      if (root.isConnected && token === scopeRequest) errorText(error);
    }
  }

  async function readScopes() {
    const token = ++scopeRequest;
    scopesReady = false;
    frozenVersion = "";
    scope.disabled = category.disabled = true;
    scope.innerHTML = selectOptions("选择冻结范围", []);
    category.innerHTML = selectOptions("不另选品类", []);
    invalidateResult();
    if (!study.value) return;
    get("plan-state").textContent = "正在读取冻结范围…";
    try {
      const data = await api(`/api/studies/${encodeURIComponent(study.value)}/scopes`);
      if (!root.isConnected || token !== scopeRequest) return;
      const frozen = data.filter(item => item.frozen_at);
      scope.innerHTML = selectOptions("选择冻结范围", frozen.map(item => [item.scope_id, item.scope_version]));
      scope.disabled = frozen.length === 0;
      get("plan-state").textContent = frozen.length ? "" : "请先在「研究项目」冻结一个研究范围。";
      if (frozen.length === 1) {
        scope.value = frozen[0].scope_id;
        await readScope();
      }
    } catch (error) {
      if (root.isConnected && token === scopeRequest) errorText(error);
    }
  }

  function planSummary(plan) {
    return pairs([
      ["项目 ID", plan.study_id], ["范围 ID", plan.scope_id], ["冻结版本", plan.scope_version],
      ["产品品类", plan.product_category_id], ["研究对象", plan.research_object], ["研究目标", plan.research_goal],
      ["搜索关键词", plan.keywords], ["包含词", plan.include_terms], ["排除词", plan.exclude_terms],
      ["来源白名单", plan.allowed_domains], ["计划搜索源", plan.providers.map(nameOf)],
      ["每路最大结果数", plan.limit], ["语言", plan.language], ["地区", plan.country],
      ["日期范围", `${plan.date_from || "—"} 至 ${plan.date_to || "—"}`],
      ["数据类型", statusOf(plan.data_class)], ["来源策略版本", plan.policy_version],
      ["模拟搜索请求预算", plan.budget?.simulated_search_requests], ["真实请求预算", plan.budget?.real_requests],
    ]);
  }

  function funnel(title, values, emptyLabel) {
    return `<section class="acquisition-section"><h3>${title}</h3>${pairs(Object.entries(stages).map(
      ([key, label]) => [label, values[key] ?? emptyLabel]
    ))}</section>`;
  }

  function providerFilters(record) {
    return [
      ["未支持的筛选", (record.unsupported_filters || []).map(filter => filterNames[filter] || filter)],
      ...Object.entries(record.filter_notes || {}).map(([filter, note]) =>
        [filterNames[filter] || filter, filterNotes[note] || note]
      ),
    ];
  }

  function queryPreview(queries) {
    return `<section class="acquisition-section"><h3>供应商查询</h3>
      <div class="acquisition-sources">${queries.map(query => `<article class="acquisition-source">
        <h4>${esc(nameOf(query.provider))}</h4>${pairs([
          ["查询", query.request.parameters.query ?? query.request.parameters.q],
          ...providerFilters(query),
        ])}</article>`).join("")}</div>
    </section>`;
  }

  function providerAttempts(attempts) {
    return `<section class="acquisition-section"><h3>搜索请求与用量</h3>
      <p class="acquisition-hint">以下用量来自合成夹具。各供应商独立计量，余额与扣费依回执记录。</p>
      <div class="acquisition-sources">${attempts.map(attempt => `<article class="acquisition-source">
        <h4>${esc(nameOf(attempt.provider))}</h4>${pairs([
          ["HTTP 状态", attempt.status], ["失败原因", reasonOf(attempt.error)],
          ["接口", `${attempt.method || ""} ${attempt.endpoint || ""}`.trim()],
          ["供应商返回条数", attempt.result_count],
          ...providerFilters(attempt),
          ...Object.entries(attempt.usage || {}).map(([field, value]) =>
            [labels[field] || field, field === "estimated_cost_basis" && value
              ? costBases[attempt.provider] : statusOf(value)]
          ),
        ])}</article>`).join("") || message("无搜索请求回执。")}</div>
    </section>`;
  }

  function discoveryReceipts(groups, discoveries, pages) {
    const byUrl = new Map();
    for (const item of discoveries) {
      const existing = byUrl.get(item.canonical_url) || [];
      existing.push(item);
      byUrl.set(item.canonical_url, existing);
    }
    const pagesByUrl = new Map(pages.map(page => [page.canonical_url, page]));
    return `<section class="acquisition-section"><h3>发现与回源回执</h3>
      <p class="acquisition-hint">同一规范 URL 可保留多条发现记录。原文资格由原始语料库核验。</p>
      ${groups.length ? `<div class="acquisition-receipts">${groups.map(group => {
        const page = pagesByUrl.get(group.canonical_url);
        return `<details>
          <summary><span class="acquisition-url">${esc(group.canonical_url)}</span>
            <span>${esc(group.discovery_count)} 条发现 · ${esc(statusOf(page?.status) || "待回源")}</span></summary>
          ${page ? pairs([
            ["回源状态", statusOf(page.status)], ["页面可访问", page.accessible], ["HTTP 状态", page.http_status],
            ["最终 URL", page.final_url], ["跳转链", page.redirect_chain], ["许可引用", page.license_reference],
            ["回源原因", reasonOf(page.http_status === 404 ? "not_found" : page.reason)],
            ["原文访问许可", statusOf(page.access_permission_status)],
            ["原文抽取许可", statusOf(page.excerpt_permission_status)],
            ["采集方式", page.synthetic ? "Stack Exchange API 离线合成夹具" : page.method],
            ["回源时间", page.fetched_at], ["发布时间", page.published_at], ["内容摘要（SHA-256）", page.content_sha256],
          ]) : ""}
          <ul class="acquisition-records">${(byUrl.get(group.canonical_url) || []).map(item => `
            <li><h4>${esc(nameOf(item.provider))} · 排名 ${esc(item.rank)}</h4>${pairs([
              ["原始 URL", item.original_url], ["规范 URL", item.canonical_url], ["查询", item.query],
              ["发现时间", item.discovered_at], ["规范化规则", item.normalization_version],
            ])}</li>`).join("")}</ul>
        </details>`;
      }).join("")}</div>` : message("本次没有发现可纳入漏斗的 URL。")}
    </section>`;
  }

  async function submit(event) {
    event.preventDefault();
    if (!scopesReady || running) return;
    const action = event.submitter?.value === "demo" ? "demo" : "preview";
    if (action === "demo" && ["limit", "date_from", "date_to"].some(key => !fields.namedItem(key).reportValidity())) return;
    const input = new FormData(form);
    const domains = input.getAll("domain");
    if (!domains.length) {
      errorText(new Error("请为本次查询勾选至少一个来源域名。"));
      return;
    }
    const [mode, selectedProviders] = strategies[input.get("strategy")];
    const text = key => (input.get(key) || "").trim();
    const data = {
      scope_id: scope.value, scope_version: frozenVersion, data_class: "synthetic",
      allowed_domains: domains, limit: Number(input.get("limit")), mode, providers: selectedProviders,
    };
    if (action === "preview") {
      for (const [field] of queryInputs) {
        data[field] = ["keywords", "include_terms", "exclude_terms"].includes(field)
          ? listValues(text(field)) : text(field);
      }
    }
    for (const field of ["product_category_id", "language", "country", "date_from", "date_to"]) {
      if (text(field)) data[field] = text(field);
    }
    const id = study.value;
    invalidateResult();
    const token = resultRequest;
    running = true;
    setFormState();
    get("plan-state").textContent = action === "demo" ? "正在运行本机合成演示…" : "正在核对查询计划…";
    try {
      const result = await api(`${endpoint}/${encodeURIComponent(id)}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-VOC-Action": "connectivity" },
        body: JSON.stringify(data),
      });
      if (!root.isConnected || token !== resultRequest) return;
      get("result-heading").textContent = action === "demo" ? "离线工程结果" : "查询预览";
      get("result-body").innerHTML = planSummary(result.plan) +
        (result.queries?.length ? queryPreview(result.queries) : "") + (action === "demo" ?
        `<p class="acquisition-hint" role="status">真实研究 API 请求 ${esc(result.real_api_calls)} 次</p>` +
          funnel("合成采集漏斗", result.engineering_funnel, "本阶段未提供") +
          funnel("正式研究分母", result.formal_funnel, "未取得正式台账") +
          providerAttempts(result.attempts) + discoveryReceipts(result.urls, result.discoveries, result.pages)
        : "");
      get("results").hidden = false;
      get("result-heading").focus();
    } catch (error) {
      if (root.isConnected && token === resultRequest) errorText(error);
    } finally {
      if (root.isConnected && token === resultRequest) {
        running = false;
        setFormState();
        get("plan-state").textContent = "";
      }
    }
  }

  form.addEventListener("submit", submit);
  form.addEventListener("input", invalidateResult);
  study.addEventListener("change", readScopes);
  scope.addEventListener("change", readScope);
  Promise.all([api(endpoint + "/sources"), api("/api/studies")]).then(([sourceData, projectData]) => {
    if (!root.isConnected) return;
    showSources(sourceData);
    study.innerHTML = selectOptions("选择研究项目", projectData.projects.map(item => [item.study_id, item.name]));
    get("fields").disabled = projectData.projects.length === 0;
    if (projectData.current && projectData.projects.some(item => item.study_id === projectData.current.study_id)) {
      study.value = projectData.current.study_id;
      readScopes();
    } else if (!projectData.projects.length) {
      get("plan-state").textContent = "请先在「研究项目」新增项目并冻结研究范围。";
    }
  }).catch(error => {
    if (!root.isConnected) return;
    get("sources").textContent = "来源配置读取失败。请重新打开「来源采集」。";
    errorText(error);
  });
}
