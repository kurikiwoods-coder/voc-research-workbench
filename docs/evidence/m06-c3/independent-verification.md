# M06-C3 独立合成复测

提交 `43c72026e1776f6b78b78beeb3d87b7126016924`。通过 Git ZIP 注释确认导出内容属于该提交。
Windows 11 Enterprise 25H2（系统版本内核号 10.0.26200），Python 3.12.9，SQLite 3.45.3。
使用原工作区已安装的虚拟环境解释器运行归档副本中的源码及项目夹具。
测试库为独立临时 SQLite，输入仅为合成样本，真实研究 API 调用为 0。

| 命令 | 退出码 |
|---|---:|
| `git archive --format=zip -o <scratch>/43c7202.zip 43c72026e1776f6b78b78beeb3d87b7126016924` | 0 |
| `python -c '<verify ZIP comment and extract with zipfile>'` | 0 |
| `<repo>/.venv/Scripts/python.exe <scratch>/m06_c3_independent_gate.py` | 0 |
| `<repo>/.venv/Scripts/python.exe <scratch>/m06_c3_same_event_context.py` | 0 |

## 实测结果

- 六项独立探针通过。实际 SQLite 延迟外键使最终 COMMIT 失败，跟踪记录显示显式回滚。命令、片段、证据、产品及故障夹具写入均回滚，同键重试只提交一个版本。
- 在同一写连接中撤销依赖上下文或撤销待审产品的来源批次，两种情况均整笔回滚，同键重试通过。
- 同时持有两个项目读权限仍无法用其中一个项目的成员或证据 ID 查询另一个项目。旧、新冻结范围只认可各自映射和目录版中的确切产品 ID，同名产品不能跨版或跨范围替代。
- 来源撤销后隐藏原文和关联，重新授权恢复当前可读原文。旧产品确认保持失效，须经新的人工确认。另一条独立产品关系始终有效。
- 同一来源事件、原文区间和上下文的两个批次副本可在一版共享发生 ID，各自留证和逐边确认。上下文区间差异会拒绝。撤销首批后只保留第二批证据及产品边。用留存副本拆分时必须提供两条谱系，符合后通过完整性与外键检查。

## 终端摘要

```text
m06_c3_independent_gate.py
test_deferred_commit (__main__.IndependentGate.test_deferred_commit) ... ok
test_governance_write_support (__main__.IndependentGate.test_governance_write_support) ... ok
test_governance_write_review (__main__.IndependentGate.test_governance_write_review) ... ok
test_project_isolation_with_dual_read_authority (__main__.IndependentGate.test_project_isolation_with_dual_read_authority) ... ok
test_scope_isolation_for_same_named_catalog_products (__main__.IndependentGate.test_scope_isolation_for_same_named_catalog_products) ... ok
test_product_regrant_observations (__main__.IndependentGate.test_product_regrant_observations) ... ok
Ran 6 tests in 4.896s
OK
m06_c3_same_event_context.py
PASS context intervals must match
PASS same-event and context aliases keep two evidence IDs and two effective edges under one occurrence
PASS batch revocation masks its evidence and edge while preserving the independent copy
PASS split on the surviving copy requires both lineage links. SQLite integrity and FK checks pass
```
