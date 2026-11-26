# M07 工程验收

负责人于 2026-11-25 单独授权 M07-A 至 D 隔离实施。入口提交 `7c02966eb7e6c54f8e30ff032f921bac6719d1d2`，M06 工程冻结提交 `3bd705befb98ee108b77603763c5571ceb7fdc44`。开发分支 `codex/p0-0-connectivity`，关联草稿 PR #1。[入口 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45588245935) · [PR #1 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)

PDT v1.3.1 Word 原件已查阅，专案 v2.2 使用仓库摘要。本次无法访问此前登记的 27 页 PDF 原件。

## 阶段和边界

| 阶段 | 交付 |
| --- | --- |
| M07-A | ENGINEERING_PASS。统一数据契约、旧样例待补主任务兼容、SQLite v8 增量迁移与 v7 恢复。 |
| M07-B | ENGINEERING_PASS。受控项目草稿、修订、预检、幂等、提交待审与撤回。 |
| M07-C | ENGINEERING_PASS。封版查询、稳定 ID 差异、谱系计划、历史恢复和精确版本消费。 |
| M07-D | ENGINEERING_PASS。注册表页面、本机 API、项目审核提案及证据授权回查。 |

`M06_ENGINEERING_BASELINE = FROZEN`。G-1 = BLOCKED。G-1-R-A/B 延期。真实研究 API 调用 0 次。正式研究、真实编码和正式发布仍关闭。M07 正式业务验收 = PENDING。M08–M15 = NOT_STARTED。

## 回归与证据

- 入口 Windows 10 Home China 22H2 x64，Build 19045.6466。Python 3.12.14，Node 24.22.3，SQLite 3.53.1，Chrome 157.0.8103.80。
- 入口普通 Windows 用户上下文的 Python 277/277、Node 2/2、Chromium 11/11 组及专用回环 HTTP 2/2，空库冷启动 3/3。同库重启 schema v7，`integrity_check` 正常，外键校验 0 项。
- Windows 10 本轮普通用户上下文的 Python **298/298**，72.589 秒，新增 21 项（迁移 4、草稿与权限 10、版本接口 7）。Node **2/2**，空库冷启动 **3/3**，四份历史脱敏归档 **4/4**。测试隔离源码清单 SHA-256 为 `fdc1e8e440081893c0b2d8509e219370b5ed7bc82a290ca15431cdc9cf45f096`。
- SQLite v7 至 v8 验证了稳定 ID、已封版历史、一致性备份和恢复、失败迁移原子回滚及同库重启。v8 完整性正常，外键校验 0 项。
- 1,000 条合成记录的两路统计一致，六桶及两条等式通过（700 = 599 + 101，599 = 100 + 100 + 99 + 100 + 100 + 100）。撤销重算得到 700 = 598 + 102。WAL 一致性备份及恢复通过。
- Playwright 1.65.2 的 M07 浏览器专项通过，覆盖搜索、历史差异、草稿、撤销资格和授权、冲突、网络重试、键盘及 320/390 px。
- Windows 10 普通用户上下文 Chromium **12/12** 组（基线 11，新 M07 1），本机专用 HTTP **2/2**，共 30 张合成截图。浏览器使用 Playwright 1.65.2 与 Chrome 157.0.8103.80。已核两张交付截图，[历史差异](m07-version-diff.png) · [390 px 视图](m07-390px.png)。
- Windows 11 实机证据缺项见 [平台记录](windows11-manifest.json)。M06-R 的 Windows 11 历史通过记录继续绑定 `9c27231376fcc32aae39a9b63df6fa9b9b98c4c6`。
- 错误复现及修复见 [独立复审](independent-verification.md) 和 [缺陷台账](bug-register.md)。

源码交付提交 `5a3bd4189d6f3e3951bdcc0d79ce79db5c8060e8` 的 Ubuntu、Windows Server 2022 和 Chromium 均通过，提交前的敏感信息扫描通过。[源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45618421502)

按负责人已批准的当前 Windows 10 开发工程验收口径，M07 = **ENGINEERING_PASS**，ROADMAP-V2 为 **35/79**，剩余 44 项。未关闭 P0/P1/P2 为 0，保留两项 P3。M07 在 Windows 11 上的同源码实机部署证据待补，M06-R 原通过记录保留。
