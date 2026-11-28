# G-1-PERSONAL 决策与 C 阶段交接

`EditionPolicy.decide` 接收实际操作、服务端运行域、经服务端核实的本机会话及当前项目/冻结范围检查，返回一个 `Decision`。结果包括实际版本、部署、操作者与负责人、项目、冻结范围、用途、权限、策略版本、门禁、状态、原因和受控授权引用。读或写入时用实际 SQLite 连接复核。历史结果只用于解释原决定。未知、过期、已归档、范围不一致的输入保持关闭。[运行方式](g1-personal-server-policy.md) · [个人最低准入](personal-research-gate.md)

| 运行域 | 当前 B 授权 | 后续绑定 |
|---|---|---|
| `local_workspace` | 已授权个人项目的精确本机操作 | 服务端当前授权、M05 隐私和来源留存规则 |
| `engineering_synthetic` | 走既有独立工程夹具和受控传输 | 合成身份、隔离库及 0 正式分母。校验数据必须保留合成来源 |
| `personal_pre_admission` | 关闭 | 独立验收授权、实际通道、账户、凭证版、模型、逐源许可、输入摘要、预算、时效、次数和批次 |
| `personal_formal_research` | `G-1-PERSONAL = NOT_EVALUATED` | C 审批、D 同批六项真实证据及 R 独立准入。全部条件在各执行点重验 |
| `business_formal_research` | 原 G-1 独立，现为 `BLOCKED` | 原商用准入、账户审核及同批证据继续适用 |

后续预约与队列应重读各自授权和来源，发送前核查预算与凭证版本。外部响应接收后保存真实用量，提交前在 SQLite 写事务内复核资格。未通过当前判定的响应只可留下受控审计。报告、历史回放、导出及发布按实际当前授权重验。应用不持有业务库写锁等待外部 HTTP。个人验证与合成账本无权产出正式编码或统计。

## G-1-P-C 接入与最小迁移草案

C 单独授权后在个人工作区的 SQLite v8 上测试下一可用 Schema 版本（当前建议 v9）。沿用原有迁移事务、原子性、一致性备份以及 `application_id` 绑定。采用追加式记录。原商用字段、诊断和材料继续独立。

| 拟建表 | 关键字段和约束 |
|---|---|
| `personal_provider_approval_events` | `event_id`、`kind`（提交、批准、撤销）、`prior_event_id`、`edition`（固定 PERSONAL）、`study_id`、`scope_id`、`scope_version`、`purpose`、`provider`、`channel_ref`、`model`、`account_ref`、`credential_revision`、`policy_version`、`actor_ref`、`owner_ref`、`authorization_ref`、生效时点与 UTC 到期、预算单位及限额、证据和允许的 UNKNOWN 项、请求摘要和幂等键。使用项目与冻结范围外键，按项目、通道、凭证版、用途和事件序列查当前决定。约束同一幂等键的单一请求并校验前件归属 |
| `personal_approval_evidence` | `event_id`、`evidence_ref`、`kind`、`sha256`、适用条款版及核对时点。仅保存受控引用和脱敏摘要，凭证及原始证明留在受保护的本机，不进入开放投影 |
| 当前有效投影 | 在同连接读操作与当前 UTC 下按追加事件派生。撤销后关闭当前决定，凭证、授权、有效期或依据改变后要求重新审核。D 的六项同批验收回执使用独立账本规范 |

拟用 `GET /api/personal/governance/{study_id}/approvals`、`POST …/approvals`，以及 `POST …/approvals/{id}/approve`、`POST …/approvals/{id}/revoke`。继续从现有可信会话取得实际操作者、Owner 及项目授权。为治理写入追加独立操作权限，同一事务内核对策略、冻结范围、当前授权及凭证版本。B 的状态仍不可通过配置提升。前端只使用脱敏状态、阻塞原因、证据引用、风险说明和期限。

测试覆盖项目越权、回复重放、事件不可变、旋转及撤销、日期边界、未知强制项、审查对象不一致、同连接并发、一致性备份恢复与真实计量为零。DPAPI 版本及 Windows 实机单独验证。保留 M06 五项政策、两条守恒等式和 `M06-B-F.1`。商用六项验收与历史结果继续保留原义。[治理计划](../planning/g1-personal-implementation-plan.md) · [冻结统计契约](m06-statistics-contract.md)
