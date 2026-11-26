# M06-C3 发生、证据及产品关系验收

开发基线为 `e64141b`，本轮最终功能源码为 `43c72026e1776f6b78b78beeb3d87b7126016924`，数据库为 SQLite v7。工程夹具经 M03 冻结研究范围、M04 本机导入和 M05 人工核验。测试使用临时数据库、合成目录和映射版本及获准历史归档。真实研究 API 调用为 **0**，正式阶段为 P0-0，G-1 为 **BLOCKED**，M06-C4 为 `NOT_STARTED`。[分阶段计划](../../architecture/m06-implementation-plan.md) · [冻结政策](../../architecture/m06-owner-approval.md)

## 负责人授权场景 A–Q

以下记录授权书 §13 的 C3 专测和独立探针。专测方法名省略 `test_` 前缀，独立复核使用共通合成夹具及另行编写的断言。每项专测及独立探针在清理前校验主库完整性和外键。各批运行的提交及平台见下方复验记录。

| 场景 | 实际合成输入与预期 | 实际结果及数据库状态 |
|---|---|---|
| A | 一条原话含离线和导出两个目的。预期各有一个发生和区间。 | 通过。拆为两个 M/E，修正第一处区间后保留其 M，第二处 M/E 保持。用例 `one_quote_supports_two_purposes_and_coordinate_correction_keeps_id`。 |
| B | 不同出处的两条同文评论进入同一 M05 组。预期两次独立发生。 | 通过。独立原帖分属不同 M，组内同文保留各自 E。用例 `equal_text_repost_and_disputed_identity_survive_dedupe_group_primary_change`。 |
| C | 原帖、具备合成审核依据的转载及各自许可。预期两 E 支持同一 M。 | 通过。原帖和转载分别保留 E，转载关联原帖精确区间。原帖依赖上下文失格时，转载读取也受限。用例 `equal_text_repost_and_disputed_identity_survive_dedupe_group_primary_change`、`repost_read_requires_its_originals_context`。 |
| D | 一个有效原帖及一个缺少定位依据的疑似转引。预期只挂起争议输入。 | 通过。争议 M 为 `needs_review`，可独立核实的 M 为 `distinct`。用例 `equal_text_repost_and_disputed_identity_survive_dedupe_group_primary_change`。 |
| E | 撤销 M05 原组主后保留合格成员。另以不同批次导入同一原帖和同一位置。预期组主迁移不改变幸存 M/E，同一原帖可同版保留两条原始 E。 | 通过。组主实际移动，幸存独立 M/E 可读。同源副本同版保留一个 M、两个 E，来源事件不一致时写入回滚。撤销一批后合格 E 仍可回读，拆分仍须登记旧支持的替代谱系。用例 `equal_text_repost_and_disputed_identity_survive_dedupe_group_primary_change`、`same_source_event_in_new_import_reuses_mention_but_has_an_independent_evidence_id`。 |
| F | 区间含 emoji 和分解形式的组合重音字符。预期原始半开码点坐标可回查。 | 通过。回读与 Python 原文切片相同，摘要错或区间越界使整版回滚。用例 `unicode_coordinates_replay_and_split_merge_keep_the_original_revision`、`invalid_digest_span_pending_or_foreign_source_rolls_back_revision`。 |
| G | 一个 M 拆为两个，再合为新 M。预期父版和替代谱系均在。 | 通过。连续封版，拆并使用新 M，精确的原始区间复用 E，旧版可回查。同键重放留原结果。用例 `unicode_coordinates_replay_and_split_merge_keep_the_original_revision`。 |
| H | 一条原话同时支持秤和炸锅。预期一个 M、一个 E、两条独立产品边。 | 通过。两边各写人工决定，暂停其中一边仍保留另一边决定，重放不追加记录。用例 `two_supported_products_have_independent_human_decisions_and_replay_once`。 |
| I | 一条仅能模糊指向产品的原话及错误比较关系。预期候选待核，人工有效决定才可生效。 | 通过。模糊候选为 `queued` 且 `effective=false`，将模糊或比较直接确认会拒绝。用例 `unresolved_mapping_and_ambiguous_edge_require_human_review`、`review_batch_rolls_back_when_any_edge_is_stale_ambiguous_or_repeated`。SQLite C1 约束同时拒绝 B 模式自动确认。 |
| J | 批量审核包含一条合格边和一条来源撤销的边。预期命令及两边均不追加。 | 通过。混合批回滚，只有合法子集重试才增加决定。独立探针在写入决定期间改变依赖资格并确认整笔回滚。用例 `review_batch_rechecks_withdrawn_support_and_retains_independent_edge`、独立 `governance_write_review`。 |
| K | 撤销一条边的证据，另有独立且仍合格的证据与决定。预期只遮蔽失格边。 | 通过。独立边持续有效。M05 明确新授权可恢复该 E 的本机读取，其旧产品决定维持无效，直至人工新审核。用例 `review_batch_rechecks_withdrawn_support_and_retains_independent_edge`、`regrant_requires_a_new_product_decision_and_leaves_independent_decision_active`、独立 `product_regrant_observations`。 |
| L | 撤销唯一支持，使封版成员失去全部原话资格。另撤销单独登记的上下文。预期历史和重放遮蔽。 | 通过。历史普通读省略失格 M，精确原话读和命令重放拒绝，既有引用保留，写入数量无变化。仅作上下文的 E 有独立区间记录，其撤销也遮蔽依赖原话。用例 `all_evidence_withdrawn_masks_history_and_command_replay`、`context_only_interval_is_persisted_and_its_withdrawal_masks_dependent_evidence`。 |
| M | 用一项目的 E 查询另一项目，或用错误的片段版引用。预期拒绝。 | 通过。返回 `KeyError`，与缺失对象一致。撤销重放授权后存储不变。双项目读授权的独立复核仍不能跨项目读同一 E。用例 `review_version_and_cross_project_support_are_checked`、`missing_authorization_and_revoked_replay_permission_leave_storage_unchanged`、独立 `project_isolation_with_dual_read_authority`。 |
| N | 两个目录版有同名异 ID 的节点，历史范围使用独立映射版。预期拒绝错 ID、错映射和目录组合。 | 通过。错误组合无记录残留，精确历史绑定可回查。独立探针额外使用两个 M03 冻结范围。用例 `product_proposal_uses_exact_frozen_scope_binding_and_catalog`、独立 `scope_isolation_for_same_named_catalog_products`。 |
| O | 已核定非产品的社区活动范围。预期开放需求仍可形成 M，产品边为空。 | 通过。保存发生，产品边和审核行均为零。虚构品类提议被拒。用例 `non_product_scope_has_occurrences_and_no_invented_product_edge`。 |
| P | 同键重放、异载荷、并发同父版、封版时悬空依赖、最终 COMMIT 延迟外键失败。预期最多一版，异常无部分残留。 | 通过。只留一版或回滚至原状态，修正后可用原键重试。用例 `replay_after_later_head_preserves_ids_and_rejects_changed_input`、`two_concurrent_revisions_from_same_head_create_one_version_and_one_command`、`seal_refuses_a_deferred_orphan_left_by_an_earlier_statement`、`failure_at_sqlite_final_commit_rolls_back_the_whole_command`、独立 `deferred_commit`。 |
| Q | 独立预检后撤销，持写锁时上下文或审核依赖失格，以及事务跨 UTC 日。预期 C2 复核阻断。 | 通过。无命令、边或中间的同事务治理变更残留。写后撤销对读快照的处理也通过。用例 `withdrawal_after_preflight_rejects_write_under_lock`、`context_withdrawal_inside_publication_rolls_back_supports_and_governance`、`utc_day_change_before_commit_rolls_back_even_when_lease_is_still_current`、`read_discards_an_older_wal_snapshot_when_withdrawal_commits`、独立 `governance_write_support` 和 `governance_write_review`。 |

独立探针对最终 SQLite COMMIT 失败、写支持及写决定过程中的资格变化、双项目读授权、同名目录的冻结范围隔离及许可重授权使用各自的事务和断言。在中间提交 `0fa4577` 的 Git 归档重跑，6/6，耗时 5.373 秒、退出码 0。重授权探针记录了撤销、取得新授权及重新确认的投影，仓库专测断言新授权后的产品决定有效性。

同源双证据反例在 `0fa4577` 首次失败，两个经 M05 核验的独立批次副本尝试挂到同一个 M 时触发 `ValueError`，原规则要求恰有一个原始支持。`43c7202` 允许经原始来源事件、区间、内容及上下文核对的同源副本同版并存，并用全部原始支持检查拆并谱系。本机开发专测复验 25/25。补强断言涵盖两个 E 对应一个稳定 M、不同事件回滚、撤销批次后幸存 E 可查，以及拆分涉及版中另一条历史支持时仍需登记谱系。

| 缺陷 | 复现及修复结果 |
|---|---|
| P1 移动后的延迟自引用外键 | SQLite 3.45.3 对受控复合外键移动漏报待提交的悬空项。封版前显式检查外键并拒绝提交，整版及命令回执均回滚。另有真实最终 COMMIT 失败和原键重试探针。 |
| P1 片段替代遗漏谱系 | 用两个新片段覆盖旧发生区间但未登记替代。按所有历史原始支持检查重叠拆并，缺边拒绝。旧版与已建立的 M/E 保留。 |
| P1 转载回读漏查原帖上下文 | 只撤销原帖语义依赖的另一区间，涉事转载曾可回查。读取与产品审核现通过精确原帖支持复核其上下文。 |
| P1 并发撤销与旧 WAL 读取快照 | 在读取快照建立之后提交撤销。用 SQLite 数据版本检查拦截在途旧投影，调用方可重试整次读取。 |
| P1 历史替代投影权限及产品边版本 | 撤销父版唯一支持后，当前版投影仍曾暴露父期发生引用。投影现在要求两端当前可见。产品投影补充精确的映射、规则和审核版次。 |
| P1 同源副本的版内证据丢失 | 两批次的同一经核事件被拒绝作为同版独立证据。上述回归及独立上下文副本探针通过。 |
| P2 来源地址类型 | 可核来源地址误投影为布尔值。当前资格通过后返回实际 URL，受限记录仍由资格机制拦截。 |

## C3 测试与架构反例

| 用例 | C3 断言 | 归属后续阶段的断言 |
|---|---|---|
| A01、A19、B01–B03 | 同文、同 M05 组的不同原帖仍各有稳定 M/E。组主移动后独立表达的身份保留。争议输入单列 `needs_review`，经过核实的转载挂到原表达及其原帖区间。 | 来源分层的待核率、六桶、同意图聚合归 C5/M12。 |
| A02、A20、B04 | 使用原文半开码点区间，原始摘要及字符完整。段界修正沿用符合条件的 M，切分和合并写入新 M，父版和 E 可回查。上下文产生 E 引用，并维持原发生数量。 | 浏览器中的三层下钻归 C4，多输入编码回执归 M12。 |
| A06–A08、B06–B09 | 原帖、转载、直接证据和使用的上下文分别按 M05 复核。撤销后历史版遮蔽相应证据，独立合格支持及边可继续使用。 | 同证据交叉过滤、旧报告重算、许可重新授权后的重新编码及发布归 C4/C5/M12/M13。 |
| A09、B09 | 当前项目读取需要可信授权。跨项目 E 和不存在的 E 使用相同的 `KeyError`；取得当前权限后仍逐次复核来源资格。 | HTTP 404 映射、六角色投影和跨项目专项授权归 C4/M11。 |
| A10、A15、A23、B16 | 边绑定同一 E 的冻结范围、精确映射版、目录版及产品 ID。版本回放保留旧引用，未解析与已确认非产品状态均单独报告。 | 目录节点治理和正式产品筛选的 `unavailable` 与零值归 C4/C5/M07。 |
| A14、B05 | 同一发生可持有多条产品边，每边有独立审核和当前决定。规则提议或待核状态不启用产品边，人工 A 模式确认后才可能生效。 | 跨产品并集按 M 去重，以及产品和意图双向分组归 C4/C5。 |
| A21、A22、B13、B14 | 当前资格检查、撤销、UTC 跨日、SQLite 最终提交失败和同版并发。相同命令重放保留已有引用，改变输入或提交过时预期版被拒绝；批中任一坏边使整批回滚。 | 三层联合封版及正式报告回放归 C4/M11/M13。 |

每个断言的合成输入及预期见专测，原反例编号和完整计数预期见冻结的验收矩阵。[专测代码](../../../tests/test_m06_mentions.py) · [架构验收矩阵](../../architecture/m06-test-plan.md) · [独立反例](../m06-b/counterexamples.md)

## 五项冻结政策

| 政策 | C3 实测 | 后续验收 |
|---|---|---|
| 1 表达身份 | 场景 A–G。区分独立原帖、同源副本、已核转载及争议输入。稳定 M/E 可用于后续去重。 | C5/M12 按来源和品类复核覆盖率、待核率及敏感性范围。 |
| 2 产品归属 | 场景 H–K。A 模式经人工权限和证据核验逐边确认。支持原子批审、暂停、撤销与新授权后重新确认。模糊候选待核，产品关系含冻结范围、目录、映射和规则版本。 | C4/M11 验证完整审核流程及按来源、规则定位影响集。B/C 生效另依冻结政策授权。 |
| 3 六桶与分母 | 场景 B–G、J–L。提供稳定 M/E、上下文及资格依赖，供同一证据交集和并集去重。 | C5/M12/M13 验证 `M06-B-F.1` 六桶、两个对账式、排除整行及未知覆盖。 |
| 4 跨项目与历史报告 | 场景 J–M、P–Q。项目级读写授权、历史及回放重新查资格。缺权与未知对象同形，真实失格影响所依赖的投影。 | C4/M11/M13 验证六角色 HTTP 投影、公共定义发布、历史报告和导出，登记分发、失效及撤回。 |
| 5 旧范围映射 | 场景 N–O。按 E 的冻结范围、映射版、目录版及产品 ID 解析，区分未解析与已核定非产品空集。 | C4/C5/M07 验证已发布节点和祖先保护、替代审核及正式视图 `unavailable` 与完整核验零值。 |

冻结依据和材料缺口沿用负责人裁定。专案 v2.2 的 27 页 PDF 原件仍待补齐，当前核对仓库专案摘要、需求验收矩阵和 PDT v1.3.1。[五项政策和材料缺口](../../architecture/m06-owner-approval.md) · [需求验收矩阵](../../requirements-matrix.md)

## 独立架构发现追踪

| 台账 | C3 实测及前置 | 后续验收 |
|---|---|---|
| B-F01 | 场景 M 验证项目接口边界和未授权错误，另有双项目读授权探针。 | C4/M11 验证全部角色、全局定义字段与自由文本、聚合和导出投影。 |
| B-F02 | C1 专测验证零主、双主、跨版、停用和封版约束。 | C4/M07/M11 联审及全局发行。 |
| B-F03 | 场景 M、N、P 验证复合键、同父版并发、单次幂等、不同载荷和最终回滚。 | C4 全局发行和跨层命令重放。 |
| B-F04 | C2 回归及场景 J–L、Q 验证当前资格、WAL、UTC、独立证据及明确新授权。 | C4/M12/M13 消费、发行和报告回放复验。 |
| B-F05 | 场景 B–G 验证同文独立、同源副本、已核转载、待核及版本谱系。 | C5 按来源与品类验证待核率及正式去重。 |
| B-F06 | 场景 H–K 验证实际产品指称、A 模式人工生效、原子批审及新授权重审。 | C4/M11 产品审核治理及影响集。 |
| B-F07 | 场景 C、J–L、Q 验证直接证据、原帖及上下文依赖随撤销退出。 | C5/M12/M13 验证正式输入回执、重编及发行。 |
| B-F08 | 场景 A–G、N–O 提供稳定 M/E、范围及依赖前提。 | C5 验证同证据交集、并集去重、六桶和双对账。 |
| B-F09 | 场景 K–M 验证缺权及真实失格的差异、旧版原话及仍有效的支持。 | C4/C5/M13 验证代表原话、历史报告、导出和分发。 |
| B-F10 | 场景 N–O 验证同名异 ID、冻结版本精确映射、未解析及非产品。 | C4/M07 验证已发布引用和祖先保护，C5 验证正式零值及不可用。 |
| B-F11 | C1 回归覆盖迁移备份和恢复。 | C5 按规模、版本史及真实资格路径复验性能。 |
| B-F12 | 场景 E 验证 `duplicate.canonical_record_id` 实际迁移及幸存 M/E 身份稳定。 | C5 验证正式统计对组主迁移的独立性。 |

[架构发现原始台账](../../audits/m06-architecture-findings.md)

## C4 内部调用契约

- `MentionStore(store, authorize=...)` 接收应用提供的可信项目授权函数。函数按 `study_id` 和 `read`、`segment`、`identity` 或 `product_review` 权限返回受控操作者引用。缺少读授权与未知对象使用 `KeyError`，缺少写授权使用 `PermissionError`，陈旧版本或已失格依赖使用 `Conflict`，语义无效输入使用 `ValueError`。完整角色管理与 HTTP 映射归 C4/M11。
- `publish_revision` 以项目、预期片段版、规则版和幂等键写入证据、成员、替代及产品提议并封版。M 表示可核的表达，E 表示项目内指定 M05 记录、摘要及区间。成功响应为版次与 ID。旧版固定 R，幂等结果在当前项目权限和依赖资格复核后返回。
- `read_revision(study_id, revision=None)` 返回封版 R、父版、规则版和当前可见 E。产品边含 `scope_id`、`mapping_revision`、`catalog_version`、`decision_seq`、`rule_version` 和 `effective`。替代关系仅在父版和当前版两端都可见时返回。分页、回查或报告应显式固定 R。`read_evidence` 接受同项目的 R/M/E，回传精确摘录、摘要、起止、批次和冻结范围版本，`research_eligible` 和 `outbound_allowed` 均为 `false`。所有投影按当前 M05 资格和 UTC 复核。
- `read_scope_mapping` 接受冻结范围及可选精确映射版和目录版。未登记范围映射得到 `unresolved`，经审核的非产品范围得到 `non_product`。产品查询依据同一 E 的冻结范围及原关系绑定的映射，跨版读取应携带历史版本引用。
- `review_products` 接收当前 R 和每条边的 M/E、目录版、产品 ID、映射版、预期审核序号及审核依据。每边只解析最新事件。A 模式人工确认须有权审定实际指称及现行 M05 依据，规则仅对提议和待核状态分流。决定引用绑定所用依赖的 M05 审核版本。新授权后旧产品决定仍待人工复核。

所有 C3 写入在 SQLite 主库 `BEGIN IMMEDIATE` 下复用 C2 同连接资格复核。直接证据、已核转载的原帖和登记的上下文一起查资格，并在离开写入范围前再次检查 UTC 日期。回放和展示也按当前权限及资格读取。C4 使用这些入口建立双向查询和权限投影，M07/M11 提供目录和审核工作流，C5/M12/M13 提供计数、编码及正式发布。[C3 实现](../../../src/raw_store/mentions.py) · [C2 事务证据](../m06-c2/README.md) · [API 契约](../../architecture/m06-api-contract.md)

## 复验记录

| 提交和环境 | 实际结果 |
|---|---|
| `e64141b`，C2 基线 Windows 本机 | Python 全量 190/190，72.449 秒，退出码 0。 |
| `0fa4577`，Windows 本机隔离源码 | Python 全量 215/215，131.209 秒。C3 25/25，29.395 秒。C2 17/17，C1 约束 22/22、迁移 11/11，M05 Corpus 16/16、许可 10/10，Pre-M06 A–H 16/16。八组均退出码 0。 |
| `0fa4577`，Windows 本机原生检查 | Node 2/2，Chromium 8/8，空库冷启动 3/3，历史归档 4/4，DPAPI `CurrentUser` 同库重启读删和敏感信息扫描均通过。四份归档记录 SQLite 完整性 `ok`。 |
| `0fa4577`，Windows 本机独立反例 | 六项事务、范围及重授权探针 6/6，5.373 秒，退出码 0。 |
| `43c7202`，Windows 11 隔离源码 | Python 全量 215/215（原有 190，新增 C3 25），117.835 秒。C3 25/25，C2 17/17，C1 约束 22/22、迁移 11/11，M05 Corpus 16/16、许可 10/10，Pre-M06 A–H 16/16。八组退出码均为 0，失败和跳过均为 0。 |
| `43c7202`，Windows 11 独立复审 | 6/6 独立事务、范围及重新授权探针（4.896 秒）。同源事件和上下文探针另有 4/4 断言通过。两条命令均退出 0。[独立复审输出](independent-verification.md) |
| `43c7202`，Windows 11 系统专项 | Node 2/2，Chromium 8/8，空库冷启动 3/3，历史归档 4/4，DPAPI CurrentUser 及敏感信息扫描通过。 |
| `43c7202`，Windows 11 启动器 | 普通、中文、空格三类路径各首次启动和同库重启，合计 6/6。首页、`/api/health`、`/api/workspace` 六次均返回 200。每次 SQLite schema v7、完整性 ok、外键 0 行。 |
| `43c7202`，GitHub Actions | Ubuntu 与 Windows Server 2022 的 Python 各 215/215，Node 各 2/2，空库冷启动各 3/3，历史归档各 4/4。Windows Server 2022 另跑原版启动器，Chromium 作业通过。Linux 工程回归取自 Ubuntu 作业。[源码基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45544903551) |

本机为 Windows 11 Enterprise 25H2 x64（26200.8655），PowerShell 7.6.9 非提权普通登录用户，Git 2.55.0.windows.5、Python 3.12.9、SQLite 3.45.3、Node.js 24.19.0、Playwright 1.65.2、Chromium 159.0.8154.6。DPAPI 原生往返、应用凭证密文存储、跨进程回读和删除后重启均通过。浏览器 DOM、存储、控制台、HTTP 响应、校验错误、应用日志及运行文件未检出合成凭证明文。四份脱敏历史归档证据数为 20、10、10、10，各归档完整性为 `ok`，G-1 均为 `BLOCKED`。

两次隔离原生运行使用的源码 ZIP SHA-256 均为 `fdd9087424ac95ed13fe42115b4fa10114a51362a6dfd05d1a96048f0fb84501`。每类路径用原版 `scripts/start-windows.cmd` 从干净目录创建环境并启动，依赖来自本机 wheelhouse。探针以 CTRL_BREAK 停止进程组，六份日志均显示 Uvicorn 正常关闭，端口可重新绑定。批处理均返回 3，探针退出码为 0。Node、Chromium、冷启动、四份归档、DPAPI 及 Git 绑定敏感信息扫描均退出 0，失败和跳过均为 0。

C3 专测及独立探针的 `PRAGMA integrity_check` 为 `ok`，`PRAGMA foreign_key_check` 为 0 行。SQLite v7 迁移复验包括历史 v1–v6、v6 活跃 WAL 一致性备份恢复并重迁移、双进程竞争、事务失败及中断重试。工作台、M01 合成及诊断库版本分别为 v7、v1、v1。测试使用独立库。Python 的 Starlette TestClient 弃用提示沿用既有技术债记录。

正式研究依然处于 P0-0。所需证据包括同一正式批次 C0-1 至 C0-6、适用供应商审查、至少三批真实来源和至少 100 条合格去重真实语义片段、逐源许可及物理清理和删除审计。专案 v2.2 的 27 页 PDF 原件待补，当前依据为库内摘要及已经确认的约束。[正式验收矩阵](../../requirements-matrix.md)

### 门禁判定

| 项目 | 当前判定 |
|---|---|
| M06-C3 | **ENGINEERING_PASS**。源码基线三项 CI 成功，C3 未解决 P0/P1 为 0。 |
| WINDOWS_11_REAL_MACHINE | **PASS** |
| WINDOWS_11_DEPLOYMENT_GATE | **PASS** |
| PRE_M06_DEVELOPMENT_GATE | **PASS** |
| G-1 | **BLOCKED** |
| M06-C4 | **NOT_STARTED**，等待负责人单独授权。 |

交付文档更新仅涉及 Markdown。验收基线按上述源码 SHA 查找，交付提交的 CI 可从草稿 PR #1 的检查页核对。[草稿 PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

### 复验命令

~~~sh
python -m unittest discover -s tests -p test_m06_mentions.py -v
bash scripts/smoke-test.sh
python tests/browser_e2e.py
for archive in docs/evidence/p0-0 docs/evidence/p0-0/regression docs/evidence/p0-0/api-setup/live-receipt docs/evidence/p0-0/tavily-live; do
  python -m src.outputs.audit_receipt --verify "$archive" || exit 1
done
~~~
