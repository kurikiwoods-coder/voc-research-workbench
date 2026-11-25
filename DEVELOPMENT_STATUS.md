# VOC Research Workbench 开发状态

## M06-C3 发生、区间、证据及产品边

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
