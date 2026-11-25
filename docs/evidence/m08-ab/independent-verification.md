# M08-A/B 独立复审记录

2026-11-25 在 Windows 10 Home China 22H2（10.0.19045）和 Python 3.12.14 的本机 Codex 会话执行。参考基线为 `81ce8818354f36ed33943d604e8890adde1f4c3f`，复测使用包含本轮修复的工作区。测试使用临时目录和合成夹具。独立集成复测禁用 Python HTTP 出站，真实研究 API 调用为 0。

| 复审项 | 实际证据 | 结果 |
| --- | --- | --- |
| 供应商请求和用量 | 搜索专项核对 Tavily、Brave 的固定端点、各自的凭证引用、各自的失败与回退行为，以及 Credit、请求数和费用的独立字段。FastAPI 预览显示实际构造的供应商参数、Tavily 的排除词限制及 Brave 的索引日期语义。 | PASS |
| 冻结范围和项目隔离 | 范围 ID 和版本均关联项目。跨项目返回 404，未冻结、错版本、错品类及超出冻结时间窗返回 422。不同合成品类使用相同适配器。归档项目保留只读预览，新的演示请求返回 422。 | PASS |
| 发现与回源 | 两路合计 3 份发现回执，规范化后为 2 个 URL，有 1 个可访问页面。保留各自来源和原始 URL。回源只使用离线固定问答路由。项目时间窗为 1969-12-31 单日时，夹具页面发布时间仍与范围一致。 | PASS |
| URL 安全与提取 | 回源专项验证协议和精确域名白名单、拒绝非公开地址及非法重定向、固定问题标识、响应字节上限、离线故障及超时。访问资格和摘录资格独立，真实传输函数会被拒绝。摘要、脚本和样式内容未进入已验证摘录，内容哈希基于原始响应。 | PASS |
| 来源许可及正式入口 | 目录的发现、访问、存储、研究和传输许可分别默认为未知。模拟演示的访问权限没有开启摘录。非回环或非法 Host、Origin 和操作头请求被拒绝。正式采集返回 403，M08 API 响应为 `no-store`。 | PASS |
| 合成回执和分母 | 模拟夹具的工程漏斗为 `2 / 1 / null / null / null`。复审注入双路 503，工程和正式漏斗均保留 `null`。永久回归另覆盖两路均完成且结果为空时，工程发现及可访问页面计数为 0。正式漏斗在演示中始终保留 `null`。 | PASS |
| 数据边界与数据库 | 单独提交用户查询文字给演示入口返回 422。标记用的冻结范围自由文本和预览查询没有进入合成回执。主库为 SQLite v8，原文快照 0 条。隔离回执账本为 v1，`integrity_check` 为 `ok`，`foreign_key_check` 无违规。 | PASS |
| 冻结架构与历史证据 | 实跑 M06 分母、M07 注册表草稿和版本、PackyCode 合成预检回归 57 项全部通过。工作区未改变既有数据库迁移或 G-1-R-B-P 证据目录。 | PASS |

复测命令在仓库根目录执行。

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_m08_*.py'
$env:PYTHONPATH = 'tests'
& .\.venv\Scripts\python.exe -m unittest test_m06_denominators test_m07_registry_drafts test_m07_registry_versions test_packycode_preflight
```

新增专项 29/29，通过。M06、M07 和 PackyCode 相关回归 57/57，通过。独立 FastAPI 复测的五项附加核对通过，覆盖供应商预览、自由文本和日期、双路故障、归档及正式门禁、账本隔离及完整性。运行输出包含已登记的 `StarletteDeprecationWarning`，测试正常结束。

全面 Python、Node、Chromium、真机启动及 CI 由本轮主交付记录汇总。正式来源审批、真实采集、正式统计及 Windows 11 实机均无本轮独立复审通过证据。G-1 保持 BLOCKED。
