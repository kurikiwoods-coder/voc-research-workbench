# M06-C 分阶段实施与回归计划

状态为 NOT_STARTED。实施须独立授权。下列文件是未来改动范围，“拟新增”指计划路径。沿用 SQLite v6 输入、M03/M05 对外契约、六层职责与原验收矩阵。阶段验收使用隔离副本和合成夹具，保留输入版本、预期/实际、失败位置和恢复结果。正式研究另验。

| 阶段与依赖 | 文件范围 | 操作、失败注入与出场断言 | 回归 |
|---|---|---|---|
| M06-C1 数据库。输入为原 v6 与[数据模型](m06-data-model.md) | `src/raw_store/store.py`、`src/raw_store/migrations/` 下拟新增下一序号 SQL；拟新增 `tests/test_m06_migration.py` | 建立一致备份，空库、历史 v6（有旧范围和撤销记录）分别升级。逐连接启用 FK；验证单根、同项目/同版复合键、NULL 组合、不可变封版。模拟中途失败和重复启动，检 integrity_check、foreign_key_check、原 ID/行数/冻结内容不变。已提交后回退按停写、备份增量、恢复并核差。 | A04/10–12/20/22–23、B10/12/16；复跑已有冷启动和归档恢复。失败保留原 v6 副本，停止后续阶段。 |
| M06-C2 资格。依赖 C1 连接和事务 | `src/raw_store/corpus.py`、`corpus_access.py`（同目录）、`src/dashboard/corpus_api.py` 兼容检查；`tests/test_corpus_licenses.py`、`tests/test_pre_m06_audit.py` | 把同一资格逻辑供既有 Python/GET 和同连接写路径复用。两个 WAL 连接交错模拟预检后撤销、写后撤销、同源/同行副本受限、独立证据仍可用、单条重授权；跨 UTC 日回滚重算。GET 响应字段和 404/409 保持兼容，许可不明则停止消费。 | A07–09/21、B04/08–09/13–14；对照 M05-R2-V 资格序列，失效后重开/导出无旧原文。 |
| M06-C3 发生、证据及产品。依赖 C1/C2 | `src/raw_store/` 下拟新增 `mentions.py`，复用 `studies.py`、`corpus.py`；拟新增 `tests/test_m06_mentions.py` | 从合格 record_id 生成稳定 mention_id 与 evidence_id。以原文摘要和 Unicode 码点定区间，拆并留父版。确认独立/转载/争议三类夹具。按范围映射版取得确切产品；逐边留审核与单一当前决定。批中坏一边回滚，重试不产生第二次决定；B/C 自动生效关闭。 | A01–02/06–08/10/14–15/19–20/23、B01–05/09/16；验证换组主不换身份、非产品空集、同名目录及跨版回放。 |
| M06-C4 三层查询与事务。依赖 C1–C3 | 拟新增 `src/raw_store/relations.py`、`src/dashboard/relations_api.py`、`tests/test_m06_relations.py`；路由登记 `src/dashboard/app.py`，现有 `tests/browser_e2e.py` 为兼容入口 | 同版双向关系取同一组边，封版恰一有效主类。实现约束/预检，留 M07/M11 操作入口。用两项目和六角色检查字段、错误、计数、历史、回放、失效授权；并发写、断连及半发行失败应零残留，同键异载荷拒绝。缺可信授权时保持特权关闭。界面从筛选下钻到获准原话，撤销后重开。 | A03–05/09/11–12/16–17/21–24、B10–14/16；CAT-1/2/5/7/8/9 工程断言，联合确认完整流程另由 M07/M11 验收。 |
| M06-C5 对账与规模。依赖 C2–C4 | 拟新增 `src/raw_store/denominators.py`、`tests/test_m06_denominators.py`；复用拟议关系 API 与 `docs/evidence/m06-b/` 原型口径，M12/M13 作为消费者 | 同证据交叉后 distinct M，逐桶、逐主类、排除输入与未切整行分别对账。核准入缺失为 null，完整空集合 0，分母为 0 时比例 null。三档 1K/10K/100K 走完整 M05 路径，比较逐条/批量资格，留耗时分布、查询计划、锁等待、版本增长、WAL 和备份恢复证据。长统计中途撤销须废弃结果。两条恒等式任一不成立则拒绝发布。 | A01–03/06–08/13–18/21/23–24、B05–09/13–16；CAT-3/6/8/10。规模结果只与同夹具及口径版比较，未设无依据的性能阈值。 |

## 验收交接

每阶段以[反例逐案记录](../evidence/m06-b/counterexamples.md)的输入、预期和计数为基础，再执行[五项政策专项回归](m06-test-plan.md)及[问题台账](../audits/m06-architecture-findings.md)对应断言。C1–C5 可在工程或 synthetic 模式检验约束。需要 M08 采样、M11 人工联审、M12 实际回执/金标、M13 发布的部分分别交所属模块。C0-6 保留合成探针，CAT-4 的发现演练、CAT-9 的完整联审和 J-14 的真实独立盲测单独取证。
