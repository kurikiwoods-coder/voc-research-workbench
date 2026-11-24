# M04 工程验收记录

使用临时 SQLite 和可复现的合成 CSV、XLSX 文件。未提交用户语料。真实 Jev、Tavily、Brave 请求各 0 次，G-1 仍为 BLOCKED。

| 工程范围 | 验证证据 |
|---|---|
| 文件解析、手工与自动映射、空白与非法值、隐私、重复与范围 | [Python 回归](../../../tests/test_imports.py) |
| 跨项目隔离、冻结范围、撤销、事务失败回滚、v2 升级、重启 | [Python 回归](../../../tests/test_imports.py) · [迁移](../../../src/raw_store/migrations/003_research_imports.sql) |
| 中文上传、拖入 CSV、XLSX 多表选择、报告、移动端、服务进程重启 | [Chromium 回归](../../../tests/imports_browser.py) |
| 本机工程测试结果 | [Linux 日志](linux-smoke.log) |
| GitHub Actions | [PR #1 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks) |
| Windows 10/11 真机 | NOT_TESTED。Windows Server 2022 由 CI 独立验证。 |

正式 G1、RAW 和跨批次去重仍须按原验收标准执行。
