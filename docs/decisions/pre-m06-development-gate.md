# Pre-M06 开发与 Windows 11 部署门禁

2026-11-24，项目负责人在 M06-C1 授权中批准调整工程门禁。当前开发环境是已通过 Pre-M06-D 验收的 Windows 10 实机，因而采纳该环境的实测结果作为 M06 开发的实机工程依据。Windows 11 的系统特定验证留到该平台部署前完成。

| 项目 | 调整前 | 调整后 |
|---|---|---|
| 开发实机证据 | Pre-M06 将 Windows 11 实机待测列为开发放行阻塞，Windows 10 实测独立登记。 | 当前开发环境采用已记录的 Windows 10 实机验收。仍须核对实现基线、CI、全量工程回归、数据库完整性、数据安全和独立审计结果。 |
| Windows 11 实机 | 当前基线为 NOT_TESTED，当时的 Pre-M06 Gate 为 BLOCKED。 | Windows 11 实机为 NOT_TESTED，部署门禁为 BLOCKED。拟部署提交须在 Windows 11 实机完成相应回归。Windows Server 2022 CI 按 runner 独立记录。 |
| 正式研究 | G-1 为 BLOCKED，PDT v1.3.1 的正式业务验收条件适用。 | G-1 为 BLOCKED。同批 C0-1 至 C0-6、适用供应商公开语料处理审批与留存审查，以及逐源许可和正式验收要求照常执行。 |

授权范围为 M06-C1 的正式工程实施及相应门禁调整。先前记录中的 `PRE_M06_GATE_BLOCKED` 是当时的结论。M06-C1 的具体迁移、回归和发布检查以实现提交的结果独立判定。后续模块依其授权和验收条件实施。

## 调整后的开发放行核对

入场核对使用开发分支 `codex/p0-0-connectivity` 的架构冻结提交 `02dfcebff52687d93578011977d5dada3bf70d27`。冻结提交与实机验收代码基线之间的变更为设计、状态、审计及隔离原型证据，`src`、`tests`、`scripts`、`.github`、`schemas` 和依赖清单经 Git 核对无差异。[冻结提交](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/02dfcebff52687d93578011977d5dada3bf70d27) · [草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1)

| 条件 | 核对结果 |
|---|---|
| M01–M05 工程审计与缺陷回归 | A–H 跨模块场景通过，10 项确认缺陷均关闭，M05-R2-V 通过。修复 CI 记录 Python 140、Node 2、启动 3、归档 4 和 Chromium 8 检查全部通过。[审计](../audits/pre-m06-audit.md) · [修复 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45373503587) |
| 当前开发环境实机 | Windows 10 Home China 22H2 x64，OS Build 19045.6466。在代码基线 `4e6369b92205c51671866935365678df351ec808` 上完成普通登录用户 DPAPI、Python 140/140、Chromium 8/8，并结合本机 Node、冷启动和路径验证。Codex 会话 DPAPI 限制已单列。[Pre-M06-D 实机记录](../evidence/pre-m06/windows10-closeout.md) |
| 数据库完整性与数据安全 | 调整前基线的 v1 → v6、v5 → v6、SQLite 完整性和外键核查通过，历史脱敏归档 4/4。审计 A–H 覆盖跨项目、内部 CX、合成与正式入口隔离、撤销遮蔽；敏感信息扫描通过。工程验证真实研究 API 调用 0。[审计记录](../evidence/pre-m06/README.md) · [Pre-M06-D 实机记录](../evidence/pre-m06/windows10-closeout.md) |
| GitHub CI | 实测代码基线与冻结提交各自的 Ubuntu、Windows Server 2022、Chromium 均通过。开发分支与草稿 PR #1 的头提交在入场时一致。[实测基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45374179477) · [冻结提交 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45422820932) |
| 已批准的设计与实施授权 | 五项架构政策获准，M06 架构已冻结。项目负责人本轮明确授权 C1。PDT 正文及需求矩阵继续作为正式验收依据，专案 v2.2 的 27 页 PDF 原件缺口沿用冻结记录。[架构批准记录](../architecture/m06-owner-approval.md) · [需求验收矩阵](../requirements-matrix.md) |

```text
PRE_M06_DEVELOPMENT_GATE = PASS
WINDOWS_11_REAL_MACHINE = NOT_TESTED
WINDOWS_11_DEPLOYMENT_GATE = BLOCKED
G-1 = BLOCKED
```

Windows 11 部署验收需在实机记录操作系统版本、拟部署提交、普通用户 DPAPI、完整 Python/Node/Chromium 结果、三次空库冷启动、历史归档完整性、中文及空格路径启动，以及隔离升级副本的完整性、外键和迁移恢复结果。用获准脱敏归档、合成夹具和隔离数据库完成实际验证，真实研究 API 调用为 0。[复建及验证命令](../../HANDOVER.md#复建开发环境)
