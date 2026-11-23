# P0-0 真实验收记录

**G-1 为 BLOCKED。六项检查中两项 PASS，四项 BLOCKED。** 批次 `84605f95-7aa1-4f30-93ad-08547334a78c` 使用 jevmodel 配置，于 2026-11-23 21:14:57 开始，21:17:58 完成第二次执行（北京时间）。原始时间戳为 UTC，界面截图按浏览器时区显示。验收分母为六个 C0 检查，正式研究样本数为零。

| 检查 | 结果 | 第二次执行的证据 ID | 已验证与阻塞原因 |
|---|---|---|---|
| C0-1 | BLOCKED | 16 | 后端生成 11 个唯一题名的 8+3 请求计划。缺少 JEVMODEL_API_KEY 和该供应商的真实语料留存审查，实际发送 0 个 Jev 分片。返回模型未知。 |
| C0-2 | BLOCKED | 16 | 缺少真实 Choice、Score、Noul 响应，Score 概率能力待核验。收到真实缺字段响应时才记录 schema_gap。本批没有推算概率。 |
| C0-3 | BLOCKED | 11–15 | 论坛搜索 API 查到网页，随后原帖接口核对问题 94603、许可 CC BY-SA 4.0、署名、发表时间和引用摘要。两接口各次均 HTTP 200。PDT 的公开搜索取证子项通过；专案指定的 Tavily 或 Brave 均未配置。 |
| C0-4 | BLOCKED | 17 | 重新连接实际 SQLite，批次与证据可读，完整性为 ok，外键违规为 0。Jev 分片用量行数为 0，余额未同步。 |
| C0-5 | PASS | 18 | 六个出口共 36 个合成限制案例全部在传输前拦截，外发 0 次，公开对照正常。断网及 401 / 402 / 422 / 429 / 502 注入使用真实分片执行逻辑，检查暂停、同键退避及不启动第二片。 |
| C0-6 | PASS | 19 | 独立内存 SQLite 载入 2 个产品品类、3 个任务大类、30 个合成意图。两次跨品类期望意图均进入全库 Top-12，附加 None 后 13 个选项。保留索引、模型和注册表版本。J-14 的人工盲测另行验收。 |
| G-1 | BLOCKED | 20 | 同批 C0-1 至 C0-4 与供应商留存审查待完成。P0、P1、P2 待前序准入。 |

## 可独立核对的证据

[run.json](run.json) 保存两次执行的 20 条脱敏证据及最后一次的需求映射。时间、实际返回状态、请求参数、返回字段投影、原始 JSON 内容的规范化摘要、原帖链接与引用摘要均可核对。没有发出的请求，其 HTTP 状态为 null。原话和署名可在本机原始证据库回看。公开摘录校验使用原句 UTF-8 的 SHA-256。

[audit.sqlite3](audit.sqlite3) 是从上述运行导出的最小可公开数据库，包含 metadata、checks、evidence、check_evidence 和 usage_ledger。源运行库的 PRAGMA 检查结果也随批次保存。两次执行各有两条外部 HTTP 200，共四条。Jev 记录的输入用量与账户余额均未知。

```sh
python -m src.outputs.audit_receipt --verify docs/evidence/p0-0
```

| 文件 | 文件字节 SHA-256 |
|---|---|
| run.json | 0216cbe253f6d4796a3dac08fac4d9b7e7b952c00641252b306b303af2a35d35 |
| audit.sqlite3 | 48530ca3c92fc8b477dd3a799fb88aada52f944ef34fbe61d4b932f97cbe0d54 |

可在 SQLite 客户端执行以下只读查询。第一条按需求取回真实证据，第二条返回本批已观察到的 HTTP 状态，第三条查询分片计量。空账本表示尚无可记录的实际 Jev 用量。

```sql
SELECT c.requirement_id, c.status, e.id, e.name, e.status_code, e.checked_at
FROM checks AS c JOIN check_evidence AS x USING(requirement_id)
JOIN evidence AS e ON e.id=x.id ORDER BY c.requirement_id,e.id;

SELECT name, status_code, count(*) AS observations
FROM evidence WHERE mode='live_http' GROUP BY name,status_code;
SELECT shard_no, tokens, remaining FROM usage_ledger;
```

## 工程与浏览器复测

本机实际运行单元与接口测试、Linux 三次独立空库冷启动、正式在线检查和只读证据核对。全门在线测试退出码为 2。首次运行与恢复保留相同批次 ID 和两组时间戳。Chromium 实际浏览器交互覆盖状态筛选、查看原话的证据抽屉、搜索验收矩阵、空结果、未同步额度、恢复批次与 JSON 下载。390 × 844 CSS 像素的窄屏浏览器测试使用同一套页面资源与本机接口，内容区宽度与滚动宽度均为 375 像素，折叠导航可以进入验收矩阵。

Windows 启动脚本和独立 Playwright 复测脚本随代码交付。当前系统为 Linux，Windows 三次冷启动的 G0 尚未验收。本机终端 Chromium 进程受运行环境的 Unix socket 限制，桌面与窄屏交互通过托管 Chromium 的 Playwright 控制接口实际执行。

[连通性首屏](connectivity.jpg) · [原话证据抽屉](evidence.jpg) · [验收矩阵](requirements.jpg) · [额度中心](tokens.jpg) · [窄屏截图](mobile.png)

## 下轮准入条件

在实际运行的后端配置一个具备固定 jev-1.14.0 权限的供应商账户，并附该供应商的留存审查。再配置 Tavily 或 Brave 中至少一个。用同一批次恢复或新建真实批次，核对两个分片的 model、问题键、Score 完整概率、usage.input_tokens 与余额状态。若某服务商缺概率或不接受固定版本，保留其真实响应；更换服务商后单独运行和审核。G-1 通过后首先交付 CSV 导入、不可覆盖的原始证据与采样批次。
