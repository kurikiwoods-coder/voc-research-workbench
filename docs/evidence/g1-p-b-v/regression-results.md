# Windows 11 原生回归结果

Windows 11 Enterprise 25H2 x64 Build 26200.8655，非管理员登录用户。Python 3.12.9，SQLite 3.45.3，Node 24.19.0，Git 2.55.0.windows.5，PowerShell 7.6.9，Playwright 1.65.2，Chromium 159.0.8154.6。隔离源码归档 SHA-256 `84dba371e1042623e7f4f68ceb28eb24cc4a0dda1655b377997f645ae29aaa7c`。

| 验证 | 通过 | 失败 | 跳过 | 退出 |
| --- | ---: | ---: | ---: | ---: |
| Python unittest 全量 | 422 | 0 | 0 | 0 |
| Node | 2 | 0 | 0 | 0 |
| 空库冷启动 | 3 | 0 | 0 | 0 |
| 历史脱敏归档 | 4 | 0 | 0 | 0 |
| 独立防御性回归 | 64 | 0 | 0 | 0 |
| Windows 启动器 | 6 | 0 | 0 | 0 |

Chromium 全量通过，退出 0，15 个浏览器上下文、36 张合成截图。1440×960 和 393×852 独立合成界面检查通过，验证 Owner 登录、授权范围、采集 403 和页面脱敏。敏感信息扫描通过。浏览器非本地请求及受控 Python 外部连接尝试分别为 0。

独立复验覆盖版本及授权策略 27 项、SQLite 迁移 15 项、PackyCode 合成预检 15 项、历史恢复 6 项、损坏库保护 1 项。核验商用默认、本机个人、两种云模式、当前 Owner 授权、跨项目和范围拒绝、导入与读取分权、application_id 绑定、旧路径兼容及正式统计 unavailable/null。

普通、中文及含空格路径均完成首次启动与同库重启。六次首页、health、workspace 均返回 200，SQLite v8，integrity_check=ok，foreign_key_check 无记录，合成项目正常持久化。受控 Ctrl+Break 导致批处理各退出 3，服务正常停止且端口释放，最终验收探针退出 0。首轮探针误传空版本枚举，服务拒绝启动，修正夹具后复测通过。

商用合成凭证经 DPAPI CurrentUser 保存、重启读取、轮换、再次读取、删除及再次重启，检查明文泄露未发现，探针退出 0。B 个人工作区原生 ACL 独立检查通过，验证目录所有者、标识文件与库的 DACL 继承、PERSONAL application_id 0x564F4350、SQLite v8 与完整性。B 个人模式未打开商用供应商凭证库。
