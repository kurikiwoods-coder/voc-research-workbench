# VOC 研究工作台开发规范

## 接续开发

1. 在 [现有 GitHub 仓库](https://github.com/kurikiwoods-coder/voc-research-workbench)核对远端分支、提交、PR 和对应提交的 Actions。当前接续入口见 [HANDOVER.md](HANDOVER.md)。切换电脑、模型或云端环境时，以 GitHub 上的代码、PR、提交和验收证据为正式记录。
2. 依次读取 [开发状态](DEVELOPMENT_STATUS.md)、[M01–M15 路线图](MODULE_ROADMAP.md)、[PDT v1.3.1 正文](docs/pdt/PDT-v1.3.1.docx)、[专案 v2.2 仓库摘要](docs/proposal/voc-workbench-proposal-2026-11-23.md)和[需求验收矩阵](docs/requirements-matrix.md)。按矩阵处理产品文档之间已登记的版本差异。
3. 每轮只处理已获准的一个模块及必要接口、回归测试和交接文档。先核对同一提交的测试证据，接续缺项。已有工作区先检查未提交改动和本地独有提交，保留其他环境正在开发的内容。工作区分叉时先检查差异，保持两侧工作可恢复。禁止强制推送、覆盖他人改动和自行合并 `main`。
4. 完成实施和缺陷复测后，在 [路线图](MODULE_ROADMAP.md)、[开发状态](DEVELOPMENT_STATUS.md)和 [交接记录](HANDOVER.md)更新模块范围、证据及剩余事项。Git 提交只包含经审阅的本轮文件。常规推送后核对远端提交与对应 CI，按实际结果记录工程验收和正式业务验收。完成模块后等待下一轮指令。

## 架构与验收边界

- 保持采集、原始、发现、执行、仪表盘和输出六层接口。研究范围登记对象范围，原话证据决定产品品类关系，编码结果关联意图，已确认意图有一个有效主任务大类。跨品类汇总按唯一 `mention_id` 去重。沿用 PDT §6.6、§9.3 的计数口径和版本追溯。
- P0-0 的 G-1 需要同一正式批次 C0-1 至 C0-6 全部通过，所选供应商的公开语料处理审批和留存审查可追溯。独立预开发可使用本机合成夹具，正式准入由真实验收记录决定。真实模型及 8+3 分片、三类完整响应、实际分片用量和余额均按原标准核验。最新实况见 [验收矩阵](docs/requirements-matrix.md)。
- 原话、背景证据、内部材料及合成样本按角色隔离。保存来源地址、原文、许可、时间窗、采集方式和排除原因。正式研究计数须满足来源、去重、编码、人工审核和发布条件。内部 CX、公司非公开数据和问卷原始答卷留在授权的本机环境。内部 CX 只做本机处理或人工编码。
- 外发仅限合法公开、可处理且已脱敏的内容，逐源与实际账户、通道均须获准。商用版须有实际留存、地区与分处理商审查记录，TypeSafe 的 ZDR 需组织实证，JevModel 审查单独核验。个人版非强制未知按下方独立政策登记。工程回归只用合成夹具、历史合规的脱敏归档及临时 SQLite，不触发真实研究 API。

## 后续模块与模型接入

- 依据 [ROADMAP-V2](docs/planning/ROADMAP-V2.md) 和 [开发顺序](docs/planning/development-sequence.md) 核对本轮授权、实际依赖和出场验收。可按复杂度合并关联子单元，每个主模块留版本、接口、测试、缺陷及接续范围。
- M09、M10 获准实施时，遵守 [I18N-PRE 提前约束](docs/decisions/i18n-pre-owner-approval.md)，分别预留研究语言参数，保持原话证据与衍生文本独立、意图 ID 稳定。M10 验收完成后等待 I18N-PRE 的单独授权，专项完成后接续 M11。
- AI 模块遵循 [Decision、LLM、Embedding 接口](docs/architecture/ai-model-adapter-contract.md)，以精确模型、供应商、通道和版本消费结果。正式 Jev 锁定 `jev-1.14.0`，禁止静默换模。新模型独立审查和验证，正式用途依 [生命周期](docs/architecture/model-lifecycle-and-calibration.md) 及 [金标准协议](docs/architecture/model-evaluation-protocol.md) 重新校准、复核并获批。
- 规划扩展依 [扩展映射](docs/requirements-matrix.md#roadmap-v2-规划扩展映射) 接续。正式研究按原 G-1、J/CAT 与阶段验收矩阵核定。

## 双版本与准入

- 定义及实现同时遵守 [EDITION-V1](docs/architecture/edition-policy.md)、[个人门禁](docs/architecture/personal-research-gate.md)和[商用 G-1](docs/architecture/business-research-gate.md)。版本与部署分别从可信服务端解析。权限由当前受信身份、项目、证据和作用范围核定。原商用阻断、C0 六项、M06 五项及统计契约保留。
- 按 [研究优先 ADR](docs/decisions/product-realignment-v1-owner-approval.md) 继续已获授权的 M09 等隔离工程。个人正式准入的 D/R 与 M12-A 增量各待独立授权。未知必要证据、过期、撤销、轮换或超预算时按现有执行边界失败关闭。日常工程测试使用合成输入、隔离库与模拟传输。
- 个人版 V2 的治理与授权以 [个人准入政策](docs/architecture/personal-research-gate.md)为准。个人版与商用版共用 C0-1 至 C0-6 的技术与研究质量标准。V2 允许获准账户的四槽批次授权和 SystemOne 专用预算控制。
- 费用只入库获准脱敏记录。本机原始账单、真实密钥、DPAPI 和 SQLite 的核验分别记录实际证据。阶段实施前读 [交接与测试](docs/planning/g1-personal-implementation-plan.md)。

## 环境与交付

- 公司电脑、个人电脑、云端均从同一 GitHub 开发分支取代码，使用 Python 3.12、Node 24、Git、Bash 和仓库的 `requirements*.txt`。各环境按 [启动与验证命令](HANDOVER.md#复建开发环境)独立建立 `.venv`。用户界面仅监听 `127.0.0.1`，云端按需使用受限回环转发。
- `.env`、本机凭证库、服务商审核附件、真实语料、公司资料、运行库及含敏感信息的截图和日志均留在授权本机。跨电脑、云端和 GitHub 交接仅传受控代码、合成夹具和已审核脱敏的工程证据。`.env.example` 保持示例值，逐项核对暂存文件并执行仓库的 secret scan。
- 按变更范围执行工程测试并记录提交 SHA、平台、命令、用例数及实际完成状态。回归、真实业务验收和 Windows 10/11 实机证据各自据实记录。GitHub Actions 的 Windows Server runner 记录其自身系统和测试范围。
