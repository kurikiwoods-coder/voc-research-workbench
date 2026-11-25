# G-1-R-B-P 合成接口预检证据

2026-11-25，从开发分支 `3390e00fc0540f1b60608fb714246477b530f71e` 接续。此基线的 Ubuntu、Windows Server 2022 和 Chromium CI 全部成功。[草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45623983177)

## 供应商公开资料

PackyAPI 公布全球生产域名、Jev 官方分组和固定模型。模型详情显示每百万输入 Token 0.2940 美元，输出 0 美元。PackyAPI 2026-10-15 的公开公告和 TypeSafe 文档描述默认 64K 上下文，超长上下文需带额外请求头，本机入口未设置该头。公开文档未说明单次在途扣费超额、网关重试和上游内部计量的处理方式。[全球网关](https://docs.packyapi.com/docs/register/6-cli.html) · [分组](https://docs.packyapi.com/docs/token/2-group.html) · [价格和协议](https://www.packyapi.ai/pricing/jev-1.14.0) · [条款](https://docs.packyapi.com/docs/tos/TOS.html) · [TypeSafe 上下文](https://docs.typesafe.ai/models#context-length) · [TypeSafe 请求与响应](https://docs.typesafe.ai/api/system-one) · [Score 档位说明](https://docs.typesafe.ai/primitives/score#response-structure)

## 工程证据

| 检查 | 结果 |
| --- | --- |
| 普通 Windows 10 用户 DPAPI | 合成字节 CurrentUser 往返 PASS。预检测试不使用真实凭证 |
| 独立预检专项 Python | 最终预算规则 12/12。覆盖固定请求、CLI、DPAPI 版本、令牌限额、首片对账、分片间凭证轮换、并发、HTTP 失败、契约缺项和 SQLite 完整性 |
| Windows 10 全量 Python | 初版工程 325/325，包含既有 313 项和新增 12 项。普通用户会话于隔离源码运行 `python -m unittest discover -s tests -p 'test_*.py'`，74.047 秒，OK |
| Chromium E2E | 13/13，Windows 10 普通用户会话，Playwright 1.65.2 和 Chrome 157.0.8103.80。覆盖 PackyCode 凭证生命周期及旧在线诊断持续受阻 |
| 未改动基线专项 | Node 2/2、SQLite v8 空库冷启动 3/3、历史归档 4/4。正式 v8 工作库、独立预检 v1 账本 |
| 敏感信息扫描 | 仓库规则扫描跟踪文件及本轮新增文件，通过 |

原有 `StarletteDeprecationWarning` 仍出现。Codex 沙箱用户的凭证测试发生 DPAPI 503，普通 Windows 用户会话复测通过。测试使用独立源码副本、临时 SQLite、合成夹具及模拟传输。

## 真实接口状态

北京时间 2026-11-25，负责人提供限额测试令牌截图。本机在普通用户会话核对 DPAPI 凭证掩码一致，截图显示令牌为启用、分组 `typesafe-officially`、无限额度关闭、余额及上限均为 2.00 美元、额度不重置，显示到期时间为 2026-11-26 21:13:22。原图及账户材料留在本机。

首片 HTTP **200**，返回 `jev-1.14.0`，八个题号对齐。Choice 三项完整、Score 三档概率及档位说明完整、六题 Noul 独立概率完整。接口实报 **488 输入 / 162 输出 Token**。SQLite `integrity_check` 为 `ok`，外键违规和正式研究结果均为 **0**。

## 第二片续接记录

2026-11-25，从 `12ab14aa1aeaa05bd137b5d35ad0c2b2cbcc6420` 接续。旧账本仍只有首片预约，首片原回执及响应证据保留在本机。核对首片响应、账本和原 DPAPI 密文版本，SQLite 完整性检查为 `ok`，外键违规和正式研究结果均为 0。[续接基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45633127275)

负责人提供的控制台截图显示北京时间 2026-11-25 22:00 时段 `jev-1.14.0` 消费汇总 **$0.0001**。同日 22:08 的单笔消费明细与首片相符，分组 `typesafe-officially`，模型 `jev-1.14.0`，488 输入 / 162 输出 Token，实扣 **$0.000144**。测试令牌列表显示一次请求及「花费」**$0.01**。调用前额度为 **$2.00**，当前剩余额度待按控制台相应字段核对。原图及未脱敏材料留在本机。

专项回归 **15/15**，其中新增 3 项覆盖保留历史证据、同批次只补第 2 片、对账失败关闭、凭证或账本变动、并发和中断后拒绝重发。测试均为模拟传输。本机 Windows 用户上下文运行 `python -m unittest discover -s tests -p 'test_*.py'`，全量 **328/328**，79.115 秒，OK。按首片实报输入和第二片估算，预计合计 **66,024** 输入 Token。

合成接口契约仍为 **PARTIAL**。累计真实模型 POST **1**，第二片等待核对当前令牌余额。此时无第二片实际用量和 11 题合并结果。

当前供应商账户审批为 **PENDING**，正式研究 API 调用 **0**。`G-1 = BLOCKED`，仍需实际通道供应商审核及同一正式批次 C0-1 至 C0-6。M06 工程为 **FROZEN**，M07 为 **ENGINEERING_PASS**。

[操作说明](../../packycode.md#一次性合成接口预检) · [授权及工程隔离](../../decisions/packycode-synthetic-preflight.md)
