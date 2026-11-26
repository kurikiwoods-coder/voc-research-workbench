# M08-A/B 搜索发现与许可回源契约

本轮以隔离合成数据验证 Tavily 和 Brave 搜索发现、URL 归一与 Stack Exchange 页面访问回执。正式采集等待来源审批与 G-1 同批验收，真实研究 API 调用为 0。[来源适配与许可](m08-source-adapter-contract.md)

## 查询计划与供应商参数

查询计划绑定 `study_id`、`scope_id`、精确 `scope_version`、冻结时间和品类选择。产品或竞品对象、研究目标、本机计划中的词项、来源域名、语言、地区、日期和结果上限分别保存。查询时间窗须处于冻结范围内。预览与模拟执行共用 `preview_queries` 请求构造器。预览不使用凭证或传输，演示只发送预设合成词项给内存夹具。`public_approved` 标签、固定端点和对应凭证头由共用外发边界校验。现有 M02 搜索诊断和 P0-0 验收探针保留原入口。[适配器](../../src/ingestion/m08_search.py) · [共用外发边界](../../src/execution/transport.py) · [现有诊断](../connectivity.md)

| 契约 | Tavily | Brave Web Search |
|---|---|---|
| 固定请求 | `POST api.tavily.com/search`，JSON `Authorization: Bearer` 凭证头 | `GET api.search.brave.com/res/v1/web/search`，`X-Subscription-Token` 凭证头 |
| 查询与数量 | `query` 最长 400 字符，`max_results` 最多 20。固定 `topic=general`、`search_depth=basic`、`auto_parameters=false`。关闭答案、原文和图片，开启 `include_usage`。 | `q` 最长 600 字符且最多 75 个词，`count` 最多 20。只请求网页结果，关闭拼写自动替换、扩展摘要和搜索操作符回退。 |
| 包含与排除 | 包含词使用引号和 `exact_match`。排除词标记为不支持。 | 包含词使用带引号的词组，排除词使用负号加带引号的词组。 |
| 来源范围 | `include_domains` 及 `include_domains_mode=restrict`。供应商上限 300。本机计划接口最多接受八个域名，当前合成演示仅允许 `cooking.stackexchange.com`。 | 为允许域名构造 `site:` 操作符，多个域名通过 `OR` 展开。收到结果后按本机精确域名白名单校验。 |
| 语言与地区 | `language` 配合 `filter_by_language`。将支持的常用两位地区代码映射到 Tavily 名称，`country` 只影响排序。 | `search_lang` 配合 `country`，按 Brave 官方客户端的枚举接受代码。`zh`、`zh-cn`、`zh-tw` 映射到相应 Brave 简繁代码。未知语言或地区代码标记为不支持。 |
| 日期 | `start_date` 和 `end_date` 支持单端或双端，设置 `filter_by_published_date`。 | `freshness` 使用 `YYYY-MM-DDtoYYYY-MM-DD`，单端日期标记为不支持。索引日期可能来自修改日期。 |

`unsupported_filters` 标记无法映射的字段，`filter_notes` 记录排序偏好、日期差异和请求长度限制。超长查询返回 `query_too_long`，不向模拟传输分发。提供商结果数量按各自上限约束。[Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search) · [Tavily 查询指引](https://docs.tavily.com/documentation/best-practices/best-practices-search) · [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get) · [Brave 语言与地区枚举](https://github.com/brave/brave-search-mcp-server/blob/4ec7ebb19cb86044357d0a4b1ccccdbd81cf5246/src/tools/web/params.ts) · [Brave 搜索操作符](https://api-dashboard.search.brave.com/documentation/resources/search-operators)

## 双源模式与用量

- `independent` 单路发现。`merge` 按选定顺序分别请求，每个提供商最多一次。`fallback` 只在主搜索离线、额度不足、限流、上游故障或响应结构不可识别时访问已选备用来源。正常空集、没有本机许可域名命中，以及凭证、配置或权限失败均停止备用切换。
- 每次尝试记录提供商、端点、方法、请求参数、供应商 HTTP 状态、受控错误代码、结果数及可用的重试提示。收到结果时保存原始列表排名、原始 URL、发现时间和可选标题。合成工作台回执保留去重前的供应商发现和查询依据，仅记载通过本机 URL 校验的发现项。原始错误正文、凭证和搜索摘要不写入回执。
- `usage` 独立记载实际请求数、模拟请求数、供应商回执中的用量值、估算计量、实际费用、估算费用和余额状态。演示 `actual_requests=0`，`actual_cost=null`。Tavily 计量单位是 credit，读取合成 `usage.credits`。Brave 计量单位是 request，读取合成月度限额头投影，缺少有效余额时记 `unsynced`。两种计量独立保存。
- 每次模拟分发以当前公开价估算 Tavily Basic 一 credit 为 `0.008 USD`，Brave Search 一请求为 `0.005 USD`，均按标价且扣除套餐抵用之前。由实际供应商账户用量和账单核定真实费用。Brave 公开 FAQ 对真实搜索结果存储要求另有约定，正式使用前逐源审核。[Tavily 定价](https://www.tavily.com/pricing) · [Brave 定价和存储条款](https://brave.com/search/api/) · [Brave 限流头](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting)

## URL 身份与页面回执

`m08-url-v1` 接受最多 2,048 字符的 HTTP/HTTPS URL 和精确允许域名。规范 URL 保持协议、路径和完整查询参数，主机转小写、去掉默认端口和片段、补全空路径。凭证式 URL、非默认端口、非标准或 IP 字面主机、回环或本地域名后缀及不安全转义会被拒绝。同一规范 URL 保留各供应商的独立发现回执，在当前搜索批次的 URL 分母中计一次。

Stack Exchange 演示只走已登记的 HTTPS 问题接口。回源不会请求搜索结果提供的主机，固定 API 路由仅接受验证后的数字问题 ID。预先记录的模拟跳转逐步校验 URL、域名、协议和同一问题 ID，最多五跳。拒绝循环、HTTPS 降级、片段、跨帖、非允许源、凭证式或不安全地址。HTTP 重定向响应不会继续追随。夹具异常和超时记 `inaccessible`，页面正文按 UTF-8 所占字节限为 2,000,000，HTML 只作不可信文本解析。[回源适配器](../../src/ingestion/m08_retrieval.py) · [Stack Exchange API 条款](https://stackoverflow.com/legal/api-terms-of-use)

回执分开记录 `status`、`accessible`、访问与摘录许可、许可引用、原始 URL、规范 URL、跳转链、最终 URL、回源方法、HTTP 状态、抓取时间、原帖发布时间和正文 SHA-256。`discovered`、`accessible`、`inaccessible`、`permission_pending`、`permission_denied`、`quote_extracted` 和 `extraction_failed` 表示不同阶段。访问批准只允许查看页面回执。正常工作台演示的摘录许可为待定，`quote=null`。专项离线夹具可单独验证受许可的合成摘录，要求同一帖子 ID、可核验时间、署名、结构化许可及抽取规则。回执的 `synthetic=true` 和 `research_denominator=0` 隔离其工程用途。

## 本机账本与统计

合成回执写入 `<VOC_DATA_DIR>/m08-offline/acquisition.sqlite3`。每条回执以生成时间、项目、范围、范围版本和回执 ID 追踪，原子提交至独立 v1 账本，写入时清理超过 30 天或最近 100 条之外的记录。工作 SQLite v8、M04/M05 原文入库、M06 资格与统计、M07 注册表及 PackyCode 独立预检账本继续使用既有接口。

工程漏斗仅对完整结果记录 `N_discovered_urls` 和 `N_accessible_pages`。后续原话、当前去重合格及已发布分类分母待相应权威台账，未完整核定时为 `null`。正式漏斗各阶段为 `null`，真实研究须通过 M04/M05 的现有许可和入库流程，再由 M06 判断当前资格。[M06 统计契约](m06-statistics-contract.md)
