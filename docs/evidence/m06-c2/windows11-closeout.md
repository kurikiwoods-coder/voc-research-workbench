# M06-C2-V Windows 11 实机验收

验收日期为 2026-11-25（台北时间）。工作区干净，本地独有提交 0，远端独有提交 2。开发分支 `codex/p0-0-connectivity` 从 `776acfed513d1b56af0adfbaf74864912817f25f` 快进至 `6ef5b2e2d9a269dc072fa2db1d8296aae38e2e93`，与当时草稿 PR #1 的头提交一致。增量包含 C2 实现 `965a4b8b3596c03437f9629f2f203e11af617726` 和工程证据。基线与实现提交的 Ubuntu、Windows Server 2022、Chromium 作业均通过。[基线提交](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/6ef5b2e2d9a269dc072fa2db1d8296aae38e2e93) · [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45532788628) · [实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45532356340) · [草稿 PR #1 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

## 环境与回归

Windows 11 Enterprise 25H2 x64，OS Build 26200.8655。Codex Desktop 从当前 Windows 登录用户的非提升会话执行原生 PowerShell 7.6.9。Git 2.55.0.windows.5、Python 3.12.9、SQLite 3.45.3、Node.js 24.19.0、Playwright 1.65.2、Chromium 159.0.8154.6。使用 `git archive` 解出的隔离源码、临时 SQLite、合成数据和四份既有脱敏归档。测试进程移除研究 API 与审核材料的环境输入。真实研究 API 调用 0 次。

| 项目 | 通过 / 执行 | 失败 / 跳过 | 退出码 |
|---|---:|---:|---:|
| Python 全量 `python -m unittest discover -s tests -p "test_*.py" -v` | 190 / 190 | 0 / 0 | 0 |
| C2 专项 `python -m unittest discover -s tests -p test_m06_eligibility.py -v` | 17 / 17 | 0 / 0 | 0 |
| 独立合成反例 | 4 / 4 | 0 / 0 | 0 |
| 独立事务探针 | 4 / 4 | 0 / 0 | 0 |
| Node `node --test tests/client_state.test.cjs` | 2 / 2 | 0 / 0 | 0 |
| Chromium `python tests/browser_e2e.py` | 8 / 8 | 0 / 0 | 0 |
| Windows 空库冷启动 `python scripts/cold_start.py` | 3 / 3 | 0 / 0 | 0 |
| 历史脱敏归档 `python -m src.outputs.audit_receipt --verify` | 4 / 4 | 0 / 0 | 每份 0 |
| SQLite 专项迁移复跑 | 11 / 11 | 0 / 0 | 0 |
| DPAPI CurrentUser 及应用凭证生命周期 | 通过 | 0 / 0 | 0 |
| 原版 Windows 启动器首次启动和同库重启 | 6 / 6 | 0 / 0 | 探针 0 |
| 敏感信息扫描 | 通过 | 0 / 0 | 0 |

Python 全量用时 84.780 秒，包含原有 173 项和 C2 新增 17 项。原有用例覆盖 Pre-M06 A–H、M05-R2 许可和撤销，以及 C1 的 33 项约束及迁移。C2 专项和迁移专项均为全量中已有用例的独立复跑。另执行 8 项临时独立验证。仓库新增测试 0 项。Chromium 覆盖凭证设置、M01 连通性、M03 项目、M04 导入、M05 审核及 M03–M05 重启。四份归档 P0-0、regression、api-setup/live-receipt、tavily-live 的证据条目依次为 20、10、10、10，SQLite 完整性均为 `ok`，各自的原验收状态照录。

## 四项独立反例

| 场景 | 实际结果 |
|---|---|
| 未逐行审核的原批次撤销，另一个批次已有合格的同文件行副本 | Python 和持写锁入口均拒绝，GET 409，详情遮蔽原话，测试引用为 0 |
| 撤销记录没有映射来源 URL，另一次导入的同文件行有 URL | 副本 GET 409，按同项目、同文件字节、同工作表、同行识别。登记明确新授权后，仅指定记录恢复本机资格 |
| 原记录撤销时保留的期限已过，再提交新材料 | 复核 409，历史原话仍遮蔽 |
| 撤销省略新截止日，副本声明较晚有效期 | 原历史期限继续约束副本，过期后复核 409，历史原话仍遮蔽 |

四个反例各自使用独立合成夹具。各库 `integrity_check=ok`，`foreign_key_check` 均为 0 行。反例初次组装时缺少结构化授权字段，服务返回 422。补齐夹具后执行上表四项。[已有修复证据](README.md) · [资格实现](../../../src/raw_store/corpus_access.py) · [资格入口](../../../src/raw_store/corpus.py)

## C2 事务及 C3 交接

- `qualified_record`、`qualified_record_in_transaction`、GET eligible 与 `qualified_write_inputs` 复核使用同一资格。跨项目与不存在记录均为 404，同项目失格为 409。复验覆盖冻结范围追溯、同源及同行副本、独立来源保留、单条重新授权、整组拒绝、错误连接、同事务许可变化，以及撤销后的历史读取、暂存、错误导出、重试和原话遮蔽。
- WAL 双连接实测覆盖撤销先提交、合法写入先提交和旧读快照升级。撤销先提交时拒绝写入，合法写入先提交时历史引用保留且之后的读取重新遮蔽。旧快照升级返回 `SQLITE_BUSY_SNAPSHOT`。写事务跨 UTC 日需整体回滚并重算，即使当时许可仍有效。
- 四项独立事务探针观察到真实写锁争用 `SQLITE_BUSY`，已声明的失格上下文在执行块前即拒绝，块内异常加外层回滚后无残留，延迟外键导致最终 COMMIT 失败时外层回滚也无残留。C2 保存点仅覆盖当前块，异常后外层仍由调用方控制。
- C3 获授权后由调用方校验操作者和项目，在 Store 主库同一连接显式执行 `BEGIN IMMEDIATE`，按实际写入推导全部直接证据和上下文 ID，在资格块内执行依赖写，正常退出后立即 COMMIT。任一步失败由调用方回滚整项命令，跨日或旧快照失败须在新事务重算。发生身份、语义片段区间、依赖关系完整性、产品归属和回放继续按冻结计划落实。[冻结实施计划](../../architecture/m06-implementation-plan.md) · [验证矩阵](../../architecture/m06-test-plan.md)

## Windows 启动器、凭证及 SQLite

- 普通、中文、含空格目录各执行首次启动和同库重启。六次均由原版 `scripts/start-windows.cmd` 启动，首页、`/api/health`、`/api/workspace` 均返回 200，工作台 schema 为 v7，服务正常关闭并释放端口。首轮保留了六份服务日志和探针退出码 0，逐进程退出码未留存。三类目录随后各额外复跑一次，三次均在 `CTRL_BREAK` 后正常关闭，批处理各退出 3，探针退出 0。
- 普通登录用户的 .NET 和 Win32 DPAPI CurrentUser 加解密通过。三次应用进程分别验证合成凭证加密持久化、重启回读、删除后重启。浏览器 DOM、存储、控制台、HTTP 响应和校验错误、应用日志及隔离运行文件均未见合成凭证明文。一次运行中读取 SQLite `-shm` 遇 Windows 文件锁，停服务后重新检查通过。
- 空库及历史 v1–v6 可迁移至 v7，同库再开保持 v7。v6 升级及活跃 WAL 一致性备份恢复保留原话、审核和撤销许可历史及稳定 ID。双进程竞争仅执行一次迁移，中途异常和中断保留 v6，重试升级成功。专项完整性均为 `ok`，外键检查均为 0 行。工作台、M01 合成契约和诊断库的版本分别为 v7、v1、v1，外键开关均启用。

## 门禁判定

| 项目 | 判定 |
|---|---|
| `M06-C2-V` | **PASS** |
| `WINDOWS_11_REAL_MACHINE` | **PASS** |
| `WINDOWS_11_DEPLOYMENT_GATE` | **PASS** |
| `M06-C2` | **ENGINEERING_PASS** |
| `PRE_M06_DEVELOPMENT_GATE` | **PASS** |
| `G-1` | **BLOCKED** |
| `M06-C3` | **NOT_STARTED**，工程前置条件满足，等待负责人单独授权 |

复验确认新增 P0/P1 为 0。既有 Starlette TestClient 弃用提示继续登记为非阻塞技术债务。C2 工程资格限于本机，正式研究仍须完成同一批次的 C0-1、C0-2、C0-4 和适用供应商审批及留存核验。正式语料数量、逐源许可、删除审计、统计及发布按原矩阵验收。专案 v2.2 的 27 页原 PDF 仍待补。[需求验收矩阵](../../requirements-matrix.md) · [负责人门禁调整](../../decisions/pre-m06-development-gate.md)
