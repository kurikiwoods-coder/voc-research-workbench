# G-1-P-B 工程验证

接续 `codex/g1-personal-phase-1` 的 `0e7a3d7ec4909cf43410728045a9bb765b2760da`，基于开发分支 `codex/p0-0-connectivity` 的 `dd89a14f25ac0dfae3f63dcf1809da2494f1c9dc`。Phase 1 的 20 个 Markdown 变更保留。草稿 PR #2 指向开发分支。已核对 Phase 1 的 Ubuntu、Windows Server 2022、Chromium 三项通过。[草稿 PR #2](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/2) · [Phase 1 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45743358197)

| 核对项 | 验证方式 |
|---|---|
| 配置及身份 | 合法四种配置、非法配置、受控目录、可信 Owner、真实请求的角色／版本字段及异源请求拒绝 |
| 项目与冻结范围 | 授权时效、跨项目／跨范围、未知对象、历史批次、草稿清理、精确来源和重复组视图 |
| 权限和同事务复核 | 数据权、审核权和导出权限分别检查。模拟预检后授权失效，原话、归档与写入均在当前数据库连接拒绝 |
| 两道准入及模式隔离 | 旧商用同批六项和当前审查校验；个人正式分母 unavailable/null；原预检封存；合成与正式结果及真实消费隔离 |
| 实际运行边界 | 正式预约、出队、恢复、诊断、外发和注册表写入保持对应阻断。受控测试无真实来源或供应商出站 |
| SQLite | v8 正常迁移、重启、备份、故障回滚、历史归档、完整性及外键。个人工作库即使 SQLite 备份至新目录仍拒绝商用打开 |
| Chromium | 已有工作台全量回归，另核对个人版桌面 1440px、移动端 393px、原生 Owner 验证入口、页面无授权摘要／原话／密钥，浏览器外部请求 0 |
| Windows 11 新源码实机及部署门禁 | **NOT_TESTED**。M08-V 的 Windows 11 证据继续绑定原验收源码 [`74590d4`](../m08-v/README.md) |

本轮真实研究 API 调用 **0**，真实供应商探针 **0**。SQLite v8，M06 工程基线 FROZEN，ROADMAP-V2 **39/79**。商用 G-1 **BLOCKED**，个人 G-1-PERSONAL **NOT_EVALUATED**。历史 PackyCode 的 `CSV_VERIFIED` 与 `LOCAL_VERIFICATION_PENDING` 记录适用原实调和账本。[独立复审](independent-review.md) · [C 阶段交接](../../architecture/g1-personal-gate-contract.md) · [历史费用证据](../g1-rb-f/README.md)

## 云端 Linux 实际执行结果

| 命令或证据 | 结果 |
|---|---|
| `bash scripts/smoke-test.sh` | Python **422/422**（原 395，新增 27）、Node **2/2**、空库冷启动 **3/3**、脱敏扫描通过 |
| `python tests/browser_e2e.py` | Chromium 141.0.7390.0 全量 E2E 通过，输出 17 组功能／接口与重启检查结果。个人版两种视口均通过，外部请求 0 |
| 四份 `python -m src.outputs.audit_receipt --verify <目录>` | connectivity、regression、api-setup 和 Tavily 已归档回执 **4/4** 通过，未回访供应商 |
| 冻结差异检查 | PDT、M06 政策及统计契约、SQLite 迁移脚本、M06 关系授权与统计引擎、ROADMAP-V2 正文在代码变更前后差异为 0 |

云端测试为 Python 3.12.14 和 Node 24.22.3。GitHub Actions 的现有流程增加对开发分支作为 PR 目标的监听，草稿 PR #2 保持原评审目标。[桌面截图](browser/edition-personal-desktop.png) · [移动端截图](browser/edition-personal-mobile.png)

## 验收反例定位

| 提示编号 | 实际自动化入口 |
|---|---|
| 1–4 默认兼容、合法四组合、非法配置、关闭云端特权 | `test_default_install_keeps_business_health_gate_and_setup`、`test_trusted_environment_accepts_each_valid_pair_only`、`test_invalid_owner_startup_and_grant_shapes_fail_closed`、`test_cloud_is_status_only_and_opens_no_directory` |
| 5–10 可信 Owner、客户端伪造及跨项目 | `test_owner_identity_is_trusted_and_only_exposes_typed_projection`、`test_http_cannot_claim_owner_edition_grant_or_gate`、`test_nonloopback_and_foreign_origin_are_denied_even_with_proof`、`test_unbound_and_nonexistent_project_are_indistinguishable`、`test_deny_without_permissions_does_not_disclose_object_existence` |
| 11–16 双门禁、真实路径、PackyCode 旧阻断、授权封存 | `test_business_status_requires_current_review_and_same_finished_attempt_evidence`、`test_personal_research_admission_and_engineering_domains_cannot_promote_each_other`、`test_legacy_services_refuse_personal_config_or_personal_store`、`test_transport_protects_configuration_independent_of_http_layer`、`test_no_claim_or_directory_can_restore_consumed_preflight` 与原 PackyCode 专项 |
| 17–20 合成与正式隔离、正式 null、数量恒等式及历史版本 | `test_import_review_replay_revocation_and_formal_status`、原 `test_m06_denominators.py`、`test_m07_*.py`、`test_recover_source_batch.py`、离线归档校验 |
| 21–22 凭证管理及任务失败关闭 | 原 `test_api_setup.py` 及 Chromium API 接入、原 M08 任务与恢复、新 `test_closed_live_routes_do_not_create_tasks_runs_or_vendor_requests`、`test_local_mutation_rechecks_inside_write_transaction_and_can_retry`。本轮 Windows 11 原生凭证和部署待测 |
| 23–25 浏览器投影、零出站、M01–M08 全量 | `tests/browser_e2e.py` 的完整套件及 `run_edition_browser`、`scripts/smoke-test.sh`。独立复审同样只使用受控传输 |

## 首轮 GitHub CI

实现提交 `385c1e455312fb3754abc4449bd90120e7bab0e5` 的 Ubuntu 与 Chromium 作业通过。Windows Server 2022 首轮 Python 运行 422 项，418 项通过、3 项断言失败、1 项清理错误，后续步骤未执行。失败根因是商用短路径形态被展开及损坏库连接在异常时未关闭。原测试保留。[首轮 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45749282638) · [Windows 失败日志](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45749282638/job/139672912126) · [缺陷台账](bug-register.md)
