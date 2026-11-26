# G-1-P-D-E 受限执行工程验收

2026-11-26 从 `37fc746177c8b7e911479f057ed78f6e0c8809ae` 接续，使用 `codex/g1-personal-phase-1` 及草稿 PR #2。运行候选源码为 `bac46aa0f7289e086b3f6c6651e71f185f471a76`。当前 D-E 为 `BLOCKED`，D-L 尚未就绪，D 正式同批为 `BLOCKED`。实际部署库未迁移。个人研究门禁为 `NOT_EVALUATED`，商用 G-1 为 `BLOCKED`。[负责人批准](../../decisions/g1-p-d-e-v10-owner-approval.md) · [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45779232960) · [候选交付检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2/checks)

## 原生 Windows 11 工程证据

使用 Windows 11 Enterprise Build 26200、Python 3.12.9、合成凭证及隔离应用数据库。专项数字与全量用例有重叠，各项退出码均按实际执行登记。

| 检查 | 结果 |
| --- | --- |
| Personal v9→v10 | 7 项迁移测试通过，退出 0。覆盖全表历史对照、稳定 ID、重复启动、双进程迁移、DDL 故障和提交前进程中止。活动 WAL 一致性备份可独立读回及恢复。完整性检查 `ok`，外键违规 0。 |
| 工作库角色隔离 | Personal 工作库 v10、Business v9，两个诊断库与两个合成契约库均 v1。历史 `37fc746` 客户端重开 v10 文件时拒绝，写入哨兵缺失。实际部署如获批准，须先停止旧客户端。 |
| 账本与恢复 | 13/13，退出 0。含线程发送竞争、跨批次共享额度、回执冲突、撤销、恢复后的原子资格以及实际旧 v10 备份回放。重放复现旧预约及旧审批表象，原会话和重启会话均拒绝发送。复核撤销旧批次和绑定，无法证明未发送的请求转入对账并保留预约。 |
| 原生 DPAPI | D 操作绑定专项 6/6，退出 0。覆盖跨操作和跨范围、撤销、轮换、C 当前锚、匿名回源绑定与 DPAPI 故障。C 清理 503 反例 1/1，旧密文仍存在时新锚有效，旧材料 HTTP 409，D 读旧锚被拒。 |
| 执行与权限 | 12/12，退出 0，其中 7 个执行用例与 5 个路由用例。包含同一命中合成回源及固定模型 8+3、11 已知候选加 None、逐片和跨片预算、过期来源、跨项目权限、响应后撤销、越界跳转、写入故障与未知结局。成功链 4 次合成传输。 |
| 浏览器 | Windows 11 Chromium 全量及审批桌面和移动专项均退出 0，分别生成 38 与 2 张合成截图。实际 D 读取、暂停与撤销通过，界面刷新在数据读完后开放交互，凭证删除确认实际 HTTP 响应。 |
| 启动 | 空库冷启动 3/3，Node 2/2，退出 0。候选早期源码的普通、中文、含空格路径首次及同库重启 6/6，SQLite v10、完整性 `ok`、外键违规 0、受权项目读回与端口释放。探针退出 0，正常终止后启动器退出 3。 |
| 全量与交付 | 最终源码的 Windows Python 全量、归档核验与三项 CI 以发布验证结果为准。 |
| 请求和费用 | 真实研究供应商请求、探针、账户查询、研究 Token 与新增费用为 0。正式研究分母新增为 0，未放行统计继续 `unavailable/null`。 |

源码与证据入口。[迁移测试](../../../tests/test_pre_admission_migration.py) · [账本测试](../../../tests/test_personal_validation_ledger.py) · [凭证测试](../../../tests/test_personal_validation_credentials.py) · [执行测试](../../../tests/test_personal_admission.py) · [路由测试](../../../tests/test_personal_admission_routes.py) · [浏览器测试](../../../tests/personal_governance_browser.py)

## 缺陷与风险

| 状态 | 事项 |
| --- | --- |
| P1 已修复并通过恢复专项 | 恢复较早 SQLite 快照可能使已撤销的历史批次重新显示为已批准。工程入口现在校验进程见证的批次、文件标识及追加账本，缺少连续性即关闭旧发送权。真实执行须另由受信证据核对授权、凭证、请求和费用连续性。 |
| P1 出场验证 | 受限入口、预算预约、回执和对账已通过专项。完整出场检查以 Windows 11 全量与最终提交的 CI 为准。 |
| P2 继续跟踪 | C 凭证锚提交后旧密文清理可能返回 503。D 回归通过旧密文重放阻断，清理失败仍需跟踪。 |
| P3 继续跟踪 | B 阶段 PB-08 界面提示。 |
| D-L 业务前置 | 实际账户 API 权利、精确通道、当前凭证、条款、逐源许可、最终载荷、硬预算和 UTC 窗口待审批。历史证据可分类登记，确认其当前资格并接入受信父回执后才可走减少请求的路径。 |

C0-1 至 C0-6 支持同批关联，工程夹具、离线回归、历史审核及缺项分开登记。六项正式状态保持 `BLOCKED`，C0-5 与 C0-6 沿用离线证据。M06 保持 `FROZEN`，R 与 M09–M15 为 `NOT_STARTED`，I18N-PRE 为 `PLANNED`，核心路线图 39/79。[六项矩阵](README.md#六项正式验收状态) · [C 缺陷台账](../g1-p-c/bug-register.md) · [D-L 申请草案](d-l-authorization-draft.md)
