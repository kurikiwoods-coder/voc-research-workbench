# P0-0 工程回归与实测

基线为 `9928025`。后端修复提交为 `de54e78`，界面和启动脚本提交为 `eb5bb2c`。PDT v1.3.1 Word 文件的 SHA-256 为 `09edf47c95151276b39c4b375cd1e7e1f805591fb8d65b8f2c512087283a11b7`。§13.0、附录 C、附录 D 和需求矩阵继续作为验收依据。

## 复现与修复

| 问题 | 复现与回归 |
|---|---|
| 一个搜索引擎能占满正文验证次数 | Tavily 返回多个失效地址时，旧版跳过了可用的 Brave 和公开论坛地址。现在为两条指定搜索通道交替安排回源，并为论坛保留回退次数。错误署名、未知许可和非法发布日期会跳过当前帖子，保留该次 HTTP 结果。 |
| Jev 返回类型异常时校验中断 | Choice 的数组值触发 TypeError，超出范围的数字也可能中断校验。现在可以识别具体缺失字段。非法 JSON 数字保留实际 HTTP 状态和解析错误。Score 依然要求原响应提供完整逐档概率。 |
| 分片响应与额度账本会分开提交 | 注入存储错误时，旧版留下响应但分片仍为发送中。现在同一笔 SQLite 事务保存响应和账本。旧批次可凭同一请求键、完整请求体与已保存的 HTTP 200 回填，恢复时只发送未完成的分片。 |
| 缺少当前余额头仍显示旧余额 | 第二片缺余额头、或供应商返回认证失败时，当前余额显示未同步，保存历史用量和上次同步时间。顶部明确显示缺密钥状态，额度页可打开连接配置。低余额和临界额度各有提示。 |
| 键盘导航和错误恢复 | 跳至正文保留额度页及原 URL。浏览器返回会关闭上一页的抽屉。异常片段回到检查页。画面可直接重读真实 503，SQLite 写锁冲突的 409 有明确提示，重读失败也会在已打开的抽屉中显示。 |
| Windows 启动目录与失败处理 | 启动入口使用成对的 `pushd` 和 `popd`，配置文件创建失败会退出，保留运行过程退出码。验证 checkout 和 Git 源码 ZIP 都保留脚本的 CRLF。解压到含中文和空格的目录后，在 Linux 实际三次空库启动成功。Windows 原生环境待验证。 |

基线在补入故障复现用例后出现 5 个断言失败和 2 个异常。最终工程回归为 31 项通过。外部响应及故障夹具仅在离线工程测试库执行。[基线复现](baseline-failures.txt) · [最终测试输出](smoke-tests.txt) · [启动兼容性检查](windows-review.txt) · [Windows pushd 文档](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/pushd)

## 六项正式复跑

批次 `ffc9fea1-cbd6-40ac-a96b-a848783a561b` 于北京时间 2026-11-23 22:09 执行。命令退出码为 2，确认阶段准入阻塞。归档共有 10 条证据，包括两条真实 HTTP 200。SQLite 完整性为 `ok`，外键违规为 0，真实 Jev 分片为 0。[运行输出](live-gate.txt) · [脱敏 JSON](run.json) · [审计 SQLite](audit.sqlite3)

| 检查 | 状态 | 证据和阻塞原因 |
|---|---|---|
| C0-1 | BLOCKED | 证据 #6 保存固定 `jev-1.14.0` 与 8+3 请求计划。JevModel 后端密钥与供应商留存记录缺失，实际 HTTP 状态为空。 |
| C0-2 | BLOCKED | 证据 #6 保存同一预检。真实 Choice、Score、Noul 待验收，尚无实际 Score 分布可判断。 |
| C0-3 | BLOCKED | 证据 #3 和 #4 为论坛搜索、回源 HTTP 200。#5 单列 PDT 公开原话子项与指定搜索引擎子项。Tavily、Brave 均未配置。 |
| C0-4 | BLOCKED | 证据 #7 保存实际 SQLite 回读结果和空账本。两片实际 usage 待回填，当前余额未同步。 |
| C0-5 | PASS | 证据 #8 记录 36 次内外发边界测试和六种合成故障的暂停、重试与隔离。 |
| C0-6 | PASS | 证据 #9 记录三层关系，2 个产品品类、3 个任务大类、30 个合成意图，两次跨品类查询均命中预期 Top-12。 |
| G-1 | BLOCKED | 证据 #10 汇总同批结果，P0 继续等待准入。 |

```sh
python -m src.outputs.audit_receipt --verify docs/evidence/p0-0/regression
```

| 归档 | SHA-256 |
|---|---|
| run.json | 5dc8ac375abc7237afdbba34ada823f0847a12c31d5ee6342b79ce96a23e09e5 |
| audit.sqlite3 | 2f81fba853fc0e46ba513d4733dd44180a6e7efa4160650064541f8ec34c3c34 |

## 浏览器与 Windows

托管 Chromium 以 Playwright 实际完成 13 个检查点，覆盖从空库发起批次、筛选、搜索、抽屉、下载、同批恢复、额度刷新和错误重试。浏览器批次 `518662c9-1f2b-485a-8395-52be28f838ef` 有两次执行和四条源站 HTTP 200，SQLite 仅有一个批次，Jev 账本为空。320 与 390 CSS 像素下，导航可开关，矩阵和额度页的文档宽度未超过视口。受控 503 只用于本机界面恢复测试。终端运行 Playwright 的 Chromium 受执行环境 Socket 权限限制，浏览器实测通过托管 Chromium 完成。[浏览器检查点](browser-results.json) · [检查页](connectivity.jpg) · [原话证据](evidence.jpg) · [额度中心](tokens.jpg) · [390 像素窄屏](mobile.jpg)

Windows `cmd.exe` 未在当前 Linux 环境运行。G0 的三次 Windows 冷启动仍为 `NOT_TESTED`，Git 源码 ZIP 核对和 Linux 独立空库冷启动已完成。[兼容性结果](windows-review.txt)

## 待确认的供应商恢复边界

供应商已收请求、但本机在保存响应前中断时，SQLite 只有预留的请求键和摘要。此时不能从本机账本判断是否扣费。现有恢复先重放已落盘响应，查不到确定响应时保留待核对。Astra Max 可在账户授权后分别确认 JevModel 与 TypeSafe 是否提供按请求键查询结果或明确的计费幂等保证，再验证一次「服务商已接收、本机先断开」的演练。要验收的是同一个请求键和供应商计费记录，与本机唯一分片用量可逐条对账。真实调用应使用已选且审查通过的供应商。
