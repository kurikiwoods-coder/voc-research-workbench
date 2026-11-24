# M04 工程验收记录

2026-11-24。使用临时 SQLite 和合成 CSV、XLSX，供应商凭证不进入测试环境。真实 Jev、Tavily、Brave 请求各 0 次，G-1 为 BLOCKED。

| 工程范围 | 实际结果 |
|---|---|
| 本机 Linux | 95 项 Python、2 项 Node、3 次空库冷启动通过，0 失败。[输出](linux-smoke.log) |
| Ubuntu CI | 95 项 Python、2 项 Node、3 次冷启动通过，0 失败。[产物](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341223418/artifacts/14895409004) |
| Windows Server 2022 CI | 95 项 Python、2 项 Node、3 次冷启动通过，0 失败。中文与空格路径启动通过。[输出](windows-smoke.log) |
| Chromium CI | 6 组通过，0 失败。包括 M01 连通性、M02 配置、M03 操作与重启、M04 导入与重启。[输出](chromium.log) |
| SQLite 与 JSON 归档 | 4 份 P0-0 归档核对通过，历史认证 Tavily 的 C0-3 为 PASS。[输出](archived-receipts.log) |
| 数据量与内存 | 本机导入 5,000 条、7,623,958 字节的合成 CSV，端到端 1.37 秒。Linux 进程 RSS 峰值 204.3 MiB，试验前进程高水位 164.7 MiB。[输出](linux-load.log) |
| Windows 10/11 真机 | NOT_TESTED。 |

[三平台代码复测](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341223418) · [浏览器产物](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341223418/artifacts/14895554671)

## 验证覆盖

| 范围 | 验证 |
|---|---|
| CSV / XLSX 格式 | 标准 CSV、UTF-8 BOM、GB18030、四种分隔符、XLSX 多表、原生日期与两种模板。 |
| 映射与质量 | 自动与手工映射、必填原话、异常日期及评分及 URL、空内容、不齐整表格、范围不符、缺少许可与同表重复。 |
| 隐私和来源 | 内部 CX 与未核验记录进入本机暂存，正式研究和外发资格为零。原文件、原话、物理行号和扩展字段可追溯。 |
| 项目集成 | 只写所选项目与冻结范围，跨项目读写隔离。当前项目切换和范围后续修改不改变旧批次，归档阻止确认。 |
| 数据库 | 并发确认幂等、事务回滚、从 SQLite v2 升级、批次撤销、服务进程重启后回读。 |
| 上传与导出 | 超限、路径名、恶意 ZIP 结构、XML DTD、宏和公式。错误报告省略原话并防公式注入，XLSX 警告不暴露工作簿元数据。 |
| 浏览器 | 中文桌面和 320／390 像素。CSV 拖入、XLSX 文件选择、预览返回修改、确认、批次及下载。 |

[26 项新增 Python 用例](../../../tests/test_imports.py) · [Chromium 用例](../../../tests/imports_browser.py) · [SQLite v3 迁移](../../../src/raw_store/migrations/003_research_imports.sql)

## 浏览器截图

- [上传文件](m04-upload.png)
- [字段映射](m04-mapping.png)
- [质量检查](m04-quality.png)
- [移动端批次结果](m04-mobile-result.png)

## 工程复核

浏览器截图复核发现质量检查页沿用了映射页的滚动位置。页面切换将焦点放回阶段标题，并验证滚动回到顶部。用合成 Excel 打印区域元数据复现了解析器警告输出原表信息。导入时过滤可能含工作簿数据的库警告，保留工作台结构化错误和行号提示。

真实 G1、RAW 和跨批次去重仍须按原验收标准执行。
