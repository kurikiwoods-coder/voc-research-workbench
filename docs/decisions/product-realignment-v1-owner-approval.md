# PRODUCT-REALIGNMENT-V1 — 研究优先产品策略

**负责人决定为 APPROVED，日期为 2026-11-27。** 本 ADR 确认产品方向、实施顺序和最小返工。它属于现有架构决策，核心路线图仍计 79 项。工程返工须按所属阶段取得独立授权。

## 决策依据及工程基线

复读了 2026-11-23 的 27 页《VOC 研究工作台专案 v2.2》原件和 PDT v1.3.1 Word 正文。SHA-256 分别为 `c613c7465d7a754e1e9b97032ae13c2b571564bd9dc76cd5d6a9691f33e0e88c` 与 `09edf47c95151276b39c4b375cd1e7e1f805591fb8d65b8f2c512087283a11b7`，均与原登记一致。保留原件、指纹、历史验收及原矩阵。当前接续顺序以本 ADR 和 ROADMAP-V2 为准。早期文档中 M09 等待个人准入的排期提示适用于正式研究，获准隔离工程可按现行授权推进。[专案摘要](../proposal/voc-workbench-proposal-2026-11-23.md) · [PDT 正文](../pdt/PDT-v1.3.1.docx) · [验收矩阵](../requirements-matrix.md) · [ROADMAP-V2 当前顺序](../planning/ROADMAP-V2.md#当前接续顺序)

| 核对项 | 本次登记时已核实 |
|---|---|
| 版本与工作区 | 本机和远端 `codex/g1-personal-phase-1`、草稿 PR #2 HEAD 均为 `da045c9f76b095f762efbf42c84190de44b20472`。工作区干净。工程源码基线为 `bee8287359c965286b1fd38005ef9d1852bad3d8` |
| 核心路线图与 M09 | 工程或复审完成 **39/79**。M09 已有消费契约及 C0-6 召回冒烟验证，未见已提交的 M09 工程交付，仓库登记为 `NOT_STARTED`。原有隔离开发授权有效 |
| G-1 与存储 | 已有双版本、Owner 审批、预算账本、回执及受控恢复。G-1-P-D `BLOCKED`，正式同批 0/6。G-1-P-R `NOT_STARTED`，Personal 正式门禁 `NOT_EVALUATED`，Business `BLOCKED`。Personal 工作库 SQLite v11、Business v9。M06 `FROZEN` |

[当前状态](../../DEVELOPMENT_STATUS.md) · [草稿 PR #2](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2)

## 产品与研究流程

VOC Research Workbench 优先服务个人研究者，支持全品类、多来源及可扩展模型。研究链路从真实用户原话采集开始，经过未知意图发现、人工研究审核、智能编码和定量洞察，再通过问卷验证与结果回流检验发现。发现与规模化编码同属 P0 核心价值，均需独立验收。已有意图的编码结果不能充当未知意图发现。

站外论坛和获准的公开原话用于发现实际场景。讨论声量提供同口径趋势信号，研究期刊与公开调查提供背景和交叉验证。Amazon 作为许可范围内的初步来源，保留原有四条窄路及证据级别。搜索摘要、便利样本及合成数据继续按原方法论处理。[来源与证据口径](../sources/source-map.md) · [Amazon 许可边界](../sources/amazon-narrow-paths.md)

冻结九项原则 **Research First**、**Personal First**、**BYOK**、**Model Extensibility**、**Evidence First**、**Governance in Background**、**Progressive Enterprise**、**UI Simplicity**、**Cost Efficiency**。治理尽可能后台执行，在需要研究者采取行动时清楚呈现状态、依据和下一步。

Personal Edition 与 Business Edition 共享完整的 M01–M15、研究引擎、数据架构、模型适配契约、证据、统计与质量标准。Personal Edition 是完整研究版，当前优先交付其从采集到验证的研究体验。Business 已有能力与正式治理继续有效，暂停新增与核心闭环无关的企业治理功能。组织权限、审批与企业合规仍按各版本政策执行。[双版本策略](../architecture/edition-policy.md)

## 模型、配置与计量

M09 使用 Embedding Adapter，M10 使用 LLM Adapter，M12 使用 Decision Adapter。采集使用独立 Connector。首个正式 Decision 验证采用 Jev 及 `jev-1.14.0` 原契约。产品允许切换获准供应商、账户、端点和模型版本，每次正式运行固定实际配置。兼容同一协议的通道优先共用适配器，通过受控配置切换。Microsoft Decision、其他模型和本地模型保留为未来候选。不同模型的 Choice、Score、Noul 与概率语义须单独验证。[现有适配契约](../architecture/ai-model-adapter-contract.md)

API & AI Model Center 按阶段复用 M02，管理 Provider ID、Base URL、API Key 引用及凭证版、Model ID、Adapter ID 及版本、接口协议、能力、模型配置版本、连接测试、项目默认、费率、计费单位、用量及余额状态。凭证继续由服务端安全库处理。按供应商、账户、模型、配置版本及请求归因，记录输入、输出和 Embedding Token、请求数、Search Credit 及供应商原生计量。实际费用和按已知用量与费率计算的估算费用分列，各保留币种和费率版本。记录请求状态、不确定扣费、可获取余额及最近同步状态。余额未知时显示未同步，余额查询能力本身不阻断研究。实际用量、预算、幂等及不确定扣费的暂停对账仍须满足。复用现有 Token Center、预算账本、DPAPI 和凭证恢复能力。

## 返工范围冻结

| 范围 | 决定 |
|---|---|
| M12-A 必须增量调整 | G-1 Personal 解除不必要的 PackyCode、账户和通道绑定，简化重复审批，保留技术准入和安全。M02 补齐实际需要的兼容配置、版本、用量归因、连接及能力验证 |
| 有证据再调整 | M03 新建项目、M08 采集流程、全局导航及个人版操作。实测存在重复操作或无必要的治理阻塞时才提最小修正 |
| 冻结 | M01、M04、M05、M06、M07，既有稳定 ID、三层关系、证据与 SQLite Schema 基线。核心契约或 Schema 迁移须先提交理由并获单独授权 |
| 按原计划开发 | M09–M15、I18N-PRE、M08-E 及原 P0/P1/P2 各单元和验收 |

## Personal 最小准入修正

G-1 暂停主动治理开发，既有工程、证据及运行约束继续保留。停止 PackyCode 额外专项调查，现有账户适用条款待决事项仅约束该通道。明确禁止拟用用途的服务保持关闭。

M12-A 独立授权后，Personal 准入围绕实际账户权限、技术可用性、准确模型身份和能力、研究输出契约、逐源许可及外发、真实用量与费用、预算和异常控制、研究验收。企业级深度审计及重复行政审批不作为默认要求。兼容通道内更新或轮换凭证、续费时核对绑定、连通性及受影响项。供应商、端点、模型或协议变化时，复验实际变化的技术、安全、用途权限、计量和研究能力。继续执行故障关闭、端点验证、SSRF 防护、DPAPI、敏感数据隔离、预算预约、幂等及未知扣费暂停和对账。商用正式治理标准继续适用。[Personal 准入](../architecture/personal-research-gate.md) · [Business 准入](../architecture/business-research-gate.md)

## 实施顺序及验收

1. 沿现有授权完成当前 M09，接续实施并验收 M10。M10 若确需提前调用外部 API，取得该用途的独立授权并核验必要技术、安全和使用条件。无法合法放行时沿用隔离工程。
2. M10 验收后单独授权实施 I18N-PRE，再完成 M11 可独立交付的工程单元。M11 的 M12 接口以隔离夹具验证。
3. M11 独立工程就绪后，单独授权启动 M12-A，同步处理 G-1 Personal 与 M02 的最小增量。M12 正式真实研究及模型校准前恢复 G-1-P-D 的同批六项及 G-1-P-R 独立复审。
4. 通过适用正式准入后完成 M12 实际模型校准和余项，再执行 M11 与 M12 原定真实联调。随后按原分期推进 M13–M15、M08-E 及既有任务，完成原 P0、P1、P2 验收。

C0-1 至 C0-6、J-14、金标准、模型准确性与概率校准、真实原话、逐源许可、原文溯源、稳定 ID、统计分母与排除规则、正式/验证/合成域隔离、内部与敏感数据外发限制、预算及凭证安全继续适用。模拟结果不能充当真实研究证据。模型自报置信度不能补齐缺失概率，便利样本的提及率不能推导为市场总体比例。[M06 冻结统计](../architecture/m06-statistics-contract.md) · [评估与校准协议](../architecture/model-evaluation-protocol.md)

## 研究工作区交互原则

| 区域 | 计划方向 |
|---|---|
| 整体 | 简洁、低饱和度的文档式研究工作区。借鉴 Notion、Linear、Dovetail、Power BI 的交互理念，形成自己的界面 |
| 首页 | 开始新研究、继续已有研究、查看进展、查看成果 |
| 主导航 | 工作台、研究项目、原始语料库、数据采集、意图发现、人工审核、智能编码、研究洞察、问卷验证、竞品 Radar |
| 设置区 | API Center、Token Center、系统与必要治理。需用户操作的阻塞说明真实原因和必要动作 |
| 项目工作区 | 采集 → 发现 → 审核 → 编码 → 洞察 → 验证。M09/M10 优先主题、候选和可回查原话。M11 优先证据与意图审核。M13 优先结果、来源分层、有效分母、需求结构和可追溯洞察 |
| 状态与交付 | 缺真实数据时使用明确空态。各模块先交必要功能界面，M13 增量完善体验，P2-R 执行原端到端可用性和视觉一致性验收 |

以上为获批准的产品方向。现有界面及未实施能力按工程状态登记，UI 工作计入原模块及 P2-R。
