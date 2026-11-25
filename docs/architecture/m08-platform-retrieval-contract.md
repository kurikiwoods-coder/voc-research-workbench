# M08-C 平台回源及精确片段契约

截至 2026 年 11 月 25 日，来源目录可登记 Stack Exchange、YouTube 和 Reddit 的逐对象能力。Stack Exchange 与 YouTube 可在隔离工程环境使用合成响应。Reddit 为受阻候选。五项正式权限分别保持未知，真实研究 API 调用为 0。[M08-A 来源权限](m08-source-adapter-contract.md) · [M08-B 发现与固定回源](m08-search-and-retrieval-contract.md)

## Stack Exchange

| 对象 | 官方 v2.3 路由与最小字段 | 合成校验 |
| --- | --- | --- |
| 问题 | `/questions/{ids}`。采集所需字段包括 `question_id`、`link`、`title`、`body`、`creation_date`、可选 `last_edit_date`、`content_license` 和最小作者署名。 | 核对请求 ID 与允许站点的问题链接。可见正文抽取独立判断。 |
| 回答 | `/answers/{ids}` 按回答 ID 获取。问题下的回答可通过 `/questions/{ids}/answers` 发现。正文、许可、署名、发布时间和可选编辑时间取回答本身。 | 同时校验回答 ID、所属问题 ID 和回答定位。 |
| 评论 | `/comments/{ids}` 按评论 ID 获取。问题或回答所属的评论可由对应 `/comments` 子路由发现。评论有独立 `content_license` 和 `creation_date`，`edited` 只有布尔值。 | 校验父帖类型、ID 和评论锚点。无可核验编辑时间时保留空值。 |

正式接入需使用能返回最少字段的 API filter，核对每条对象自己的许可版本、原作者和原始定位，遵守来源展示与署名要求。缺少已识别许可或署名批准时停止存储。遵守 API 的 `backoff` 和每日配额，避免一分钟内重复同义请求。夹具沿用 M08-A/B 已登记的精确站点白名单及 HTTPS 路径校验，抽取规则独立于品类。[问题](https://api.stackexchange.com/docs/types/question) · [回答](https://api.stackexchange.com/docs/types/answer) · [评论](https://api.stackexchange.com/docs/types/comment) · [字段过滤](https://api.stackexchange.com/docs/filters) · [API 条款](https://stackoverflow.com/legal/api-terms-of-use) · [限流](https://api.stackexchange.com/docs/throttle)

## YouTube Data API

| 对象 | 官方接口与配额 | 合成范围 |
| --- | --- | --- |
| 视频发现 | `search.list` 使用 `type=video`。每次调用消耗独立 Search Queries 配额 1 单位，默认每日 100 次。 | 提取视频 ID 和规范来源 URL。搜索摘要未进入原文。 |
| 公开元数据及描述 | `videos.list` 的 `snippet` 提供标题、描述、频道与发布时间，请求消耗共享配额 1 单位。 | 元数据按背景角色处理。描述作为产品或商家内容单独核验。两者不生成用户发生片段。 |
| 评论及回复 | `commentThreads.list` 提供顶层评论及可能不完整的回复。完整回复经 `comments.list` 使用 `parentId`。各请求消耗共享配额 1 单位。 | 验证获准顶层评论的夹具身份和原文字段，以及禁用评论、权限拒绝和限额状态。回复、分页及评论研究扩展保留至 M08-E。 |
| 字幕轨道及文本 | `captions.list` 需要 OAuth 授权，只返回轨道信息，消耗 50 单位。`captions.download` 还要求有权编辑视频，消耗 200 单位。 | 轨道及文本均登记为需要授权。 |

YouTube 可以改变 `textDisplay` 的链接等内容，即使请求 `plainText`。官方资源仅向经认证的评论作者返回 `textOriginal`。顶层评论夹具模拟已授权作者的原文字段，缺少该字段返回 `original_unavailable`。真实公开视频、评论和字幕各自需要账号通路、用途审批和许可审核。过滤或分页请求另计，共享配额与 Search Queries 独立记录。[视频搜索](https://developers.google.com/youtube/data/reference/rest/v3/search/list) · [视频资源](https://developers.google.com/youtube/data/reference/rest/v3/videos) · [评论原文字段](https://developers.google.com/youtube/data/reference/rest/v3/comments) · [评论串资源](https://developers.google.com/youtube/data/reference/rest/v3/commentThreads) · [字幕列表](https://developers.google.com/youtube/data/reference/rest/v3/captions/list) · [字幕下载](https://developers.google.com/youtube/data/reference/rest/v3/captions/download) · [配额](https://developers.google.com/youtube/data/determine_quota_cost)

正式审批须覆盖 YouTube 对 API 数据用途及衍生数据的限制，并核实本工作台统计与提取用途。开发政策对相关的授权数据和有限非授权数据要求最长 30 个日历日后删除或刷新。正式留存和删除机制待逐源审查及验证。[YouTube 开发政策 III.C、III.E](https://developers.google.com/youtube/terms/developer-policies)

## Reddit 候选

Reddit 要求事先明确批准、注册客户端、适用 OAuth 及如实声明身份与用途。Reddit for Researchers 面向获批的非商业研究，商业用途须 Reddit 批准及独立协议。符合免费额度资格的 OAuth 客户端以 10 分钟窗口平均 100 查询/分钟，实际额度以授权和限流回执为准。须删除 Reddit 已删除的内容和对应账号的身份信息。官方 Wiki 建议例行清理存储的用户数据，匿名化无法替代删除。[Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy) · [Reddit for Researchers](https://www.reddit.com/r/RedditforResearchers/) · [Data API 条款](https://redditinc.com/policies/data-api-terms) · [Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)

目录区分搜索发现、公开元数据、帖子及评论。合成 listing 验证对象结构、权限受阻、限额及服务不可用。受阻回执无正文和证据。正式访问、存储、研究、外发及自动备用采集持续关闭。[Reddit Data API 方法](https://www.reddit.com/dev/api/)

## 证据与权限

- `platform_catalog()` 输出来源概要、独立权限、逐对象能力、配额及审批缺项。`project_fixture()` 接收一个固定来源的合成响应对象及服务器选择的操作授权。发现权限放行发现字段，访问权限放行访问判断，存储权限和署名判断放行正文保留，研究权限与核定内容角色共同放行候选片段。合成适配器没有模型外发通路。
- `retrieve_fixture(source_id, batch_no=…, limit=…, published_date=…, fetched_at=…)` 按调用方提供的冻结范围内日期生成合成样本，用来源、批次号及返回序号稳定索引。发布时间和模拟采集时间分别记录。采样适配器没有 URL、凭据或传输参数。原始链接及页面身份经 M08-B 规范化规则和精确对象校验。M08-B 既有回源保留 DNS、私网和重定向边界。新适配器读取内存夹具，拒绝转跳响应、错误媒体类型以及超过 2,000,000 UTF-8 字节的正文。嵌入标记只作纯文本投影。
- `m08-visible-lines-v1` 以可见非空段落或行生成候选。论坛 API HTML 投影确定块边界、解码字符实体、压缩空白并移除隐藏内容。YouTube 评论原文字段直接作为正文。正文 `raw_sha256` 为进入 M05 的不可变 UTF-8 文本摘要，`response_body_sha256` 对照原始 API 正文字段。候选以半开 Unicode 码点区间 `[start,end)` 对该正文精确切片，保留规则版本。`original_url`、`canonical_url` 和 `source_locator` 分别保存 API 链接、去重页面身份和精确对象定位。
- 来源的内容角色区分用户原话、背景、产品或商家内容、内部材料及合成材料。当前夹具的入库角色固定为 `synthetic`。搜索摘要、改写和模型生成内容无法形成原话证据。采样任务绑定项目及精确冻结范围，只有经 M04/M05 入库并由 M06 验证摘要和区间后才获得相应模式的稳定证据引用。正式分母保持不可用。[M06 核心数据模型](m06-data-model.md) · [现有采样统计](m06-statistics-contract.md)
