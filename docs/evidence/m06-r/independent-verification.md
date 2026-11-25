# M06-R 独立验证

复审从开发分支 `7b26d8da89db636c7e3f4ad73490b53dcc555155` 开始。基线在原生 Windows 11 执行 Python 269/269 和 Node 2/2，退出码均为 0。下表定义每项反例的证据和预期。最终源码测试及状态见[实机验收](README.md)。

每个 Python 用例使用临时 SQLite。全链路用例经 M03 项目、M04 导入、M05 审核和 C3 封版入口建立素材，经现有 C4 读取及 C5 统计入口验证。只有隔离合成测试允许注入未来 M12 回执。正式模式须保持 `counts: null`。

| # | 反例 | 执行证据及预期 |
|---|---|---|
| 1 | 一条原话产生多个发生 | C3 Unicode 区间及 C5 `test_a_one_quote_two_occurrences_and_b_multiple_supports`，保留独立发生 ID。 |
| 2 | 不同来源的独立同文表达 | M04→M05 独立来源导入及 C5 `test_c_independent_same_text_and_d_repost_union`，可分别审核和计数。 |
| 3 | 同一发生的多个来源 | C5 用例 A/B，同一 `mention_id` 计一次并保留证据来源。 |
| 4 | 原帖与转载 | C3 `test_repost_read_requires_its_originals_context` 和 C5 用例 C/D，转载保留实际原帖依赖。 |
| 5 | 产品、来源、批次、时间和范围交集 | C5 `test_e_product_union_and_f_no_cross_evidence_matching` 与 localhost 统计接口，跨证据拼接结果为零。 |
| 6 | 多产品并集 | C5 用例 E/F，同一发生只计一次。 |
| 7 | 唯一主任务及次任务 | C1 的双主边约束及 C5 `test_g_secondary_task_filter_accounts_under_the_primary`，次任务筛选只在主类记账。 |
| 8 | 未确认候选与确认意图 | C4 候选保存与预检及 C5 `test_only_an_active_candidate_missing_a_primary_is_pending_parent`，候选保留缺父状态。 |
| 9 | 撤销关系及统计 | C4 `test_current_revocation_masks_old_witness_and_leaves_independent_product` 及新增双项目对账，受限证据退出。 |
| 10 | 只撤销编码上下文 | C5 `test_m_revoke_only_encoding_context_preserves_independent_occurrence`，发生保留，旧编码退出。 |
| 11 | 再授权发布状态 | C3 `test_regrant_requires_a_new_product_decision_and_leaves_independent_decision_active` 及 C5 上下文依赖回归，旧结论需重审。 |
| 12 | 历史版当前资格 | C5 用例 P 及新增双项目对账，旧版按当前许可核算。 |
| 13 | 用户授权撤回及来源撤销 | C5 `test_n_source_revocation_mid_query_and_o_grant_withdrawal` 分别重算和拒绝。 |
| 14 | 跨项目访问及计数 | C2 跨项目投影及新增双项目对账，只统计所授权项目。 |
| 15 | 隐藏版、片段及证据 | C4 新增精确版本授权回归，及 C4 隐藏谱系、C5 隐藏编码依赖和正式查询回归。 |
| 16 | 同键异载荷及旧重放 | C4 `test_lost_response_replay_changed_payload_and_revoked_sources`，核对幂等和当前授权。 |
| 17 | 写入并发及版本竞争 | C4 `test_two_writers_competing_for_the_same_parent_leave_one_sealed_version`，只有一个版本封存。 |
| 18 | 最终提交失败 | C4 `test_final_sqlite_commit_failure_rolls_back_and_leaves_key_retryable`，整项回滚且键可重试。 |
| 19 | 统计中途变更 | C5 用例 N/O 覆盖逐条路径。默认批量路径由 `test_batch_query_rechecks_source_revocation_and_exact_read_grant` 覆盖来源撤销和读授权收窄，`test_long_query_rechecks_utc_retention_after_midnight` 覆盖 UTC 跨日。 |
| 20 | 两条恒等式 | C5 `test_s_accounting_difference_blocks_publication` 和 `test_s_missing_bucket_entry_blocks_publication` 分别使主类合计和六桶合计失衡，均验证阻止发布。 |
| 21 | 缺失、未准入、空集及零分母 | C5 用例 K/L，缺失或未准入给 `null`，有效空集给零，零分母比例为 `null`。 |
| 22 | 审计 tombstone | C4 精确审计投影与 C5 历史撤销对账，遮蔽记录只保留审计所需字段，六桶不纳入失格发生。 |
| 23 | 非产品与映射未解析 | C4 Chromium 范围场景及 C5 用例 Q，分别返回有效空关系和不可用。 |
| 24 | 浏览器重新下钻 | C4/C5 Chromium 聚焦、证据抽屉和撤销场景，旧摘录清除。 |
| 25 | G-1 正式能力关闭 | M01 外发隔离、M02 本机诊断和 C4/C5 正式模式验证。正式统计保持不可用，合成回执不能成为正式编码，研究资料未经准入不得外发。已获准的 P0-0 诊断仍按原规则核验。 |

## 双项目手算账

新增 `test_two_project_ledgers_reconcile_independently_across_history_and_withdrawal`。项目甲导入三条独立原话。第一版唯一合成已发布回执归入主任务，六桶依固定顺序为 `(1,0,0,0,0,2)`。第二版无该版回执，六桶为 `(0,0,0,0,0,3)`。甲项目撤销第一条来源批次后，第一版保留 3 条已抽取候选，合格减为 2，发布减为 0，许可排除增加 1。项目乙的独立同源记录持续为 1 条合格且无发布。用例将这些字面期望、主类和两条差值同生产输出相比，并检查项目间不出现对方 ID。
