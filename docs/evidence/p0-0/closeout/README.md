# P0-0 工程收尾证据

2026-11-24 从 PR #1 的远端 `eb5bb2c169` 接续两项修复。正式验收保持 G-1 **BLOCKED**。[PR #1](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1) · [历史正式批次](../regression/README.md)

## 修复与复现

| 缺陷 | 基线复现 | 修复后的断言 |
|---|---|---|
| 恢复旧批次会误清另一个新请求的幂等键 | 首次请求结果无法读取后恢复旧批次，原键从会话消失 | 恢复请求保留原键。重试新请求使用同一键，取得新批次结果后才清除 |
| 旧响应覆盖最后选中的批次 | 先查看慢批次，再查看新批次，慢响应返回后抽屉跳回旧批次 | 只有最新一次读取更新批次信息，抽屉仍选中新批次 |

永久回归在基线为 0 通过、2 失败，应用修复后为 2 通过、0 失败。测试使用真实前端函数和隔离传输夹具。[复现日志](frontend-baseline.log) · [复测日志](frontend-retest.log) · [修复 `40b3a9a`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/40b3a9a)

连接配置列出四家供应商的注册入口、本机配置、所选批次的证据、能力差异和 G-1。SQLite 中收到响应后提交失败的用例另验证了重启恢复。进程重开后保留待核对状态，账本没有成功用量，原分片没有再发送。[配置与恢复测试 `7936f73`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/7936f73805aa4bbf0cc5aa8959d80c08b94dd81a) · [配置指南](../../../connectivity.md)

## 工程运行记录

| 环境或项目 | 通过 | 失败 | 未执行 |
|---|---:|---:|---:|
| 本地 Linux Python 与前端状态回归 | 32 + 2 | 0 | 0 |
| 本地 Linux 空库冷启动 | 3 | 0 | 0 |
| GitHub Ubuntu Python 与前端状态回归 | 32 + 2 | 0 | 0 |
| GitHub Windows Server 2022 Python 与前端状态回归 | 32 + 2 | 0 | 0 |
| GitHub Ubuntu / Windows Server 2022 空库冷启动 | 3 + 3 | 0 | 0 |
| Windows Server 2022 从中文及空格路径运行 `start-windows.cmd` | 1 | 0 | 0 |
| GitHub Chromium Playwright 套件，含 320 和 390 像素布局 | 1 | 0 | 0 |
| Windows 10/11 真机 | 0 | 0 | 1 |
| 本地 SQLite 与 JSON 归档复核 | 2 | 0 | 0 |

Chromium 通过真实 localhost 服务检查配置、运行批次、证据抽屉、筛选、导航、恢复、导出和响应式布局。容器中的本地 Chromium 启动受套接字权限限制，表中浏览器通过项来自 GitHub 托管运行环境。Windows Server 运行了真实启动器及 localhost 页面检查，Windows 10/11 为 NOT_TESTED。[首轮 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45309973056) · [配置版 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45310667386) · [CI 运行记录](ci-run.json) · [工作流校验](workflow-lint.log) · [本地回归](local-smoke.log)

[Linux 输出](linux-smoke.log) · [Windows Server 输出](windows-smoke.log) · [Windows 启动器结果](windows-launcher-result.log) · [浏览器输出](browser.log)

[桌面截图](browser/connectivity.png) · [证据抽屉](browser/evidence.png) · [390 像素移动截图](browser/mobile.png) · [供应商配置截图](browser/connection-settings.png)

## 正式验收

本机检查确认四个密钥均未配置，所选 Jev 供应商留存审查未完成。本轮未启动有授权的 `tests/live_gate.py` 全量批次，未发送供应商认证请求。匿名重取既有论坛原文得到 HTTP 200，CC BY-SA 4.0 许可及原句 SHA-256 与归档一致。[本机预检](provider-preflight.json) · [本机配置接口](localhost-configuration.json) · [公开原文复核](public-source.json) · [最新归档复核](archived-receipt-recheck.json)

| 项目 | 状态 | 依据 |
|---|---|---|
| C0-1 | BLOCKED | 8 + 3 题的真实分片及固定模型待证实 |
| C0-2 | BLOCKED | 等待真实 Choice、Score 和 Noul 响应，Score 分布完整性未验证 |
| C0-3 | BLOCKED | 公开原话取证已复核，指定的 Tavily 或 Brave 实际搜索发现仍待验 |
| C0-4 | BLOCKED | SQLite 和 JSON 已复核，真实 Jev 用量账本为空，额度回填待验 |
| C0-5 | PASS | 归档通过，工程回归再次运行外发隔离和故障演练 |
| C0-6 | PASS | 归档通过，工程回归再次运行三层模型和跨品类召回 |
| G-1 | BLOCKED | 保持 P0-0 |

下一轮需要本机配置有固定模型权限的 Jev 密钥、对应供应商留存审查及 Tavily 或 Brave 任一密钥。供应商侧的幂等仍需独立验收。Astra Max 可在取得授权后，对照同一分片键对应的供应商记录、真实账单及本机用量，核查供应商已收单但 SQLite 尚未提交时的恢复边界。[JevModel 幂等说明](https://jevmodel.org/zh/docs/) · [本机接入说明](../../../connectivity.md)
