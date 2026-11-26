# M08-V 本机回归结果

源码 `74590d4a4d43a66c7a3296943da9205bc6ff65e0`。下列回归均使用原生 Windows 11 普通用户、空的隔离运行目录及合成夹具。

| 验证 | 通过 | 失败 | 跳过 | 退出码 |
| --- | ---: | ---: | ---: | ---: |
| `python -m unittest discover -s tests -p 'test_*.py' -v` | 395 | 0 | 0 | 0 |
| M07 迁移、M08 任务与采样独立定向复跑 | 32 | 0 | 0 | 0 |
| `node --test tests/client_state.test.cjs` | 2 | 0 | 0 | 0 |
| `python scripts/cold_start.py` | 3 | 0 | 0 | 0 |
| Chromium 全量、采集专项及 PackyCode 专项 | 3 次运行 | 0 | 0 | 各 0 |
| 独立 Chromium 键盘导航，320/390 px 各 11 条路由 | 22 | 0 | 0 | 0 |
| 四份历史脱敏归档 | 4 | 0 | 0 | 各 0 |
| 普通、中文、含空格路径启动器及同库重启 | 6 | 0 | 0 | 验证程序 0 |
| DPAPI CurrentUser 及应用凭证生命周期 | 1 | 0 | 0 | 0 |
| `bash scripts/check-no-secrets.sh` | 1 | 0 | 0 | 0 |

Python 395 项与 Windows 10 基线数量一致，本轮复验新增 0 项，运行 253.747 秒。32 项定向复跑已包含在全量计数中。Node 另有 0 项取消。Chromium 全量开启 13 个受保护浏览器上下文，生成 34 张本机合成截图。采集专项 1 个上下文，PackyCode 专项 2 个上下文。使用 `python tests/browser_e2e.py`、`--acquisition-only` 和 `--packycode-only` 执行。全量、专项及独立探针的外部浏览器请求和 Python 外部连接尝试均为 0。独立 HTTP 探针同源返回 200，跨源返回 403，不受信任 Host 返回 400。响应仅允许同源连接且禁止缓存。

| 模块 | 实际回归 |
| --- | --- |
| M01–M02 | 回环启动、连通性、API 配置及 Token Center、故障与恢复、原生 DPAPI。 |
| M03–M05 | 项目及冻结范围、CSV/XLSX 批次、字段映射与质量、快照、去重、来源许可与撤销。 |
| M06 | 稳定发生及证据、三层双向关系、精确版本、项目权限、同连接事务资格、六桶、两条恒等式及正式 `unavailable/null`。 |
| M07 | 21 项注册表定向用例包含于全量。覆盖候选及封版定义、搜索筛选、主次关系、问卷状态、历史版本、差异、私有草稿、预检、权限及消费。 |
| M08 | 67 项定向用例包含于全量。覆盖 Tavily/Brave 演示、合成 Stack Exchange 与 YouTube、禁用 Reddit、CSV/XLSX、冻结、暂停继续、重启、预算、未知预约、切换与重放、当前授权及正式隔离。3 批 120 精确片段和 30/30 回读断言通过，正式五项计数为 `null`。 |
| PackyCode | 30 项工程和合成预检用例包含于全量。验证独立卡片、批准状态、固定 `jev-1.14.0`、`typesafe-officially`、端点白名单、SystemOne、8+3 合成契约、Choice/Score/Noul、用量预算、失败关闭、未授权外发阻断及其他 Jev 通道兼容。 |

PackyCode 专项用临时合成凭证验证 Win32 DPAPI CurrentUser 往返、加密持久化、重启读取、删除及二次重启。状态为 `REVIEW_REQUIRED`，校验拒绝返回 422。浏览器 DOM、存储、控制台、HTTP、日志和运行文件未发现合成凭证明文。真实供应商探针为 0，历史真实合成回执沿用既有归档。

原版 `scripts/start-windows.cmd` 用本地离线依赖，在三种路径各做首次启动和同库重启。每轮首页、`/api/health`、`/api/workspace` 均为 200，SQLite v8 中的合成项目持续可读，Uvicorn 正常停止，8765 可独占重新绑定。批处理收到 Ctrl+Break 的退出码为 3，验证程序退出码为 0。

历史归档 `p0-0`、`p0-0/regression`、`p0-0/api-setup/live-receipt`、`p0-0/tavily-live` 均由 `src.outputs.audit_receipt --verify` 本机校验，SQLite 完整性均为 `ok`。
