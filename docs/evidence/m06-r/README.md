# M06-R 工程复审与验收

开发分支为 `codex/p0-0-connectivity`。进入基线为 `7b26d8da89db636c7e3f4ad73490b53dcc555155`。上轮 C5 实测源码为 `a9eebee24616984dda8e72bab1242373555b06db`，与进入基线之间仅有 15 个文档和证据文件变更。M06-R 修复和规模测量源码为 `eb0e2c0780cb15ed413eaca206ff9ce2615b4b0a`，最终实机归档源码为 `9c27231376fcc32aae39a9b63df6fa9b9b98c4c6`，后者仅增加两条永久分母回归。验收提交在该归档上补充文档和脱敏证据。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45573612526) · [修复源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45580317606) · [草稿 PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1)

| 材料 | 核验范围 |
| --- | --- |
| [工程审计](../../audits/m06-final-engineering-audit.md) | M01–M06 源码、跨模块边界及历史依据。 |
| [独立复验](independent-verification.md) | 25 项反例及双项目手算账。 |
| [缺陷台账](bug-register.md) | 复现、严重程度、修复及复验。 |
| [规模复验](performance-comparison.md) | 1K/10K/100K 查询计划、耗时、完整响应等价性及独立恢复。 |
| [Windows 11 脱敏清单](windows11-manifest.json) | 固定源码、系统、用例数、退出码、SQLite、DPAPI 和归档核验。 |
| [独立浏览器复审](browser-observations.md) · [实机合成截图](screenshots/README.md) | 撤权、错误和重试，真实回环请求，九个导航入口及两个视口。 |
| [后续接入契约](../../architecture/m06-consumer-handover.md) | M07–M15 可用接口、授权边界及待建接口。 |

## 运行范围

使用原生 Windows 11 Enterprise 25H2，Build 26200.8655，AMD64，普通用户未提权。环境为 PowerShell 7.6.9、Git 2.55.0.windows.5、Python 3.12.9、Node v24.19.0、SQLite 3.45.3、Playwright 1.65.2 与 Chromium 159.0.8154.6。使用隔离源码归档、临时 SQLite、合成夹具和既有脱敏归档。真实研究 API 调用为 0。用户选择 Sol Ultra，会话模型设置未能独立核验。主代理统一集成，导入与许可、统计性能、界面分别由协作代理复核。专案 v2.2 的 27 页 PDF 原件待补，复审使用仓库摘要和批准记录。

| 证据 | 实测结果 |
| --- | --- |
| 原版本基线 | Windows 11 Python 269/269，125.199 秒。Node 2/2。两项均退出 0。 |
| 修复定向 | M04/M05 7/7，C4/C5 25/25，含双项目手算账。两项均退出 0。 |
| Windows 11 全量 | Python 277/277，191.155 秒，既有 269 项及新增 8 项，失败、错误和跳过均为 0。Node 2/2，无失败、取消或跳过。 |
| Python 专项复跑 | C1 约束 22/22、迁移 11/11，C2 17/17，C3 25/25，C4 34/34，C5 25/25。M05 语料 16/16、许可 10/10，Pre-M06 A–H 套件 19/19。专项与全量有重叠。 |
| 实机 UI 和 HTTP | Chromium 11/11 组、本机 HTTP 2/2 组。补充独立键盘导航 18/18。生成 26 张合成截图，复核并归档 5 张。 |
| 冷启动、启动器及凭证 | 空库冷启动 3/3。普通、中文、含空格路径各两轮，包括同库重启、首页及健康 API、正常停止、端口释放。启动器验证退出 0，发送 Ctrl+Break 后的批处理状态为 3。DPAPI CurrentUser 加密、重启读取和删除通过，所检查的浏览器、响应、日志及运行文件中无合成明文标记。 |
| 数据库和安全 | 脱敏归档 4/4，证据行数 20、10、10、10。SQLite v1–v6 历史库逐一升级至 v7 并重启比对稳定记录，合成库和诊断库为 v1。完整性均为 `ok`，外键违规 0。源码秘密扫描通过。 |
| 规模与恢复 | 1K/10K/100K 的批量与逐条响应、旧版与候选响应均等价，比较时仅剔除 `as_of_utc`。三档并发撤销、异常退出、活跃 WAL 备份及独立恢复通过。十万条 P95 为 39.073 秒，15 秒探索目标待后续优化。 |
| GitHub | Ubuntu、Windows Server 2022、Chromium 的修复源码检查已通过。最终验收提交的同 SHA 作业见 [PR 检查](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1/checks)。 |

原生 Windows 11 归档的 21 个验证分组和独立导航探针均退出 0。

## 当前门禁

归档源码的 **WINDOWS_11_REAL_MACHINE = PASS**，**WINDOWS_11_DEPLOYMENT_GATE = PASS**。本验收提交在开发分支和草稿 PR #1 同一 SHA 的三项 CI 均通过时，**M06_IMPLEMENTATION = ENGINEERING_PASS**、**M06-R = PASS**、**M06_ENGINEERING_BASELINE = FROZEN** 生效。冻结覆盖核心数据接口、行为和兼容契约，后续合法修复仍按原审批及回归流程执行。

G-1 = **BLOCKED**，PRE_M06_DEVELOPMENT_GATE = **PASS**，M07–M15 = **NOT_STARTED**。SQLite 保持 v7，沿用五项负责人批准的业务政策与 `M06-B-F.1`。正式 CAT、J-14、逐源许可、删除审计、真实采样及编码、金标准与正式发布仍需按[原验收矩阵](../../requirements-matrix.md)取证。
