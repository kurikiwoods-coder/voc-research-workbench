# 阶段变更记录

## 2026-11-26 · G-1-P-B 双版本服务端

- 本机可信 Owner 在获准的项目与冻结范围内操作。新增个人版及云模式状态，保留商用原验收路径。
- 工作库维持 SQLite v8，个人版按运行目录及 SQLite 版本标识隔离。请求和数据读写复核授权，正式外发、发布及原 PackyCode 预检重启保持关闭。
- 独立复审修复跨范围草稿、原话权限与历史回读等风险。两道门禁状态为 NOT_EVALUATED 与 BLOCKED。[工程证据](docs/evidence/g1-p-b/README.md)

## 2026-11-24 · Pre-M06 独立工程审计

- 运行证据补充本机地址检查，上游截断响应进入连接中断处理，留存审查与本机凭证绑定。
- 同内容改名上传重用已存在文件，暂存去重区分隐私与内容角色。旧许可按当前规则核对，SQLite v6 保留审核历史并刷新撤销视图。
- 记录 10 项修复和 16 项独立回归。Windows 11 真机为 NOT_TESTED，PRE_M06_GATE_BLOCKED，G-1 保持 BLOCKED。

[审计交付](docs/audits/pre-m06-audit.md)

## 2026-11-24 · M05-R2 许可及数据资格

- 核验要求明确的许可状态、可追溯证据和审核依据。缺少明确授权的旧核验记录留待复核。
- SQLite v5 追加不可变许可和撤销记录。有效新授权材料经明确人工复核后才恢复对应记录的本机资格。
- 同一文件行的旧核验副本在缺少结构化授权时各自进入待审核。逐条复核后恢复各自的本机资格。
- 新增统一资格读取接口，按当前上下文读取有效原话。导入暂存、预览、批次历史和错误报告按资格遮蔽。G-1 保持 BLOCKED。

[本机核验与重新授权](docs/imports.md#m05-原始语料审核) · [修复前后证据](docs/evidence/m05/permissions-review.md)

## 2026-11-24 · M04 本机表格导入

- 实现 CSV 多编码及 XLSX 多工作表导入，支持自动和手工字段映射、数据质检与错误报告。
- SQLite v3 增量迁移新增项目级暂存批次。保留文件、原话和行号，复用冻结范围及幂等事务。
- 新增两种导入模板、批次撤销和后续原话证据接口。Ubuntu、Windows Server 与 Chromium 验证通过，G-1 保持 BLOCKED。

[本机操作](docs/imports.md) · [工程测试](docs/evidence/m04/README.md)

## 2026-11-24 · M03 研究项目与范围管理

- 新增本机项目创建、编辑、搜索、切换、归档和恢复，覆盖五种研究范围与历史快照。
- SQLite v2 增量迁移保留 P0-0 验收记录。冻结范围可用项目 ID 与范围版本 ID 成对引用，历史内容不可覆盖。
- 新增 16 项回归，覆盖旧库升级、回滚、项目隔离、并发提交和服务重启。Ubuntu、Windows Server 与 Chromium 复测通过。G-1 保持 BLOCKED。

[本机使用](docs/studies.md) · [工程测试证据](docs/evidence/m03/README.md)

## 2026-11-24 · P0-0 Tavily 认证搜索

- 正式验收显式请求 Tavily 基础搜索的实际积分，用量和结果数写入本机证据及脱敏归档。新增回归覆盖供应商未返回积分时保留空值。
- 一次真实 Tavily 搜索返回 HTTP 200 和 1 个 credit，回源许可原话通过 C0-3。C0-5 和 C0-6 同批通过。JevModel 等待留存审查，C0-1、C0-2、C0-4 和 G-1 保持阻塞。

[实测日志与审计包](docs/evidence/p0-0/tavily-live/README.md)

## 2026-11-24 · P0-0 API 接入中心

- 新增 API 接入页和可跳过的首次配置向导。TypeSafe、JevModel、Tavily、Brave 密钥可在本机保存、更换、停用，操作立即生效。YouTube 和 Google Forms 提供后续接入说明。
- 新增各供应商的独立连接诊断、脱敏证据和额度显示。Jev 的合成诊断复用固定 8 + 3 分片与账本。公开搜索保留发现、回源、许可、原句四层状态。
- Windows 凭证用当前用户 DPAPI 加密。Linux 和 macOS 使用仅当前用户可访问的文件。连接诊断独立落库，正式验收继续使用原有批次及 G-1 规则。

[本机操作说明](docs/connectivity.md#从工作台配置-api) · [本轮测试证据](docs/evidence/p0-0/api-setup/README.md) · [需求与验收](docs/requirements-matrix.md)

## 2026-11-24 · P0-0 工程收尾

- 恢复旧批次时保留另一个新请求的待重试幂等键。批次切换只采用最近一次读取，迟到响应无法覆盖已选批次。
- 新增常规 Node 回归和 PR 工程 CI。Linux、Windows Server 和 Chromium 任务均保存日志，Windows 额外从中文及空格路径运行启动器。
- 为四个供应商补充注册和取钥路径，展示当前密钥配置、所选批次的连接和能力状态、留存审查与正式验收状态。
- 将收到供应商夹具响应后 SQLite 提交失败的用例扩展到重启恢复。保留前轮正式批次和原始回归证据，本轮继续等待有授权的服务商调用。

[工程报告](docs/evidence/p0-0/closeout/README.md) · [API 配置](docs/connectivity.md#注册与创建密钥) · [需求矩阵](docs/requirements-matrix.md) · [GitHub Actions](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/workflows/p0-0-ci.yml)

## 2026-11-23 · P0-0 连通性验收

| 提交阶段 | 变更 |
|---|---|
| 需求基线 | 比对 PDT v1.3.1 与专案 v2.2，分别映射新版六项 C0、旧五项、新意图验收和各阶段 G 门。 |
| 后端与存储 | 新增迁移、不可覆盖的证据、分片计量、固定版本适配、真实论坛搜索回源、外发隔离和全局跨品类召回冒烟。 |
| 浏览器工作台 | 连通性检查、需求矩阵、恢复与导出、Jev 额度中心。桌面和窄屏均使用同源本地 API。 |
| 验收加固 | 计划与已发送请求分别记录。保留两份规范的搜索子项，锁定恢复时的输入，支持无密钥批次首次绑定账户，真实与合成数据库分开。重复计量、故障退避和中断恢复有自动化回归。 |
| 可复核交付 | 收录同批两次执行的 JSON、脱敏 SQLite、五张浏览器截图、Windows 启动方法和离线核对程序。 |
| 独立复核 | 增加原帖重取与许可、内容摘要校验。保存一次 HTTP 503 和随后的匹配响应 HTTP 200，以及供应商无密钥元数据探测。收录 23 项工程回归与 Linux 三次空库冷启动的逐项输出。 |

本批验收为 C0-5、C0-6 通过，C0-1～C0-4 阻塞，G-1 阻塞。下一阶段在 G-1 通过后启动。[验收记录](docs/evidence/p0-0/README.md) · [需求矩阵](docs/requirements-matrix.md) · [本地运行](docs/connectivity.md)
