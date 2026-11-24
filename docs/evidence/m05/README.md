# M05 本机工程验证

2026-11-24 在 Windows Enterprise 25H2（build 26200）复测。Python 3.12.9、Node 24.19.0、SQLite 3.45.3。在单独的 .venv 安装 requirements-dev.txt，通过 pip check。启动监听回环地址，回归使用临时 SQLite 和合成来源地址。

| 检查 | 实际结果 |
|---|---|
| Python 回归 | 104 项通过。覆盖 v3 → v4 兼容和失败后重试、项目隔离、原话审核与回放、去重、排除、到期、撤销、同源副本及旧导入入口遮蔽。[执行输出](python.log) |
| Node | 2 项通过。 |
| 空库启动 | 3/3，打开主页依赖的 workspace API，确认新建 SQLite v4 的运行历史为空。 |
| Chromium | 8 组通过，包括 M05 核验、溯源、跨来源去重、撤销、320 / 390 像素布局及重启回查。[执行输出](chromium.log) |
| 历史归档 | p0-0、regression、api-setup/live-receipt 和 tavily-live 共 4 份 SQLite 与 JSON 收据核验通过。 |

[桌面原话溯源](m05-record.png) · [移动端审核](m05-mobile-review.png)

Tavily、Brave 和 Jev 真实请求 0 次。G-1 为 BLOCKED，当前工程审核关闭正式计数与外发资格。G1、G2、RAW、RAW-ROLES 和 SOURCE-POLICY 正式验收待取真实证据。应用层执行原话遮蔽，SQLite 原始文件、行与备份的物理清理及删除审计待按逐源政策落实。

本轮发布目标为 PR #1 的开发分支。接管提交 `bca9363` 的 Ubuntu、Windows Server 2022、Chromium 工程检查已通过。本提交的远端 CI 状态以发布后的同 SHA 运行记录为准。[接管基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341736949)
