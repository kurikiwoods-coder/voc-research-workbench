# P0-0 本地运行与取证

工作台接受任意研究主题。StudyScope 可关联零个、一个或多个产品品类。这里的厨房论坛检索词是稳定的小型技术探针。召回演练的智能手表与空气净化器同属合成测试域。两组材料都不进入正式研究统计。

## 启动

Windows 10/11 安装 64 位 Python 3.12，自开发分支下载代码并解压，双击 `scripts/start-windows.cmd`。脚本在项目内创建虚拟环境和空白配置，安装依赖，然后启动服务。打开 <http://127.0.0.1:8765/>。可在 PowerShell 的项目目录手动执行下列命令。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
```

已有 .env 时请直接编辑原文件。macOS/Linux 使用 Python 3.12。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
python -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
```

打开「连通性检查」，点「运行检查」后确认本次范围。连通性运行会尝试当前可用的服务。查看页面、刷新余额和下载现有证据只访问本机。批次中断后从「运行记录 → 查看批次 → 恢复此批次」继续。成功分片重放缓存，结果保留此前各次执行的时间与证据 ID。缺失凭证的批次可在首次配置密钥后恢复；已有 Jev 请求的批次绑定原账户。更换账户请建新批次。

## 后端配置

| 变量 | 用途 |
|---|---|
| JEV_PROVIDER | jevmodel 为默认第三方通道，typesafe 为官方通道。选择哪个就只调用哪个。固定模型写入程序。 |
| JEVMODEL_API_KEY / TYPESAFE_API_KEY | 填写所选服务商的账户凭证。服务重启时读取。 |
| TAVILY_API_KEY / BRAVE_API_KEY | C0-3 综合验收至少一个指定引擎须实际发现允许回源的链接。两个引擎各自留证。 |
| JEV_REVIEW_FILE | 本机 JSON 审查记录的路径。凭证文件保留在仓库之外。 |
| JEV_TOKEN_CAPACITY | 可选的、已核对的第三方账户额度上限，用于进度百分比和 20% / 5% 预警。余额未知时保留空值。官方货币账户单独展示。 |
| VOC_DATA_DIR | 诊断数据库目录，默认 runtime/。Windows 可填写用户目录下的绝对路径。 |
| YOUTUBE_API_KEY | 预留给 P0 的 YouTube 适配器。P0-0 不读取。 |

公开短句外发须有与服务商相符的留存审查。下表是 JSON 字段说明，运维应填写真实值，另存附件并计算 SHA-256。本机只对前端公开审核状态，对审计记录公开核验时间和摘要。

| 字段 | 所需信息 |
|---|---|
| provider / checked_at | 所选通道，及带时区的实际审核时间 |
| reviewer / region / terms_reference | 实际审查人、处理地区、已审条款版本或地址 |
| evidence_file / evidence_sha256 | 审查文件的本地路径（可相对 JSON）及文件 SHA-256。Windows 可用 Get-FileHash 查值，使用小写十六进制。 |
| public_text_approved | 实际批准发送经许可、脱敏公开原话时填写 true |
| zdr_enabled | TypeSafe 需要真实组织控制台的启用记录 |
| retention_reviewed / subprocessors_reviewed | 独立第三方 JevModel 的留存及转发链分别审查 |

内部 CX 与非公开材料只允许留在本机。后端的外发闸门先检查所有来源标签，混有内部或无授权标签时会在 HTTP 客户端调用前拒绝。前端只接受预定义探针和批次 UUID。审查记录是管理人员对组织设置的本地凭证，核验范围为供应商、审批字段、日期以及附件摘要。

## 数据与接口

SQLite 迁移位于 `src/raw_store/migrations/`。服务从空库启动时自动建表。runs 保存批次，attempts 保存重试，results/evidence 只追加。shards 以批次、分片号和正文摘要绑定幂等键，用于恢复和计量。进程锁保证同一数据目录一次仅执行一个写批次。真实公开样本是连通性证据。C0-5 使用单独的临时合成数据库，C0-6 使用内存数据库。本地正式研究分母为零。研究结束后，按来源保留策略管理和清理本机证据库及备份。

| 接口 | 用途 |
|---|---|
| GET /api/health | 检查服务和迁移版本 |
| GET /api/workspace | 当前验收矩阵、批次历史、配置是否就绪、当前账户的额度记录 |
| GET /api/workspace?run_id=UUID | 回到所选批次核查，同批计算状态 |
| POST /api/runs | JSON 含 request_key（UUID）；同键返回原批次 |
| POST /api/runs/{id}/resume | 恢复同一批次，保留各次尝试 |
| GET /api/runs/{id}/evidence | 本地完整的脱敏证据、时间、HTTP 状态和历次验收结果 |

写接口要求同源，使用请求头 `X-VOC-Action: connectivity`。本机信任 localhost 和 127.0.0.1。Jev 每片响应独立保留，输出概率须有合法范围与完整分布。不能确认是否已扣费的传输中断会暂停该分片并要求核对。401、402、422 会记录具体原因；429 和有幂等保证的 502 使用同键限次退避。长 Retry-After 留待后续恢复。Token Center 跳转供应商购买页，用量和余额的留存来源分别是 usage.input_tokens 与真实余额头。

## 来源边界

公开检索限定在预先登记的站点。搜索摘要只作候选线索。后端仅向固定 HTTPS API 发请求，核对原帖 ID、原网址、公开许可、署名和发表日期，摘录原话并登记采样时间。可在本机抽屉回看来源、引用和许可。仓库留存端点、字段、状态、摘要与合成演练，正文及署名保留在本机。Stack Exchange 许可来自各帖子返回的 content_license。源站维护、额度或权限异常时保留相应状态。[Stack Exchange API](https://api.stackexchange.com/docs) · [API 条款](https://stackoverflow.com/legal/api-terms-of-use)

固定版本与问答字段分别按管道核验。供应商的公开示例只用于编写适配器，最终以本账户的真实响应验收。[TypeSafe Score](https://docs.typesafe.ai/primitives/score) · [TypeSafe 数据使用](https://help.typesafe.ai/articles/5974925716) · [第三方接口文档](https://jevmodel.org/zh/docs/)

## 复测

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/cold_start.py
python -m playwright install chromium
python tests/browser_e2e.py
python tests/live_gate.py
```

离线工程测试使用独立临时目录。cold_start 会在运行操作系统上用三个独立空库真实启动和停止服务。浏览器脚本启动自己的本地临时服务，仅匿名访问公开来源，保存桌面、窄屏和抽屉截图到 test-results/browser/。指定现有 Chromium 时，可设置 VOC_CHROMIUM。live_gate 使用本机真实环境，凭证齐备时会产生供应商用量。退出码 0 表示全门通过，1 表示测试错误，2 表示存在阻塞。可在「运行记录」回看该次检查。四周历史与真实问卷继续等待相应阶段的运营样本。
