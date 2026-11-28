# G-1-P-D-L 隔离工程证据与部署前核验

以 `bfd0af65b8807268ebafad5b053a3c32a6ee963e` 接续。工程源码 `32011552dce73f03d732843cc98d69f61ce6ccb8`。Personal 分支继续由草稿 PR #2 交接。[D-E 基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45800882085) · [Personal PR #2](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2)

**G-1-P-D-L 工程已交付隔离实现，正式执行 BLOCKED。** 六项正式同批为 **0/6**。未建立实际批次和正式凭证绑定。实际供应商请求、余额查询、费用、历史证据正式复用及新增正式分母均为 0。

2026-11-27 对 `6d70cd5011a249c83bf6c9df15f3900c2f595994` 补验 Windows 11，定向套件 70/70、原生 DPAPI 3/3。负责人已批准新建独立工作区。Personal v11、Owner provision、当前用户 DACL、一致性备份、新目录恢复及重启回读均验证通过。实际历史库保持未操作。正式批次仍需独立恢复连续性、逐项授权及模型硬预算证明。[Windows 11 与部署证据](d-l-windows11-deployment.md)

## 实现与边界

- Personal 专库通过事务迁移 011 达 v11，保留 v9/v10 数据、稳定 ID、历史批准、撤销及合成记录。Business v9，诊断及合成契约库 v1。SQLite Backup API 包含可见 WAL，恢复使用新目录及独立副本。工程验证覆盖并发升级、故障回滚和完整性核验。
- 受信本机 Owner 命令默认关闭。独立 DPAPI 档案和同库授权锚共同绑定 Owner 验证配置、项目授权、工作库及授权目录文件身份。负责人须先确认实际 Windows 用户、目录 ACL、库与备份，再执行 `provision`。同一受信 Windows 用户能控制本机程序与文件，部署验收须核查目标目录和账户归属。
- 固定 Tavily basic 和 Stack Exchange 匿名回源。独立账本根据当前凭证、有效期、精确载荷、预算和已结算父回执验权。每槽只有一次已提交发送权。恢复或撤销先提交时阻止发送，已取得独立发送权的请求按在途处理，结算时再复核资格。调用期间释放 SQLite 写锁。
- 未知发送和未知费用保留预约。撤销后保留只用于结算的受保护凭证。丢失或回滚 SQLite 对账记录会阻止新的外发，允许依据原不可变账单恢复同一结算。原地恢复不受支持，恢复到新目录后重新审查。
- PackyCode 两片均由 `LIVE_MODEL_HARD_BUDGET_UNVERIFIED` 在预约前关闭。现有 8+3 及 C0-1/C0-2 判定通过模拟档案测试。实际模型发送与响应归档需在可执行的逐请求输出及费用控制可核验后接通复验。
- 正式判定要求同批受保护回执、当前授权及审阅证据。C0-5/C0-6 的本机 Owner 审阅记录需逐项对照独立日志、合成数据、源码版本和摘要。在正式纳入前完成该交叉核验。[正式矩阵](README.md#六项正式验收状态)

## Windows 10 初次交付回归

Windows 10 22H2 Build 19045.6466，Python 3.12.14、SQLite 3.53.1、Node 24.22.3、Playwright 1.65.2。浏览器全量使用已安装的 Chrome 157.0.8103.80。使用隔离数据库和合成凭证。普通 Windows 用户会话原生 DPAPI CurrentUser 往返可用。沙箱会话保存测试凭证返回 503，采用普通用户会话完成原生测试，保留原凭证保护。

| 核验 | 实际结果 |
| --- | --- |
| Python 全量 | `python -m unittest discover -s tests`，532 项，531 通过，0 失败，1 非 Windows 用例跳过，148.118 秒 |
| D-L 专项 | `test_personal_live_*.py`，50/50。含部署身份绑定、授权和档案、正式传输、v11 迁移、同批证据。合成电子邮箱夹具修订后传输 7/7 |
| Node | `node --test tests/client_state.test.cjs`，2/2 |
| Browser | `tests/browser_e2e.py`，全量通过。包含本机原生 DPAPI、Personal 隔离及桌面和移动审批 |
| 冷启动 | `scripts/cold_start.py`，3/3。另从工程提交解包，在普通、中文和带空格路径各运行同脚本 3 次，9/9 |
| 历史归档 | 依 CI 的四条 `src.outputs.audit_receipt --verify` 命令，4/4。正式复用 0 |
| Git 扫描 | `git diff --cached --check` 与 `scripts/check-no-secrets.sh` 通过。合成电子邮箱探针改为运行时构造 |

## 对账复审

| 优先级 | 已关闭缺陷及复验 |
| --- | --- |
| P1 | 两笔本地请求可在不同批次重复认领同一供应商请求 ID。现按供应商、账户及供应商请求 ID 核对 SQLite 回执与受保护费用档案，在同一 SQLite 写事务内绑定归属、归档及结算。后到的重复回执进入对账，原预约保留。 |
| P1 | 结算事务回滚留下费用档案，或 SQLite 保留结算而档案缺失时，跨批次归属可能失去保护。现双向核对已结算记录与档案。孤立档案保留其请求归属，按原证明恢复 SQLite 结算。现有结算缺少档案时，停止新发送及对账，恢复原档案后复核。 |

四项新增集成用例及强化的既有用例覆盖已有回执冲突、后到回执、并发争用、费用档案缺失、SQLite 回滚、重启恢复和幂等。数据库版本沿用 v11。响应档案保存后若 SQLite 回执提交失败，请求继续按结果未知处理。负责人需要用实际逐笔账单核验供应商请求 ID 及费用，结算记录本身不能补充正式响应证据。

对账补修后的 Windows 10 普通用户回归共运行 536 项 Python 测试，535 通过、1 项非 Windows 用例跳过、0 失败，用时 146.105 秒。Node 2/2、冷启动 3/3、Chrome 全量及原生 DPAPI 均通过。历史归档完整性 4/4，正式纳入 0。补修前的提交 2519672ec1ccf5cb6341b5b1f03a427835d06120 的三项 CI 均通过，补修提交的核验见草稿 PR 的检查记录。[补修前 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45852101131) · [PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2/checks)

## 未关闭的正式执行条件

| 优先级 | 待核实 |
| --- | --- |
| P1 | 独立工作区部署复验已通过。正式批次仍需独立可信的恢复连续性证据，核对批次、当前工作库身份、撤销水位、凭证轮换和请求费用状态。 |
| P1 | Tavily、Stack Exchange 和 PackyCode 的账户及用途授权，当前条款、费率、额度、风险和逐源许可。包内引用由 Owner 背书，实际材料和失效条件须单独查验。 |
| P1 | PackyCode SystemOne 逐请求硬输出限额、供应商可能重试和最坏费用的实际证明。 |
| P1 | 正式 C0-5、C0-6 需对照实际测试产物、源码及数据摘要后纳入，当前批次及对应批准均未创建。 |
| P2 | 继续跟踪已知 StarletteDeprecationWarning。未影响本机回归。 |

部署和真实请求的批准材料见 [D-L 授权申请](d-l-authorization-draft.md)。Personal Research Gate 仍为 `NOT_EVALUATED`，Business G-1 为 `BLOCKED`，G-1-P-R 及 M09–M15 为 `NOT_STARTED`。M06 冻结，I18N-PRE `PLANNED`，核心路线图 39/79。
