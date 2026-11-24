# M03 工程测试记录

2026-11-24。本轮使用本机临时 SQLite、人工编写的测试课题、无供应商凭证的运行配置。M03 工程验证不变更原有正式验收，G-1 继续 BLOCKED。

| 验证 | 记录 |
|---|---|
| Linux 本地 | Python 69 项、Node 2 项、空库冷启动 3 次，均通过。[实际输出](linux-smoke.log) |
| M03 单元与集成 | 16 项包含五种模式、版本冻结与隔离、并发提交、生命周期、回滚、v1 迁移和服务重开。[用例](../../../tests/test_studies.py) |
| 归档一致性 | 4 份已提交的 P0-0 SQLite 与 JSON 归档核验通过，历史 Tavily 批次保持 C0-3 PASS。[核验输出](archived-receipts.log) |
| 本地 Chromium | 当前执行环境的 Chromium 启动因系统禁止创建浏览器 socket 而中断。使用 GitHub Actions 的真实 Chromium 重跑。 |
| Windows 10/11 真机 | NOT_TESTED。Windows Server CI 另行登记。 |

[当前 PR 的工程检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks) · [M03 浏览器用例](../../../tests/studies_browser.py)

Tavily、Brave、Jev 真实请求均为 0。历史认证搜索的用量保留在原始归档。
