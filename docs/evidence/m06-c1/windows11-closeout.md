# M01–M06-C1 Windows 11 实机验收

验收日期为 2026-11-25（台北时间）。开发分支 `codex/p0-0-connectivity` 从 `958ebcb948fa9677a7254dde4516c4a49761b798` 快进至 `29dd1ffec595dccb3fad08b1194f5151b12decda`。同步前工作区干净，本地独有提交 0，远端独有提交 16。验收基线与草稿 PR #1 的头提交一致。它相对 C1 实现 `f54b5734a632503b35066b9ab4fb197b8597d967` 的改动仅涉及文档。[基线提交](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/29dd1ffec595dccb3fad08b1194f5151b12decda) · [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45436754359) · [草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1)

## 环境与隔离

| 项目 | 实测 |
|---|---|
| 操作系统 | Windows 11 Enterprise 25H2，OS Build 26200.8655，x64 |
| 执行上下文 | Codex Desktop 启动的原生 PowerShell 7.6.9，当前 Windows 登录用户、非管理员提升，会话具备用户配置文件。应用通过原生 Windows Python 和回环网络运行。 |
| 工具 | Python 3.12.9 x64、SQLite 3.45.3、Node.js 24.19.0、Playwright 1.65.2、Chromium 159.0.8154.6、Git 2.55.0.windows.5 |
| 数据 | 通过 `git archive` 提取验收代码，分别使用独立运行目录、临时 SQLite 与合成夹具。执行进程清除研究 API 凭证及审核路径的环境输入。仅回读仓库内四份既有脱敏归档。真实研究 API 调用 0 次。 |

## 全量回归

| 核验 | 通过 / 执行 | 失败 / 跳过 | 退出码 |
|---|---:|---:|---:|
| Python `unittest discover -s tests -p 'test_*.py' -v` | 173 / 173 | 0 / 0 | 0 |
| Node `node --test tests/client_state.test.cjs` | 2 / 2 | 0 / 0 | 0 |
| 原版 `tests/browser_e2e.py` | 8 / 8 | 0 / 0 | 0 |
| `scripts/cold_start.py` | 3 / 3 | 0 / 0 | 0 |
| 历史归档 `src.outputs.audit_receipt --verify` | 4 / 4 | 0 / 0 | 每份 0 |
| 敏感信息扫描 `scripts/check-no-secrets.sh` | 通过 | 0 / 0 | 0 |

Python 用时 79.074 秒，包含 M01–M05 原有 140 项及 C1 新增 33 项（22 项结构约束、11 项迁移）。本轮新增仓库测试 0 项。Pre-M06 审计 16 项及 M05 结构化许可 10 项均包含在 173 项内。实际覆盖 A–H 跨模块场景、许可撤销后的遮蔽、同项目同来源副本限制、内部 CX 隔离、冻结范围版本与现有资格接口。Chromium 八组覆盖设置向导、M01 连通性、M03 项目、M04 导入、M05 原话审核及 M03–M05 的服务重启回查。

四份归档依次为 P0-0、regression、api-setup/live-receipt、tavily-live，证据条目分别为 20、10、10、10。各份 SQLite 完整性均为 `ok`，归档核验保持各自的历史状态。

## DPAPI CurrentUser 与应用凭证

非提升登录用户执行 .NET `ProtectedData` 及应用使用的 Win32 DPAPI 加解密，合成字节均正确回读。专项验证通过真实回环服务和 Chromium 使用临时合成凭证，服务进程启动三次。第一次写入后，磁盘凭证库为 DPAPI 密文，同用户解密可回读。第二次启动读取成功，删除后凭证立即禁用。第三次启动仍未配置，解密后的凭证库无该条目。API 保存和删除返回 200，包含合成值的无效输入返回 422，响应不回显。浏览器 DOM、浏览器存储和控制台、HTTP 响应、应用日志及隔离运行文件中均未发现合成值明文。专项退出码 0。

## 启动器与数据库

| Windows 路径 | 首次启动 | 同库重复启动 | 关闭及端口回收 |
|---|---|---|---|
| 普通目录 | PASS | PASS | 两次均通过 |
| 中文目录 | PASS | PASS | 两次均通过 |
| 含空格目录 | PASS | PASS | 两次均通过 |

六次通过原版 `scripts/start-windows.cmd` 启动。每次首页、`/api/health` 和 `/api/workspace` 返回 HTTP 200，工作台历史为空，工作台数据库实测 schema v7。Windows 控制台停止信号后，Uvicorn 记录完整关闭，回环端口 8765 均可重新独占绑定。各次受到控制台停止信号的批处理退出码均为 3，启动器验证程序退出码为 0。

| SQLite 检查 | 实测结果 |
|---|---|
| 空库、历史 v1–v6 与同库重启 | 六个隔离历史版本分别升级至 v7，两次打开维持 v7，合成历史行和稳定 ID 保留。工作台为 v7，M01 合成契约库和诊断库分别为 v1，三类 Store 连接均启用外键。 |
| 原话与许可历史 | v6 夹具升级前后逐表比较全部历史行。快照与原话、文件行、批次、冻结范围、审核和已撤销许可均保留稳定标识。项目错挂的旧批次保有历史记录并由 v7 拒作新证据。 |
| 双进程、失败和中断 | 既有回归跑过空库启用 WAL、空库及 v6 的双进程迁移。仅一方执行 007。注入 SQL 异常和提交前中断均保留 v6、原数据及版本号，重试后升级成功。 |
| 活跃 WAL 备份与恢复 | 回归通过 SQLite 备份 API 取得包含已提交 WAL 变动的一致性 v6 副本。核对源库、备份及恢复库的全部历史行，再独立升级并重新对账。 |
| 完整性、外键和约束 | 上述迁移检查的 `integrity_check` 为 `ok`，`foreign_key_check` 返回 0 行。C1 回归验证证据与冻结范围复合引用、跨项目引用、唯一主任务、版本谱系与封存、命令幂等键和事务原子性。 |

同写事务实时资格复核属于已冻结的 C2 实施范围。C1 实机核验使用现有 M05 Python/GET 资格入口及 v7 结构约束。[C1 工程证据](README.md) · [C1–C5 计划](../../architecture/m06-implementation-plan.md)

## 缺陷和门禁

本轮发现新增阻塞性产品缺陷 0。已登记的非阻塞性 `StarletteDeprecationWarning` 在调用 TestClient 时仍出现，173 项全部通过。专项探针初次运行使用了错误的请求头值及 SQLite 行比较方式，分别修正探针后实测通过。提交范围为本验收记录及状态文档。

| 项目 | 判定 |
|---|---|
| `WINDOWS_11_REAL_MACHINE` | **PASS** |
| `WINDOWS_11_DEPLOYMENT_GATE` | **PASS** |
| `PRE_M06_DEVELOPMENT_GATE` | **PASS** |
| `M06-C1` | **ENGINEERING_PASS** |
| `G-1` | **BLOCKED** |
| `M06-C2` | **NOT_STARTED**，工程前置条件满足，等待负责人单独授权。 |

正式研究准入仍缺同批 C0-1、C0-2、C0-4 及适用供应商公开语料处理审批和留存审查。真实语料数量、逐源许可及删除审计继续按需求矩阵验收。专案 v2.2 的 27 页 PDF 原件缺口沿用架构冻结记录。[门禁决议](../../decisions/pre-m06-development-gate.md) · [需求验收矩阵](../../requirements-matrix.md) · [架构批准记录](../../architecture/m06-owner-approval.md)
