# M06-C5 工程验收

## 基线及 C5-G 前置检查

开发分支 `codex/p0-0-connectivity` 从 `db0c2c86385950b6630a2691e1263d5dd429aa32` 接续，C4 实机验收源码为 `fce76a06195c7f45638c39b0347301fbb6bfbbae`。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45562948589) · [草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [C4 工程证据](../m06-c4/README.md)

**M06-C5_ENTRY_CHECK = PASS**。Windows 隔离源码归档的 C4 基线 Python 全量 247/247，耗时 115.578 秒，退出 0。独立探针批次通过 81/81，耗时 51.452 秒，退出 0，其中有 7 项新探针与 74 项 C2–C4 既有用例。两次运行的失败、错误和跳过均为 0。七项新探针覆盖：

1. C2 当前资格和写事务边界。
2. C3 稳定 M/E 坐标、实际证据依赖及人工审核。
3. C4 同证据交集、精确冻结版本、范围映射及无产品分支。
4. C4 内部完整切片与 HTTP 分页数差异、工程归属回执用途及正式模式空字段。
5. 当前精确读权限与证据自身资格分别判定。
6. 来源撤销和授权撤回后丢弃旧结果并重算。
7. 审计 tombstone 仅保留于治理投影，排除于有效发生快照。

## 实现及统计契约

| 位置 | 行为 |
| --- | --- |
| `src/raw_store/denominators.py` | 使用完整项目快照，复用 C4 关系、精确授权、冻结映射及 C2/M05 当前资格。计算分母、六桶、主类、排除账及两条恒等式。 |
| `src/raw_store/corpus.py`、`corpus_access.py`、`relations.py`、`store.py` | 为同一查询快照复用批量资格读和关系投影，保留逐条对照及 SQLite v7。 |
| `src/dashboard/relations_api.py`、`static/denominators.js`、`static/relations.js`、`static/app.css` | `GET /api/studies/{study_id}/denominators` 及中文「三层关系 → 分母对账」。复用本机回环、Host 检查、可信授权、`no-store` 与证据抽屉。 |
| `tests/test_m06_denominators.py`、`tests/relations_browser.py`、`scripts/benchmark_m06_denominators.py` | 合成反例、实际 Chromium 与本机 HTTP、批量和逐条 SQLite 路径比较及备份恢复。 |

- `counting_policy_version=M06-B-F.1`。每次统计回传项目、注册表、片段、冻结范围及映射、目录、统计模式、筛选和 UTC 判定时间。`index_version` 随选择回显。同维多选取并集，维间取交集。产品、来源、批次、时间和范围先在同一条当前合格 `evidence_id` 上求交，再按 distinct `mention_id` 计数。时间使用 UTC 半开区间，发布时间和采集时间各自匹配。
- 分母链分别计独立 URL、可访问页面、抽取候选输入、合格唯一发生及已发布已归类发生。M08 台账缺项返回 `null`。工程模式中 `N_published_classified` 为 `null`，覆盖说明为 `M12_RECEIPTS_MISSING`。隔离合成模式用显式回执核验六桶和已发布阶段，完整核验的空集合可返回 0，零分母的比例为 `null`。`G-1 = BLOCKED` 时正式模式为 `availability=unavailable`，带缺项原因、`counts=null` 和 `reconciliation=null`。
- 六桶依冻结优先级判定。实际分片或格式失败、失格输入、`Choice=None` 或独立 Noul、待人审、候选缺主类及完整发布条件分别核验，每个合格发生只落一桶。真实编码缺项与单次尝试缺分片各有原因。新授权后须显式复核或重编和重新检查发布状态。存在竞争决定时报告一致性故障。
- 排除账以切片内抽取候选输入计一次主因，可保留次因。未合法切片的整行按 `record_id` 单列。同一发生的代表在当前切片内确定，来源或批次并集重算重复数。无法核验筛选归属时报告覆盖缺项，并保持受限原话遮蔽。
- 两条对账分别比较 `N_eligible_dedup` 与六桶合计、`N_published_classified` 与主任务已发布数合计。次任务可关联下钻，已发布发生仍按唯一主类计数。任一已核对恒等式失衡会阻止发布资格，缺项保留为空。
- 长查询在完成后退出原读事务，再检查数据库变动、UTC 日期及当前授权。变动时丢弃旧结果并重新取快照，重复冲突返回可重试错误。证据抽屉重新检查当前资格和访问权。检查完成至发送响应间仍有自然时间窗口。

[冻结统计契约](../../architecture/m06-statistics-contract.md) · [API 契约](../../architecture/m06-api-contract.md) · [需求验收矩阵](../../requirements-matrix.md)

## 证据与关闭条件

| 材料 | 覆盖内容 |
| --- | --- |
| [C5-V 独立复审](independent-verification.md) | 隔离候选、独立手算、双连接和授权反例、缺陷记录及复测。 |
| [规模基准](scale-benchmark.md) | 1K、10K、100K 合成 SQLite 全链路、资格等价性、查询计划、资源观测、竞争及恢复。 |
| [Windows 11 脱敏清单](windows11-manifest.json) | 源码归档 SHA-256、20 项退出码、分组计数和四张合成截图哈希。 |
| [界面与截图](screenshots/README.md) | 工程与正式模式、当前证据抽屉、320/390 px 布局和脱敏图片哈希。 |

### Windows 11 实机和部署门禁

最终实测源码为 `a9eebee24616984dda8e72bab1242373555b06db`，20 组检查全部退出 0。`WINDOWS_11_REAL_MACHINE = PASS`，`WINDOWS_11_DEPLOYMENT_GATE = PASS`，覆盖该源码对应的本机工程部署。

原生 Windows 11 Enterprise 25H2，Build `26200.8655`，AMD64，非提升进程。PowerShell 7.6.9、Python 3.12.9、SQLite 3.45.3、Node 24.19.0、Playwright 1.65.2、Chromium 159.0.8154.6、Git 2.55.0.windows.5。用户选择 Sol Ultra，当前会话无法独立核验设置。开发、规模专项、独立复审和实机证据工作由主代理与三个协作子代理完成。

| 核验 | 实际结果 |
| --- | --- |
| Python 全量 | 269/269（247 既有、22 新增），237.756 秒，失败、错误和跳过均为 0。 |
| Python 专项复跑 | C5 22/22，C4 32/32，C3 25/25，C2 17/17，C1 33/33，M05 26/26，Pre-M06 16/16。各组已包含在全量数内。 |
| Node / 浏览器 / 本机 HTTP | Node 2/2，Chromium 11 组，本机 HTTP 2 组。 |
| 冷启动和历史档 | 3 次空库冷启动，4 份脱敏历史档经完整性核验，记录数分别为 20、10、10、10。 |
| 启动器与 SQLite | 普通、中文及含空格路径各首次启动及同库重启，共 6/6。三处 HTTP 入口返回 200，退出后端口释放，schema v7，`integrity_check=ok`，外键违规 0。 |
| DPAPI CurrentUser | 原生加解密、应用加密持久化、重启读取和删除后重启均通过。浏览器、服务响应、日志和运行文件均未出现合成明文标记。 |
| 敏感信息扫描 | Git 内容和暂存扫描退出 0。 |

一次中间候选的双启动器复测争用固定端口，测试端过早发出停止信号，打断了隔离目录依赖安装。最终候选在先确认端口空闲后完整复跑六轮，源码启动器沿用原实现。

### GitHub 交付

最终实测源码已快进同步到开发分支，Ubuntu、Windows Server 2022 和 Chromium 三项均通过。C5 前置、专项独立复审 A–T、三档规模及恢复、Windows 11 实机已完成，未解决 P0/P1 为 0。**M06-C5 = ENGINEERING_PASS** 在本验收提交的三项 CI 全部通过时生效。草稿 PR #1 保持开放。[源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45569514279) · [PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

## 后续消费契约

| 模块 | 接口及责任 |
| --- | --- |
| M07 | 消费精确 `registry_version` 下已封版的共享定义、主次任务边和版本索引。管理获准发行及精确版本，保留历史版的可追溯性。项目内原话、证据、计数和编码决定须走独立项目授权。 |
| M08 | 提供可核的发现 URL 与可访问页面台账，保留原始键、规范化依据、采集回执、来源和 UTC 采集窗口。C5 在台账缺失时保留 `null`。 |
| M12 | 以项目、稳定 `mention_id`、`evidence_id`、代表 `record_id`、实际原话区间及原帖或跨句上下文依赖绑定回执。固定片段版、注册表版、`index_version`、模型、题组、校准及回执版本，保留 `Choice` 与独立 Noul。依赖需满足当前授权、许可、资格和放行检查，编码完成或历史读取时也须复核。单条依赖失效会使原决定退出统计依据。 |
| M13 | 使用同切片、同版本、同排除账及两条恒等式的完整结果。发布与历史读取前核验当前授权、实际证据和回执依赖。条件变化时保留受控的旧版审计引用、标记失效并重算，保持失格原话遮蔽。 |

M06-R 等待负责人单独授权，M07 保持 `NOT_STARTED`。真实研究 API 调用为 0。真实语料、逐源许可、删除审计、真实 M12 编码与校准、完整 CAT/J-14 和正式报告分别按原标准验收。专案 v2.2 的 27 页原 PDF 缺失继续登记。
