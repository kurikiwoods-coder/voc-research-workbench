# 个人供应商审批中心契约

在个人版「版本与研究准入」中选择获准项目后进入审批中心。用浏览器原生 Owner 登录框核验身份。可信启动授权按需配置 `read_personal_approvals`、`write_personal_approvals` 和 `manage_personal_credentials`。继续使用 B 的项目、冻结范围和个人研究用途。商用及云模式拒绝这些接口。

| 操作 | 入口 |
| --- | --- |
| 查看审批、缺项和准备用量 | `GET /api/personal/governance/{study_id}/approvals` |
| 提交申请 | `POST …/approvals` |
| 核准或撤销当前事件 | `POST …/approvals/{event_id}/approve` 或 `/revoke` |
| 维护当前冻结范围的凭证 | `PUT` 或 `DELETE …/credential` |

先验证权限，再查同范围对象。申请选择实际供应商、模型、通道及账户引用，登记 UTC 到期时间、整数 Token 上限、材料引用及可接受的 UNKNOWN 风险。风险记录保存未知原因、影响、保护措施、Owner 责任引用、到期和复核引用。重放按当前授权返回原事件的当前状态，换载荷使用新请求键。确认及撤销均选择当前事件版本。待申请可补齐材料后以新申请复核。更换同一账户、通道和模型的有效审批前，明确撤销前次审批。

## 本机证据登记

个人受保护工作目录中的 `personal-approval-registry.json` 由可信本机人员登记并原子替换。服务端从当前文件逐次核对。浏览器选择已登记材料的安全引用。文件存 JSON 对象数组，每条包括 `study_id`、`scope_id`、`scope_version`、`purpose`、`provider`、`channel_ref`、`account_ref`、`model`、`credential_revision`、`evidence_ref`、`kind`、`status`、`sha256`、`terms_version`、`verified_at` 和 `expires_at`。从当前本机 SQLite 的 `personal_credential_binding` 只读取得该范围的凭证版本。只保存材料摘要和引用，原件保留在获准本机环境。浏览器不会收到摘要、原始材料、密钥或凭证版本。失效材料在同一受信登记中标为 `REVOKED`。

强制材料对应六类记录：账户 API 权利、实际供应商条款、逐源许可、数据隔离及脱敏、预算计量、当前项目用途授权。预算记录另含 `budget_unit`（固定为 `TOKENS`）及 `budget_limit`。人工审查必须核验真实原件后才能登记 `VERIFIED`。未知、禁止、过期、凭证变化或证据摘要变化会阻断批准或导致原审批失效。权威审查标入 `mandatory_risks` 的未解决条件须先补证及更新；仅余六类非强制未知可登记风险接受。现有 PackyCode 真实账户审批仍待实际材料。

## 事务、迁移和恢复

SQLite v9 在 v8 基础上追加审批事件、证据快照及个人凭证版本锚。个人工作库使用既有 application_id，商用工作库读取旧数据，个人写入仍受版本域限制。诊断库和合成契约库继续为 v1。追加式历史不可更新、删除或替换。证据快照按事件声明的成员数量封存。

审批写入以同一个 `BEGIN IMMEDIATE` 核对可信授权、准确作用域、当前凭证、请求版次及材料后追加事件，提交前再复核授权。个人凭证按项目和冻结范围使用 Windows DPAPI CurrentUser，各版本先写加密文件再提交 SQLite 当前锚。中断只会留下未绑定密文，后续获准凭证维护清理过时版本。审批和撤销无需等待外部请求。撤销可以在当前凭证或证据不可读时完成。审批状态投影仅反映当次读取条件，未来 D/R 每次使用前重新核验。

## 后续真实验证准备

D 须经负责人单独授权。准备真实账户及当前 DPAPI 凭证、实际通道和固定模型、逐源许可与脱敏最小输入、可核的计费单位与预算、审批到期和撤销口径，以及同一批次六项的预期结果和真实计量记录。沿用同批 8+3 分片口径。正式最小请求数和预算由 D 根据实际通道与六项方案核定。本轮请求为 0。个人预准入和正式研究保持关闭，商用 G-1 BLOCKED，G-1-PERSONAL NOT_EVALUATED。
