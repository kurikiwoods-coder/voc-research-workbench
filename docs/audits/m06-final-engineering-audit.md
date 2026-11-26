# M01–M06 最终工程复审

复审基线为 `7b26d8da89db636c7e3f4ad73490b53dcc555155`，对应开发分支与开放草稿 PR #1。[三项基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45573612526)

C5 原实测源码为 `a9eebee24616984dda8e72bab1242373555b06db`。两次提交之间仅有 15 个验收文档和证据文件变更。本轮在原生 Windows 11 上以合成数据复验。专案 v2.2 的 27 页原 PDF 缺失，依据仓库内摘要、PDT v1.3.1、验收矩阵及负责人已批准的架构与政策核对。

| 模块 | 审计范围与主要代码 | 验证入口 |
|---|---|---|
| M01 基础工程 | 本机 HTTP 回环、来源许可及外发、批次状态、分片重试、旧归档恢复。检查 `src/dashboard/app.py`、`src/execution/checks.py`、`src/execution/transport.py`、`src/outputs/recover_source_batch.py`。 | 连通性、旧批次恢复、Pre-M06 异常中断及四份历史归档。 |
| M02 API 配置 | 逐服务诊断、配置与额度投影、同源变更控制、凭证存取及轮换。检查 `src/dashboard/api_setup.py`、`src/execution/provider_diagnostics.py`、`src/raw_store/credentials.py`。 | API 配置回归、普通 Windows 登录用户 DPAPI 与本机 Chromium。 |
| M03 项目范围 | 创建、编辑、项目切换、冻结、历史、归档及恢复；消费时按项目、范围和版本绑定。检查 `src/dashboard/study_api.py`、`src/raw_store/studies.py`。 | 主流程 Chromium、项目和范围回归、双项目手算。 |
| M04 导入 | CSV/XLSX 读取、编码及容量限制、映射、幂等、续跑、来源和物理行、排除及撤销。检查 `src/ingestion/import_files.py`、`src/ingestion/import_mapping.py`、`src/raw_store/imports.py`、`src/dashboard/import_api.py`。 | 导入回归、浏览器、新增同文独立来源反例。 |
| M05 语料治理 | 审核、历史许可、不可变原话、组主切换、同文件行和同源限制、撤销与保留期、内部 CX 隔离。检查 `src/raw_store/corpus.py`、`corpus_access.py` 与 `corpus_policy.py`。 | 原话及许可套件、Pre-M06 A–H、C2 并发、双项目撤销手算。 |
| M06-C1 | 001–007、v7 角色与旧库、封版、唯一键、延迟外键、幂等及 WAL 恢复。 | 约束、迁移、历史升级及活跃 WAL 备份恢复。 |
| M06-C2 | 同连接资格、UTC 界线、保存点与最终外层回滚。 | C2 专项、真实 SQLite 竞争、撤销先后及旧读快照。 |
| M06-C3 | 稳定 M/E、证据区间和上下文、产品边、身份及版本谱系。 | C3 专项与生产接口构造的合成证据。 |
| M06-C4 | 双向关系、组合写、六角色、精确 R/M/E 授权、审计投影和前端。 | C4 专项、精确版本回归、localhost HTTP 及 Chromium。 |
| M06-C5 | 同证据交集、六桶、排除账、全量分母、两条恒等式与当前授权。 | C5 专项、双项目独立手算、并发撤销与规模对照。 |

[缺陷与处置](../evidence/m06-r/bug-register.md) · [25 项跨模块反例](../evidence/m06-r/independent-verification.md) · [性能证据](../evidence/m06-r/performance-comparison.md) · [最终源码及实机验证](../evidence/m06-r/README.md)

业务政策与统计口径 `M06-B-F.1` 依[负责人批准](../architecture/m06-owner-approval.md)。工程验收只覆盖已实施入口。正式 CAT、J-14、逐源许可、删除审计、真实采样及编码、金标准和正式发布继续纳入[需求验收矩阵](../requirements-matrix.md)。工程复验使用合成夹具及既有脱敏归档，真实研究 API 调用为 0。M07 开发需负责人授权，[M07–M15 工程交接](../architecture/m06-consumer-handover.md)已登记各模块的现有接口和待实现职责。
