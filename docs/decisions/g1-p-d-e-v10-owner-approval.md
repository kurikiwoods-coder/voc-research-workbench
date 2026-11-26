# G-1-P-D-E Personal SQLite v10 负责人批准

2026-11-26，项目负责人批准以 `37fc746177c8b7e911479f057ed78f6e0c8809ae` 为工程基线，接续 G-1-P-D-E。授权记录为《G-1-P-D-E-CONTINUE — Personal SQLite v10 受控迁移及预准入执行工程正式实施》。沿用 G-1-P-D 既有位置及核心路线图计数 39/79。[Phase 0 审计](../evidence/g1-p-d/phase-0.md) · [批准的设计](../architecture/g1-personal-pre-admission-design.md) · [基线 PR](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2)

| 批准事项 | 工程边界 |
| --- | --- |
| Personal 工作库 SQLite v9→v10 | 追加迁移 010。可信 `application_id`、Edition 及库用途前置校验，DDL 与版本号在同一事务提交。保留 v9 历史、稳定 ID、C 阶段 PackyCode 旧审批和凭证锚的读取语义。Business 工作库目标 v9，两版诊断及合成契约库目标 v1。 |
| 受限执行与同批账本 | `personal_pre_admission`、逐操作授权、预算预约、唯一发送权、回执、对账、恢复和 C0 六项证据，接入现有个人审批中心。复用原 Jev、Tavily、回源及当前用户 DPAPI。搜索、回源和模型分别绑定实际账户、通道、凭证版本、用途及许可。 |
| 隔离验收 | 使用合成夹具、受控测试副本和隔离传输替身。验证 WAL 一致性备份、失败回滚、旧客户端拒绝写入、重启、并发、撤销连续性与 v9 兼容。实际部署库须在核验归属、位置、备份及使用情况后取得对应部署授权。 |
| 冻结与正式门禁 | M06 三层结构、统计口径和模型校准标准维持冻结。Personal 正式门禁为 `NOT_EVALUATED`，Business G-1 为 `BLOCKED`。正式研究分母新增为 0。 |
| 外部执行 | 本轮真实供应商请求、探针、余额查询和新增供应商费用上限均为 0。G-1-P-D-L 实证执行须由负责人另行书面批准。 |

工程通过须有 Windows 11 实机回归、专项安全测试、敏感信息扫描及最终 GitHub SHA 的三项 CI。阶段状态以实测证据为准。[工程证据](../evidence/g1-p-d/README.md) · [D-L 申请草案](../evidence/g1-p-d/d-l-authorization-draft.md)
