# G-1-P-D 个人研究版同批验收准备

D-E Phase 0 复现了 v9 账本缺口。经负责人批准，Personal 工作库 v9→v10 受控迁移工程和 D 受限执行达到 **ENGINEERING_PASS**。以下将 D-E 历史证据和 D-L 当前进展分开记录。[Phase 0 复验与风险](phase-0.md) · [D-E 负责人批准](../../decisions/g1-p-d-e-v10-owner-approval.md) · [D-E 工程证据](engineering.md)

**G-1-P-D-L 真实执行 `BLOCKED`。** 隔离实现和 Windows 10 回归已交付，Windows 11 实机待验。正式批次尚未建立，实际部署库未操作。**G-1-P-D = BLOCKED，正式矩阵 0/6**。个人门禁 `NOT_EVALUATED`，商用 G-1 `BLOCKED`，R 及 M09–M15 `NOT_STARTED`。M06 冻结，I18N-PRE 为 `PLANNED`，核心路线图 39/79。[个人准入](../../architecture/personal-research-gate.md) · [D-L 工程证据](d-l-engineering.md) · [D-L 授权申请](d-l-authorization-draft.md)

## D-L 当前风险及核验

| 项目 | 当前状态及停机条件 |
| --- | --- |
| PackyCode/SystemOne 硬预算 | `BLOCKED`。缺少当前通道及版本可执行的逐请求最大输出证明及最坏费用上限。历史合成账单、限额余额与估算不证明逐请求硬限额。两片模型暂不开放。 |
| 独立批准和恢复连续性 | 隔离测试通过。实际 Owner 部署锚、冻结范围、政策、账户、通道、凭证、固定用途及 UTC 窗口待绑定。恢复旧库须与独立受信的撤销、发送和费用记录相符。未知发送保留预约并转人工对账。 |
| 四个请求槽位 | `PENDING`。按 Tavily、同一命中官方回源、PackyCode 8、PackyCode 3 的顺序批准。当前路径使用新批取证。跳转、补查余额、探针及自动重试不属于本批范围。 |
| 来源和数据边界 | `PENDING`。合法公开来源、逐源许可、最小脱敏内容及当前绑定待实际审批。内部资料、受限内容和工程夹具不能进入正式 D 外发与计数。 |
| 工程证据和实际部署 | 合成迁移、正式与合成隔离、恢复、接口及最终平台检查据实际日志登记。个人门禁 `NOT_EVALUATED`，实际部署库未操作。 |

真实研究供应商请求、供应商探针、账户或余额查询、真实研究 Token、新增研究费用、正式历史纳入及正式研究分母均为 0。

## D 准备阶段历史基线与阻塞

准备前的本机、远端和开放草稿 PR #2 均指向 `5106bb1098ebc706fb3429ba462cd5e82c55b169`，PR 目标为 `codex/p0-0-connectivity`。该提交的 Ubuntu、Windows Server 2022、Chromium 均通过。接续前工作区仅有已授权的八份 I18N-PRE 规划文档，已独立提交为 `0a5014f7d79d0612a94ba5074894e9a954c3a382`。I18N-PRE 为 `PLANNED`，在 M10 验收后另行授权，安排于 M11 前。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45762882859) · [草稿 PR](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2) · [规划授权](../../decisions/i18n-pre-owner-approval.md)

- **P1，D 执行阻塞。** 版本策略和工作台权限在治理操作之外关闭个人预准入。个人审批中心支持当前项目和冻结范围的审批、证据、凭证和撤销。预算材料保存整数 Token 上限。D 还缺受限执行入口及将单次请求、预算预约、幂等键、合格回执和对账结果绑定到验收批次的能力。旧验收与来源适配器继续受商用门禁和 PackyCode 原授权限制。[版本策略](../../../src/edition_policy.py) · [工作台权限](../../../src/dashboard/edition_access.py) · [个人审批](../../../src/dashboard/personal_governance.py) · [原验收入口](../../../src/execution/checks.py) · [来源发现](../../../src/ingestion/public_source.py)
- **P1，执行材料缺项。** 需核实实际账户 API 权利、精确通道、当前凭证版本、供应商条款与必要风险处置、逐源许可、脱敏输入、固定题组及金额、额度、次数和 UTC 窗口。C 阶段的审批需要与当前材料一致。恢复后材料撤销须有单调记录和恢复复核方案。[审批与风险](../../architecture/personal-approval-workflow.md) · [预准入契约](../../architecture/g1-personal-gate-contract.md)
- **P2，C 已登记。** 提交后的未绑定密文清理异常可返回 503。SQLite 当前锚已生效，旧密文无法再次用于审批，可重读当前状态。Windows 合成探针通过清理及旧密文重放阻断。此项继续登记，D 仍须以当前锚和撤销状态判定。[C 缺陷台账](../g1-p-c/bug-register.md)

本轮未发现新的 P0 或推翻 C 工程验收的缺陷。B 阶段的 P3 界面提示与个人 Windows 10 原始账本的本机复核继续独立登记。[B 缺陷台账](../g1-p-b/bug-register.md) · [历史费用](../g1-rb-f/README.md)

## 六项正式验收状态

以下状态属于个人 D 同批验收。C0-5 和 C0-6 的离线验证均已通过，后续在正式批次逐项纳入及复核。原商用矩阵保留其各项历史判定。[个人验收政策](../../architecture/personal-research-gate.md) · [原验收矩阵](../../requirements-matrix.md)

| 项目 | 本轮实际验证与证据 | 同批状态和缺口 |
| --- | --- | --- |
| C0-1 固定模型与分片 | 现行适配器及历史合成回执核对固定模型、11 题 8+3、唯一题号和完整合并。[适配器](../../../src/execution/jev.py) · [历史合成回执](../g1-rb-p/README.md) | **BLOCKED**。实际通道逐请求硬预算未证明。待实际公开原话获批、真实通道两片响应及同批证据。 |
| C0-2 三类响应 | 同一题组可载入 Choice、Score 和独立 Noul。离线和历史合成响应覆盖字段校验。Choice 每选项、Score 每档保留概率与 `confidence`，Noul 独立保留 `noul` 概率，缺项记 `schema_gap`。[校验器](../../../src/execution/jev.py) · [历史合成回执](../g1-rb-p/README.md) | **BLOCKED**。待同批真响应核验空结果、题号、档位与字段完整性。解析反例可离线复现。 |
| C0-3 搜索及原话 | 历史 Tavily 搜索与原帖回源归档通过完整性核验。本轮合规历史证据正式纳入数为 0。[历史链路](../p0-0/tavily-live/README.md) | **BLOCKED**。按新批核验当前用途、账户、许可、时间窗、同一命中和原话摘要。 |
| C0-4 计量和持久化 | 历史两片合成实扣有 CSV 旁证，当前 C 审批和诊断账本回归通过。[历史费用](../g1-rb-f/README.md) · [C 迁移](../g1-p-c/database-migration.md) | **BLOCKED**。待实际预算预约、供应商回执、逐次用量与费用、SQLite 重启回读、幂等与对账。 |
| C0-5 隔离与故障 | 36 个合成隐私用例均在传输前拦截，内部传输 0 次。六类故障返回预期状态。版本、项目、权限及已关闭真实入口回归通过。[离线夹具](../../../src/execution/checks.py) · [权限回归](../../../tests/test_edition_policy.py) | **BLOCKED**。离线工程通过。D 专用入口具备后复验预算不足、撤销、风险变化、无审计及重放，再纳入批次。 |
| C0-6 三层与全局召回 | 独立离线复验 2 品类、3 主任务、30 意图和 30 合成发生。两条跨品类探针均排全库 Top-12 首位。每条返回 12 个唯一稳定 ID 和 `None`；19 个已知加 `None` 允许，20 个已知拒绝。两次结果完全一致，孤立关系、外连和正式分母均为 0。[召回复验入口](../../../tests/test_connectivity.py) · [召回实现](../../../src/discovery/recall.py) | **BLOCKED**。离线冒烟通过，待正式批次引用固定注册表 `b031aa1275b8b2b6`、索引 `18e87696ba7bc015` 和脱敏结果。M12 的 J-14 及金标准独立验收。 |

## 真实调用申请与预算

全新顺利路径需 **4 次**。当前仓库历史在两次固定 `jev-1.14.0` 混合题组响应中验证了三种返回结构，独立 Noul 指独立题号。本轮无需为三种类型分别申请额外请求。题组冻结时登记实际候选 ID、定义和顺序，按任务要求准备 11 个已知候选加 `None`，同步定义守门问题，并独立登记 11 道判断题。既有合成默认 Choice 题仅有 2 个已知候选。第二片缺失、返回不符、许可变化、接口要求变动、额外余额查询或回源跳转均先停并核准调整，保留原审批和预约。

| 计划 | 供应商及用途 | 最小输入及预算基准 |
| --- | --- | --- |
| 1 次搜索 | Tavily，定位获准公开来源 | 批次批准的非敏感检索词和来源白名单。历史同类请求为 1 credit。当前账户适用计划、可用额度及金额待核。 |
| 1 次回源 | 同一命中的获许可页面或官方接口，验证原话 | 使用已复核 URL。所需网络操作、许可和可能费用依实际来源确认。 |
| 1 次模型首片 | PackyCode `typesafe-officially`，`jev-1.14.0`，前 8 题 | 单条经许可、脱敏原话，Choice、Score、守门 Noul 与另 5 道 Noul。历史合成 488 输入、162 输出，实扣 USD 0.000144。 |
| 1 次模型次片 | 同一账户、通道、模型和原话，余 3 题 | 最后 3 道 Noul。历史合成 321 输入、58 输出，实扣 USD 0.000094。 |

两片历史合成参考合计输入 809、输出 220、总计 1,029 Token，费用 USD 0.000238。历史费率为 USD 0.2940/百万输入 Token、输出免费。正式估算按审核后的两片输入和输出硬上限乘当前账户分项费率，再加搜索和回源费用。负责人核准请求、Token、金额上限及可用额度。当前 D-L 按全新四次取证计划，正式历史复用 **0**。[D-L 授权模板](d-l-authorization-draft.md) · [费用旁证](../g1-rb-f/README.md)

D-L 的实际费用上限和凭证绑定待正式批准。**实际请求 0，搜索 0，回源 0，模型 0，实际 Token 0，新增费用 USD 0。** 正式批次、预约和结算均为 0，账户余额查询 0 次。

实际执行前按契约绑定批次 ID、可信身份、版本、项目及冻结范围、用途、供应商、通道、账户、固定模型、凭证版本、批准输入和指纹、风险决议、审批引用、证据、UTC 有效期及预算。逐次检查权限和来源、预约并保存响应及用量。在外部请求结束后于本地写事务复核资格，对账和重启回读独立确认。扣费或结果不明时暂停，不增加调用。[批次契约](../../architecture/g1-personal-gate-contract.md) · [正式最低准入](../../architecture/personal-research-gate.md)

## 原生 Windows 11 离线证据

工程复验固定于 `5106bb1098ebc706fb3429ba462cd5e82c55b169`，从跟踪文件导出源码。原生 Windows 11 Build 26200 普通用户上下文，Python 3.12.9、Node 24.19.0、SQLite 3.45.3、Playwright 1.65.2、Chromium 159.0.8154.6。测试用合成凭证和隔离库。源码压缩包 SHA-256 为 `ab68257b6d54a20578a1d73907e43ae0d7cd7a83208ae9b0d9e0cba6b7cd66ef`。以下是源码工程回归结果。脱敏汇总可结合测试入口及 C 历史实机记录复核。[C 实机证据](../g1-p-c/windows11-results.md)

| 验证 | 结果 | 退出码 |
| --- | --- | ---: |
| Python unittest 全量 | 443 项，442 通过，0 失败，1 跳过，314.134 秒。跳过项 `test_no_unencrypted_production_fallback` 只适用于非 Windows 平台。 | 0 |
| Node | 2/2，0 失败，0 跳过。 | 0 |
| Chromium 全量 | 17 个隔离上下文，38 张合成截图。浏览器和 Python 外连尝试均为 0。 | 0 |
| 空库及原生启动器 | 空库 3/3。原有 `.cmd` 在普通、中文、带空格路径首次及同库重启共 6/6。HTTP 200、重启项目回读、停止及端口释放。探针退出 0，启动器接收终止信号后按预期退出 3。 | 0 |
| 凭证 | 原生 DPAPI CurrentUser 及 ACL 通过。长路径下保存、重启回读、轮换、删除及旧密文防重放。真实传输 0。 | 0 |
| SQLite | v8→v9 迁移专项 4/4，含 WAL 恢复、写入隔离、谱系和故障回滚。工作库重启 v9，`integrity_check = ok`，外键违规 0。 | 0 |
| 历史归档 | 四份脱敏求证归档完整性 4/4，另重跑归档恢复 6/6。仅用本地归档。 | 0 |
| 个人治理及隔离 | 审批状态及凭证绑定专项 10/10，版本与权限专项 27/27。C0-5 和 C0-6 离线用例通过。C0-6 独立定向 1/1，另执行两次确定性探针。专项与全量有重叠。 | 0 |
| M06 及商用门禁 | 全量覆盖关系、资格、分母与历史回读。商用 G-1 `BLOCKED`，个人门禁 `NOT_EVALUATED`。 | 0 |

I18N-PRE 提交通过 `git diff --cached --check`、相对链接和路线图顺序核对，以及仓库 `scripts/check-no-secrets.sh` 所含扫描。D 准备提交同样执行文档检查及该扫描。阶段交付对应远端提交及三项 CI 以草稿 PR #2 记录为准。[PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2/checks)

G-1-P-R 的接续前提是 D 的同批证据完整。D-L 须由负责人另行批准最终载荷、当前凭证、来源许可及可执行预算。个人准入由后续独立复审决定。
