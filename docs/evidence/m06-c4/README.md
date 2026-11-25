# M06-C4 工程验收

## 基线和入门检查

2026-11-25，开发分支 `codex/p0-0-connectivity` 从 `71a0668a9c9677c805ffe0f494c070fc6b9645d3` 接续。接续时本地、远端和草稿 PR #1 同版。该基线的 Ubuntu、Windows Server 2022 和 Chromium 均通过。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45546117449)

**M06-C4_ENTRY_CHECK = PASS**。Windows 11 隔离基线的 Python 通过 215 项，失败及跳过均为 0，退出 0。三项独立探针核对精确 S/R/M/E、默认拒绝、原帖与上下文实际依赖、同事务内资格变化、最终 COMMIT 的实际外键拒绝及重试。SQLite 完整性为 `ok`，外键违规为 0。复审详见 [独立验证](independent-verification.md)。

## 实现及版本

- 原始层按已封存版本投影共享产品、任务、意图及主次边。两个任务方向共用 `m06_intent_task`，两个产品方向共用 `(S,V,R,M,E,P,A)` 证据边。合格原话、有效人工归属、冻结范围以及来源、批次和时间筛选必须在同一 E 成立。
- 项目读和写接受可信服务端授权，范围含操作者、项目、数据、用途、授予根据、期限和撤回。项目数据和共享字段用不同查询投影。HTTP 上线实例只在接入实际授权源后才开放项目投影。
- 内部组合事务在一个主库连接内取写锁、检查授权和期望版本、计算幂等摘要与实际证据依赖、调用 C2、封存注册表并提交。事务包含命令记录和可选工程归属。任一失败整项回滚。
- HTTP 提供共享定义、双向关系、项目片段、证据和候选预检，另提供按授权过滤的项目选择器。签名游标绑定版本、筛选和结果投影，每次翻页重新查询。中文工作台可查看主次任务、冻结范围及合格来源。
- 数据库保持 SQLite v7。正式模式未准入时返回 `unavailable`、原因和 `counts:null`。真实研究 API 调用 0。G-1 = **BLOCKED**，M06-C5 = **NOT_STARTED**。

源码验收提交为 `fce76a06195c7f45638c39b0347301fbb6bfbbae`。

| 变更位置 | 职责及回归范围 |
|---|---|
| `src/raw_store/relations.py`、`relation_access.py`、`relation_queries.py`、`relation_registry.py` | C4 服务、授权投影、版本化关系及组合写入。沿用 v7 和 C2 同连接接口。 |
| `src/dashboard/relations_api.py`、`app.py` | 注册共享定义、双向关系、项目列表、片段、证据和预检路由。复用本机安全入口、无缓存响应及错误脱敏。 |
| `src/dashboard/static/relations.js`、`app.js`、`app.css` | 增加中文关系工作台、筛选、分页、原话抽屉和响应式布局。 |
| `scripts/start-windows.cmd`、`scripts/cold_start.py`、根 `README.md` | 启动与验证命令关闭代理头解析。 |
| `tests/test_m06_relations*.py`、`tests/browser_e2e.py`、`tests/relations_browser.py`、`tests/corpus_browser.py` | 32 项 C4 Python 用例和可独立运行的合成浏览器/HTTP 固件。保留现有工作流及重启断言。 |

## 场景和冻结验收

见下表的合成反例及同仓库回归。正式业务 CAT、真实编码、分母、已发布报告及外发另按冻结要求验收。

| 场景 | 合成输入及断言 |
|---|---|
| A–B | 同一确认意图在两个产品有各自已审核支持，两个方向都复用一个意图 ID。 |
| C–E | 确认意图恰一主任务和同版有效次任务。零主、双主和不在目标版的边拒绝并保留原库。无父候选可留 `pending_parent`。 |
| F | 将产品、冻结范围、批次、来源和时间分别放到不同 E，组合筛选不可拼接。 |
| G–I | 项目授权隔离、字段白名单、六类角色各自允许与拒绝、默认关闭。跨项目和不存在对象统一 404。 |
| J–L | 撤回精确授予及撤销依赖后复核历史回执、游标和证据。失格边消失，独立合格证据可继续支持关系。 |
| M | 同名不同产品 ID、多个目录版和历史冻结映射互不替代。 |
| N–O | 半发行中断、同父竞争、最终 SQLite COMMIT 拒绝、响应丢失和同键异载荷。事务及同键重试与数据库快照逐项核对。 |
| P–Q | 本机 HTTP 验证 Host、Origin、动作头、代理地址和默认身份。实际 Chromium 重开已撤销证据时清除旧原话和投影。 |
| R–S | 无正式准入返回不可用与空计数。明确无产品的工程研究返回有效空集。 |
| T | 拒绝停用已发布节点的祖先，继续读取原封存目录和精确历史版本。 |

[冻结映射](../../requirements-matrix.md#m06-c4-工程验收范围)包含 A03–A05、A09、A11–A12、A16–A17、A21–A24、B10–B14、B16 和 CAT-1/2/5/7/8/9。A16/A24 的正式召回和 Noul 输入留 M12/J-14。C4 验收覆盖准入隔离和已有 C0-6 合成回归。

## 实机及发布结果

实机环境为 Windows 11 Enterprise 25H2 x64（构建 26200.8655），以普通用户运行。使用 PowerShell 7.6.9、Git for Windows 2.55.0、仓库 `.venv` 的 Python 3.12.9 和 SQLite 3.45.3，以及 Node 24.19.0、Playwright 1.65.2 和 Chromium 159.0.8154.6。启动器从 24 个离线 wheel 安装依赖。

用 `git archive` 解出指定提交，为浏览器、Python 和启动器检查建立隔离环境。回归运行 `python -m unittest discover -s tests -v`、`node --test`、`python tests/browser_e2e.py`、`python scripts/cold_start.py`、`python -m pip check` 和仓库敏感内容扫描，并通过 `python -m src.outputs.audit_receipt --verify` 核查历史脱敏归档。C4 专项另执行 `python -m unittest discover -s tests -p 'test_m06_relat*.py' -v`。

原版 `scripts/start-windows.cmd` 分别在普通、中文和含空格目录进行首次启动和同库重启，检查首页、健康端点、工作台、SQLite 库完整性、外键和端口释放。凭证探针使用合成标记核对当前用户 DPAPI、加密落盘、跨重启读取和删除，以及页面、浏览器存储、日志及本机运行文件中的明文残留。浏览器使用合成数据和本地回环，记录关系、证据、320/390 像素布局和撤回后页面。截图经人工检查后才进入脱敏证据包。

中间提交 `1128bbd` 的 Chromium CI 和 Windows 11 全量浏览器均复现测试夹具串扰。C4 混合冻结范围夹具写入了共享测试库的当前项目，导致 M03 重启断言失败。`fce76a0` 使用关系页自身的项目筛选，保留 M03 当前项目及重启断言。[中间 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45560257947)

2026-11-25，Windows 11 实机从最终源码 `fce76a06195c7f45638c39b0347301fbb6bfbbae` 的隔离归档执行全量验收，19 项检查全部退出 0。Git tree 为 `9edcf48197ddfd17ddea18415f4a600d22fcf323`。源码归档 SHA-256 为 `d4416d8595f6979f6d3e1d150c09b6bd4da3f3b9bf2a12f5cd29fb471a4939e3`。独立复审代理另以同一源码执行 Chromium 与 HTTP 专项。[独立复审](independent-verification.md)

| 实机检查 | 结果 |
|---|---|
| Python 全量与 C4 专项 | 全量 247/247（155.560 秒），C4 32/32（36.922 秒），均无失败、错误或跳过。 |
| Python 定向回归 | C1 约束 22/22、迁移 11/11，C2 17/17，C3 25/25，M05 语料 16/16、许可 10/10，Pre-M06 16/16。 |
| Node 与本机端到端 | Node 2/2，Chromium 10 组与回环 HTTP 1 组均通过。M03、M04、M05 在同库重启后各自复核。 |
| 冷启动与原版启动器 | 冷启动 3/3，普通、中文和含空格路径的首启及同库重启 6/6。HTTP 三个入口均为 200，SQLite schema 7，完整性 `ok`，外键违规 0。每次发送 Ctrl+C 后原版批处理进程退出 3，服务优雅退出且端口释放，启动器验证进程退出 0。 |
| 凭证和敏感扫描 | DPAPI 当前用户往返、加密落盘、重启读取和删除后重启通过。合成明文标记检查和 Git 跟踪内容扫描均通过。 |
| 历史脱敏归档 | 4 档记录数 20、10、10、10，SQLite 完整性均为 `ok`，G-1 均为 `BLOCKED`。 |

[实机脱敏清单](m06-c4-windows11-manifest.json)记录各退出码、用例数和六张合成截图的 SHA-256。[关系](screenshots/c4-relations.png)、[原话证据](screenshots/c4-evidence.png)、[320 像素](screenshots/c4-mobile-320.png)、[390 像素](screenshots/c4-mobile-390.png)、[撤回后](screenshots/c4-revoked.png)和[冻结范围映射未解析](screenshots/c4-unresolved-scope.png)均经人工复核。原话与批次标识来自合成夹具，测试请求在本机回环完成。

最终源码的 Ubuntu、Windows Server 2022 和 Chromium 三个作业全部通过。M06-C4 = **ENGINEERING_PASS**，WINDOWS_11_REAL_MACHINE = **PASS**，WINDOWS_11_DEPLOYMENT_GATE = **PASS**。文档及脱敏证据提交随草稿 PR #1 复跑同一套检查。[最终源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45560884986) · [PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

[脱敏测试输出](windows11-results.txt)保留了各项实际运行的摘要和退出码。
