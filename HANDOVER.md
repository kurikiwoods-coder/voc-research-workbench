# 开发交接

## 当前接续 · M09-C 实机复验通过，待负责人验收

活动分支 `codex/g1-personal-phase-1`，沿用草稿 PR #2。**M09-A/B = ENGINEERING_PASS**，**M09 = PARTIAL**，本机已验收核心 **41/79**。M09-A 原生 Windows 11 CPU 的实际模型通过 3/3。M09-B 定向及上游回归通过 86/86，真实运行专项 3 项通过、3 项主题纯度诊断未通过。[向量接口、安装及复验](docs/evidence/m09-a/README.md) · [聚类接口及证据](docs/evidence/m09-b/README.md)

M09-C 的本地发现服务 TopicRuns 提供已封存快照、精确证据回查、离线复跑与比较。2026-11-28，原生 Windows 11 26H2 x64（26300.9974）完成固定模型复验。受控重建的 `jieba==0.42.1` 经两次独立构建哈希一致，锁定依赖离线安装 44/44，`pip check` 通过。专项 22 通过、0 失败、3 项 G3 诊断跳过，进程审计的非回环尝试 0。M09-C 为 **PENDING_ACCEPTANCE**，待负责人验收。M09-D 候选视图与独立留出集待负责人授权，G3 保持待验收。[接口、备份与复验命令](docs/evidence/m09-c/README.md)

后续交付记录功能完整度、技术验证、质量缺口、Token 效率、成本风险和接续条件，并附 SHA、PR、工作区状态与下一阶段交付条件。以实际执行和可核验证据填写，缺少 Token 数据时填 N/A。[工程交付报告规范](docs/decisions/product-realignment-v1-owner-approval.md#工程交付报告规范)

## 研究优先策略与当前接续

2026-11-27 负责人批准 PRODUCT-REALIGNMENT-V1。先交付 Personal 的完整研究闭环，Business 保留共享核心和原治理标准。API & AI Model Center 复用三类模型适配器与独立采集连接器，首版 Decision 验证仍用 Jev。现有 M09 工程授权、数据契约与证据口径继续适用。[正式 ADR](docs/decisions/product-realignment-v1-owner-approval.md) · [适配器契约](docs/architecture/ai-model-adapter-contract.md)

按模块选择性复用成熟开源组件，先核对依赖许可、兼容性和本地部署条件。M01–M08 只按批准范围增量调整，M06 保持冻结。各模块先完成可用流程与真实数据接入，M15-F 后、P2-R 前在既有交付范围内统一视觉与研究交互。M09-A 复验与 M09-B 接续沿用原授权及前置条件。[增量开发与开源复用](docs/decisions/product-realignment-v1-owner-approval.md#增量开发与开源复用)

继续 M09 隔离工程，之后推进 M10、单独授权的 I18N-PRE 和可独立验收的 M11 单元。M11 先用隔离夹具验证编码复核接口。M12-A 单独授权时实施 G-1 Personal 与 M02 最小增量，在正式真实研究和模型校准前恢复 G-1-P-D/R。完成 M12 校准及余项后执行 M11/M12 原定联调，再按原分期接续。M10 如确需提前调用外部模型，须取得该用途的独立授权并遵守现有门禁。[当前开发顺序](docs/planning/ROADMAP-V2.md#当前接续顺序)

G-1 暂停期间，既有工程和验收证据继续有效于其原范围。PackyCode 账户条款问题留在原通道记录。Personal 正式门禁为 **NOT_EVALUATED**，Business 正式门禁为 **BLOCKED**。以下四槽草案保留供历史追溯。现行隔离工程及正式研究的授权边界以本节和个人门禁政策为准。[个人门禁](docs/architecture/personal-research-gate.md) · [当前仓库状态](DEVELOPMENT_STATUS.md#product-realignment-v1-与当前工程状态)

## G-1-PERSONAL V2 既有工程与草案

开发分支 `codex/g1-personal-phase-1`，草稿 PR #2。现有 Personal v11 独立验收工作区的原生 Windows 11 部署证据绑定源码 `6d70cd5011a249c83bf6c9df15f3900c2f595994`。既有复验包含可信本机 Owner、工作库及恢复连续性。草案列明当前账户、凭证、通道、条款、逐源许可、脱敏、费用和剩余风险材料。[Windows 11 历史部署证据](docs/evidence/g1-p-d/d-l-windows11-deployment.md) · [V2 授权草案](docs/evidence/g1-p-d/personal-v2-authorization-draft.md)

既有未签发的四槽草案依次登记 Tavily、同一命中的官方回源、PackyCode 前 8 题及后 3 题，每槽一次。两个模型槽固定于 `typesafe-officially`、`/v1/systemone`、`jev-1.14.0`，共用一份 C0-2 脱敏及题组复核。草案中的来源核验、预算、对账与证据复用要求保留。[个人准入政策](docs/architecture/personal-research-gate.md)

在本机批准包保留未知费用风险的区别，以 `null` 记录，并引用 Owner 已签发的风险接受证据和金额。实际账户、凭证与令牌额度须和该批绑定。当前草案待签发，正式同批 0/6，真实请求 0。**G-1-PERSONAL = NOT_EVALUATED，G-1-P-D = BLOCKED，G-1-P-R = NOT_STARTED**。商用 G-1 **BLOCKED**。下列 D-E 与 D-L 条目保留其交付时的状态和证据。

## M09 离线隔离开发接续

四槽真实实证因当前 PackyCode 账户的个人用途无法确认而暂停。M09-A/B 已完成本机离线工程验收，M09-C Windows 11 复验通过，工程交付待负责人验收。正式运行依适用版本门禁。[工作单元](docs/planning/ROADMAP-V2.md) · [M08 消费契约](docs/architecture/m08-consumer-handover.md)

1. **M09-A**。在临时 SQLite 和合成夹具中接续 M05 资格、M06 冻结范围与片段版本、M07 精确封版注册表及 M08 追溯。保存预处理、输入摘要、向量模型与维度版本。原话语言、分析语言及输出语言分别传递，保留模型多语言能力配置。合成向量验证适配器契约，固定 MiniLM 权重复验中英相似度、向量与缓存复跑。
2. **M09-B/C**。使用预装且获准的本地模型和固定 BERTopic 参数验证聚类。在断网环境保存并复跑主题、成员、参数、运行版本、证据引用与差异。回查须重验当前资格和精确片段版本。原话只读，候选与正式注册表分别保存。
3. **M09-D**。用合成已知主题、未知主题、空结果和跨品类样本验证候选交接、证据下钻与盲测。复验跨项目隔离、失效证据拒绝、可重放、正式统计隔离，并记录结果与 GitHub CI。运行测量标明合成或本地模型证据及适用范围；准入、真实语料处理、正式编码和发布由各自门禁判定。

隔离环境使用合成数据和无凭证运行配置，关闭出网，模型和依赖从已有的获准离线资产准备。缺失依赖时先完成本地接口与合成回归，真实模型验证据实挂起。[适配器协议](docs/architecture/ai-model-adapter-contract.md) · [语言接口约束](docs/decisions/i18n-pre-owner-approval.md)

## G-1-P-B-V 与 G-1-P-C 接续

工作分支 `codex/g1-personal-phase-1`，草稿 PR #2，目标 `codex/p0-0-connectivity`。本机从 `0d43be5f7b707c4ad8a3384dabc5c595b15d0b7b` 接续。B-V 的原生实机及部署门禁和证据提交 `97e942d` 的三项 CI 通过。C 验收源码为 `912ff28e0a10e3329bc49c6e9fdc97e290229a68`。[B-V 证据](docs/evidence/g1-p-b-v/README.md) · [C 验收](docs/evidence/g1-p-c/README.md)

**G-1-P-B = ENGINEERING_PASS**，验收源码 `d7c711660843c8c095fccbedd4b67d5303f9226b`。[三项 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45749971864)

个人版通过本机可信启动开启。Owner 在「版本与研究准入」选择获准项目，按权限配置本机凭证、登记材料和风险、提交申请、批准或撤销。C 工作库 SQLite v9，经隔离验证后接续。G-1-PERSONAL 为 **NOT_EVALUATED**，原商用 G-1 为 **BLOCKED**。原 PackyCode 执行与续跑授权已耗尽。M06 冻结，核心进度 39/79。[可信启动](docs/architecture/g1-personal-server-policy.md) · [C 契约](docs/architecture/g1-personal-approval-contract.md)

**G-1-P-D = BLOCKED，G-1-P-D-E = ENGINEERING_PASS**。D-E 交付 `4c7d705b277352af530c59f917f787bcc3a69bfd` 的三项 CI 已通过。隔离 Windows 11 核验 Personal v10 迁移备份、回滚、撤销连续性、Business v9 兼容及合成执行。继续采用草稿 PR #2。[D-E 工程证据](docs/evidence/g1-p-d/engineering.md) · [D-E 交付 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45794168453)

**G-1-P-D-L 真实执行 `BLOCKED`。** Windows 11 定向复验 70/70、原生 DPAPI 3/3。新建 Personal v11 独立验收工作区已验证本机 Owner、ACL、备份、恢复与重启回读。接续使用当前 Windows 用户的 LocalApplicationData 下的专用目录，实际位置及受保护部署材料只在本机使用。核对独立恢复连续性、当前账户与凭证、限额和逐操作授权。两个模型槽位保留 `LIVE_MODEL_HARD_BUDGET_UNVERIFIED`。正式同批 0/6，真实请求 0，正式历史证据纳入 0。G-1-P-R 与 M09–M15 为 `NOT_STARTED`，I18N-PRE 为 `PLANNED`。[Windows 11 与部署证据](docs/evidence/g1-p-d/d-l-windows11-deployment.md) · [D-L 授权草案](docs/evidence/g1-p-d/d-l-authorization-draft.md)

对账按供应商、账户与供应商请求 ID 绑定唯一归属。SQLite 结算与受保护费用档案任一侧缺项时停止新发送。恢复原结算须核对原档案和逐笔账单。各操作须独立批准账户、凭证、来源、载荷、硬上限及 UTC 窗口。[D-L 工程证据](docs/evidence/g1-p-d/d-l-engineering.md)

## G-1-PERSONAL Phase 1 与后续授权

接续 M09、M10 时先核对适用准入及独立开发授权，并遵守语言参数、Embedding 能力、TopicGPT 多语言 Prompt、原话证据和稳定 ID 的提前约束。M10 验收完成后，等待负责人单独授权 I18N-PRE，在 M11 开始前完成专项。[授权与约束](docs/decisions/i18n-pre-owner-approval.md)

基于已验收的 M08-V `dd89a14`，交付双版产品规划、个人最低准入及两条 PackyCode 费用证据。各阶段按实际授权接续。接续顺序为 G-1-P-B 服务端版本策略、G-1-P-C 个人审批、G-1-P-D 同批实证、G-1-P-R 独立复审。个人版准入及 M09 各自待负责人授权。**G-1-PERSONAL = NOT_EVALUATED**，商用 **G-1 = BLOCKED**，M09 = **NOT_STARTED**。[批准记录](docs/decisions/dual-edition-owner-approval.md) · [下一轮实施与测试](docs/planning/g1-personal-implementation-plan.md)

后续保留旧 `run_checks`、分片和传输的 PackyCode 真实阻断，个人版由可信服务端作用域独立判定。两版共用全部研究引擎，版本和部署方式独立，保留原关系、可信权限、实时资格及统计口径。[个人门禁](docs/architecture/personal-research-gate.md) · [商用门禁](docs/architecture/business-research-gate.md) · [风险审批](docs/architecture/personal-approval-workflow.md)

历史费用 **$0.000238** 已据原始 CSV 脱敏补证。个人 Windows 10 的原始 SQLite 及相关材料需设备内只读复核，标记 **LOCAL_VERIFICATION_PENDING**。原发送授权已耗尽，复核以原证据为准。M08-V 的 Windows 11 实机与部署 PASS 按原验收源码保留。[费用及本机核对](docs/evidence/g1-rb-f/README.md)

## M08-V 跨设备接续

`codex/p0-0-connectivity` 在公司 Windows 11 上从 `3bd705b` 安全快进 9 个提交至验收源码 `74590d4a4d43a66c7a3296943da9205bc6ff65e0`。M08-V、Windows 11 实机及部署门禁均通过。后续部署用现有受控迁移及一致性备份升级工作库至 v8，保留诊断、演示、任务及 PackyCode 预检的独立账本。[Windows 11 实机证据](docs/evidence/m08-v/README.md) · [v7→v8 恢复证据](docs/evidence/m08-v/database-migration.md)

M08-V 验收时，M08-E 与 M09–M15 均尚未启动。接续按项目、冻结范围、记录、精确片段与 M07 封版注册表指针读取当前合格证据。G-1 当时为 BLOCKED，正式准入、外发、供应商审批及同批验收按原矩阵处理。该轮真实研究 API 和真实供应商探针各 0 次。当前 M09 状态见本页顶部。[M09 消费契约](docs/architecture/m08-consumer-handover.md)

## M08-C/D 接续

「来源采集」页面支持固定合成计划、平台许可、任务检查点、暂停及继续。Stack Exchange 与 YouTube 在隔离夹具中回源，Reddit 是禁用候选。每任务独立 v8 工作库保存 M04 批次、M05 审核和本机回执，任务 v1 账本在 `m08-sampling/ledger.sqlite3`。结果未知的计量预约继续阻断。只有已提交的本机回执可以恢复结算。[平台回源](docs/architecture/m08-platform-retrieval-contract.md) · [任务契约](docs/architecture/m08-acquisition-task-contract.md) · [验收证据](docs/evidence/m08-cd/README.md)

M08 的 P0 工程通过。M09 获得授权后，按项目、冻结范围、批次、记录、M06 片段版本及 M07 精确注册表版接续。当前合成样本仅允许工程回查。正式业务和 G-1 的来源、供应商、同批验收要求继续适用。[M09 消费交接](docs/architecture/m08-consumer-handover.md)

## M08-A/B 接续

本机工作台左栏进入「来源采集」，选择项目及冻结范围。查询计划显示供应商映射和限制，离线演示以固定合成文本产生发现及页面访问回执。运行目录中的 `m08-offline/acquisition.sqlite3` 保存演示证据。正式采集返回 403，正式漏斗缺数据时为 `null`。[来源权限契约](docs/architecture/m08-source-adapter-contract.md) · [双搜索与回源契约](docs/architecture/m08-search-and-retrieval-contract.md) · [验收证据](docs/evidence/m08-ab/README.md)

本节保留 A/B 结项记录。G-1 仍为 **BLOCKED**，PackyCode 供应商审批、实际完整对账和同批六项正式验收继续待办。

## G-1-R-B-P 接续

在个人电脑普通 Windows 用户会话运行 `python -m src.execution.packycode_preflight` 查询合成回执。同一账本已有两次预约和两份成功响应，11 题合并回执为 **PASS**，此次发送授权已耗尽。保留原账本和账户证据。两片控制台实际费用已由原始 CSV 补证，个人 Windows 10 原始账本待本机复验。[追加证据](docs/evidence/g1-rb-f/README.md)正式 G-1 的供应商审核及 C0-1 至 C0-6 同批验收仍适用。[安全决定](docs/decisions/packycode-synthetic-preflight.md) · [验收证据](docs/evidence/g1-rb-p/README.md)

## G-1-R-A 接续

本机工作台打开「API 配置」，在 PackyCode 卡片查看端点、分组、固定模型、凭证、审查和计费状态。负责人可在普通 Windows 用户会话通过该卡录入独立短期凭证。账户审核材料先留本机，绑定到当前凭证后再导入。轮换或删除凭证会清除关联审批。[配置、供应商证据和后续预检](docs/packycode.md)

本轮既有传输门禁和正式 G-1 均阻塞。下一授权入口先检查 PackyCode 当前账户及实际上游的证明，准备受控合成预检及预算，然后按同批次六项及原审批标准处理 G-1-R-B。交接以草稿 PR #1 对应 SHA 的三项 CI 为准。[工程证据](docs/evidence/g1-ra/README.md) · [PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

## M07 意图注册表接续

开发由 `7c02966eb7e6c54f8e30ff032f921bac6719d1d2` 开始。源码 `5a3bd4189d6f3e3951bdcc0d79ce79db5c8060e8` 已通过 Windows 10 开发工程验收及三项源码 CI。M07 使用 SQLite v8。迁移走 Store 自带的事务和一致性备份，已有 v7 定义、稳定 ID 和历史版本沿用。[M07 工程记录](docs/evidence/m07/README.md)

- 本机工作台选择「意图注册表」可查询封版版本、主次任务、独立问卷验证状态及历史差异。项目候选提案由可信服务端授权。原话及其引用经项目、精确证据和当前资格复核。
- 下游先读 [注册表契约](docs/architecture/m07-registry-contract.md)、[版本及 M11/M09–M12 接续](docs/architecture/m07-versioning-contract.md) 与 [M06 冻结契约](docs/architecture/m06-consumer-handover.md)。正式联合确认、模型接入、校准和问卷回写按所属模块另行授权。
- G-1 保持 **BLOCKED**，G-1-R-A/B 已延期。正式研究、编码和发布仍关闭。待负责人另行授权后才可执行 G-1-R 或 M08。M07 同源码 Windows 11 实机结果仍待补。

## ROADMAP-V2 后续开发入口

以 `3bd705b` 的 M06-R 冻结政策及当前远端 HEAD 为接续基线。G-1 = **BLOCKED**。查询 100K 的已知性能债务交 M13-A。在获准的后续模块开发前读取 [完整工作单元](docs/planning/ROADMAP-V2.md)、[当前接续顺序](docs/planning/ROADMAP-V2.md#当前接续顺序)、[M06 消费接口](docs/architecture/m06-consumer-handover.md)和[验收矩阵](docs/requirements-matrix.md)。

AI 模块同时读取[适配器协议](docs/architecture/ai-model-adapter-contract.md)、[生命周期与版本](docs/architecture/model-lifecycle-and-calibration.md)及[金标准与对照](docs/architecture/model-evaluation-protocol.md)。M09 承接向量边界，M10 承接最小生成式接口，M12 承接通用决策接口及 Jev 首套正式实现。按各阶段授权实施，保留固定版本、实际通道身份、原有 G-1 和正式验收。ROADMAP-V2 已核验本机专案 v2.2 的 27 页原件及原登记指纹，仓库提供摘要供接续阅读。[负责人批准](docs/decisions/roadmap-v2-owner-approval.md)

## M06-R 复审与接续

开发分支为 `codex/p0-0-connectivity`。Windows 11 验收归档源码为 `9c27231376fcc32aae39a9b63df6fa9b9b98c4c6`。接续时核对远端 HEAD、草稿 PR #1 和同一 SHA 的三项 CI，按复审记录确认冻结状态。[复审与实机证据](docs/evidence/m06-r/README.md) · [M07–M15 接入契约](docs/architecture/m06-consumer-handover.md)

- 片段读、组合事务及统计各自校验当前项目授权和精确片段版。读取和写入必须使用实际证据依赖和当前资格。M04 保留同文但规范来源独立的候选，由 M05 逐项审核。
- M07 从已发布定义、目录版和任务关系接续注册表治理。绑定稳定 ID 和明确版本，保留旧定义，继续限制共享投影和项目原话。M07 仍待负责人单独授权。
- G-1 保持 BLOCKED。正式准入、逐源许可、删除审计、真实数据与正式发布留在原验收矩阵。M06-R 复审所用材料见当轮证据。

## M06-C5 统计接口

开发分支为 `codex/p0-0-connectivity`，C5 开发基线为 `db0c2c86385950b6630a2691e1263d5dd429aa32`，实测源码为 `a9eebee24616984dda8e72bab1242373555b06db`。交接时确认草稿 PR #1 的 HEAD 和实际交付提交一致，且三项 CI 通过。C5 的独立复审、Windows 11 实机及 1K/10K/100K 恢复证据均已归档。[C5 工程证据](docs/evidence/m06-c5/README.md) · [源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45569514279) · [PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

- 消费 `RelationStore.denominators` 或本机 `GET /api/studies/{study_id}/denominators`。按同一授权切片使用返回的 `resolved_versions`、`filter_echo`、`as_of_utc`、`coverage` 和 `M06-B-F.1`。跨来源、批次或品类汇总应重新查询并集。
- M07 复用稳定发生、片段版和精确证据引用，将发现状态及身份待核作为本地流转依据。M12 提供实际输入、资格授权版本及唯一当前回执，绑定题组、模型、索引、校准与回执版。M13 使用同一结果检查两条恒等式、正式批准和报告发放要件，权限、输入变化或过期后重新统计。
- 正式模式当前 `unavailable`，正式计数和对账均为 `null`。工程和隔离合成结果分别使用。G-1 = **BLOCKED**，M07 = **NOT_STARTED**。专案 v2.2 的 27 页原 PDF 待补。

## M06-C4 交付及 C5 接口

开发分支为 `codex/p0-0-connectivity`，对应草稿 PR #1。C4 从 `71a0668a9c9677c805ffe0f494c070fc6b9645d3` 接续，验收源码为 `fce76a06195c7f45638c39b0347301fbb6bfbbae`。C4 为 **ENGINEERING_PASS**，Windows 11 实机与该版本部署门禁为 **PASS**。接续时核对开发分支、草稿 PR 和同一验收提交的检查。[C4 工程证据](docs/evidence/m06-c4/README.md) · [PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

- `RelationStore` 提供共享定义、项目关系读、候选预检及内部组合事务。读取和写入使用服务端签发的精确授权。部署的 HTTP 默认没有可信项目授权注入，项目原话、预检及特权写入维持关闭。受限证据的授权粒度为 `(study_id, R, M, E)`。
- C5 输入固定 `study_id`、`registry_version`、`segment_revision`、`scope_id/scope_version`、`mapping_revision`、`catalog_version`，使用当前合格的精确 `M/E`。产品、来源、批次、时间和冻结范围在同一证据相交后再按唯一 `M` 去重。次任务仅作关联解释。撤销后用新快照重算。
- C5 复用同一证据交集和当前资格，按已冻结的 `M06-B-F.1` 检查六桶、排除账和主类对账。长查询遇撤销、失格或到期时须弃用结果并重算。开始前核对当前批准的 [统计契约](docs/architecture/m06-statistics-contract.md)与[实施计划](docs/architecture/m06-implementation-plan.md)。规模试验和两条守恒等式在 C5 取证。
- C4 的工程归属回执绑定精确 E 及其依赖核验版本。正式统计仍需 M12 当前完整编码回执、C5 对账及正式准入。缺项返回 `unavailable` 和 `counts:null`。明确非产品范围可返回有效的工程空集。
- 产品关系中涉及未解析冻结映射时返回不可用。治理审核者的当前精确审计授权只允许看脱敏失格记录。检测、统计、排序、导出及编码依赖应继续使用当前合格证据集合。审计失格记录仅供复核。
- 组合写保持单主库、`BEGIN IMMEDIATE`、C2 同连接复核及失败整项回滚。跨项目继承代表证据保守拒绝。将来由获准联合流程逐项目核验。保护已发布目录节点和祖先时，调用方提供可信已发布引用，正式报告引用来源由 M13 接入。
- C5 当前交付及后续授权见本页顶部。G-1 = **BLOCKED**。专案 v2.2 的 27 页原 PDF 待补。

## 历史记录 · M06-C3 交付及 C4 接入

先核对 `codex/p0-0-connectivity` 的远端 HEAD、草稿 PR #1、对应 CI 和 [C3 验收](docs/evidence/m06-c3/README.md)。C3 源码基线为 `43c72026e1776f6b78b78beeb3d87b7126016924`，工程验收、Windows 11 实机和部署门禁均已通过。M06-C4 = **NOT_STARTED**，工程前置已验证，等待负责人单独授权。G-1 = **BLOCKED**，专案 v2.2 的 27 页原 PDF 待补。

- `MentionStore` 在原始层提供 `publish_revision`、`review_products`、`read_evidence`、`read_revision`。服务依赖可信的项目权限回调，默认拒绝。C4 的 HTTP 与 M11 正式审核入口须核验真实授权。
- 关系固定引用 `study_id`、`segment_revision`、`mention_id` 和 `evidence_id`。每条 E 绑定原始 `record_id`、冻结 `scope_id`、`raw_sha256` 和 Unicode 半开码点区间。产品边再绑定 `product_category_id`、`catalog_version`、`mapping_revision` 与逐边 `decision_seq`。发生、证据、文本重复组和产品边各有独立键。
- C4 组合命令由外层拥有主库连接、`BEGIN IMMEDIATE`、幂等键、版次检查和整项提交／回滚。C3 公共写方法已各自拥有事务。组合接入须复用同连接辅助逻辑，在 C2 `qualified_write_inputs` 范围内完成依赖写并立即提交。依赖从精确成员、原帖、跨句上下文及逐边证据推导。遇 UTC 跨日、旧 WAL 快照或失败提交，整项回滚后在新事务重算。
- C3 投影对历史读取也执行当前资格。重新授权后的产品边需要新的人工确认。完整三层关系命令、API 与六角色授权联验由 C4 验收。正式统计分母、重算及报告发布依 C5、M12、M13 和 G-1 的原门槛。[冻结实施计划](docs/architecture/m06-implementation-plan.md)

## 历史记录 · M06-C2-V 验收及 C3 交接

M06-C2 = **ENGINEERING_PASS**。[三项实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45532356340) 均通过。C2 实现为 `965a4b8`。现有 Python/GET 合同及 SQLite v7 保持兼容。C2 在 Linux 已执行 190 项 Python、2 项 Node、8 个 Chromium 场景、三次冷启动及四份归档。桌面端在 `6ef5b2e` 完成独立验证，M06-C2-V、Windows 11 实机及部署门禁均为 **PASS**。四项独立反例和四项事务探针均通过。普通登录用户 DPAPI、三类路径、同库恢复及 SQLite v7 迁移均通过。测试只用隔离夹具，真实研究 API 调用 0。[Windows 11 验收证据](docs/evidence/m06-c2/windows11-closeout.md)

C3 NOT_STARTED，待负责人另行授权。实施时由调用方校验操作者与项目、从实际证据关系和写入推导全部直接证据及上下文 ID，在主库同一连接的 BEGIN IMMEDIATE 内使用 `CorpusStore.qualified_write_inputs(db, study_id, record_ids)`。所有依赖写置于该上下文，正常退出后立即提交，保存点仅覆盖该块。包括最终 COMMIT 在内的任何失败均由外层回滚整项操作，跨 UTC 日或旧 WAL 快照升级失败时在新事务重算。GET、旧回执、同文副本或暂存内容均不授予后续处理权。C3 负责声明依赖是否完整以及发生、区间和产品关系。G-1 BLOCKED，正式统计与外发继续关闭。

## 历史记录 · M06-C1 数据库实施交接

正式开发分支为 `codex/p0-0-connectivity`。本轮使用已冻结设计实施 SQLite v7，生产工作台类数据库运行 001–007，M01 合成契约库和诊断库继续使用 v1。先使用隔离的 v6 一致性备份复验升级与恢复，运行环境和验收命令见[迁移证据](docs/evidence/m06-c1/README.md)。[负责人门禁调整](docs/decisions/pre-m06-development-gate.md)记载开发与部署条件。M06-C1 为 ENGINEERING_PASS，代码基线为 f54b5734a632503b35066b9ab4fb197b8597d967。[实施 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45435846994)的 Ubuntu、Windows Server 2022 和 Chromium 均通过。2026-11-25 Windows 11 实机及部署门禁均为 PASS。DPAPI、启动器、全量回归及 SQLite v7 恢复实测通过。G-1 为 BLOCKED，M06-C2 为 NOT_STARTED。[Windows 11 验收记录](docs/evidence/m06-c1/windows11-closeout.md)

M06-C2 开始前，核对开发分支、草稿 PR #1、C1 实现提交及对应的 Ubuntu、Windows Server 2022 与 Chromium 三项结果，并等负责人单独授权。C2 在现有 M05 逻辑上实现同连接资格复核，保留现有 Python 与 GET 入口及 404/409 契约，实测撤销先后、同源副本、独立证据、单条重新授权和 UTC 日界。运行命令、授权重放、统计及发布分别依冻结的后续阶段安排。[M05 → M06 数据契约](#m05--m06-数据契约) · [分阶段计划](docs/architecture/m06-implementation-plan.md)

## 历史记录 · M06-B-F 架构冻结

2026-11-24，以 M06-B 审核提交 `2651d66c6f14f93b05e8123f4ca8009eaede37a4` 为输入，负责人批准表达身份、产品归属、统计口径、跨项目授权及旧范围映射五项政策。架构审核 PASS、设计批准 APPROVED、架构 FROZEN。12 项问题均有设计处置及实施回归，未解决 P0/P1 设计阻塞为 0。M06_IMPLEMENTATION=NOT_STARTED，Windows 11 实机 NOT_TESTED，Pre-M06 Gate 和 G-1 均 BLOCKED，真实研究 API 调用 0。

接续以[冻结记录](docs/architecture/m06-owner-approval.md)和[C1–C5 实施计划](docs/architecture/m06-implementation-plan.md)为准。M06-C 须另行获准。计划保留 M05 既有公开资格入口并要求写事务同连接复核；仅凭旧 verified、报告或同组副本均不足以恢复证据。CAT-1 至 CAT-10、C0-6 与 J-14 的原门槛和现有证据范围见[专项矩阵](docs/architecture/m06-test-plan.md)。

## 历史记录 · M06-B 交接

对开发分支 M06-A 提交 `48b5352feb72df852417d6c9edb96775896153a7` 的独立审核为 **PASS_WITH_CONDITIONS**。M06 架构审批 PENDING，实施 NOT_STARTED。SQLite v6；Windows 11 NOT_TESTED；Pre-M06 Gate 与 G-1 均 BLOCKED；本轮真实研究 API 调用 0。技术原型的范围、缺失的专案 v2.2 PDF 及正式验收缺项见[审核结论](docs/audits/m06-architecture-review.md)。

当时要求核对[决策与备选](docs/architecture/m06-decisions.md)和[逐项台账](docs/audits/m06-architecture-findings.md)。获批后按审核报告的实施顺序验证同连接资格、不可变发行、发生身份、同证据过滤与当前编码。保留公开 M05 Python 方法和 GET 契约。回放、缓存、导出均须按当前许可限制访问；业务准入和外发权限另验。原 24 例与新增 16 例属于设计推演，双连接与规模原型另列在[证据索引](docs/evidence/m06-b/README.md)。M06-C 等待另行授权。

## 前轮 M06-A 交接

开发分支 `codex/p0-0-connectivity`，设计依据为 Pre-M06-D 冻结提交 `06a233e157631c9f9a004d8b1311c2948597a429`。M06-A 已获授权并完成文档交付，提交 M06-B 独立评审。设计 READY_FOR_REVIEW，审批 PENDING，实现 NOT_STARTED。Windows 11 实机 NOT_TESTED，Pre-M06 Gate 和 G-1 均 BLOCKED，真实研究 API 调用 0 次。

评审从[总体设计](docs/architecture/m06-design.md)、[决策与风险](docs/architecture/m06-decisions.md)和[反例与验收矩阵](docs/architecture/m06-test-plan.md)开始。需签认转载身份、按证据撤销、旧冻结范围品类映射、M05 同事务复核、正式产品边与排除计数单位。数据库仍为 v6。下文保留当时各轮冻结状态与已实现的 M05 接口。

## Pre-M06-D 实机验收与工程冻结

本轮验收基线为开发分支 `4e6369b92205c51671866935365678df351ec808`。Windows 10 真机 **PASS**。普通用户会话完成 DPAPI CurrentUser 加解密、Python 140/140 和原版 Chromium 8/8。Codex 会话补齐 Node、冷启动、历史归档、SQLite 迁移、中文空格路径及敏感信息扫描，DPAPI 有独立的执行会话限制记录。[实机验收证据](docs/evidence/pre-m06/windows10-closeout.md)

Windows 11 实机仍为 **NOT_TESTED**，**PRE_M06_GATE_BLOCKED**，G-1 **BLOCKED**。M03 冻结范围和 M05 实时资格契约已具备开展 M06-A 架构设计的工程基础，等项目负责人另行授权。M06 实现、正式准入及正式语料接入沿用原验收条件。[审计报告](docs/audits/pre-m06-audit.md) · [M05 → M06 数据契约](#m05--m06-数据契约)

## Pre-M06 工程审计

开发分支按 `d64fb4f29094be9a3fc9b91e2910830ea0c1c8c2` 的修复实现和对应 CI 核对。M01–M05 跨模块场景 A–H 及 M05-R2-V 已通过，10 个确认缺陷已关闭。**PRE_M06_GATE_BLOCKED**，本轮 Windows 11 实机为 NOT_TESTED。M06 等实际验证及授权。G-1 继续 BLOCKED。 [审计报告](docs/audits/pre-m06-audit.md) · [实际日志](docs/evidence/pre-m06/README.md)

## 接管基线

2026-11-24 接管时，开发分支为 `codex/p0-0-connectivity`，远端提交为 `bca93639043e176f4159b9bf9fb98b4b2e2b32d8`。`main` 当时为 `f849242c5c37a2dc6a03a30215dd335424738c61`。开发成果汇集在指向 `main` 的草稿 PR #1，接管提交的 Ubuntu、Windows Server 2022 和 Chromium 工程检查均通过。[接管提交](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/bca93639043e176f4159b9bf9fb98b4b2e2b32d8) · [PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [接管提交 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341736949)

M03 和 M04 已完成独立工程验收。M04 代码复测为 `336e68c`，本机 Linux、Ubuntu 和 Windows Server 均通过 95 项 Python、2 项 Node 和 3 次冷启动。Chromium 通过 6 组，4 份历史归档核对通过。M05 已接入本机原话审核、去重与溯源，沿用 M04 的冻结范围及原文件引用。最新本机测试和发布状态见 [开发状态](DEVELOPMENT_STATUS.md)。[M04 证据](docs/evidence/m04/README.md) · [M05 工程记录](docs/evidence/m05/README.md)

M05-R 的历史工程验收为 **ENGINEERING_PASS**。当轮最终实现 `d0414f5e7b978460d7dec3784c0862d7f1f0bdd0` 已同步到草稿 PR #1 的开发分支，Windows 11 实机回归和远端三项作业均通过。收到 M06 授权后使用隔离合成夹具启动独立预开发。[复审证据](docs/evidence/m05/review.md) · [M05-R CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45359711019)

当前正式阶段为 P0-0，G-1 为 **BLOCKED**。C0-3、C0-5、C0-6 已通过，C0-1、C0-2、C0-4 及 Jev 所选通道的留存与分处理商审查待验。继续保留固定 `jev-1.14.0`、8+3 分片、Choice / Score / Noul 完整返回及实际用量和余额要求。后续正式验收由有权限的人员在授权设备上按同批六项规则执行。G1/G2 的正式语料验收仍要求三个真实来源批次、至少 100 条合格语义片段及抽查 30/30 可回源。[正式历史批次](docs/evidence/p0-0/tavily-live/README.md) · [需求验收矩阵](docs/requirements-matrix.md)

仓库保留 PDT v1.3.1 Word 正文和专案 v2.2 的 Markdown 摘要。27 页专案 PDF 的 SHA-256 登记在需求矩阵，复核原件时从其授权来源取得。[PDT 正文](docs/pdt/PDT-v1.3.1.docx) · [专案摘要](docs/proposal/voc-workbench-proposal-2026-11-23.md) · [原件指纹](docs/requirements-matrix.md)

M05-R2 许可与数据资格复修为 **ENGINEERING_PASS**。两项缺陷和旧库副本复核问题均关闭。SQLite v5 保留历史。缺少明确授权依据且原基础规则有效的旧记录待人工复核，同一文件行的此类副本可单独复核。[最终实现 `62a7c1c`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/62a7c1c132b72a8e07679f1713e6834aa7893c91) · [实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45367761470) · [复测证据](docs/evidence/m05/permissions-review.md)

## M05 → M06 数据契约

| 数据 | 交接约束 |
|---|---|
| 原始语料 | `record_id` 稳定标识 M05 原始导入行。通过 `batch_id`、`file_id`、文件 SHA-256、工作表和物理行号回查。使用 `raw_sha256` 核对核验快照，派生文本与分类结果另存。 |
| 研究范围 | 以 `study_id` 和冻结的 `scope_id` 校验归属，记录 `scope_version` 和冻结时间窗。范围中的品类仅供抽样和范围检查。 |
| 来源与许可 | 使用采集时间和方法、提取规则、可核对 URL、发布时间及本机审核依据。统一资格服务在每次读取时核对当前结构化许可、最近审核、隐私、有效期限、范围及撤销。许可到期、撤销或证据不足时暂停使用。同项目同来源的副本遵守当前限制，历史撤销保留。正式许可须有逐源审批记录。 |
| 重复组 | `duplicate.group_id` 为研究项目内的有效原话分组。当前主记录和成员数随排除、到期、来源或批次撤销及重新核验而重算。历史引用继续指向原始 `record_id`。 |
| 后续处理 | 通过 `CorpusStore.qualified_record(study_id, record_id)` 或 `GET /api/corpus/{study_id}/records/{record_id}/eligible` 读取本机工程合格公开原话，校验返回的冻结范围、`license_status`、`source_permission_revoked` 和 `engineering_eligible`。禁止直接用历史 `verified` 放行，禁止通过 `import_rows`、暂存、历史或附件绕过资格。待审、受限与不合格原话只进入授权审计或清理流程。内部 CX 限授权本机，背景证据按角色使用，合成测试使用独立夹具。 |
| 语义片段与证据 | PDT §6.6、§6.9、§9.3 的 `mention_id` 标识去重后的语义片段。后续证据记录用独立 `evidence_id` 引用 M05 原话及来源，供片段与品类关系使用。分段规则、片段标识生成、证据持久化和版本设计留待 M06 的授权工作。 |

M06 复用原话与来源记录，使用证据确定产品品类关系。意图保有一个已确认的有效主任务大类。正式分母只纳入 `published_classified` 的 distinct `mention_id`，按使用的研究范围及注册表版本复算。读取历史片段或证据时重新核对当前上游资格，审计状态和引用可继续追溯。本机工程资格、正式统计资格和外发资格分别判定。当前服务始终返回 `research_eligible=false`、`outbound_allowed=false`。处理路径与正式门槛详见需求矩阵。[PDT 正文](docs/pdt/PDT-v1.3.1.docx) · [原始语料接口](docs/imports.md#m05-原始语料审核) · [需求验收矩阵](docs/requirements-matrix.md)

## 复建开发环境

在每台电脑或云端工作区使用 Git、Python 3.12 和 Node 24。新设备克隆现有仓库，已有工作区先执行 `git status --short --branch`、`git fetch origin`，核对与 [PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) 最新 head 的差异。分支与工作区核对后，用 `git merge --ff-only origin/codex/p0-0-connectivity` 更新同名开发分支。出现本地改动或分叉时保留现场并查看两侧提交。新设备可用以下命令。

```sh
git clone --branch codex/p0-0-connectivity https://github.com/kurikiwoods-coder/voc-research-workbench.git
cd voc-research-workbench
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765 --no-proxy-headers
```

也可用 `scripts/start-windows.cmd` 启动。PowerShell 的执行策略限制虚拟环境激活脚本时可直接调用上面的 venv Python。运行统一回归时从 Git Bash 进入仓库根目录，执行 `source .venv/Scripts/activate` 后运行下方测试命令。

### Linux、macOS 和云端工作区

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765 --no-proxy-headers
```

工程开发和回归从空凭证的新工作区启动。`VOC_DATA_DIR` 可指向工作区专用的本机目录，默认是 Git 忽略的 `runtime/`。各环境独立重建 `.venv`，旧电脑或旧解压版中的 `.env`、`runtime/`、凭证库及真实研究数据留在原授权环境。云端保留回环监听，使用受限的本机端口转发访问。浏览器地址为 `http://127.0.0.1:8765/`，健康检查为 `/api/health`。

## 工程验证与交付

在激活 `.venv` 的 Bash 执行以下命令。Windows PowerShell 可直接用 `.venv\Scripts\python.exe` 执行 Python 命令。

```sh
bash scripts/smoke-test.sh
python -m playwright install chromium
python tests/browser_e2e.py
```

smoke 包含 Python、Node、三次空库冷启动和密钥扫描。Linux 缺少 Chromium 系统库时可按 Actions 工作流执行 `python -m playwright install --with-deps chromium`。跨平台基准由 GitHub Actions 的 Ubuntu、Windows Server 和 Chromium 作业给出。Windows 10/11 实机、macOS 或其他云端环境的运行结果按实际验证单独登记。[工程工作流](.github/workflows/p0-0-ci.yml)

提交前检查暂存列表和 diff，确保夹具为合成数据、证据已审核脱敏。推送前重新核对远端 head，常规推送开发分支后在 PR 和 Actions 上核对对应提交。公开 GitHub 仓库存放代码、开发记录与获准的工程证据。凭证、真实语料、公司资料和运行数据库留在原授权环境。[开发规范](AGENTS.md) · [模块路线图](MODULE_ROADMAP.md) · [开发状态](DEVELOPMENT_STATUS.md)

### M05 发布与恢复

Windows 上可用 Git Credential Manager 在浏览器完成 GitHub 登录。在 PowerShell 运行 `git credential-manager github login --browser`，在 GitHub 页面选择具备仓库写权限的账号。验证凭证的远端账号及仓库权限后，重新获取开发分支并核对两侧提交。确认远端为待发布提交的祖先后，常规推送 `codex/p0-0-connectivity`，再在 PR #1 核对提交 SHA 及 Ubuntu、Windows Server 2022 和 Chromium 作业。

2026-11-24 已通过 GitHub CLI 确认 `kurikiwoods-coder` 的仓库写入权限。Codex 和普通 Windows PowerShell 的 Git HTTPS 推送均在发包阶段返回 `Bad file descriptor`。M05 从 `bca9363` 通过获准的临时仓库 SSH 密钥常规推送，核对远端实现提交为 `b02a2b647bff67f7e091b51fcdfc46cc719077e8`，随后撤销临时密钥。对应的 Ubuntu、Windows Server 2022 和 Chromium 作业全部通过。[M05 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45352022477)

本机交付目录保留已验证的增量包 `voc-workbench-m05-b02a2b6.bundle`，包含 `b02a2b647bff67f7e091b51fcdfc46cc719077e8`，需要现有仓库包含基线 `bca93639043e176f4159b9bf9fb98b4b2e2b32d8`。恢复时先执行 `git bundle verify <本机包路径>`，然后将包的开发分支取到新的本机恢复分支，核对恢复结果及当前远端历史后再决定如何接续。

```sh
git fetch <本机包路径> refs/heads/codex/p0-0-connectivity:refs/heads/recovery/m05-b02a2b6
```
