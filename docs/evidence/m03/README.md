# M03 工程测试记录

2026-11-24。测试使用临时 SQLite、人工编写的测试课题和无供应商凭证的配置。工程测试不变更正式业务验收，G-1 保持 BLOCKED。

| 验证 | 实际结果 |
|---|---|
| Linux 本地 | Python 69 项、Node 2 项、空库冷启动 3 次，均通过，0 失败。[实际输出](linux-smoke.log) |
| Ubuntu CI | Python 69 项、Node 2 项、空库冷启动 3 次，均通过，0 失败。[产物](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45336483119/artifacts/14894042980) |
| Windows Server 2022 CI | Python 69 项、Node 2 项、空库冷启动 3 次，均通过，0 失败。通过中文及空格路径的 `start-windows.cmd` 启动。[实际输出](windows-smoke.log) |
| Chromium CI | 浏览器测试 4 组通过，0 失败。包括 M01 连通性、M02 配置中心、M03 项目操作与 M03 服务重启。[实际输出](chromium.log) |
| M03 单元与集成 | 新增 16 项，覆盖五种模式、版本冻结与隔离、并发提交、生命周期、回滚、v1 迁移和服务重开。[用例](../../../tests/test_studies.py) |
| 归档一致性 | 4 份已提交的 P0-0 SQLite 与 JSON 归档核验通过，历史 Tavily 批次保持 C0-3 PASS。[核验输出](archived-receipts.log) |
| Windows 10/11 真机 | NOT_TESTED。 |
| 本地 Chromium | 执行环境的 Chromium 因禁止创建浏览器 socket 无法启动。已在 GitHub Actions 的真实 Chromium 完成浏览器测试。 |

[最终工程复测 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45336483119) · [M03 浏览器用例](../../../tests/studies_browser.py)

## 截图

- [桌面项目列表](m03-project-list.png)
- [390 像素项目详情](m03-mobile-detail.png)
- [表单、详情及其他截图压缩包](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45336279837/artifacts/14893798757)

## 首轮复测修正

- 第一次 Chromium 运行在窄屏流程遇到同名链接定位冲突。当前项目与项目列表均提供同一入口，回归用例限定到项目列表区域。
- Windows Server 首轮两个旧库迁移用例在临时目录回收时遇到 WinError 32。迁移断言已执行，夹具显式关闭 SQLite 连接后完成清理。[首轮 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45336038813)

本轮 Tavily、Brave、Jev 真实请求均为 0。历史认证搜索的用量保留在原始归档。
