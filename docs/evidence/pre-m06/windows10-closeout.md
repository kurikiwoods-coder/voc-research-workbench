# Pre-M06-D Windows 10 实机验收

2026-11-24，Windows 10 Home China 22H2 x64，OS Build `19045.6466`。核对时本机工作树干净，`codex/p0-0-connectivity` 的本机 HEAD、远端分支和草稿 PR #1 对应验收代码基线 `4e6369b92205c51671866935365678df351ec808`。本次冻结提交记录验收文档，测试结果绑定上述代码基线。[基线提交](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/4e6369b92205c51671866935365678df351ec808) · [PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1)

| 证据来源 | 环境与结果 |
|---|---|
| 项目负责人手动实测 | 普通登录用户 PowerShell。当前用户 DPAPI 加密、解密通过。Python 全量 140/140，17.747 秒，最终 `OK`。原版 Chromium 8/8，最终 `Chromium E2E passed`。M02 向导和合成凭证保存、轮换、删除，M01 连通性和批次记录，M03 项目、M04 导入、M05 语料审核、撤销和重新授权均通过。M03、M04、M05 重启后的数据回查通过。 |
| Codex 本机实测 | 同一代码基线的 Pre-M06-L。Node 2/2、空库冷启动 3/3、历史归档完整性 4/4、敏感信息扫描通过。两次中文及空格路径启动均返回健康状态和 schema 6，关闭后回环端口释放。SQLite 完整性通过，外键错误 0，旧库 v1 → v6 和 v5 → v6 回归通过。 |
| Codex 执行会话限制 | 合成字节的 DPAPI CurrentUser 在仓库调用中返回 Win32 2，独立 .NET 探针也失败。应用合成凭证写入返回 HTTP 503。该会话 Python 执行 140 项，131 通过、6 失败、3 报错，原版 Chromium 在 M02 中止。补测八个页面及 M03、M04、M05 主流程和重启回查通过。凭证保护实现维持现状。 |
| GitHub CI | 同一代码基线的 Ubuntu、Windows Server 2022 和 Chromium 作业均成功。[Actions #32](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45374179477) |

## 证据核对

本机 `test-results/browser` 下有 16 张原版 Playwright 截图，文件时间集中在 2026-11-24 21:31:24 至 21:31:39（UTC+08:00）。Codex 检查了图像可读性和画面，覆盖 M02 配置、M01 连通性及证据、M03 项目、M04 导入、M05 原始语料，含窄屏画面。以下为代表性原始产物的 SHA-256。

| 截图 | SHA-256 |
|---|---|
| `connection-settings.png` | `52637e3d6d4b2350ef0e433ca9156fc3ee1804817d5edc2dc76d5dd090dc8a44` |
| `connectivity.png` | `c4f6c03d8b48ea6b63c79abd66c742e7d4140cc5963cd489d09a448786bd1617` |
| `m03-project-list.png` | `8cd09c446b36204afa8b9431ea9c8ff064ff3d9b51d512388fa40edb5bc0ac1d` |
| `m04-quality.png` | `e094db16cf00ec0bd71eab8ffe8a9ee08d762e326ece64f51f9010aff3ca6137` |
| `m05-mobile-review.png` | `7084d2175551345dcea9e765be88abcaf7f3d34e49c18587cb896b44c0ac56f3` |

已查阅的本机目录中未发现普通 PowerShell 手动测试的终端转录。该会话的 DPAPI、Python 耗时与计数、Chromium 最终结论及重启回查由执行者提供。截图佐证浏览器流程，Pre-M06-L 的原始日志佐证 Codex 项下的结果。原始截图和日志留存在本机，仓库只登记脱敏摘要和指纹。工程验收使用合成夹具、隔离 SQLite 与既有脱敏归档。真实研究 API 调用为 0。

## 工程状态

- Windows 10 实机工程验收 **PASS**，证据合并普通登录用户会话与 Pre-M06-L 隔离本机检查。
- Windows 11 实机 **NOT_TESTED**。Pre-M06 Gate 为 **PRE_M06_GATE_BLOCKED**，G-1 为 **BLOCKED**。
- `StarletteDeprecationWarning` 记录为非阻塞性技术债务。此提示来自 Starlette TestClient 的 `httpx` 集成，留待依赖维护时验证兼容方案。
- M03 冻结范围、M05 实时资格和现有端到端证据已具备支持 M06-A 架构设计的工程基础。设计等待单独授权，正式实现与语料接入按既有条件放行。
