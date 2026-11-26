# M06-C1 迁移与工程验收证据

2026-11-24 至 2026-11-25，在正式开发分支 codex/p0-0-connectivity 上实施。架构冻结基线为 02dfcebff52687d93578011977d5dada3bf70d27。以下本机证据使用实现工作区的代码。工程放行须同时核对实现提交的 GitHub Actions 作业。[负责人门禁调整](../../decisions/pre-m06-development-gate.md) · [草稿 PR #1 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

## 同提交的 GitHub CI

实施提交 f54b5734a632503b35066b9ab4fb197b8597d967 为草稿 PR #1 的实际头提交。GitHub Actions 45435846994 的 head_sha 与其一致。Ubuntu、Windows Server 2022 和 Chromium 均以 success 完成，分别生成 smoke-ubuntu-latest、smoke-windows-2022 及 chromium-evidence 归档。结合本机回归，M06-C1 判定为 ENGINEERING_PASS。Windows Server 2022 为独立 CI 平台，Windows 11 实机及部署门禁维持已登记的状态。[实施提交](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/f54b5734a632503b35066b9ab4fb197b8597d967) · [实际 CI 与产物](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45435846994)

## 迁移及对账

| 验证 | 实测结果 |
|---|---|
| 空库与重复启动 | 工作台从 001 顺序迁移至 007，schema 版本为 7。重复启动仍为 v7。M01 合成契约库及诊断库分别保留原路径和 v1。每个 Store 连接启用外键。 |
| 双进程竞争 | 两个独立进程竞争为空数据库启用 WAL。对受控的空库及 v6 并发启动，等待者先抵达写锁，写锁释放后两个进程均读到 v7。轨迹证明只有持锁者执行 007。 |
| 历史数据 | 合成 v6 夹具的历史运行、结果、证据、项目、范围、冻结、文件、导入批次、原话、快照、许可及审核的完整行集合逐表相等，保留稳定 ID 与关联。包含已验证和已撤销记录。原 M01–M05 v1 至 v5 迁移回归也执行。 |
| 一致性备份与恢复 | v6 升级前 integrity_check 为 ok，foreign_key_check 为 0 行。保留活跃 WAL 并提交合成变动，通过 SQLite Connection.backup 取得包含 WAL 内容的一致性副本。升级原隔离库，通过备份 API 还原出另一个 v6 副本，确认全字段相同后重新迁移。升级、恢复及重迁移的完整性检查均为 ok，外键违规 0。 |
| 迁移中断与失败 | 让子进程执行 007 DDL 并暂存新版本号，在提交前终止。另注入 SQL 失败。两案均保持 v6、原行和原 ID，新对象无残留，重试升级成功。未知高版本拒绝启动，保留原版本和记录。 |
| 历史来源异常 | 合成 v6 夹具复现直接 SQL 替换批次造成的项目错挂。升级仍保留历史行，但拒绝用不一致的来源建立新的 M06 证据。v7 拒绝替换已有语料快照的批次 ID 或项目、范围及签名组合。原导入重试和撤销路径均纳入回归。 |

[迁移源码](../../../src/raw_store/migrations/007_m06_core.sql) · [迁移测试](../../../tests/test_m06_migration.py)

## 数据库保证与服务验收

007 新增 20 张表。三层目录及谱系使用 m06_registry、m06_product、m06_task、m06_intent、m06_intent_task、m06_representative、m06_change_edge。冻结范围映射使用 m06_scope_binding、m06_scope_product。证据和项目发生版本使用 m06_evidence、m06_mention、m06_segment_rev、m06_member、m06_support、m06_replacement。产品和发现审核使用 m06_mention_product、m06_product_review、m06_discovery_review、m06_discovery_input。m06_command 保存幂等键与审计引用。两个视图提供已封存的目录和项目片段 HEAD。历史表的数据布局保留，增加语料快照的复合引用索引及来源、范围的防替换触发器。

| 数据库断言 | 独立测试覆盖 |
|---|---|
| 主任务 | 拒绝已确认意图没有主任务、提交时缺少主边、存在两个主任务、主任务跨版本或生命周期失效。允许有效次因共存。 |
| 归属与引用 | 拒绝跨项目、跨版本、部分 NULL 的条件引用。证据须匹配原快照、内容摘要、来源归属和 Unicode 区间。验证撤销时间及原文件关系保留。 |
| 谱系与封存 | 拒绝多根、分叉、错误父版本、循环及直接封存。验证封存后的增删改和 REPLACE 均被拒绝。并发发行同一父版本只有一个成功，失败事务无多余命令或关系。 |
| 范围、产品及事件 | 核对冻结原快照、旧绑定保留、同版产品映射、逐证据产品边、独立发现输入、替代关系和审核事件。 |
| 命令 | 验证命令键按操作和命名空间唯一，重复键不能写入第二条命令。 |

后续服务须验证同写事务的 M05 实时资格与撤销竞态、可信授权、跨项目发生判同、同载荷重放及异载荷冲突、已发布引用及祖先节点的保护、正式统计及下游发布。三项结构独立支撑只有在业务层完成身份、有效性和独立性复验后，才能进入正式统计。[约束测试](../../../tests/test_m06_constraints.py) · [架构问题台账](../../audits/m06-architecture-findings.md)

## Windows 10 本机回归

Windows 10 Home China 22H2 x64，Build 19045.6466。Python 3.12.14、SQLite 3.53.1、Node 24.22.3、Playwright 1.65.2、Chrome 157.0.8103.80。数据库和工作台运行均使用隔离目录。

| 检查 | 结果 |
|---|---|
| Python | 173/173，24.819 秒，退出码 0。M01–M05 原有 140 项，包括 Pre-M06 场景 A–H、M05-R2 许可回归和现有 Python/GET 资格接口。新增 33 项，由 22 项约束和 11 项迁移组成。三处历史迁移夹具准备阶段清除空的 v7 对象后再构造 v3/v4/v5，原业务断言保留。 |
| Node | 2/2。 |
| Chromium | 原版 E2E 8/8。16 张合成场景截图保存在本机忽略目录 test-results/m06-c1-browser。 |
| 冷启动及启动器 | 空库冷启动 3/3。原版 Windows .cmd 在中文及空格路径首次启动及同库重启均通过。回环 /api/health 返回 v7，首页和 /api/workspace 为 200，历史为空。两次停止均释放端口，Uvicorn 日志记录正常关闭。 |
| 归档 | 四份既有脱敏归档 4/4，证据条目 20、10、10、10，完整性均为 ok。 |
| 数据安全 | Git 暂存内容通过仓库敏感信息扫描。实测使用合成输入、隔离数据库及既有脱敏归档，真实研究 API 调用为 0。 |

Python 与 Chromium 由 Codex 在获准的普通 Windows 用户执行上下文中复跑。受限 Codex 会话中的 DPAPI CurrentUser 凭证写入可返回 HTTP 503。现有凭证保护保留。需手工复测时，在普通 Windows PowerShell 中执行以下命令。StarletteDeprecationWarning 是已登记的非阻塞性技术债。[既有环境限制记录](../pre-m06/windows10-closeout.md)

~~~powershell
Set-Location -LiteralPath 'C:\Users\kurik\Documents\Codex\VOC Workbench 研究'
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
$env:VOC_CHROMIUM = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
& .\.venv\Scripts\python.exe tests/browser_e2e.py --output test-results/m06-c1-browser
~~~

M06-C2 需负责人另行授权、通过验收的 C1 提交及现有 CorpusStore.qualified_record 与 GET /eligible 契约。Windows 11 实机为 NOT_TESTED，Windows 11 部署门禁和 G-1 均为 BLOCKED。专案 v2.2 的 27 页 PDF 原件仍缺失。[实施计划](../../architecture/m06-implementation-plan.md) · [正式验收矩阵](../../requirements-matrix.md)
