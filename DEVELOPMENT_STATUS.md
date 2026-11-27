# VOC Research Workbench 开发状态

## PRODUCT-REALIGNMENT-V1 与当前工程状态

2026-11-27 负责人决策 **APPROVED**。从本机、远端及草稿 PR #2 一致的 `da045c9f76b095f762efbf42c84190de44b20472` 接续，工作区干净。Personal 工作库 SQLite v11，Business v9，M06 `FROZEN`。核心进度 **39/79**。可见分支仍登记 M09 为 `NOT_STARTED`，已有消费契约及 C0-6 冒烟验证，尚未见已提交的 M09 工程交付。M09 原有隔离开发授权有效。[正式 ADR](docs/decisions/product-realignment-v1-owner-approval.md) · [当前接续](docs/planning/ROADMAP-V2.md#当前接续顺序)

当前 **G-1-P-D = BLOCKED，G-1-P-R = NOT_STARTED，G-1-PERSONAL = NOT_EVALUATED，Business G-1 = BLOCKED**。Product Realignment 仅登记方向和返工边界。G-1 Personal 与 M02 等 M12-A 独立授权，M11 接口先在隔离环境验收，真实联调等 M12 校准与余项完成。本轮真实研究调用、供应商探针、余额查询、真实研究 Token 和费用均为 0。[返工范围](docs/decisions/product-realignment-v1-owner-approval.md#返工范围冻结)

## API 架构确认与 G-1 暂停

2026-11-27 核对草稿 PR #2 的开发分支 `codex/g1-personal-phase-1`，文档接续基线为 `bee8287359c965286b1fd38005ef9d1852bad3d8`，对应三项 CI 已通过。现行 Personal 工作库为 SQLite v11，Business 工作库为 v9，M06 冻结。核心进度 **39/79**。核对时仓库仍登记 M09–M15 为 **NOT_STARTED**，未发现已提交的 M09 工程成果。M09 的既有隔离开发授权继续有效。I18N-PRE 为 **PLANNED**。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45932760024) · [当前开发顺序](docs/planning/ROADMAP-V2.md#当前接续顺序)

**G-1-P-D = BLOCKED，G-1-P-R = NOT_STARTED，G-1-PERSONAL = NOT_EVALUATED，商用 G-1 = BLOCKED**。本轮仅登记 API 架构和接续决策。G-1 的最小修正及 M02 增量等 M12-A 单独授权，正式研究及模型校准前复验。Personal V2、原 PackyCode 通道的待决事项及其已有回执继续按原范围保留。本轮真实研究 API、供应商探针、余额查询、研究 Token 和研究费用均为 0。[个人门禁](docs/architecture/personal-research-gate.md) · [适配器契约](docs/architecture/ai-model-adapter-contract.md)

## G-1-PERSONAL V2 本机预准入

2026-11-27，Personal V2 沿用既有 G-1-P-D 受控执行，按当前账户、凭证、固定通道、逐源许可、Owner 费用及剩余风险批准准备一次四槽取证。既有 C0-5、C0-6 离线证据可在复核版本、适用范围及摘要后引用至该批次。历史模型合成回执及两笔费用继续用于原批次审计。C0-1 至 C0-6 的正式标准见原政策。[个人准入政策](docs/architecture/personal-research-gate.md) · [待签发的四槽草案](docs/evidence/g1-p-d/personal-v2-authorization-draft.md)

**G-1-PERSONAL = NOT_EVALUATED，G-1-P-D = BLOCKED，G-1-P-R = NOT_STARTED**。正式批次和逐槽授权尚未签发，正式同批 0/6。真实请求、探针、余额查询、实际 Token、费用及正式研究分母增量均为 0。独立复审待六项同批证据齐备。商用 **G-1 = BLOCKED**，M09–M15 为 **NOT_STARTED**，核心进度 **39/79**。

## I18N-PRE 规划登记

2026-11-26，**I18N-PRE = PLANNED**。M09、M10 的语言接口和证据提前约束已登记。M10 验收完成后等待负责人单独授权实施，在 M11 启动前完成专项。G-1 的当前接续见本页顶部，核心进度为 39/79。[负责人批准](docs/decisions/i18n-pre-owner-approval.md)

## G-1-P-D 个人版正式同批验收准备

2026-11-26，**G-1-P-D-E = ENGINEERING_PASS**。D-E 的 Personal v10、受限执行及恢复修复通过隔离 Windows 11 实机验收，交付提交 `4c7d705b277352af530c59f917f787bcc3a69bfd` 的 Ubuntu、Windows Server 2022、Chromium 均通过。隔离验证确认 Business 工作库 v9，两版诊断及合成契约库 v1。[负责人批准](docs/decisions/g1-p-d-e-v10-owner-approval.md) · [D-E 工程证据](docs/evidence/g1-p-d/engineering.md) · [D-E 交付 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45794168453)

**G-1-P-D-L 真实执行 `BLOCKED`。** 隔离 v11、逐操作授权和两项跨批次对账 P1 通过 Windows 11 定向实机复验，Python 70/70、原生 DPAPI 3/3。独立 Personal v11 正式验收工作区已部署，Owner、ACL、备份、新目录恢复与重启回读通过。PackyCode/SystemOne 仍缺实际通道可执行的逐请求输出硬上限及含重试的最坏扣费证明，正式逐槽授权及恢复连续性待复核。真实请求 0，正式同批 0/6。[Windows 11 与部署证据](docs/evidence/g1-p-d/d-l-windows11-deployment.md) · [D-L 授权草案](docs/evidence/g1-p-d/d-l-authorization-draft.md)

**G-1-P-D = BLOCKED**。C0-1 至 C0-6 的个人正式同批状态均为 `BLOCKED`，C0-5 和 C0-6 保留既有离线通过。真实研究供应商请求、探针、账户查询、真实研究 Token、新增研究费用、正式研究分母和正式历史证据纳入均为 0。[D 六项及证据](docs/evidence/g1-p-d/README.md)

## G-1-P-C 个人供应商审批中心

**G1_PERSONAL_APPROVAL_CENTER = IMPLEMENTED**，**G1_PERSONAL_IMPLEMENTATION = PARTIAL**。源码 `912ff28e0a10e3329bc49c6e9fdc97e290229a68` 实现可信本机 Owner 的项目和冻结范围审批、必要材料复核、非强制风险登记、凭证绑定及不可变事件，工作库 SQLite v9。该源码 **WINDOWS_11_REAL_MACHINE = PASS**，**WINDOWS_11_DEPLOYMENT_GATE = PASS**。C 交付提交的三项 CI 已通过，**G-1-P-C = ENGINEERING_PASS**，具备 D 准备工作的工程接续条件。[C 证据](docs/evidence/g1-p-c/README.md) · [C 交付 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45762882859)

**G-1-PERSONAL = NOT_EVALUATED**，**G-1 = BLOCKED**。M06 工程基线 FROZEN，正式统计继续 `unavailable/null`，核心 39/79。R、M09–M15 为 **NOT_STARTED**。C 阶段真实研究和真实供应商探针分别为 **0 次**。[D 批次准备规范](docs/evidence/g1-p-c/d-preparation.md)

## G-1-P-B-V 网页成果接管

**WEB_CODE_TAKEOVER = PASS**，**G-1-P-B-V = PASS**。原生 Windows 11 在隔离的 B 版源码快照上通过全量回归、DPAPI、ACL 及三种路径启动重启。该源码的 **WINDOWS_11_REAL_MACHINE = PASS**、**WINDOWS_11_DEPLOYMENT_GATE = PASS**。验收提交 `97e942d9339921089cabb6fe2b0ea01d6832f5fe` 的三项 CI 通过。[验收证据](docs/evidence/g1-p-b-v/README.md) · [B-V CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45757091621)

## G-1-P-B 双版本服务端工程

2026-11-26 从 Phase 1 实际远端 `0e7a3d7ec4909cf43410728045a9bb765b2760da` 接续。**G-1-P-B = ENGINEERING_PASS**，`G1_PERSONAL_SERVER_POLICY = IMPLEMENTED`，`G1_PERSONAL_IMPLEMENTATION = PARTIAL`。个人本机 Owner、项目及冻结范围权限、两道门禁与云模式关闭已实现。独立复审及 Windows 兼容回归完成，未关闭 P0/P1 为 0。[工程证据](docs/evidence/g1-p-b/README.md) · [本机启动](docs/architecture/g1-personal-server-policy.md)

该 B 源码使用 SQLite v8，M06 工程基线 FROZEN，核心 39/79。B 阶段真实研究及供应商探针各 **0 次**。

实现验收绑定 `d7c711660843c8c095fccbedd4b67d5303f9226b`。Ubuntu 与 Windows Server 2022 均通过 422 项 Python、2 项 Node、三次空库冷启动及四份归档校验。Chromium 全量通过。Windows Server 的中文及空格路径启动回归通过。[三项 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45749971864)

## G-1-PERSONAL Phase 1

2026-11-26，以 M08-V 报告提交 `dd89a14f25ac0dfae3f63dcf1809da2494f1c9dc` 接续，原验收源码 `74590d4a4d43a66c7a3296943da9205bc6ff65e0` 的 Windows 11 实机及部署均 PASS，当轮新增未关闭 P0/P1/P2/P3 为 0/0/0/0，基线三项 CI 均通过。M06 工程基线 FROZEN，SQLite 工作库 v8，ROADMAP-V2 **39/79**。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45740807294) · [M08-V](docs/evidence/m08-v/README.md)

`DUAL_EDITION_STRATEGY = APPROVED_AND_DOCUMENTED`，`PERSONAL_EDITION = FULL_ACCESS_PLANNED`，`BUSINESS_EDITION = PLANNED`，`G1_PERSONAL_POLICY = DOCUMENTED`，`G1_PERSONAL_IMPLEMENTATION = NOT_STARTED`。个人门禁 **G-1-PERSONAL = NOT_EVALUATED**，商用 **G-1 = BLOCKED**，M09 = **NOT_STARTED**。下一轮为 G-1-P-B/C，各阶段待独立授权。个人 M09 等 G-1-P-D 与 G-1-P-R 完成准入后另行授权。[批准记录](docs/decisions/dual-edition-owner-approval.md) · [实施计划](docs/planning/g1-personal-implementation-plan.md)

G-1-R-B-F 原始 CSV 两条消费 **CSV_VERIFIED**，累计 809 输入、220 输出、1,029 合计 Token，实际费用 **$0.000238**。与仓库合成回执交叉核对一致。个人 Windows 10 的原始 SQLite 独立核对为 **LOCAL_VERIFICATION_PENDING**。云端离线回归 Python 395/395、Node 2/2、三次空库冷启动通过。M08-V 实机沿用原证据。真实研究及真实供应商 API 调用各 **0 次**。[脱敏费用证据](docs/evidence/g1-rb-f/README.md)

## M08-V Windows 11 实机与部署验收

2026-11-26 在普通登录用户的原生 Windows 11 Enterprise 25H2 x64（26200.8655）上复验 `74590d4a4d43a66c7a3296943da9205bc6ff65e0`。**M08_V = PASS**、**M01_M08_WINDOWS_11_REGRESSION = PASS**、**WINDOWS_11_REAL_MACHINE = PASS**、**WINDOWS_11_DEPLOYMENT_GATE = PASS**。Python 395/395、Node 2/2、Chromium 全量与两项专项、空库冷启动 3/3、历史归档 4/4、路径启动 6/6、SQLite v7→v8 迁移及恢复、DPAPI 合成凭证均通过。[实机证据](docs/evidence/m08-v/README.md)

**M06_ENGINEERING_BASELINE = FROZEN**、**M07 = ENGINEERING_PASS**、**M08_P0_ENGINEERING = ENGINEERING_PASS**、**M08_FORMAL_BUSINESS_ACCEPTANCE = PENDING**。**G-1 = BLOCKED**、**PACKYCODE_PROVIDER_APPROVAL = PENDING**，真实研究 API 与真实供应商探针各 0 次。ROADMAP-V2 为 **39/79**，M08-E 和 M09–M15 尚未启动。M09 的隔离工程前置接口具备，接续条件见本页顶部的个人版准入。

## M08-C/D 隔离工程验收

起点 `411f43388daf140c1dc33bfd1de2e26d89b17641`。M08-A/B/C/D 均为 **ENGINEERING_PASS**，`M08_P0_ENGINEERING = ENGINEERING_PASS`，路线图 **39/79**。Windows 10 普通用户环境 Python 395/395、Node 2/2、Chromium 全量、冷启动 3/3、归档 4/4。三批 120 片段及 30/30 证据回查通过。已确认 P0/P1 关闭。本轮源码 Windows 11 实机为 **NOT_TESTED**。[M08-C/D 证据](docs/evidence/m08-cd/README.md)

SQLite 正式工作库 v8，A/B 演示账本 v1，C/D 任务账本 v1 独立。M06 基线 **FROZEN**，M07 **ENGINEERING_PASS**，PackyCode 合成契约 **PASS**，供应商审批 **PENDING**。G-1 **BLOCKED**，M08 正式业务验收 **PENDING**，真实研究 API 调用 0。M08-E 及 M09–M15 为 **NOT_STARTED**。

## M08-A/B 隔离来源采集

从 `81ce8818354f36ed33943d604e8890adde1f4c3f` 接续。M08-A、M08-B 的本机隔离工程验收均为 **ENGINEERING_PASS**，M08 为 **PARTIAL**，路线图已完成 **37/79**。Windows 10 Python 359/359、Node 2/2、Chromium 全量通过、冷启动 3/3、归档 4/4。复审确认的 P1 已关闭。工作库 SQLite v8。G-1 **BLOCKED**，M08 正式业务验收 **PENDING**。M08-C/D/E 及 M09–M15 为 **NOT_STARTED**，真实研究 API 调用 0。[工程证据](docs/evidence/m08-ab/README.md)

## G-1-R-B-P 独立合成接口预检

负责人批准一次固定 8+3 的 PackyCode 合成契约试验，最多两次 POST，使用独立、不可重置的小额令牌和 100,000 输入 Token 本地预算目标。首片通过后须核对扣费和余额再发第二片。独立 SQLite 保存预约、分片证据及回执。结项时 G-1 为 **BLOCKED**，M06 冻结，M07 工程通过，M08 及 M12 当时未启动。[安全决定](docs/decisions/packycode-synthetic-preflight.md) · [验收证据](docs/evidence/g1-rb-p/README.md)

原批次完成 8+3 题，两个请求均返回 HTTP 200、`jev-1.14.0`。11 题字段校验通过，接口实报合计 **809 输入 / 220 输出 Token**，合成契约为 **PASS**。首片单笔实扣 **$0.000144**，最终测试令牌余额显示 **$2.00**，原结项时第二片消费及总额未核实，Phase 1 已追加原始 CSV 取证。[原验收](docs/evidence/g1-rb-p/README.md#实际接口结项) · [费用补证](docs/evidence/g1-rb-f/README.md)

## G-1-R-A PackyCode 工程接入

从开发分支 `a7b1de491c85fb879bed4b2ce25f9f3164add6a0` 接续。M02 增加独立 PackyCode 候选通道，固定 `typesafe-officially`、`jev-1.14.0` 和 SystemOne。沿用分片账本和 DPAPI，使用当前账户独立审查。报价估算、真实扣费与余额分别登记。[接入及取证](docs/packycode.md) · [工程证据](docs/evidence/g1-ra/README.md)

G-1-R-A 交付时，`PACKYCODE_CONNECTOR = IMPLEMENTED`，`PACKYCODE_PROVIDER_APPROVAL = PENDING`，`PACKYCODE_LIVE_CONTRACT = NOT_TESTED`。研究 API 和 PackyCode 合成探针真实调用均为 0。G-1 为 **BLOCKED**，G-1-R-B 当时为 **NOT_STARTED**。ROADMAP-V2 为 **35/79**，M06 冻结底座及 SQLite v8 继续适用。

## M07 隔离注册表工程

2026-11-25 从 `7c02966eb7e6c54f8e30ff032f921bac6719d1d2` 接续。负责人批准 M07-A 至 D 在 G-1 阻塞状态下进行隔离工程，G-1-R-A/B 延期待另行授权。SQLite v8 新增草稿、修订、命令回执及版本化共享示例。M06 封版定义、三层关系、五项政策与 `M06-B-F.1` 继续适用。[数据契约](docs/architecture/m07-registry-contract.md) · [版本接口](docs/architecture/m07-versioning-contract.md) · [M07 验收](docs/evidence/m07/README.md)

M07-A 至 D 为 **ENGINEERING_PASS**。Windows 10 Python 298/298、Node 2/2、Chromium 12/12 组，源码 `5a3bd4189d6f3e3951bdcc0d79ce79db5c8060e8` 的三项 CI 通过。核心计划工程或复审完成 35/79，待推进 44 项。[源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45618421502)

M07 正式业务验收为 **PENDING**。G-1 为 **BLOCKED**，当前阶段 P0-0。M07 同源码 Windows 11 实机为 **NOT_TESTED**，部署证据待补。Windows 11 的 M06-R 历史证据归属原验收源码。M07 结项时 M08–M15 尚未开始。

## ROADMAP-V2 正式规划

2026-11-25 采用 `3bd705befb98ee108b77603763c5571ceb7fdc44` 为 M06-R 冻结基线，草稿 PR #1 的 Ubuntu、Windows Server 2022、Chromium 检查均通过。M01–M06 为 **ENGINEERING_PASS**，M06-R 为 **PASS**，M06 工程基线 **FROZEN**。路线图批准时核心计划含 79 个工作单元，工程或复审完成范围 31 项。P2 后另列 15 个可选单元。[完整规划](docs/planning/ROADMAP-V2.md) · [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45585265229)

`ROADMAP_V2 = APPROVED_AND_DOCUMENTED`，`MULTI_MODEL_DIRECTION = APPROVED`，`MODEL_ADAPTER_CONTRACT = PLANNED`，`MODEL_ADAPTER_IMPLEMENTATION = NOT_STARTED`。G-1 仍为 **BLOCKED**。M13-A 接手十万级查询性能债务。路线图批准时的规划变更只涉及文档，研究 API 调用 0 次。[负责人批准](docs/decisions/roadmap-v2-owner-approval.md) · [模型接口](docs/architecture/ai-model-adapter-contract.md)

## M06-R 独立工程复审

2026-11-25 从 `7b26d8da89db636c7e3f4ad73490b53dcc555155` 接续。复审覆盖 M01–M06，独立核对 25 项反例，修复 P1 三项及 P2 三项，未关闭 P0/P1 为 0。SQLite 保持 v7，沿用五项冻结政策及 `M06-B-F.1`。

归档源码 `9c27231376fcc32aae39a9b63df6fa9b9b98c4c6` 的 **WINDOWS_11_REAL_MACHINE = PASS**、**WINDOWS_11_DEPLOYMENT_GATE = PASS**。Python 277/277（既有 269，新增 8）、Node 2/2、Chromium 11/11 组和本机 HTTP 2/2 组通过。三档规模通过响应等价性和隔离恢复验证。**M06_IMPLEMENTATION = ENGINEERING_PASS**、**M06-R = PASS**、**M06_ENGINEERING_BASELINE = FROZEN** 在本验收提交的 Ubuntu、Windows Server 2022 和 Chromium 三项 CI 均通过时生效。[M06-R 证据](docs/evidence/m06-r/README.md) · [草稿 PR #1 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

G-1 = **BLOCKED**，PRE_M06_DEVELOPMENT_GATE = **PASS**，M07–M15 = **NOT_STARTED**。真实研究 API 调用 0 次。正式 CAT、J-14、逐源许可、删除审计、真实采样和编码、金标准及正式发布按原标准待验。

## M06-C5 统计分母、六桶与对账

2026-11-25 从 `db0c2c86385950b6630a2691e1263d5dd429aa32` 接续。**M06-C5_ENTRY_CHECK = PASS**，原生 Windows 11 的基线 Python 247/247，独立前置复核另有 7 个探针。统计实现固定 `M06-B-F.1`，同一证据相交后按唯一发生汇总，分别核六桶、主任务和排除账。SQLite schema 保持 v7。真实研究 API 调用 0 次。

源码 `a9eebee24616984dda8e72bab1242373555b06db` 通过 Windows 11 实机和部署门禁。Python 269/269（新增 22），Node 2/2，Chromium 11 组，隔离独立复审 22/22 加 6/6 探针。1K、10K、100K 三档完成 SQLite 全路径、双路资格比较及备份恢复，十万原始行得到 59,999 个合格唯一发生。未解决 P0/P1 为 0。**M06-C5 = ENGINEERING_PASS** 在本验收提交的 Ubuntu、Windows Server 2022 和 Chromium CI 全部通过时生效。[本轮证据](docs/evidence/m06-c5/README.md) · [草稿 PR #1 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

G-1 = **BLOCKED**，M07 = **NOT_STARTED**。正式业务准入继续执行原验收标准。

## M06-C4 三层关系、组合事务与权限

2026-11-25 从 `71a0668a9c9677c805ffe0f494c070fc6b9645d3` 接续。**M06-C4_ENTRY_CHECK = PASS**。原生 Windows 11 上 C3 基线 Python 215/215，另通过 3 项 C1–C3 同连接、依赖及最终提交独立探针。

C4 提供已封版共享定义、三层双向查询、精确证据下钻、可撤回的服务端授权、预检及单连接组合事务。SQLite 保持 v7。实机、复审和 CI 状态见 [C4 工程证据](docs/evidence/m06-c4/README.md)。G-1 = **BLOCKED**，PRE_M06_DEVELOPMENT_GATE = **PASS**。真实研究 API 调用 0 次。

在验收源码 `fce76a06195c7f45638c39b0347301fbb6bfbbae` 上，**M06-C4 = ENGINEERING_PASS**，**WINDOWS_11_REAL_MACHINE = PASS**，**WINDOWS_11_DEPLOYMENT_GATE = PASS**。原生 Windows 11 的 Python 247/247（既有 215、新增 32）、Node 2/2、Chromium 10 组、本机 HTTP 1 组及其余实机检查均通过。独立复审确认的三项 P1 和两项 P2 已修复，另修复一项 Chromium 测试夹具串扰。未解决 P0/P1 为 0。草稿 PR #1 保留验收提交的检查记录。[源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45560884986) · [PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

## 历史记录 · M06-C3 发生、区间、证据及产品边

2026-11-25 自 `e64141b76f78e17508133de0b91510d80e9daa81` 实施 C3。源码验收基线为 `43c72026e1776f6b78b78beeb3d87b7126016924`。SQLite v7 的 Python 服务可登记稳定发生和证据、封存片段版和拆并谱系、消费冻结范围和精确目录映射，并保存逐边人工审核与撤销。读和写均按当前 M05 资格校验实际直接证据与上下文。G-1 = **BLOCKED**，M06-C4 = **NOT_STARTED**，PRE_M06_DEVELOPMENT_GATE = **PASS**，真实研究 API 调用 0 次。[C3 实机及独立复审证据](docs/evidence/m06-c3/README.md)

M06-C3 = **ENGINEERING_PASS**，WINDOWS_11_REAL_MACHINE = **PASS**，WINDOWS_11_DEPLOYMENT_GATE = **PASS**。最终功能源码在原生 Windows 11 通过全量 Python 215/215、Node 2/2、Chromium 8/8、冷启动 3/3、归档 4/4、DPAPI、三类路径共 6 次启动及 SQLite v7 迁移和恢复。独立探针与同源副本复验通过，C3 未解决 P0/P1 为 0。[源码基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45544903551)

## 历史记录 · M06-C2-V 独立验证与 Windows 11 实机验收

2026-11-25，开发分支快进至实测基线 `6ef5b2e2d9a269dc072fa2db1d8296aae38e2e93`。M06-C2-V、WINDOWS_11_REAL_MACHINE、WINDOWS_11_DEPLOYMENT_GATE 均为 **PASS**。Windows 11 全量 Python 190/190，C2 专项 17/17 另行复跑，独立合成反例及事务探针各 4/4。Node 2/2、Chromium 8/8、冷启动 3/3、归档 4/4、DPAPI、三类路径启动与同库重启、SQLite v7 迁移恢复均通过。新增 P0/P1 为 0，真实研究 API 调用 0 次。PRE_M06_DEVELOPMENT_GATE = PASS。G-1 = BLOCKED。C3 = NOT_STARTED，工程前置条件满足，等待负责人单独授权。[Windows 11 验收证据](docs/evidence/m06-c2/windows11-closeout.md)

## 历史记录 · M06-C2 云端工程验收

2026-11-25，从 C1 基线 `776acfe` 实施 C2。实现提交 `965a4b8b3596c03437f9629f2f203e11af617726`。M06-C2 = **ENGINEERING_PASS**。该实现的[Ubuntu、Windows Server 2022 和 Chromium CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45532356340) 均通过。C2 的 Python/GET 与调用方写事务共用 M05 当前资格，修复同文件行撤销和到期的四项缺陷。Linux 全量 Python 190/190（新增 17）、Node 2/2、Chromium 8/8、冷启动 3/3、归档 4/4。云端实施交付时 C2 实机 Windows 11 为 NOT_TESTED，部署门禁为 BLOCKED。Pre-M06 开发门禁 PASS，G-1 BLOCKED，C3 NOT_STARTED，真实研究 API 调用 0。[C2 工程证据](docs/evidence/m06-c2/README.md)

核查日期 2026-11-25。接管分支 `codex/p0-0-connectivity`，历史接管基线 `bca93639043e176f4159b9bf9fb98b4b2e2b32d8`。[PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [接管基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341736949) · [15 个模块](MODULE_ROADMAP.md)

## 历史记录 · C1 Windows 11 实机验收及部署门禁

2026-11-25 在公司电脑 Windows 11 Enterprise 25H2 x64 上验收开发分支 `29dd1ffec595dccb3fad08b1194f5151b12decda`。Python 173/173、Node 2/2、Chromium 8/8、空库冷启动 3/3、脱敏归档 4/4 均通过。普通登录用户 DPAPI、三类路径启动和同库重启、SQLite v7 迁移及恢复通过。Windows 11 实机及其部署门禁均为 **PASS**。M06-C1 为 **ENGINEERING_PASS**，Pre-M06 开发门禁为 **PASS**，G-1 为 **BLOCKED**，M06-C2 为 **NOT_STARTED**，等待单独授权。真实研究 API 调用 0 次。[Windows 11 验收证据](docs/evidence/m06-c1/windows11-closeout.md)

## 历史记录 · M06-C1 数据库迁移与结构约束

2026-11-24，负责人批准以当前 Windows 10 实机证据核定开发门禁，Windows 11 验收移至该平台部署前。以冻结提交 `02dfcebff52687d93578011977d5dada3bf70d27` 核对原工程条件后，`PRE_M06_DEVELOPMENT_GATE = PASS`。M06 架构为 FROZEN。当时 Windows 11 实机为 NOT_TESTED，部署门禁和 G-1 均为 BLOCKED。[负责人门禁调整](docs/decisions/pre-m06-development-gate.md)

本轮实施 SQLite v7 新表与约束、写锁内版本复核、历史库升级及一致性备份恢复验证。Windows 10 实机通过 Python 173/173（新增 33 项）、Node 2/2、Chromium 8/8、空库冷启动 3/3、历史归档 4/4 及隔离启动器复测。M06-C1 为 ENGINEERING_PASS。实施提交 f54b5734a632503b35066b9ab4fb197b8597d967 的 Ubuntu、Windows Server 2022、Chromium 均通过。本机证据和远端验收见[迁移证据](docs/evidence/m06-c1/README.md)和[草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)。真实研究 API 调用 0。M06-C2 等待负责人另行授权。

## 历史记录 · M06-B-F 架构冻结

2026-11-24，以 M06-B 审核提交 `2651d66c6f14f93b05e8123f4ca8009eaede37a4` 为输入，负责人批准表达身份、产品归属、统计口径、跨项目授权及旧范围映射五项政策。架构审核 PASS、设计批准 APPROVED、架构 FROZEN。12 项问题均有设计处置及实施回归，未解决 P0/P1 设计阻塞为 0。M06_IMPLEMENTATION=NOT_STARTED，Windows 11 实机 NOT_TESTED，Pre-M06 Gate 和 G-1 均 BLOCKED，真实研究 API 调用 0。 [负责人批准记录](docs/architecture/m06-owner-approval.md) · [问题台账](docs/audits/m06-architecture-findings.md) · [实施计划](docs/architecture/m06-implementation-plan.md)

## 历史记录 · M06-B 独立架构审核

审核基线为开发分支 `48b5352feb72df852417d6c9edb96775896153a7`。M06_ARCHITECTURE_REVIEW=PASS_WITH_CONDITIONS，M06_ARCHITECTURE_APPROVAL=PENDING，M06_IMPLEMENTATION=NOT_STARTED。完成原 24 例逐项复核、16 例新增推演和临时 SQLite 实验。保留 SQLite v6、PDT v1.3.1 与原验收条件。Windows 11 实机 NOT_TESTED，PRE_M06_GATE=BLOCKED，G-1=BLOCKED，REAL_RESEARCH_API_CALLS=0。冻结前需负责人签认业务口径、明确授权控制及缺失原件的处置。工程实施须另获授权。[审核报告](docs/audits/m06-architecture-review.md) · [问题台账](docs/audits/m06-architecture-findings.md) · [实验记录](docs/evidence/m06-b/README.md)

## 前轮 M06-A 架构设计交付

本轮在 Pre-M06-D 文档冻结提交 `06a233e157631c9f9a004d8b1311c2948597a429` 上完成三层关系设计。六份设计文档包含证据与片段身份、SQLite v6 增量预案、双向查询、六桶、24 个合成反例及 12 项验收映射。反例为纸面推演。M06_ARCHITECTURE=READY_FOR_REVIEW，M06_ARCHITECTURE_APPROVAL=PENDING，M06_IMPLEMENTATION=NOT_STARTED。下一步为另行授权的 M06-B 独立审核。[设计入口](docs/architecture/m06-design.md) · [验收映射](docs/architecture/m06-test-plan.md)

真实研究 API 调用 0 次。正式阶段 P0-0，Windows 11 实机 NOT_TESTED，PRE_M06_GATE=BLOCKED，G-1=BLOCKED。

## 前轮 Pre-M06-D 实机验收与工程冻结

验收代码基线为 `4e6369b92205c51671866935365678df351ec808`，核对时 Windows 10 本机与开发分支远端一致。Windows 10 Home China 22H2 x64 实机工程验收 **PASS**。普通 PowerShell 会话由项目负责人实测，DPAPI CurrentUser 加解密通过，Python 140/140（17.747 秒），原版 Chromium 8/8。Codex 的 Pre-M06-L 本机记录补齐 Node 2/2、空库冷启动 3/3、历史归档 4/4、SQLite v6 迁移、中文空格路径及敏感信息扫描。[实机证据及来源](docs/evidence/pre-m06/windows10-closeout.md)

Codex 执行会话的 DPAPI 限制单独登记。Starlette 的 TestClient 弃用提示登记为非阻塞性技术债务。Windows 11 实机仍为 **NOT_TESTED**，**PRE_M06_GATE_BLOCKED**，G-1 **BLOCKED**。M01–M05 的实测基线可支撑另行授权后的 M06-A 架构设计，M06 实现及正式接入继续遵循现有放行条件。[审计报告](docs/audits/pre-m06-audit.md)

## 前期 Pre-M06 独立工程审计

基线 `04049b375f8b0e281c5f09f51d2fb07b5f1c3463`。修复 10 项缺陷并新增 16 项独立测试。实现 `d64fb4f29094be9a3fc9b91e2910830ea0c1c8c2` 的 Ubuntu、Windows Server 2022 各通过 Python 140/140、Node 2/2、三次冷启动及四份档案，Chromium 8/8。Windows 11 实机为 NOT_TESTED。**PRE_M06_GATE_BLOCKED**，G-1 仍为 BLOCKED。 [报告](docs/audits/pre-m06-audit.md) · [缺陷台账](docs/audits/bug-register.md) · [实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45373503587)

## 上轮 M05-R2 许可与数据资格复修

M05-R2 为 **ENGINEERING_PASS**。BUG-01、BUG-02 及旧库同文件行副本互相锁住复核的问题均已关闭。SQLite v5 保留历史并追加不可变许可事件。缺少结构化授权的旧核验记录可逐条复核，原文经当前资格校验后显示。

本机 Linux、Ubuntu CI、Windows Server 2022 CI 各通过 Python 124/124、Node 2/2、冷启动 3/3、历史归档 4/4。Chromium 8/8。Windows Server 的中文及空格路径启动通过，本轮 Windows 10/11 实机为 NOT_TESTED。正式阶段为 P0-0，G-1 **BLOCKED**，本轮真实研究 API 调用 0 次。[最终实现 `62a7c1c`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/62a7c1c132b72a8e07679f1713e6834aa7893c91) · [实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45367761470) · [复测证据](docs/evidence/m05/permissions-review.md) · [下游数据契约](HANDOVER.md#m05--m06-数据契约)

## 上轮 M05-R 独立工程复审

M05-R 当轮记录为 **ENGINEERING_PASS**。复审基线为 `f279c7e0075b07e581d528709ffd5c9824e1a811`，最终实现为 `d0414f5e7b978460d7dec3784c0862d7f1f0bdd0`。原留存期限、许可撤销、跨文件来源限制、批次重试和遮蔽均有回归。Windows 11 实机通过 Python 114/114（基线 104，新增 10）、Node 2/2、冷启动 3/3、Chromium 8/8 和归档 4/4。对应 Ubuntu、Windows Server 2022、Chromium 作业全部通过。真实研究 API 调用 0 次。正式阶段仍为 P0-0，G-1 **BLOCKED**。[M05-R CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45359711019) · [合成回归证据](docs/evidence/m05/review.md) · [M06 数据契约](HANDOVER.md#m05--m06-数据契约)

## 上轮 M05 原始语料库、去重及溯源

本机工作台已接入原始语料审核。记录绑定冻结范围与导入文件行，保存原话快照摘要、角色、许可核验依据、保留期限和历史。跨批次按项目聚合重复原话，撤销、排除及到期会重算可用组成员。原话审核走回环 FastAPI 和 SQLite v4，正式统计和外发资格均关闭。[本机操作与接入](docs/imports.md#m05-原始语料审核) · [工程测试记录](docs/evidence/m05/README.md)

M05 实现提交为 `b02a2b647bff67f7e091b51fcdfc46cc719077e8`，直接基于 `bca93639043e176f4159b9bf9fb98b4b2e2b32d8`。Windows 11 本机通过 Python 104 项、Node 2 项、空库冷启动 3 次、Chromium 8 组及四份历史归档核验。验证使用合成输入、隔离数据库和既有脱敏归档，真实 Tavily、Brave、Jev 请求均为 0。

2026-11-24，GitHub 确认 `kurikiwoods-coder` 具备仓库写入权限。Windows 上的 Git HTTPS 推送在发包阶段遇到 `Bad file descriptor`。通过获准的临时仓库 SSH 密钥，将 `b02a2b6` 常规推送到 `codex/p0-0-connectivity`，并核对远端完整 SHA。临时密钥已撤销。该提交的 Ubuntu、Windows Server 2022 和 Chromium 作业全部通过，M05 完成本轮工程交付。M05 增量 Git bundle 已通过 `git bundle verify` 并保存在本机交付目录。[草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [M05 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45352022477)

## 上轮 M04 CSV / Excel 数据导入

完成本机文件上传、工作表选择、字段映射、质量检查、确认入库、批次查询及撤销。导入写入 SQLite v3 暂存，绑定原项目和冻结范围。真实 Tavily、Brave、Jev 请求 0 次，G-1 保持 BLOCKED。[本机用法、模板与 M05 契约](docs/imports.md) · [工程测试记录](docs/evidence/m04/README.md)

M04 交付时，本地 Linux、Ubuntu 和 Windows Server 2022 各通过 95 项 Python（含新增 26 项）、2 项 Node 与 3 次空库冷启动，Chromium 六组通过。四份既有归档核验通过。[CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341223418) · [截图和实际输出](docs/evidence/m04/README.md)

## 上轮 M03 研究项目与范围管理

交付本机项目列表、新建和编辑、搜索排序、当前项目切换、归档恢复、五种研究模式及范围快照冻结。SQLite v2 增量迁移保留 M01 和 M02 存储边界。[本机操作与接口](docs/studies.md) · [工程测试记录](docs/evidence/m03/README.md)

Linux 本机、Ubuntu CI 和 Windows Server 2022 各通过 69 项 Python（含 16 项 M03）、2 项 Node、3 次空库冷启动，失败均为 0。Windows Server 中文及空格路径的启动器通过。Chromium 四组浏览器测试通过，含 M03 的研究项目操作与服务重启。四份历史收据经 SQLite 与 JSON 核对。Windows 10/11 真机 NOT_TESTED。本轮 Tavily、Brave、Jev 调用量均为 0。[三平台 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45336483119) · [桌面截图](docs/evidence/m03/m03-project-list.png) · [移动端截图](docs/evidence/m03/m03-mobile-detail.png)

## 上轮 M01 基础工程与连通性

已交付同批来源恢复。在本机运行 `python -m src.outputs.recover_source_batch` 可从锁定的 Tavily 归档恢复原批次，原帖许可、时间和原句指纹重新核对后才写入。恢复保留原批次 ID 和搜索证据。继续验收从「运行记录 → 恢复此批次」执行。原帖发生变化、归档损坏或中途写库失败时停止恢复，重复执行无额外搜索请求。[操作说明](docs/connectivity.md#原运行库缺失时继续原批次)

| 验证范围 | 实际结果 |
|---|---|
| Ubuntu | 53 项 Python、2 项 Node、3 次空库冷启动，四份 SQLite 与 JSON 归档核验通过 |
| Windows Server 2022 | 53 项 Python、2 项 Node、3 次空库冷启动，归档及中文和空格路径启动通过 |
| Chromium | 浏览器 E2E 通过，涵盖桌面和 320 / 390 像素布局 |
| 归档恢复 | 新增 6 项回归通过，覆盖锁定摘要、同批幂等、原帖变化、篡改拒绝、事务回滚及夹具隔离 |
| Windows 10/11 真机 | NOT_TESTED |

已通过工程测试的实现提交为 [`47051f3`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/47051f3749589478aef41b0fa2b73a9ac542bf30)。恢复回归使用隔离夹具及已提交的归档核验。真实 Jev 和付费 Tavily 请求在本轮均为 0。[本轮 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45325025692) · [恢复回归](https://github.com/kurikiwoods-coder/voc-research-workbench/blob/47051f3749589478aef41b0fa2b73a9ac542bf30/tests/test_recover_source_batch.py)

## 正式验收

| 要求 | 状态 | 现有证据 |
|---|---|---|
| C0-1 | BLOCKED | 固定版本和 8 + 3 实发分片需要符合审核的 Jev 调用 |
| C0-2 | BLOCKED | 等待 Choice、Score、Noul 完整真实响应 |
| C0-3 | PASS | Tavily 认证搜索一次，HTTP 200、实报 1 credit，原帖 94603 许可回源成功 |
| C0-4 | BLOCKED | SQLite 归档通过核对，真实 Jev 用量及余额回填待验证 |
| C0-5 | PASS | 36 次限制案例在传输前拦截，六种故障演练 |
| C0-6 | PASS | 两个产品品类及 30 个意图的跨品类召回冒烟 |
| G-1 | BLOCKED | 等待供应商留存审查及 C0-1、C0-2、C0-4 |

[正式批次 `89b0c2d1-576d-420f-9046-9e55878159be`](docs/evidence/p0-0/tavily-live/README.md) · [需求矩阵](docs/requirements-matrix.md)

## 下一轮候选

当前正式阶段为 P0-0。正式语料验收需完成逐源清理审计、三批和至少 100 条真实语义片段，并抽查 30/30 可回源。后续模块等待开发指令。
