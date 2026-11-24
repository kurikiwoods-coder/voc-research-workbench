# M06-B 审核证据

输入为固定的 [M06-A 提交](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/48b5352feb72df852417d6c9edb96775896153a7)。三组审查分别覆盖数据库/许可、用户研究/统计、下游/规模，主审负责交叉复核和分级。真实研究 API 调用 0。

| 证据层级 | 材料 | 可以复核的范围 |
|---|---|---|
| DESIGN_CHECKED | [24 个原反例和 16 个新增反例](counterexamples.md) | 发生身份、证据、版本、事务、隐私及排除单位逐案手算，包含两条恒等式与后续可执行步骤。 |
| PROTOTYPE_TESTED | [事务与资格实验](sqlite-results.md) · [脚本](sqlite-probe.py) | 两个 SQLite 连接的受控操作、发行约束和现有资格规则的取证，覆盖范围以逐项记录为准。 |
| PROTOTYPE_TESTED | [第二产品品类脚本](category-probe.py) | 2026-11-24 主审以项目 Python 在内存 SQLite 实测。只插数据增加第二品类，两品类各回查相同的 2 个意图、2 个主任务；sqlite_schema 前后一致。撤销第二品类的一条证据只移除对应边，非产品范围继续有合法发生。正反查、外键、上述断言通过，退出码 0。简化许可标志仅用于关系验证，正式 CAT-6 工作台流程待验。 |
| PROTOTYPE_TESTED | [规模结果](scale-results.md) · [脚本](scale-probe.py) | 1,000/10,000/100,000 条合成来源行的多对多筛选、去重、分页、版本复制及备份恢复。 |
| IMPLEMENTATION_NOT_TESTED | [实施验收矩阵](../../architecture/m06-test-plan.md) | 正式 M06 持久化、接口、产品规则校准、全量资格路径并发及正式发布仍待实施验收。 |
| 历史独立证据 | [Windows 10 记录](../pre-m06/windows10-closeout.md) · [M06-A 基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45413664128) | 分列既有工作台验证、Windows Server CI 与本次原型。Windows 11 实机仍为 NOT_TESTED。 |

主审在同一 Windows 10 环境用项目 Python 3.12.14、SQLite 3.53.1 独立复跑规模脚本。88/871/8,689 条命中证据分别对应 76/746/7,444 个片段，三份备份通过完整性、外键和逻辑计数检查。10 万规模筛选中位数 15.151 ms，一次片段快照 493.827 ms，主库增量 9,216,000 B；首次实测见规模结果。时间随运行变化，计数及断言可复现。脚本只打开临时合成库。仓库业务代码、Schema、正式迁移和业务测试不在本轮差异内。

主审另行复跑 SQLite 事务与资格脚本，退出码 0。同源副本和独立来源的资格序列为 `200/200/200 → 409/409/200 → 409/409/409 → 200/409/409`。旧读事务仍能看到旧许可，把旧快照提升为写事务得到 `SQLITE_BUSY_SNAPSHOT`。写锁内把判定日推进一天后，最后一个独立来源也过期。新授权只恢复指定原话的工程资格。

[审核评语与原需求复核](../../audits/m06-architecture-review.md) · [问题台账](../../audits/m06-architecture-findings.md) · [决策与审核历史](../../architecture/m06-decisions.md) · [后续 M06-B-F 政策批准](../../architecture/m06-owner-approval.md)
