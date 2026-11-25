# M08-C/D 隔离工程验收

起始开发分支和草稿 PR #1 的 HEAD 均为 `411f43388daf140c1dc33bfd1de2e26d89b17641`。起始 CI 的 Ubuntu、Windows Server 2022、Chromium 均通过。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45644043363) · [草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1)

| 验证 | 实际结果 |
| --- | --- |
| Windows 10 Home China 22H2，19045 | Python 3.12.14、SQLite 3.53.1、Node 24.22.3、Chrome 157.0.8103.80。普通 Windows 用户上下文 Python 395/395，84.546 秒。基线 359 项，新增平台 8、任务账本 17、采样集成 11。 |
| 本机浏览器 | Chromium 全量及 M08 定向通过。M08 包含 320/390 px、键盘、冻结计划、故障切换、暂停及刷新后继续、Excel 兜底、证据回读和零浏览器外发。 |
| 合成规模 | 3 个独立 M04 批次，120 条发现回执、60 个规范 URL、60 个访问页和 60 份 M05 快照，120 条精确候选片段。30/30 回读验证了当前许可、稳定记录与范围、原文摘要和 Unicode 码点切片。 |
| 漏斗与偏差 | 完整工程漏斗为 `60 / 60 / 120 / null / null`。正式五项均为 `null`。空集复验为工程 `0 / 0 / 0 / null / null`。保留查询、引擎、原始排名、时间窗、语言设定、来源及失败记录。跨源同文标为待核并保留各记录。 |
| 恢复与计量 | 重启、并发、暂停回读、同键重放、权限撤销、预算不足、在途未知、回执提交前中断、备份恢复均通过。规模用例模拟消耗 3 Tavily credit、3 Brave request、30 Stack Exchange request 和 30 YouTube quota unit。真实费用及调用为 0。 |
| SQLite | 正式工作库 v8、M08-A/B 演示账本 v1。新增独立任务账本 v1 与每任务独立 v8 工作库。M04 批次、M05 快照和本机恢复回执同事务。验证中断回滚、SQLite 一致性备份、恢复、`integrity_check`、`foreign_key_check`，以及正式库没有导入记录。 |
| 其他回归 | Node 2/2、Windows 空库冷启动 3/3、脱敏历史归档 4/4。覆盖 M06 六桶和两条等式、M07 注册表与 PackyCode 原预检证据。 |
| 平台部署 | 本轮源码 Windows 11 实机为 NOT_TESTED。历史 Windows 11 部署证据继续按其原源码记录。GitHub 的 Windows Server 2022 结果单独核对。 |

用 `python -m unittest discover -s tests -p 'test_*.py'`、`node --test tests/client_state.test.cjs`、`python scripts/cold_start.py`、`python tests/browser_e2e.py` 和 `bash scripts/check-no-secrets.sh` 复现。Windows 可用 `VOC_CHROMIUM` 指定已安装的 Chrome。M08 浏览器专项用 `python tests/browser_e2e.py --acquisition-only`。受限会话的原生 DPAPI 在全量浏览器凭证用例返回 503，普通 Windows 用户环境通过。继续记录既有 Starlette 弃用提示。

Stack Exchange、YouTube 顶层评论和 CSV/Excel 使用固定夹具。Reddit 未取得批准，保持禁用候选。YouTube 公共展示文本不能代替作者原文字段。正式 G1/G2/G7、INGEST、RAW、SOURCE-POLICY、PRIVACY 仍待真实证据，G-1 BLOCKED。M08-E 扩展至第二论坛、YouTube 评论深度访问及期刊背景对照。

[平台契约](../../architecture/m08-platform-retrieval-contract.md) · [任务契约](../../architecture/m08-acquisition-task-contract.md) · [M09 接续](../../architecture/m08-consumer-handover.md) · [独立复审](independent-verification.md) · [缺陷台账](bug-register.md)
