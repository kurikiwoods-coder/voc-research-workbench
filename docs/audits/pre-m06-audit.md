# Pre-M06 工程审计

## 当前开发与部署门禁

2026-11-24，项目负责人批准采用已通过验收的 Windows 10 实机作为当前开发环境的实机工程依据，并将 Windows 11 实机验收移至 Windows 11 部署之前。入场基线的全量工程回归、数据安全、数据库完整性和对应 GitHub CI 均有证据，`PRE_M06_DEVELOPMENT_GATE=PASS`。Windows 11 实机维持 `NOT_TESTED`，`WINDOWS_11_DEPLOYMENT_GATE=BLOCKED`，`G-1=BLOCKED`。[新旧规则及放行核对](../decisions/pre-m06-development-gate.md)

## 历史放行状态

**PRE_M06_GATE_BLOCKED**。Pre-M06-D 在 `4e6369b92205c51671866935365678df351ec808` 完成 Windows 10 实机工程验收，结果为 **PASS**。当前基线的 Windows 11 实机仍为 **NOT_TESTED**，Windows Server 2022 结果单独登记。G-1 保持 **BLOCKED**，M06-A 架构设计具备工程基础，等待项目负责人另行授权。M06 实现和正式接入继续按原条件放行。[Windows 10 实机证据](../evidence/pre-m06/windows10-closeout.md) · [前期审计证据](../evidence/pre-m06/README.md)

审计起点为 `04049b375f8b0e281c5f09f51d2fb07b5f1c3463`，分支为 `codex/p0-0-connectivity`，采用草稿 PR #1 当时的远端提交。其 CI 三项均通过。审计执行基于绑定具体提交的 GitHub Actions、隔离临时库和合成夹具。开发分支采用快进更新。主分支基线为 `f849242c5c37a2dc6a03a30215dd335424738c61`。 [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45368417661) · [PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1)

按 PDT v1.3.1 正文、专案 v2.2 与现有矩阵核对。§9.3 的稳定引用和正式分母、§13.0 同批六项真实连通性、附录 C 的冷启动标准以及内部 CX 的本机边界继续适用。M01–M05 的工程审计沿用现有六层结构和业务标准。 [PDT](../pdt/PDT-v1.3.1.docx) · [专案摘要](../proposal/voc-workbench-proposal-2026-11-23.md) · [验收矩阵](../requirements-matrix.md)

## 模块健康与覆盖

| 模块 | 工程状态 | 实测重点 |
|---|---|---|
| M01 基础工程 | CI 通过，Windows 11 实机待复测 | Ubuntu 和 Windows Server 2022 各三次空库冷启动。中文及空格路径启动器。异常退出后的事务回滚及重启回查。损坏库拒绝启动且原文件字节不变。运行记录、证据回放、分片重试和数据库外键 |
| M02 API 配置 | CI 通过 | 向导、凭证保存轮换停用、Linux 文件权限和 Windows Server DPAPI。重启后的凭证和帐号审查状态。401、402、403、429、5xx、超时和截断响应的受控夹具。未知余额、用量及诊断和正式库隔离 |
| M03 研究项目 | CI 通过 | 五种研究模式、项目创建和编辑、活动项目切换、冻结范围、并发修改、归档和恢复。无效 ID 和跨项目引用。范围更新后历史批次仍指向原冻结快照 |
| M04 CSV / XLSX | CI 通过 | 三类编码和常用分隔符、多个工作表、空文件和损坏包、边界检查、公式及路径限制、字段预览、错误报告、幂等和事务回滚。同内容改名和跨隐私或角色去重 |
| M05 原始语料 | CI 通过，M05-R2-V 独立通过 | 两处已知缺陷、许可文字变体、旧批准与撤销迁移、同源副本、重启回查、限制后的重复组重算。详情、暂存、导入历史和错误 CSV 遮蔽。现行资格接口 |

浏览器回归在真实 Chromium 和回环服务中执行，覆盖首次向导、角色状态、凭证轮换、项目与版本、导入映射和质量反馈、撤销、新授权、重启以及 320/390 像素布局。检查使用脚本覆盖的主操作，未进行逐控件穷举或实体手机测试。真实研究 API 调用 **0 次**。 [修复提交 CI 和截图](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45373503587) · [覆盖与证据](../evidence/pre-m06/README.md)

### 实际接口

| 模块 | 路由及数据边界 |
|---|---|
| M01 | `/api/health`、`/api/workspace`、`/api/runs`、运行证据、恢复、SQLite 账本及启动脚本 |
| M02 | `/api/setup/…/key`、`/api/setup/…/review`、供应商切换、向导、`/api/setup/…/diagnostics`、诊断 SQLite |
| M03 | `/api/studies`、项目与范围查询、冻结、编辑、选择当前项目、搜索、归档及恢复 |
| M04 | `/api/imports` 下的上传、预览、确认、批次历史、错误 CSV 和批次撤销 |
| M05 | `/api/corpus` 下的批次和记录详情、审核及实时资格、受限 `import_candidates` 视图 |

## 跨模块联调

| 场景 | 结果 | 实测结果 |
|---|---|---|
| A 正常研究 | PASS | 回环接口创建项目、冻结、导入 CSV 和 XLSX、审核、去重，复核文件指纹、物理行、来源网址与时间窗 |
| B 跨项目隔离 | PASS | 两个项目分别导入相同原话，使用不同重复组。跨项目读取返回 404 |
| C 范围变更 | PASS | 更新范围后导入第二批，旧批仍绑定原 `scope_id` 和 `scope_version` |
| D 异常恢复 | PASS | 持有未提交写事务的子进程被终止，重启后保留已批准原话，撤销未误提交。保留失败注入与并发重试回归 |
| E 撤销遮蔽 | PASS | 已撤销原话及同源片段副本退出资格和重复组，查看详情与导入历史时原话为空，错误报告和暂存视图无原话 |
| F 旧库升级 | PASS | 版本 1 到 6 保留历史批次和审计 ID，加测版本 5 到 6 的撤销视图及完整性。历史存档 4/4 |
| G API 与数据隔离 | PASS | 诊断库主表独立，合成夹具进入正式执行入口时被拒绝。内部 CX 在资格接口返回 409，诊断与运行记录未混入内部原话 |
| H M06 入口 | PASS | 核实 `record_id`、批次和文件行引用、冻结范围、重复组、摘要及来源、审核与许可状态、撤销标记、隐私与角色。工程资格、正式统计、外发分别返回 |

跨模块检查采用实际 FastAPI 路由及 SQLite 状态。源站和 Jev 的异常响应采用受控夹具。M06 应通过 `CorpusStore.qualified_record` 或 `GET /api/corpus/{study_id}/records/{record_id}/eligible` 读取实时资格。该入口对不合格请求返回 409，`research_eligible` 和 `outbound_allowed` 保持 false。 [独立测试](../../tests/test_pre_m06_audit.py) · [交接契约](../../HANDOVER.md)

## 缺陷和范围边界

确认 **10 项**，其中 P1 八项、P2 两项，均已修复并回归。已知 M05-R2 两项独立复现的预期行为均通过，新增六个中英文限制、冲突或撤销变体也通过。已有批准与撤销记录在新版资格视图中重新核对，原历史和证据保持可追溯。 [Bug 台账](bug-register.md) · [修复前后日志](../evidence/pre-m06/README.md)

- Windows 11 实机、自定义盘符和人工逐控件遍历留待相应设备。Windows Server 2022 的 CI 覆盖中文及空格路径、DPAPI、冷启动与回滚夹具。
- **本机执行环境限制**。Pre-M06-L 的 Codex 执行会话中，合成数据的 DPAPI CurrentUser 保护调用失败，应用凭证写入返回 HTTP 503。普通登录用户会话的 DPAPI 加解密和 M02 实测均通过。保留两种执行结果及现有凭证保护实现。[实机证据](../evidence/pre-m06/windows10-closeout.md)
- **非阻塞性技术债务**。Starlette 在 TestClient 使用 `httpx` 时发出 `StarletteDeprecationWarning`。后续依赖维护时核对推荐客户端和版本兼容性，并复跑相关回归。
- 损坏库当前在启动终端报 SQLite 错误并保留文件。带人工备份恢复指引的界面是可延后的工程改进。
- 已绑定的本机留存审批只适用于对应凭证。使用环境密钥和独立审批文件的部署，凭证与组织匹配仍由环境管理者核对。原有未绑定的本机审批必须重新核对并登记。
- 来源匹配保留完整路径和查询，按同一文档处理 URL 片段。不同路径或实质不同查询的网页是否同源须由运营核对。原话遮蔽保留审计数据，实际删除及备份保留继续依来源政策验收。
- 正式业务缺 C0-1、C0-2、C0-4 和供应商审核。业务验收证据采用原标准。

## 验证记录

修复提交为 `d64fb4f29094be9a3fc9b91e2910830ea0c1c8c2`。Ubuntu、Windows Server 2022 各通过 **140 项 Python**（124 项原有、16 项新增）、**2 项 Node**、**3 次冷启动**和 **4 份历史归档核验**。Chromium 通过 **8 组**，工程测试 **0 失败**。敏感信息扫描通过。[实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45373503587)

Pre-M06-D 的 Windows 10 普通 PowerShell 会话由项目负责人手动执行，DPAPI 通过，Python **140/140**，原版 Chromium **8/8**。Codex 核验了本地 HEAD、远端 SHA、16 张浏览器截图及已有本机日志，并保留 Pre-M06-L 的部分通过结果。当前基线的 GitHub Actions 三项作业通过，另行记录。[证据与归属](../evidence/pre-m06/windows10-closeout.md) · [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45374179477)
