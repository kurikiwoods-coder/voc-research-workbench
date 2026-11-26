# P0-0 Tavily 认证搜索实测

2026-11-24 11:22（UTC+8）执行批次 `89b0c2d1-576d-420f-9046-9e55878159be`。临时凭证只在子进程运行期间生效。保留脱敏证据，运行结束后清理临时运行库。

| 服务 | 本轮实际观测 |
|---|---|
| Tavily | 一次认证基础搜索，HTTP 200。返回 5 条合规候选链接。响应中的 `usage.credits` 为 1。 |
| Stack Exchange | 匿名论坛搜索及原帖回源分别返回 HTTP 200。原帖 94603 由 Tavily 发现。原文、署名、日期和 CC BY-SA 4.0 通过核验。 |
| JevModel | 临时凭证已载入，留存审核待核验。模型请求数和本批输入 tokens 均为 0。余额未同步。 |
| Brave | 未配置，实际请求为 0。 |

模型路径和 MCP 路径的匿名 GET 都收到 HTTP 403 HTML。这两次探测在正式批次之外且不含凭证。固定模型 `jev-1.14.0`、11 题实发分片和三类返回仍待供应商留存审查后的认证验证。当前只保存了 8 + 3 题的请求计划。 [原帖](https://cooking.stackexchange.com/questions/94603/) · [JevModel 接口说明](https://jevmodel.org/zh/docs/)

## 验收

| 检查 | 状态 | 理由 |
|---|---|---|
| C0-1 | BLOCKED | 留存审核待核验，固定版本与实发分片等待确认 |
| C0-2 | BLOCKED | Choice、Score、Noul 与完整分档概率等待真实响应 |
| C0-3 | PASS | Tavily 发现，许可原帖及原话通过回源核验 |
| C0-4 | BLOCKED | SQLite 与 JSON 已核对，真实分片用量和余额待测 |
| C0-5 | PASS | 36 次外发拦截及六种故障演练通过 |
| C0-6 | PASS | 三层模型和两次跨品类召回通过 |
| G-1 | BLOCKED | 当前仍处于 P0-0 |

`tests/live_gate.py` 执行 7 项检查，3 项通过、4 项因前置条件阻塞而跳过，退出码为 2。归档 10 条证据，Jev 账本 0 片，SQLite 完整性为 `ok`。正式研究分母为零。[测试原始输出](live-gate.log) · [脱敏 JSON](run.json) · [审计 SQLite](audit.sqlite3) · [计量摘要](summary.json)

正式搜索此前未请求和保留 Tavily 的积分字段。本轮显式选择基础搜索并请求 `include_usage`，以同一次响应记录实报积分；未报用量保留空值。47 项 Python 测试、2 项 Node 回归、3 次 Linux 冷启动及密钥扫描均通过。[工程回归](smoke.log) · [Tavily Search 接口](https://docs.tavily.com/documentation/api-reference/endpoint/search)
