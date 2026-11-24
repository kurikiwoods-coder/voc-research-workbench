# 开发交接

## 接管基线

2026-11-24 接管时，开发分支为 `codex/p0-0-connectivity`，远端提交为 `bca93639043e176f4159b9bf9fb98b4b2e2b32d8`。`main` 当时为 `f849242c5c37a2dc6a03a30215dd335424738c61`。开发成果汇集在指向 `main` 的草稿 PR #1，接管提交的 Ubuntu、Windows Server 2022 和 Chromium 工程检查均通过。[接管提交](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/bca93639043e176f4159b9bf9fb98b4b2e2b32d8) · [PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [接管提交 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341736949)

M03 和 M04 已完成独立工程验收。M04 代码复测为 `336e68c`，本机 Linux、Ubuntu 和 Windows Server 均通过 95 项 Python、2 项 Node 和 3 次冷启动。Chromium 通过 6 组，4 份历史归档核对通过。M05 已接入本机原话审核、去重与溯源，沿用 M04 的冻结范围及原文件引用。最新本机测试和发布状态见 [开发状态](DEVELOPMENT_STATUS.md)。[M04 证据](docs/evidence/m04/README.md) · [M05 工程记录](docs/evidence/m05/README.md)

当前正式阶段为 P0-0，G-1 为 **BLOCKED**。C0-3、C0-5、C0-6 已通过，C0-1、C0-2、C0-4 及 Jev 所选通道的留存与分处理商审查待验。继续保留固定 `jev-1.14.0`、8+3 分片、Choice / Score / Noul 完整返回及实际用量和余额要求。后续正式验收由有权限的人员在授权设备上按同批六项规则执行。G1/G2 的正式语料验收仍要求三批来源、至少 100 条合格原话及抽查 30/30 可回源。[正式历史批次](docs/evidence/p0-0/tavily-live/README.md) · [需求验收矩阵](docs/requirements-matrix.md)

仓库保留 PDT v1.3.1 Word 正文和专案 v2.2 的 Markdown 摘要。27 页专案 PDF 的 SHA-256 登记在需求矩阵，复核原件时从其授权来源取得。[PDT 正文](docs/pdt/PDT-v1.3.1.docx) · [专案摘要](docs/proposal/voc-workbench-proposal-2026-11-23.md) · [原件指纹](docs/requirements-matrix.md)

## M05 → M06 数据契约

| 数据 | 交接约束 |
|---|---|
| 原始语料 | `record_id` 稳定标识 M05 原始导入行。通过 `batch_id`、`file_id`、文件 SHA-256、工作表和物理行号回查。使用 `raw_sha256` 核对核验快照，派生文本与分类结果另存。 |
| 研究范围 | 以 `study_id` 和冻结的 `scope_id` 校验归属，记录 `scope_version` 和冻结时间窗。范围中的品类仅供抽样和范围检查。 |
| 来源与许可 | 使用采集时间和方法、提取规则、可核对 URL、发布时间及本机审核依据。读取当前审核、隐私、许可、有效期限及批次撤销状态。许可到期、撤销或证据不足时暂停后续使用。正式许可须有逐源审批记录。 |
| 重复组 | `duplicate.group_id` 为研究项目内的有效原话分组。当前主记录和成员数随排除、到期及批次撤销重算。历史引用继续指向原始 `record_id`。 |
| 后续处理 | 检查 M05 当前生效的 `status`，并同时校验来源、角色、隐私和冻结范围。`verified` 记录通过本机审核，其正式研究和外发字段仍为 `false`。待审、排除、撤销、到期、缺证据及许可未确认的记录留在审核或审计流程。背景证据按角色独立使用。内部 CX 仅限授权本机的处理或人工编码。合成数据进入独立工程夹具。 |
| 语义片段与证据 | PDT §6.6、§6.9、§9.3 的 `mention_id` 标识去重后的语义片段。后续证据记录用独立 `evidence_id` 引用 M05 原话及来源，供片段与品类关系使用。分段规则、片段标识生成、证据持久化和版本设计留待 M06 的授权工作。 |

M06 复用原话与来源记录，使用证据确定产品品类关系。意图保有一个已确认的有效主任务大类。正式分母只纳入 `published_classified` 的 distinct `mention_id`，按使用的研究范围及注册表版本复算。读取历史片段或证据时重新核对当前上游资格，审计状态和引用可继续追溯。处理路径与正式门槛详见需求矩阵。[PDT 正文](docs/pdt/PDT-v1.3.1.docx) · [原始语料接口](docs/imports.md#m05-原始语料审核) · [需求验收矩阵](docs/requirements-matrix.md)

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
