const stages = {
  N_discovered_urls: ["发现网址", "URL"],
  N_accessible_pages: ["可访问页面", "页面"],
  N_extracted_mentions: ["抽取候选", "候选输入"],
  N_eligible_dedup: ["合格且去重", "唯一需求发生"],
  N_published_classified: ["已发布且归类", "唯一需求发生"],
};
const buckets = {
  published_classified: "已发布且归类",
  none_unknown: "未知意图",
  review_pending: "待人工复核",
  partial_or_schema_gap: "分片或字段异常",
  pending_parent: "缺主任务",
  other_pending: "其他待处理",
};
const labels = {
  G1_BLOCKED: "G-1 尚未通过",
  RESEARCH_NOT_ADMITTED: "当前项目尚未准入正式研究",
  M08_SAMPLING_LEDGER_MISSING: "缺少 M08 采样台账",
  M12_RECEIPTS_MISSING: "缺少 M12 编码回执",
  SYNTHETIC_FIXTURE_REQUIRED: "合成演练需要独立夹具",
  SCOPE_MAPPING_UNRESOLVED: "冻结范围的产品映射未解析",
  REGISTRY_UNAVAILABLE: "暂无已封版的注册表",
  SEGMENT_REVISION_UNAVAILABLE: "暂无可用片段版",
  CATALOG_VERSION_UNAVAILABLE: "指定的产品目录版本不可用",
  DOWNSTREAM_FILTER_NOT_AVAILABLE_AT_STAGE: "此阶段缺少所选的编码或归类属性",
  EXACT_EVIDENCE_GRANT_ONLY: "当前授权限于指定证据",
  INPUT_NOT_VISIBLE: "部分输入在当前权限范围内不可见",
  RESTRICTED_INPUT_FILTER_UNKNOWN: "部分输入的筛选归属无法核验",
  TIME_FIELD_MISSING: "部分输入缺少所选时间字段",
  SOURCE_FIELD_MISSING: "部分输入缺少可核验来源",
  UNSEGMENTED_PRODUCT_UNKNOWN: "未切片整行的产品归属无法核验",
  COMPETING_CURRENT_DECISIONS: "存在多个竞争的生效决定",
  RECONCILIATION_MISMATCH: "统计对账存在差额",
  LICENSE_RESTRICTED: "许可受限、撤销或到期",
  EVIDENCE_UNVERIFIABLE: "无可核验证据",
  IDENTITY_PENDING: "发生身份待核验",
  DUPLICATE_OCCURRENCE: "同一发生的重复输入",
  NO_LEGAL_SEGMENT: "未合法切片",
};
const stageNames = { N_excluded: "排除候选输入", excluded_unsegmented_records: "未切片原始整行" };
const numberFormat = new Intl.NumberFormat("zh-CN");
const ratioFormat = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 2 });

export function denominatorPage(page, { esc, project, category, evidence }) {
  const resolved = page.resolved_versions || {};
  const scopes = resolved.scope_mappings || [];
  const values = page.counts;
  const coverage = Object.entries(page.coverage || {}).flatMap(([stage, reasons]) =>
    (reasons || []).map(reason => ({
      stage: stages[stage]?.[0] || stageNames[stage] || stage,
      reason,
    })));
  const reasonLabel = code => labels[code] || buckets[code] || code || "待核验";
  const reasonText = code => esc(reasonLabel(code));
  const count = value => value == null ? "不可用" : esc(numberFormat.format(value));
  const ratio = value => value == null ? "不可用" : esc(ratioFormat.format(value));
  const pairs = entries => '<dl class="denominator-pairs">' + entries.map(([key, value]) =>
    `<div><dt>${key}</dt><dd>${value}</dd></div>`).join("") + "</dl>";
  const modes = { engineering: "工程查看", synthetic: "合成演练", formal: "正式研究" };
  const metadata = pairs([
    ["研究项目", esc(project)],
    ["统计模式", esc(modes[page.mode] || page.mode)],
    ["注册表版本", esc(resolved.registry_version ?? "未解析")],
    ["片段版本", esc(resolved.segment_revision ?? "未解析")],
    ["产品目录版本", esc(resolved.catalog_version ?? "见冻结范围映射")],
    ["统计口径", esc(page.counting_policy_version)],
    ["统计时间（UTC）", esc(page.as_of_utc)],
    ...(resolved.index_version ? [["编码索引版本", esc(resolved.index_version)]] : []),
  ]) + (scopes.length ? '<ul class="denominator-scopes">' + scopes.map(scope =>
    `<li>冻结范围 ${esc(scope.scope_version)} · ${esc(scope.scope_id)} · 映射版 ${esc(scope.mapping_revision ?? "未解析")} · 目录 ${esc(scope.catalog_version ?? "未解析")}</li>`
  ).join("") + "</ul>" : "");
  const availability = page.availability === "unavailable" || page.reasons?.length || coverage.length
    ? `<section class="denominator-section"><h3>可用性与覆盖范围</h3>
       ${page.availability === "unavailable" ? '<p class="state-box">当前切片统计不可用。</p>' : ""}
       <ul class="denominator-notes">${(page.reasons || []).map(reason => `<li>${reasonText(reason)}</li>`).join("")}
       ${coverage.map(({ stage, reason }) => `<li>${esc(stage)} · ${reasonText(reason)}</li>`).join("")}</ul></section>`
    : "";
  const chain = `<section class="denominator-section"><h3>分母链</h3>
    <dl class="denominator-stages">${Object.entries(stages).map(([key, [label, unit]]) =>
      `<div><dt>${label}</dt><dd data-denominator-stage="${key}">${count(values?.[key])}<small>${unit}</small></dd></div>`).join("")}</dl>
    </section>`;
  if (!values) return metadata + availability + chain;

  const eligible = values.N_eligible_dedup;
  const distribution = Object.entries(buckets).map(([key, label]) => {
    const value = values.buckets?.[key];
    const share = eligible > 0 && Number.isFinite(value) ? value / eligible : null;
    return { key, label, value, share };
  });
  const bar = distribution.some(({ share }) => share > 0)
    ? '<div class="denominator-bar" aria-hidden="true">' + distribution.filter(({ share }) => share > 0)
      .map(({ key, share }) => `<span data-counting-bucket="${key}" style="flex-grow:${share}"></span>`).join("") + "</div>"
    : "";

  const primary = page.by_primary_category;
  const categories = primary?.length ? pairs(primary.map(row => [
    esc(row.name || category(row.category_id)), count(row.count) + " · " + ratio(row.ratio),
  ])) : `<p>${primary == null ? "主任务统计不可用。" : "当前没有已发布的主任务归类。"}</p>`;
  const excluded = page.excluded_by_reason;
  const unsegmented = excluded?.excluded_unsegmented_records;
  const exclusionReasons = reasons => Object.entries(reasons || {}).map(([code, amount]) =>
    [reasonText(code), count(amount)]);
  const exclusions = excluded == null ? "<p>当前排除账不可用。</p>" : pairs([
    ["排除候选输入", count(values.N_excluded)],
    ...exclusionReasons(excluded.primary),
    ...Object.entries(excluded.secondary || {}).map(([code, amount]) =>
      ["次因 · " + reasonText(code), count(amount)]),
    ["未切片原始整行", count(unsegmented?.count)],
    ...exclusionReasons(unsegmented?.by_reason),
  ]);

  const check = page.reconciliation;
  const difference = value => value == null ? "不可用" : (value === 0 ? "平衡 · 差额 0" : "不平衡 · 差额 " + count(value));
  return metadata + availability + chain +
    `<section class="denominator-section"><h3>六桶分布</h3>${bar}
       ${pairs(distribution.map(({ key, label, value, share }) =>
         [`<span class="denominator-swatch" data-counting-bucket="${key}"></span>${label}`, count(value) + " · " + ratio(share)]))}
     </section>
     <section class="denominator-section"><h3>主任务大类</h3>${categories}</section>
     <section class="denominator-section"><h3>排除原因</h3>${exclusions}</section>
     <section class="denominator-section"><h3>对账差额</h3>
       ${pairs([["合格发生与六桶", difference(check?.eligible_difference)],
         ["已发布发生与主任务大类", difference(check?.primary_difference)]])}
       ${check?.eligible_difference || check?.primary_difference ? '<p class="state-box" role="status">存在对账差额，发布资格已阻止。</p>' : ""}
     </section>` + (page.anomaly_refs?.length ?
       `<section class="denominator-section"><h3>异常证据</h3><ul class="relation-list">${page.anomaly_refs.map(ref =>
         evidence(reasonLabel(ref.reason), ref)).join("")}</ul></section>` : "");
}
