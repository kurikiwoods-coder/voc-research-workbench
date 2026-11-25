# 开发交接

## M06-C2 交接给桌面端及后续 C3

M06-C2 = **ENGINEERING_PASS**。[三项实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45532356340) 均通过。C2 实现为 `965a4b8`。现有 Python/GET 合同及 SQLite v7 保持兼容。C2 在 Linux 已执行 190 项 Python、2 项 Node、8 个 Chromium 场景、三次冷启动及四份归档。桌面端须对 C2 版核对 SHA、普通登录用户启动、同库恢复、全量及 C2 WAL/UTC 专测，记录 Windows 11 实机证据后再判定平台部署门禁。当前 C2 实机 NOT_TESTED、部署门禁 BLOCKED；C1 历史 PASS。[测试命令与证据](docs/evidence/m06-c2/README.md)

C3 NOT_STARTED，待负责人另行授权。实施时由调用方校验操作者与项目、准备全部证据及上下文 ID，在主库同一连接的 BEGIN IMMEDIATE 内使用 `CorpusStore.qualified_write_inputs(db, study_id, record_ids)`。所有依赖写置于该上下文，正常退出后立即提交，任何失败由外层回滚整项操作，跨 UTC 日在新事务重算。GET、旧回执、同文副本或暂存内容均不授予后续处理权。C3 负责声明依赖是否完整以及发生、区间和产品关系。G-1 BLOCKED，正式统计与外发继续关闭。

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
.\.venv\Scripts\python.exe -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
```

也可用 `scripts/start-windows.cmd` 启动。PowerShell 的执行策略限制虚拟环境激活脚本时可直接调用上面的 venv Python。运行统一回归时从 Git Bash 进入仓库根目录，执行 `source .venv/Scripts/activate` 后运行下方测试命令。

### Linux、macOS 和云端工作区

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
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
