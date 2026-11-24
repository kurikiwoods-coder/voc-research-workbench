# P0-0 本地运行与取证

工作台接受任意研究主题。StudyScope 可关联零个、一个或多个产品品类。这里的厨房论坛检索词是稳定的小型技术探针。召回演练的智能手表与空气净化器同属合成测试域。两组材料都不进入正式研究统计。

## 启动

Windows 10/11 安装 64 位 Python 3.12，自开发分支下载代码并解压，双击 `scripts/start-windows.cmd`。脚本在项目内创建虚拟环境和空白配置，安装依赖，然后启动服务。打开 <http://127.0.0.1:8765/>。可在 PowerShell 的项目目录手动执行下列命令。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
```

macOS/Linux 使用 Python 3.12。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
python -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
```

打开「连通性检查」，点「运行检查」后确认本次范围。连通性运行会尝试当前可用的服务。查看页面、刷新余额和下载现有证据只访问本机。批次中断后从「运行记录 → 查看批次 → 恢复此批次」继续。成功分片重放缓存，结果保留此前各次执行的时间与证据 ID。缺失凭证的批次可在首次配置密钥后恢复；已有 Jev 请求的批次绑定原账户。更换账户请建新批次。

## 从工作台配置 API

1. 在本机打开工作台。首次启动会提示选择 Jev 通道和搜索引擎。「稍后配置」可直接进入工作台，从「设置 → API 接入」能再次打开向导。
2. 在 TypeSafe 和 JevModel 之间选择一个当前通道。通过供应商卡片的「官方控制台」取钥，粘贴到密码框并点「保存密钥」。同样配置 Tavily 或 Brave 中的至少一个。保存、更换和删除立即生效。两种 Jev 通道的凭证和审核材料各自保留。
3. 在所选 Jev 通道点「导入留存审核」。选择已有的审查 JSON 和对应证明附件。JSON 上限 32 KB，附件上限 1 MB。工作台核对供应商、审批字段、日期和附件摘要，将材料保存在本机。审查由实际管理人员根据供应商账户和条款完成。[审查材料格式](#变量与审核凭证)
4. 在对应卡片点「检查连接」，展开「最近测试证据」。实际请求可能消耗供应商额度。Jev 只发送程序内置的合成句子，按 8 + 3 题检查固定模型、三类字段、逐档概率、用量和分片键。遇到留存审核未完成时，检查保存阻塞证据。搜索检查先查看命中，再向允许的原帖接口核对出处、许可和原句。
5. 点击「运行正式验收」并确认。只有正式批次的六项检查和留存审核全部满足，G-1 才通过。诊断记录的正式研究分母为零。

YouTube 和 Google Forms 卡片可查看官方入口。公开视频采集安排在 P0，Forms OAuth 和问卷回流安排在 P1。[YouTube 授权文档](https://developers.google.com/youtube/data/guides/authentication) · [Google Forms 快速入门](https://developers.google.com/workspace/forms/api/quickstart/python)

### 注册与创建密钥

从工作台保存密钥是日常配置入口。已有后端环境变量可继续使用，界面会注明来源。

| 供应商 | 注册与取钥 | P0-0 所需能力 |
|---|---|---|
| TypeSafe · `TYPESAFE_API_KEY` | 在官方控制台注册或登录，选择实际使用的组织并创建 API key。通过支持页选择 **Privacy & data → Enable zero data retention**。收到确认后在 **Settings → Organization** 核对启用，并留存审查附件。设置 `JEV_PROVIDER=typesafe`。[官方控制台](https://console.typesafe.ai/login) · [ZDR 官方说明](https://help.typesafe.ai/articles/9520184411) | 账户可调用 `jev-1.14.0`。真实的 8 + 3 分片须返回固定模型、Choice、Score 的逐档完整概率及 Noul。[账户模型接口](https://docs.typesafe.ai/api/list-models) · [Score](https://docs.typesafe.ai/primitives/score) |
| JevModel · `JEVMODEL_API_KEY` | 在 JevModel 控制台登录或新建账户，从 **API keys** 创建密钥并记录该供应商的留存及分处理商审查。设置 `JEV_PROVIDER=jevmodel`。[控制台](https://jevmodel.org/zh/dashboard/) · [接口文档](https://jevmodel.org/zh/docs/) | 实测固定 `jev-1.14.0` 和完整 Score 分布。若出现别名、缺字段或模型不可用，按真实响应记录阻塞并人工决定是否切换供应商。 |
| Tavily · `TAVILY_API_KEY` | 从官方文档的 **Get API key** 进入平台，注册或登录并创建 API key。[控制台](https://app.tavily.com/home) · [Search 文档](https://docs.tavily.com/documentation/api-reference/endpoint/search) | 账户允许 Search 请求。需通过 Tavily 实际发现允许回源的 URL 并核对原文许可。 |
| Brave · `BRAVE_API_KEY` | 在 Brave Search API 注册，按控制台的套餐和 API Keys 指引创建密钥。[注册链接](https://api-dashboard.search.brave.com/register) · [API 快速入门](https://api-dashboard.search.brave.com/documentation/quickstart) | 账户启用 Web Search API，支持 `X-Subscription-Token`，实际发现的 URL 可用于许可回源。 |

### 保存与删除

工作台通过回环地址接受同源配置操作。凭证库位于工作区的 `credentials/` 目录（默认 `runtime/credentials/`），配置以原子替换方式保存。Windows 用当前系统用户的 DPAPI 加密。Linux 和 macOS 以文件系统权限保护凭证，目录限当前用户访问（0700），文件限当前用户读写（0600）。浏览器只在提交时发送密钥至本机后端。前端存储、公开接口、日志和证据导出不含原始密钥。[Windows DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)

界面设置优先于环境变量。删除环境来源的密钥时，工作台停用该值，环境文件中的原记录由部署人员管理。要在供应商侧撤销密钥，请使用供应商控制台。更换账户后，请从配置页重新检查连接并创建正式批次。旧批次仍可回看。

### 状态和额度

| 状态 | 含义 |
|---|---|
| NOT_CONFIGURED | 未配置凭证 |
| NOT_TESTED | 当前凭证尚无有效的诊断结果 |
| CONNECTED | 服务已响应。搜索还没有同时通过来源、许可和原话核验 |
| CAPABILITY_BLOCKED | 实际响应的模型或字段缺失。查看证据的 `schema_gap` |
| REVIEW_REQUIRED | 对应 Jev 通道的留存审查尚未完成 |
| READY | 当前供应商的连接条件与诊断契约已核验 |
| ERROR | 连接或请求失败。按 HTTP 状态采取操作 |

额度栏显示返回的余额、最近一次同步、已知上限和本机用量。缺可信余额时显示「未同步」。Jev 使用实际 `usage.input_tokens` 核对本机消耗，JevModel 从 `X-Tokens-Remaining` 读取余额。Tavily 使用实际返回的 credits 汇总本机诊断。Brave 显示可识别的月配额，诊断用量按成功请求计数。界面保留 G-1 单独状态。预算闸门在 P0 范围内。[JevModel 计费](https://jevmodel.org/zh/docs/) · [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) · [Brave 限流响应头](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting)

### 变量与审核凭证

| 变量 | 用途 |
|---|---|
| JEV_PROVIDER | jevmodel 为默认第三方通道，typesafe 为官方通道。选择哪个就只调用哪个。固定模型写入程序。 |
| JEVMODEL_API_KEY / TYPESAFE_API_KEY | 可选部署方式，提供账户凭证。服务启动时读取，工作台可覆盖或停用。 |
| TAVILY_API_KEY / BRAVE_API_KEY | C0-3 综合验收至少一个指定引擎须实际发现允许回源的链接。两个引擎各自留证。 |
| JEV_REVIEW_FILE | 本机 JSON 审查记录的路径。凭证文件保留在仓库之外。 |
| JEV_TOKEN_CAPACITY | 可选的、已核对的第三方账户额度上限，用于进度百分比和 20% / 5% 预警。余额未知时保留空值。官方货币账户单独展示。 |
| VOC_DATA_DIR | 诊断数据库目录，默认 runtime/。Windows 可填写用户目录下的绝对路径。 |
| YOUTUBE_API_KEY | 预留给 P0 的 YouTube 适配器。P0-0 不读取。 |

公开短句外发须有与服务商相符的留存审查。下表是 JSON 字段说明，运维应填写真实值，另存附件并计算 SHA-256。本机只对前端公开审核状态，对审计记录公开核验时间和摘要。

| 字段 | 所需信息 |
|---|---|
| provider / checked_at | 所选通道，及带时区的实际审核时间 |
| reviewer / region / terms_reference | 实际审查人、处理地区、已审条款版本或地址 |
| evidence_file / evidence_sha256 | 审查附件的文件名或本地路径及 SHA-256。界面使用你选中的附件。环境变量方式下，会按 JSON 指定的路径读取。Windows 可用 Get-FileHash 查值，使用小写十六进制。 |
| public_text_approved | 实际批准发送经许可、脱敏公开原话时填写 true |
| zdr_enabled | TypeSafe 需要真实组织控制台的启用记录 |
| retention_reviewed / subprocessors_reviewed | 独立第三方 JevModel 的留存及转发链分别审查 |

内部 CX 与非公开材料只允许留在本机。后端的外发闸门先检查所有来源标签，混有内部或无授权标签时会在 HTTP 客户端调用前拒绝。前端只接受预定义探针和批次 UUID。审查记录是管理人员对组织设置的本地凭证，核验范围为供应商、审批字段、日期以及附件摘要。

## 数据与接口

SQLite 迁移位于 `src/raw_store/migrations/`。服务从空库启动时自动建表。runs 保存批次，attempts 保存重试，results/evidence 只追加。shards 以批次、分片号和正文摘要绑定幂等键，用于恢复和计量。进程锁保证同一数据目录一次仅执行一个写批次。真实公开样本是连通性证据。C0-5 使用单独的临时合成数据库，C0-6 使用内存数据库。本地正式研究分母为零。研究结束后，按来源保留策略管理和清理本机证据库及备份。

| 接口 | 用途 |
|---|---|
| GET /api/health | 检查服务和迁移版本 |
| GET /api/workspace | 当前验收矩阵、批次历史、配置是否就绪、当前账户的额度记录 |
| GET /api/workspace?run_id=UUID | 回到所选批次核查，同批计算状态 |
| POST /api/runs | JSON 含 request_key（UUID）；同键返回原批次 |
| POST /api/runs/{id}/resume | 恢复同一批次，保留各次尝试 |
| GET /api/runs/{id}/evidence | 本地完整的脱敏证据、时间、HTTP 状态和历次验收结果 |
| PUT /api/setup/{provider}/key | 在本机保存或更新密钥，只返回配置状态 |
| DELETE /api/setup/{provider}/key | 删除本机密钥或停用该环境凭证 |
| PUT /api/setup/jev/{provider} | 选择当前 Jev 通道 |
| PUT /api/setup/{provider}/review | 本机导入审查 JSON 与附件，核对后生效 |
| POST /api/setup/{provider}/diagnostics | 使用唯一请求键执行一次连接诊断，独立保留脱敏证据 |

写接口要求同源，使用请求头 `X-VOC-Action: connectivity`。本机信任 localhost 和 127.0.0.1。Jev 每片响应独立保留，输出概率须有合法范围与完整分布。不能确认是否已扣费的传输中断会暂停该分片并要求核对。401、402、422 会记录具体原因；429 和有幂等保证的 502 使用同键限次退避。长 Retry-After 留待后续恢复。Token Center 跳转供应商购买页，用量和余额的留存来源分别是 usage.input_tokens 与真实余额头。

### 失败时核对

| 页面状态或响应 | 检查位置 |
|---|---|
| 未配置 / 未测试 | 在 API 接入页核对当前通道，保存密钥后点击「检查连接」。 |
| 审核未完成 | 核对供应商、审批类型、实际附件和 SHA-256 后重新导入。 |
| HTTP 401 / 403 | 核对密钥所属账户、模型或搜索权限，以及账户状态。 |
| HTTP 402 / 429 | 在供应商控制台核对余额或限流。有 Retry-After 时按响应等待。 |
| HTTP 422 / 能力不满足 | 查看当前批次的模型、请求字段和 `schema_gap`。文档中的示例响应可用于对照。 |
| HTTP 5xx | 核对供应商服务状态。供应商可能已接单时，先核对请求和账单，再发起检查。 |
| 传输中断、计费待核对 | 一旦结果可能已经被供应商接收，用原分片键核对供应商账单或请求记录。本地只自动重放已落盘成功片，未落盘时把批次保留在待核对状态。 |

## 来源边界

公开检索限定在预先登记的站点。搜索摘要只作候选线索。后端仅向固定 HTTPS API 发请求，核对原帖 ID、原网址、公开许可、署名和发表日期，摘录原话并登记采样时间。可在本机抽屉回看来源、引用和许可。仓库留存端点、字段、状态、摘要与合成演练，正文及署名保留在本机。Stack Exchange 许可来自各帖子返回的 content_license。源站维护、额度或权限异常时保留相应状态。[Stack Exchange API](https://api.stackexchange.com/docs) · [API 条款](https://stackoverflow.com/legal/api-terms-of-use)

固定版本与问答字段分别按管道核验。供应商的公开示例只用于编写适配器，最终以本账户的真实响应验收。[TypeSafe Score](https://docs.typesafe.ai/primitives/score) · [TypeSafe 数据使用](https://help.typesafe.ai/articles/5974925716) · [第三方接口文档](https://jevmodel.org/zh/docs/)

**选择复测供应商。** TypeSafe 的模型目录列有 `jev-1.14.0`，Score 文档定义了每档概率。有组织 ZDR 审查记录和相应 Key 后，可在本机将 `JEV_PROVIDER` 明确设为 `typesafe` 并新建批次。JevModel 公开文档示例使用 `jev-latest`，其 Score 示例只列分数与置信度。走该通道时仍发送 `jev-1.14.0`，逐字段保存真实响应。两个通道均按工作台规则拆为 8 + 3 题。[TypeSafe 模型目录](https://docs.typesafe.ai/models) · [账户模型查询](https://docs.typesafe.ai/api/list-models) · [TypeSafe Score](https://docs.typesafe.ai/primitives/score) · [JevModel 服务说明](https://jevmodel.org/zh/docs/)

## 复测

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/client_state.test.cjs
python scripts/cold_start.py
python -m playwright install chromium
python tests/browser_e2e.py
```

有真实密钥、供应商留存审查和指定搜索源权限后，可在界面执行正式验收，也可运行 `python tests/live_gate.py`（读取同一个本机凭证库）。CI 运行工程检查和无需密钥的匿名公开来源浏览器测试。Node 24 用于前端状态回归。

已发布批次可离线交叉核对 SQLite 与 JSON，也可向原帖接口重新取证。后者返回 0 表示原句及许可一致，1 表示观察到差异，2 表示无可用响应或原帖不可读取。独立复核不会修改已发布的批次。

```sh
python -m src.outputs.audit_receipt --verify docs/evidence/p0-0
python -m src.outputs.audit_receipt --verify-source docs/evidence/p0-0
```

离线工程测试使用独立临时目录。cold_start 会在运行操作系统上用三个独立空库真实启动和停止服务。浏览器脚本启动自己的本地临时服务，仅匿名访问公开来源，保存桌面、窄屏和抽屉截图到 test-results/browser/。指定现有 Chromium 时，可设置 VOC_CHROMIUM。live_gate 使用本机真实环境，凭证齐备时会产生供应商用量。退出码 0 表示全门通过，1 表示测试错误，2 表示存在阻塞。可在「运行记录」回看该次检查。四周历史与真实问卷继续等待相应阶段的运营样本。
