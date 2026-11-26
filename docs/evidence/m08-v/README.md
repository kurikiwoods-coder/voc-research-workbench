# M08-V Windows 11 跨设备实机验收

2026-11-26 在公司电脑的原生 Windows 11 Enterprise 25H2 x64（Build 26200.8655）、普通交互登录用户、未提权环境进行 M01–M08 复验。同步前现场为 `3bd705befb98ee108b77603763c5571ceb7fdc44`，工作区干净。GitHub 开发分支和未合并的草稿 PR #1 指向 `74590d4a4d43a66c7a3296943da9205bc6ff65e0`。获取后左右计数为 0/9，无分叉，保护忽略文件的快进完成后为 0/0。三项源码 CI 均通过。[源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45651637195) · [草稿 PR](https://github.com/kurikiwoods-coder/voc-research-workbench/pull/1)

测试从被验收提交导出跟踪文件，使用隔离运行目录、SQLite、合成夹具与四份历史脱敏归档。项目默认运行目录中未发现正式运行库，本轮迁移对象为隔离合成库及其一致性备份。实机证据固定于功能源码 SHA，交付提交补充验收文档。已有 Windows 10 和 M06-R Windows 11 证据沿用各自的源码 SHA。[M08-C/D Windows 10 证据](../m08-cd/README.md) · [M06-R Windows 11 证据](../m06-r/README.md)

| 门禁 | 判定 |
| --- | --- |
| M08_V、M01_M08_WINDOWS_11_REGRESSION | PASS |
| WINDOWS_11_REAL_MACHINE、WINDOWS_11_DEPLOYMENT_GATE | PASS |
| M06_ENGINEERING_BASELINE | FROZEN |
| M07、M08_P0_ENGINEERING | ENGINEERING_PASS |
| M08_FORMAL_BUSINESS_ACCEPTANCE、PACKYCODE_PROVIDER_APPROVAL | PENDING |
| G-1、正式 G-1-R-B | BLOCKED |
| M08-E、M09–M15 | NOT_STARTED |
| ROADMAP-V2 | 39/79 |
| 真实研究 API、真实供应商探针 | 各 0 次 |

M09-A 的隔离工程接口与回归前置满足。立项需负责人单独授权，正式处理依当前证据资格、逐源与通道审批、G-1 同批六项及原验收矩阵。历史 PackyCode 真实合成契约继续归档，第二片实扣及完整费用对账待补。M13-A 十万级统计性能债务继续登记。[M09 接续](../../architecture/m08-consumer-handover.md) · [需求矩阵](../../requirements-matrix.md)

[平台清单](windows11-manifest.json) · [回归结果](regression-results.md) · [数据库迁移](database-migration.md) · [缺陷台账](bug-register.md)
