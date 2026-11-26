# M05-R2 许可与数据资格复测

2026-11-24，在 `958ebcb948fa9677a7254dde4516c4a49761b798` 和修复提交 `6f3b345640456182851830d67f3569c1e37b4501` 上分别用隔离 SQLite、同源 FastAPI TestClient 与合成 CSV 实测。每次先建研究项目并冻结范围，再写入初始批次。真实研究 API 调用 0 次。前后日志只保留测试结论字段。

| 缺陷 | 复现条件 | 基线实测 | 修复实测 |
|---|---|---|---|
| BUG-01 | 导入许可说明为「未授权，等待书面审批」的行并提交核验。 | HTTP 200，记录进入 `verified`。 | HTTP 422，许可为 `denied`，原文为空。 |
| BUG-02 | 核验一条原话，排除并填写「复核：授权已撤销」，再凭旧证据核验。 | 撤销标记为 false，复核 HTTP 200，原话可见。 | 撤销标记为 true，复核 HTTP 409，原话受限。 |

[基线输出](permissions-before.log) · [修复输出](permissions-after.log) · [永久回归](../../../tests/test_corpus_licenses.py)

SQLite v5 追加六种结构化许可状态和不可变撤销历史。模糊或矛盾的表述只会触发限制，历史已有核验且缺少结构化证据的记录须复核。恢复须显式人工审核并登记覆盖撤销日的新材料。回归覆盖中英文、简繁体、标点、许可冲突、正向授权、旧证据、导入和读取遮蔽、同项目副本、并发、重试、回滚，以及旧库迁移。现有受限批次幂等确认回归保留。

| 工程检查 | 本轮执行结果 |
|---|---|
| `bash scripts/smoke-test.sh` | Linux Python 123/123、Node 2/2、三次空库冷启动 3/3，秘密扫描通过。 |
| `python -m src.outputs.audit_receipt --verify <归档目录>` | 四份历史 SQLite 与 JSON 归档完整性通过。 |
| 本机 Chromium | 可用的系统 Chromium 在创建 socket 时被执行环境拒绝，浏览器用例未启动。 |
| Ubuntu CI | Python 123/123、Node 2/2、空库冷启动 3/3、历史归档 4/4，秘密扫描通过。 |
| Windows Server 2022 CI | Python 123/123、Node 2/2、空库冷启动 3/3、历史归档 4/4，秘密扫描及中文和空格路径的启动器通过。 |
| Chromium CI | 8/8，含撤销后旧证据拒绝、有效新许可恢复、重启和 320 / 390 像素布局。 |
| Windows 10/11 实机 | 本轮 NOT_TESTED。 |

BUG-01 与 BUG-02 在首个实现提交与其冻结记录的 CI 上通过。[实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45366372653) · [实际 CI 日志摘录](permissions-ci.log)

## 最终迁移边界复测

在 `3465278e72f898fb9a55cc007337ff965d10c5a7` 的合成库中登记两个指向同一文件行的 v4 样式核验历史，均缺少结构化授权。修复前两条记录均为 `source_restricted`，无法提交人工复核，HTTP 409。修复后两条均为 `pending_review`，原文受限，可分别登记证据复核。复核一条后，仅该条可读；两条都复核后重新纳入有效重复组。真实撤销和到期的限制有既有回归继续验证。[上一轮 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45367027115) · [新增回归](../../../tests/test_corpus_licenses.py)

最终实现为 **ENGINEERING_PASS**。本机 Linux、Ubuntu 和 Windows Server 2022 各通过 Python 124/124、Node 2/2、冷启动 3/3、历史归档 4/4。Chromium 8/8，Windows Server 中文和空格路径启动通过，工程测试 0 失败。[最终实现 `62a7c1c`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/62a7c1c132b72a8e07679f1713e6834aa7893c91) · [实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45367761470) · [实际 CI 输出](permissions-final-ci.log)

正式业务验收仍要求逐源许可、三个真实来源批次、至少 100 条合格真实语义片段、30/30 回源和实际物理清理及删除审计。C0-1、C0-2、C0-4 和 Jev 供应商留存与分处理商审查待验。G-1 为 BLOCKED。[验收矩阵](../../requirements-matrix.md) · [M06 数据契约](../../../HANDOVER.md#m05--m06-数据契约)
