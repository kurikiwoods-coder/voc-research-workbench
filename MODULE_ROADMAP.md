# VOC Research Workbench 模块路线图

接管基线 `bca93639043e176f4159b9bf9fb98b4b2e2b32d8`，分支 `codex/p0-0-connectivity`，核查日期 2026-11-25。范围来自 [PDT v1.3.1](docs/pdt/PDT-v1.3.1.docx)、[专案 v2.2 摘要](docs/proposal/voc-workbench-proposal-2026-11-23.md)及[需求验收矩阵](docs/requirements-matrix.md)。六层架构和产品品类、任务大类、意图三层关系沿用现有定义。本文登记模块归属、实施顺序与证据。需求跨层时可以映射多个模块。

每个模块分别记录工程开发、工程测试、正式业务验收。工程通过意味着对应代码与测试已执行，正式验收状态由需求矩阵和真实证据决定。Schema、样例、隔离夹具与计划路径均据实标注。

每轮只改一个获准的模块及其必要接口、测试和交付文档。完成后记录实现提交和实际测试，更新本文件与 [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md)，等待下一条指令。G-1 为 BLOCKED 时继续 P0-0，已批准的独立预开发单独记账，正式准入口径及数据安全边界照常执行。

## 当前模块

M01–M05 与 M06-C1–C4 为 **ENGINEERING_PASS**。M06-B-F 五项政策与架构保持冻结。C4 的 Windows 11 实机与版本部署门禁均为 **PASS**。当前正式阶段为 P0-0，G-1 为 **BLOCKED**。M06-C5 为 **NOT_STARTED**，待负责人另行授权。[C4 验收证据](docs/evidence/m06-c4/README.md) · [开发状态](DEVELOPMENT_STATUS.md)

M01–M05 Pre-M06 独立审计的实现 CI 已通过，确认的阻塞性代码缺陷均关闭。Pre-M06-D 在 `4e6369b92205c51671866935365678df351ec808` 上完成 Windows 10 实机验收，结果为 **PASS**。原审计的 **PRE_M06_GATE_BLOCKED** 已作为历史结论保留。现行开发门禁为 **PASS**。2026-11-25 在 C1 基线上完成 Windows 11 实机验收，实机及部署门禁均为 **PASS**，G-1 为 **BLOCKED**。[Windows 11 实机证据](docs/evidence/m06-c1/windows11-closeout.md)[负责人门禁调整](docs/decisions/pre-m06-development-gate.md) · [审计](docs/audits/pre-m06-audit.md) · [实机证据](docs/evidence/pre-m06/windows10-closeout.md)

## M01 基础工程与连通性

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | C0-1～C0-6、G-1、G0、G7；BATCH-RECOVERY、PRIVACY、UI-STATES |
| 模块职责 | 构建本机运行、批次审计、公开来源连通、幂等恢复、Jev 固定版本技术门。 |
| 前置依赖 | Python 与 SQLite、合规原帖。正式 Jev 验收还依赖 M02 凭证和供应商审核。 |
| 工程开发 | P0-0 工作台及验收程序已实现。已交付同批资料恢复，继续使用原批次入口。 |
| 工程测试 | M01 交付时工程测试通过。Ubuntu 与 Windows Server 各 53 项 Python、2 项 Node、3 次空库冷启动。Chromium E2E 通过。 |
| 正式业务验收 | C0-3、C0-5、C0-6 PASS；C0-1、C0-2、C0-4、G-1 BLOCKED；P0 G0、G7 未完成。 |
| 数据库及 API | SQLite runs、attempts、results、evidence、shards。GET `/api/health`、`/api/workspace`、`/api/runs/{id}/evidence`，POST `/api/runs`、`/api/runs/{id}/resume`。 归档恢复使用本机 CLI，写入同一批次凭据且无 Schema 迁移。 |
| 前端页面 | 连通性检查、验收矩阵、运行记录、证据抽屉。 |
| 验收标准 | 同一批次的六项都通过且供应商审核可追溯才放行 G-1。G0 另有 Windows 本地三次冷启动，G7 按矩阵执行故障与安全实测。 |
| 最近相关提交 | `47051f3` |
| 测试结果与证据 | [M01 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45325025692)记录六个新增恢复回归和四份归档的完整性核验。[认证 Tavily 批次](docs/evidence/p0-0/tavily-live/README.md)记录历史业务结果。 |
| 剩余问题 | JevModel 审查、固定模型真实响应和额度实测待补。当前 C1 基线在 Windows 10 和 Windows 11 实机均已通过。 |

## M02 API 配置中心

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §7、§13.0；TC-01～TC-08、J-7、J-8、G5、D3、D5 |
| 模块职责 | 本机配置服务商与审核材料，管理凭证生命周期、诊断及额度。 |
| 前置依赖 | M01 基础存储与出站控制。正式额度验收需要真实 Jev 响应和账户。 |
| 工程开发 | P0-0 配置、向导、四家供应商诊断和基础额度条已实现。P0 批量预算等仍待做。 |
| 工程测试 | 配置与凭证隔离回归、窗口布局和冷启动通过。 |
| 正式业务验收 | Tavily 已实调。Jev 额度、真实账户契约和 P0 G5/TC 全项待验。 |
| 数据库及 API | 本地凭证库与独立 api-diagnostics SQLite。`/api/setup/{provider}/key`、`/diagnostics`、`/review`、`/api/setup/jev/{provider}`，配置随 `/api/workspace` 返回。 |
| 前端页面 | API 接入、首次向导、Jev Token Center。 |
| 验收标准 | 凭证限后端，脱敏证据能区分预检和业务验收。TC-02/03/05～07 依矩阵验证手动同步、预算、告警与真实用量。 |
| 最近相关提交 | `452e16f` |
| 测试结果与证据 | [配置中心实测](docs/evidence/p0-0/api-setup/README.md)含密钥保存、轮换、删除、重启持久化与无回显。 |
| 剩余问题 | 缺审核与真实 Jev；正式批量预算、手工余额基线、多客户端余额对账未验。 |

## M03 研究项目与范围管理

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §6.9、§13；BIZ-SCOPE、D1、CAT-6（关联） |
| 模块职责 | 本机项目生命周期、当前项目、五种研究范围及冻结快照。 |
| 前置依赖 | M01 本机 FastAPI、SQLite 和界面。正式发布仍按 G-1。引用的品类有效性在 M06 接入。 |
| 工程开发 | 已完成独立预开发。支持跨产品、跨品类，也支持不设品类的产品外课题。 |
| 工程测试 | Linux 本地、Ubuntu 和 Windows Server 各通过 Python 69 项（M03 新增 16 项）、Node 2 项、冷启动 3 次。Chromium 四组均通过。 |
| 正式业务验收 | BIZ-SCOPE 研究范围、许可来源与第二品类的正式决定待验收。G-1 BLOCKED。 |
| 数据库及 API | SQLite v2 增量迁移，含 study_projects、study_scopes、study_scope_freezes、study_workspace。详见 [项目接口](docs/studies.md#本地接口)。 |
| 前端页面 | 研究项目列表、项目表单、详情、历史范围快照。 |
| 验收标准 | 本机范围可冻结和追溯，归档保留数据。引用以 study_id、scope_id 校验归属，范围标签不直接赋给语料。正式统计继续记录 scope_version。 |
| 最近相关提交 | [实现 `3224823`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/322482357ddf7511d62094aad77c5574a27c4a9d)、[工程复测 `dbb131f`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/dbb131f32eaf8f0a58227c33bfa0b4f04e8fe62f) |
| 测试结果与证据 | [M03 工程证据](docs/evidence/m03/README.md) · [CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45336483119) |
| 剩余问题 | 实际研究范围和采样来源需正式确认。后续批次关联、来源许可、品类注册表验证随对应模块接入。 |

## M04 CSV / Excel 数据导入

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §6.9、统一数据表；INGEST、RAW、G1、RAW-ROLES、PRIVACY |
| 模块职责 | 本机解析、映射、预览、质检、暂存和导入批次回查。 |
| 前置依赖 | M03 项目与冻结范围。M05 消费同一 SQLite 中的待处理记录。 |
| 工程开发 | 已实现 CSV / XLSX 多编码、批次幂等、撤销、报告及稳定来源记录。 |
| 工程测试 | Python 95 项（新增 26）、Node 2 项、Chromium 6 组通过。Ubuntu 和 Windows Server 2022 各 3 次冷启动。[本机和三平台证据](docs/evidence/m04/README.md) |
| 正式业务验收 | G1 要求的实际来源与合格样本、正式证据及全局去重仍待验。G-1 BLOCKED。 |
| 数据库及 API | 主库 v3 迁移、import_files / import_batches / import_rows / import_candidates、/api/imports。 |
| 前端页面 | 数据导入中心、字段映射、质量检查、结果与项目批次历史。 |
| 验收标准 | 结构、出处、时间与许可分别校验。原话字节和文件行保留，待审、重复、拒收不进入正式研究统计。 |
| 最近相关提交 | [M04 代码复测 `336e68c`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/336e68c7e02bda08e00210e02958ed02250fc80e) · [CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45341223418) |
| 剩余问题 | 本机核验与跨批次去重由 M05 提供，G1、RAW 仍需按原标准复验真实语料。 |

## M05 原始语料库、去重及溯源

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §6.6、§9.3；RAW、G1、G2、RAW-ROLES、SOURCE-POLICY、J-6 |
| 模块职责 | 存储不可变原文、出处和时间窗，治理语料资格与重复引用。 |
| 前置依赖 | M03 冻结范围与 M04 本机导入。线上批次和证据关系分别依赖 M08、M06。 |
| 工程开发 | 已实现本机核验、快照摘要、角色隔离、按项目去重、溯源、保留期限和可追查的审核历史。 |
| 工程测试 | Windows 11 本机通过 Python 104 项、Node 2 项、三次空库冷启动、Chromium 8 组及四份历史归档核验。实现提交的 Ubuntu、Windows Server 2022 和 Chromium 作业全部通过。 |
| 正式业务验收 | G1、G2、RAW、SOURCE-POLICY 待正式核验。当前语料的正式统计及外发资格均关闭。 |
| 数据库及 API | SQLite v5 在既有快照与审核表基础上追加不可变的 `corpus_licenses`，保留历史。统一资格端点 `GET /api/corpus/{study_id}/records/{record_id}/eligible`。暂存视图只提供标识与状态。 |
| 前端页面 | 原始语料、批次候选、原文溯源与审核详情。 |
| 验收标准 | 3 批来源、≥100 条真实片段，30/30 可回源。许可、采样窗口、角色、重复与剔除原因可查。 |
| 最近相关提交 | [M05 原始实现 `b02a2b6`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/b02a2b647bff67f7e091b51fcdfc46cc719077e8) · [M05-R 最终实现 `d0414f5`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/d0414f5e7b978460d7dec3784c0862d7f1f0bdd0)，均已推送到 `codex/p0-0-connectivity`。 |
| 测试结果与证据 | [本机验收记录](docs/evidence/m05/README.md) · [M05 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45352022477) · [历史正式连通性归档](docs/evidence/p0-0/tavily-live/README.md) |
| M05-R 独立复审 | **ENGINEERING_PASS**。新增 10 项 Python 回归，Windows 11 全量 114/114。Ubuntu、Windows Server 2022 和 Chromium 作业全部通过。[复审证据](docs/evidence/m05/review.md) · [M05-R CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45359711019) |
| M05-R2 专项复修 | **ENGINEERING_PASS**。Linux 本机、Ubuntu 及 Windows Server 2022 各通过 Python 124/124、Node 2/2、冷启动 3/3、历史归档 4/4，Chromium 8/8。[最终实现 `62a7c1c`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/62a7c1c132b72a8e07679f1713e6834aa7893c91) · [实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45367761470) · [复测证据](docs/evidence/m05/permissions-review.md) |
| 剩余问题 | 逐源许可与实际清理审计，SQLite 和备份的受控清理，接入线上批次与正式证据关系。 |

## M06 三层用户需求数据关系

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §6、§6.6、§6.9、§9.3；C0-6、CAT-1～CAT-10（CAT-4 协作）、J-14 接口 |
| 模块职责 | 维护 Product Category、Task Category、Intent 以及证据驱动的双向关系。 |
| 前置依赖 | 依赖 M03 冻结范围、M05-R2 工程冻结与实时资格契约。M06-B-F 架构已冻结。负责人已授权 C1–C4。正式语料接入按 G-1 与逐源业务验收执行。与 M07 共享注册表约束，与 M11 协作候选事务。[数据契约](HANDOVER.md#m05--m06-数据契约) |
| 工程开发 | M06-B-F 审核 PASS，审批 APPROVED，架构 FROZEN。C1 为 ENGINEERING_PASS，涵盖 v7 数据库迁移与关系约束。C2 提供调用方写锁内的资格复核与 UTC 日界回滚。C3 交付稳定发生和证据、区间和拆并谱系、精确冻结映射、逐边人工审核。C4 在此基础上交付双向关系、权限和原子组合事务。[六份设计文档](docs/architecture/m06-design.md) |
| 工程测试 | C4 前置复验通过原有 Python 215 项与 3 个独立探针。最终源码通过 Windows 11 全量 Python 247/247、Node 2/2、Chromium 10 组和本机 HTTP 1 组，以及部署回归和独立复审。三个源码 CI 作业均通过。[C4 工程证据](docs/evidence/m06-c4/README.md) · [源码 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45560884986) |
| 正式业务验收 | CAT 系列待验。 |
| 数据库及 API | SQLite v7。C4 提供定义、关系双向、项目片段、合格证据和预检 HTTP。原子组合发行作为内部工程接口。正式联合确认归 M07/M11。 |
| 前端页面 | C4 中文基础关系浏览，支持主次任务、冻结版本和合格证据下钻。 |
| 验收标准 | 已确认意图唯一主任务大类。产品关系由合格原话证据得出。仅 published_classified 的 distinct mention_id 入分母，主大类合计精确对账。 |
| 最近相关提交 | C4 验收源码 `fce76a0`，C3 验收源码 `43c7202`，C2 实现 `965a4b8`，M06-B 审核基线 `2651d66`。[C4 验收证据](docs/evidence/m06-c4/README.md) · [负责人批准记录](docs/architecture/m06-owner-approval.md) |
| 测试结果与证据 | C0-6 合成冒烟为 2 个产品品类、3 个任务大类、30 个意图、两次跨品类命中。C1 在 Windows 10 实机通过 Python 173/173（新增 33 项）及既有回归，见[迁移与工程验收证据](docs/evidence/m06-c1/README.md)。 |
| 剩余问题 | C5 对账及规模未启动。完整身份及审核入口、真实编码、正式统计和发布仍待所属阶段验收。专案 v2.2 原 PDF 待补。[分阶段计划](docs/architecture/m06-implementation-plan.md) · [专项矩阵](docs/architecture/m06-test-plan.md) |

## M07 意图注册表及版本管理

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §8.2；CAT-1/2/5/9、J-2、J-9、J-14、P1-REFLOW |
| 模块职责 | 维护意图定义、示例、生命周期、历史快照和验证状态。 |
| 前置依赖 | M06 三层关系及 M05 证据。发布依赖 M11。 |
| 工程开发 | 注册表 Schema 与合成样例已存在，正式版本服务未实现。 |
| 工程测试 | 未测试正式注册表。 |
| 正式业务验收 | 待验收。 |
| 数据库及 API | `schemas/intent-registry.schema.json` 与 `examples/sample-intent-registry.json`。待注册表版本、差异、历史和发布 API。 |
| 前端页面 | 正式注册表和版本对比页未实现。 |
| 验收标准 | 生命周期与问卷验证状态独立。确认意图有唯一主任务大类；金标准、索引、正式结果绑定具体版本。 |
| 最近相关提交 | `8e8a74e` |
| 测试结果与证据 | C0-6 只验证样例数据，未覆盖版本发布、回滚和历史查询。 |
| 剩余问题 | 注册表事务、版本追踪、审计和发布。 |

## M08 多来源数据采集

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | 专案 §3/§5；C0-3、INGEST、G1/G2、SOURCE-POLICY、PRIVACY、P1-SOURCES |
| 模块职责 | 实现合规搜索发现、来源回源、采样日志及来源故障切换。 |
| 前置依赖 | M02 接入凭证、M03 范围、M05 原文库与来源授权；CSV 兜底来自 M04。 |
| 工程开发 | 已有 Tavily、Brave、Stack Exchange P0-0 探针及原帖回源。正式采样任务和第二来源未实现。 |
| 工程测试 | 指定搜索与官方原帖回源通过，故障切换有夹具。 |
| 正式业务验收 | C0-3 PASS，正式 G1/G2 与 P1-SOURCES 待验。 |
| 数据库及 API | P0-0 执行/证据接口；正式 connector、采样批次 API 与日志待建。 |
| 前端页面 | 连通性证据页已有。正式来源管理与采样任务页未实现。 |
| 验收标准 | 指定搜索发现的链接必须回到许可原文。3 批≥100 条真实片段、源故障可切换和 CSV 兜底。期刊背景证据独立分母。 |
| 最近相关提交 | `a650478` |
| 测试结果与证据 | 一次 Tavily HTTP 200，1 credit，原帖 94603。Brave 未实调。 |
| 剩余问题 | 正式采样、Brave 实测、YouTube、第二论坛／备用源和逐源许可。 |

## M09 BERTopic 主题发现

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | 专案 §5 第三层、PDT §8；DISCOVERY、G3、CAT-4（协作） |
| 模块职责 | 在合格样本上提取主题、记录聚类和候选复查所需的证据。 |
| 前置依赖 | M05 可追溯语料、M06 范围与分类、M07 注册表；M11 提供人工审核。 |
| 工程开发 | 仅有发现层说明及通用向量召回冒烟，无 BERTopic 实现。 |
| 工程测试 | 未测试 BERTopic。 |
| 正式业务验收 | 待验收。 |
| 数据库及 API | 待主题运行、聚类成员、版本、差异和运行查询 API。 |
| 前端页面 | 主题发现与聚类证据页未实现。 |
| 验收标准 | 按 DISCOVERY 保存单轨与两轨结果、复算差异；盲测与真实小样本确认可提出或驳回候选。 |
| 最近相关提交 | `0044906` |
| 测试结果与证据 | C0-6 向量召回未覆盖 BERTopic。 |
| 剩余问题 | 模型参数、离线复跑、主题样本和盲测。 |

## M10 TopicGPT 与未知意图发现

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §7.2.1、§8.1；DISCOVERY、G3、CAT-4/5、J-10、J-14（协作） |
| 模块职责 | 实现 TopicGPT 四步、未知残差队列及与另一轨的对照。 |
| 前置依赖 | M05、M06、M07；联验对接 M09 和 M11。托管调用依赖明确供应商和隐私批准。 |
| 工程开发 | 无 TopicGPT 或真实未知意图管线。 |
| 工程测试 | 未测试。 |
| 正式业务验收 | 待验收。 |
| 数据库及 API | 待发现运行、残差、候选信号和差异接口。 |
| 前端页面 | 未知意图和双轨结果页未实现。 |
| 验收标准 | 盲测可发现并驳回候选，真实批次允许无新意图；None、低相似或 Noul 否进入待审。内部语料遵守本地隔离。 |
| 最近相关提交 | `33a4905` |
| 测试结果与证据 | 验收矩阵对 DISCOVERY 与 G3 已登记。 |
| 剩余问题 | 四步实现、残差回放、来源审核和真实审核。 |

## M11 人工审核与候选意图管理

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §6.5、§8.1/8.2；CAT-4/5/9、J-5、G3、P1-GOLD |
| 模块职责 | 人工确认、驳回、合并或拆分候选，联审任务大类及低置信条目。 |
| 前置依赖 | M06 关系校验、M07 版本、M09/M10 候选。低置信复核还依赖 M12。 |
| 工程开发 | 无正式候选队列或联审事务。 |
| 工程测试 | 未测试。 |
| 正式业务验收 | 待验收。 |
| 数据库及 API | 待候选队列、操作审计、联合确认和事务接口。 |
| 前端页面 | 人工队列、候选详情、联合确认页未实现。 |
| 验收标准 | 未归主类只能处于候选态；联审任一步失败整组回滚。低置信 100% 入队且不进正式统计。 |
| 最近相关提交 | `33a4905` |
| 测试结果与证据 | CAT-4/5/9 和 J-5 的测试口径已登记。 |
| 剩余问题 | 队列、审计、并发事务和人工实际试用。 |

## M12 Jev 编码与金标准校准

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §7、§13；J-1～J-14、G4/G5、D2/D3/D5、P1-GOLD；C0-1/2/4（前置） |
| 模块职责 | 把 Choice、Score、Noul、8+3 分片、None 守门与人工金标准接到正式语料。 |
| 前置依赖 | M01 G-1、M02 凭证审查、M05 语料、M06/M07 已确认注册表、M11 复核流程。 |
| 工程开发 | P0-0 真实请求路径和固定字段校验已有，P0 编码与金标准未实现。 |
| 工程测试 | 分片、防重和缺概率有工程夹具，正式金标准未测试。 |
| 正式业务验收 | C0-1/2/4 BLOCKED；J-1～J-14、G4 不作通过。 |
| 数据库及 API | 诊断 shards 和独立账本。待正式编码、金标准、阈值版本和运行接口。 |
| 前端页面 | 连通性与额度页已有。正式编码和校准页面未实现。 |
| 验收标准 | 实际固定模型及三类概率齐全；100–200 条金标准与中文子集；关键分片幂等，J-14 依矩阵盲测达标。 |
| 最近相关提交 | `452e16f` |
| 测试结果与证据 | 分片、故障和模型拒绝的离线测试通过，真实 Jev 0 次。 |
| 剩余问题 | 供应商审核、真实固定模型返回、全分布、真实计量、人工标注与阈值。 |

## M13 用户洞察仪表盘

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | §6.6、§9.3、§10；BASIC-DASH、UI-EVIDENCE、UI-STATES、P1-ANALYSIS、P1-TREND、RESEARCH-REPORT |
| 模块职责 | 提供情感、问题、趋势、建议及同口径的证据下钻。 |
| 前置依赖 | M03、M05、M06、M11、M12。趋势验收依赖真实四周数据。 |
| 工程开发 | 已有诊断统计和 Token Center，正式研究仪表盘未实现。 |
| 工程测试 | 诊断 UI E2E 通过，正式统计未测试。 |
| 正式业务验收 | 基础和 P1 仪表盘待验。 |
| 数据库及 API | 现有 `/api/workspace` 提供诊断状态。待研究指标、筛选分母和逐指标证据 API。 |
| 前端页面 | 现有连通性及额度页面。VOC 指标页未实现。 |
| 验收标准 | 按实际口径互斥计数、维度切换时重算分母，所有指标可追溯。P1 小分母保护和四周周期遵从矩阵。 |
| 最近相关提交 | `452e16f` |
| 测试结果与证据 | [Chromium 记录](docs/evidence/p0-0/api-setup/README.md)覆盖诊断页，正式数据分母未验证。 |
| 剩余问题 | 聚合与证据逻辑、视觉页面、统计校验及真实数据积累。 |

## M14 问卷生成、验证及数据回流

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | 专案 §8；SURVEY、D4、G6、P1-REFLOW、PRIVACY |
| 模块职责 | 将真实发现映射题型、人工审题、试填、发布与回收后回写验证状态。 |
| 前置依赖 | M05 证据、M07 注册表、M11 人工审定和 M13 发现输出；Google Forms 授权及真人样本。 |
| 工程开发 | 仅有题型映射和样例。配置中心展示未来的 Forms 接入。 |
| 工程测试 | 未测试正式问卷。 |
| 正式业务验收 | P0 草稿和 P1 G6／回流均待验。 |
| 数据库及 API | 已有题型映射 JSON 与问卷样例。待题项、审批、答卷隔离和回流 API。 |
| 前端页面 | 草稿、人工审题、Forms 发布和回收面板未实现。 |
| 验收标准 | 每题可回链一个发现，保留开放题和匿名性，2–3 人真实试填。实际回收和阈值回写才满足完整 G6。 |
| 最近相关提交 | `2043c2e` |
| 测试结果与证据 | 无正式 Forms OAuth、发布或真实回流测试。 |
| 剩余问题 | 草稿与授权、试填、发布、真实答卷和回写。 |

## M15 竞品 Radar 与持续监控

| 项目 | 记录 |
|---|---|
| PDT 与矩阵编号 | P2-RADAR、P2-AMAZON、P2-GITHUB、P2-SCHEDULE、P2-HISTORY |
| 模块职责 | 分开统计竞品与自有语料，调度已授权来源与生成跨期报告。 |
| 前置依赖 | P1 运营验收之后，依赖 M03、M05、M08、M13 与授权范围。 |
| 工程开发 | 只有来源边界和研究方法文档。 |
| 工程测试 | 未测试。 |
| 正式业务验收 | P2 待准入及验收。 |
| 数据库及 API | 待竞品样本分域、任务计划、运行日志、版本化历史和对比 API。 |
| 前端页面 | 竞品 Radar、巡检日志和历史报告页未实现。 |
| 验收标准 | 样本独立且口径可比，Amazon 限四条授权渠道，GitHub 信号不进主统计。任务可暂停恢复，报告与引用可复核。 |
| 最近相关提交 | `2043c2e` |
| 测试结果与证据 | 无 Radar、定时巡检及跨期报告测试。 |
| 剩余问题 | 平台授权、任务幂等、真实样本和客观报告。 |
