# M08 向 M09 的原话及证据接续

M08 任务绑定 `study_id`、精确 `scope_id` 和 `scope_version`，保存冻结查询、来源、时间窗、适配器和抽取规则。以 `acquisition_task_id → request_id → batch_id → record_id` 追溯发现、回源、质量检查和 M05 记录。来源定位包括平台、对象类型、稳定对象 ID、规范 URL、精确定位、发布时间、采集时间、许可与署名。正文摘要和 `[start_cp, end_cp)` 使用当前 M05 快照及 M06 Unicode 码点规则。

| 使用场景 | 权威读取 |
| --- | --- |
| 本轮合成工程回查 | `GET /api/acquisition/{study_id}/tasks/{task_id}/evidence/{index}` 重验冻结范围、当前来源授权和 M05 快照。回执含精确 `record_id`、`batch_id`、摘要、码点区间及 `role=synthetic`。 |
| 获准的本机原话输入 | 在可信项目授权下调用 `CorpusStore.qualified_record(study_id, record_id)`。以返回的当前角色、许可、快照摘要和冻结范围为准。 |
| 已登记的精确 M/E | 使用 `MentionStore.read_evidence(study_id, segment_revision, mention_id, evidence_id)`。核对该返回的 `scope_id`、`scope_version`、`batch_id`、`record_id`、`raw_sha256` 及区间，失格的证据和上下文随当前资格拒绝。 |
| 需使用注册表定义 | 另以精确封版 `registry_version` 读取 `RegistryVersions.consumer`。引用实际消费版本，不以最新版覆盖历史。 |

合成回查提供片段定位证据，M05 正式和外发资格均为 false，`mention_id`、`evidence_id`、`segment_revision`、`registry_version` 为 `null`。真实原话获得权限后从现有 M05/M06 权威入口读取 M/E 标识。M08 不实施主题聚类、开放编码、注册表发行及意图或任务大类分配。历史审核状态、重复 URL、同文摘要、便捷样本量都不能证明当前资格或同一发生。

M09 引用需保留来源、采样时间窗、内容角色、当前资格和完整版本绑定。M09 隔离工程按现有授权继续。正式研究须通过适用的个人或商用门禁，正式数据须有实际来源和用途审批。正式漏斗遵循 M06-B-F.1、六桶及两条守恒等式。[研究优先 ADR](../decisions/product-realignment-v1-owner-approval.md) · [个人准入](personal-research-gate.md)合成分片与旧 PackyCode 预检回执各自归档。

[采样任务契约](m08-acquisition-task-contract.md) · [平台回源契约](m08-platform-retrieval-contract.md) · [M06 消费交接](m06-consumer-handover.md) · [统计冻结契约](m06-statistics-contract.md) · [M07 版本契约](m07-versioning-contract.md)
