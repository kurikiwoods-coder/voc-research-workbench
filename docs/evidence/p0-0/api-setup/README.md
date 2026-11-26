# P0-0 API 接入测试

2026-11-24 从 `4daaf7b371` 延续开发。TypeSafe、JevModel、Tavily 与 Brave 可在首次向导和「设置 → API 接入」管理。YouTube 和 Google Forms 提供后续接入资料。[使用说明](../../../connectivity.md#从工作台配置-api) · [PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1)

## 工程验收

| 测试范围 | 结果 |
|---|---|
| 本地 Linux 全量回归 | 46 项 Python、2 项 Node 和 3 次冷启动通过 |
| GitHub Ubuntu | 46 项 Python、2 项 Node、3 次冷启动及归档核验通过 |
| GitHub Windows Server 2022 | 46 项 Python、2 项 Node、3 次冷启动及归档核验通过。真实启动器从含中文和空格的目录运行成功 |
| GitHub Chromium Playwright | 1 套通过。覆盖零密钥启动、向导、保存、更换、刷新、删除、诊断、运行正式批次及 320/390 像素宽度 |
| Windows 10/11 真机 | NOT_TESTED |

Python 新增用例共 14 项，包括跨源和非回环请求拦截、输入校验无密钥回显、轮换和重启持久化、Windows DPAPI、Linux 权限、写入失败恢复、供应商留存材料核对、诊断账本隔离，以及固定模型、分片、来源和错误状态的隔离响应夹具。浏览器的凭证采用测试字符串。Jev 检查因缺真实审核停在预检，搜索检查在零密钥时只写本机诊断。[本地回归输出](smoke.log) · [Windows Server 输出](windows-smoke.log) · [Windows 启动脚本结果](windows-launcher-result.log) · [浏览器输出](browser.log)

首轮托管 Chromium 发现测试程序使用了无基址的相对 URL。修复后重新运行并完成全套断言。当前容器的 Chromium 启动受套接字权限限制，浏览器截图和通过记录来自 GitHub 托管 Chromium。[首轮 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45314923430) · [浏览器复测与截图来源](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45315273417) · [运行记录 JSON](browser-workflow.json)

[首次配置向导](browser/api-wizard.png) · [桌面 API 接入](browser/connection-settings.png) · [390 像素移动端](browser/mobile-api-setup.png)

## 正式批次

批次 `7fbcdf4d-3e8b-4f02-9974-ce52fe1a520e` 在缺少四家 API 凭证与 Jev 留存审核的工作区执行。公开论坛搜索及原帖接口各返回一次 HTTP 200。认证 Jev、Tavily 与 Brave 请求为零。SQLite 完整性与 JSON 归档一致，正式研究分母及 Jev 分片均为零。命令退出码为 2。[实际命令输出](live-gate.log) · [脱敏 JSON](live-receipt/run.json) · [审计 SQLite](live-receipt/audit.sqlite3) · [归档核验](live-receipt-verification.json)

| 要求 | 状态 | 当前证据或阻塞 |
|---|---|---|
| C0-1 | BLOCKED | 等待固定 `jev-1.14.0` 和实发 8 + 3 分片 |
| C0-2 | BLOCKED | 等待 Choice、Score、Noul 真实返回及完整概率 |
| C0-3 | BLOCKED | 论坛回源已通过。等待 Tavily 或 Brave 实际发现合规原帖 |
| C0-4 | BLOCKED | 库已核对。等待真实 Jev 输入用量和可核验余额 |
| C0-5 | PASS | 本地隔离及故障演练验证 |
| C0-6 | PASS | 三层关系及跨品类召回验证 |
| G-1 | BLOCKED | 当前阶段为 P0-0 |

可在取得真实权限后，从 API 接入页完成同一条验收路径。[供应商取钥](../../../connectivity.md#注册与创建密钥)
