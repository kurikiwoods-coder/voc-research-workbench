# 双版本与个人研究治理负责人批准

2026-11-26，项目负责人授权 **G-1-PERSONAL Phase 1**，交付 **G-1-R-B-F** 费用补证、**EDITION-V1** 双版本架构、**G-1-P-A** 个人研究最低准入政策及后续实施设计。核对开发分支和草稿 PR #1 基线 `dd89a14f25ac0dfae3f63dcf1809da2494f1c9dc` 的 Ubuntu、Windows Server 2022 和 Chromium 均通过。此前 M08-V 实机结论绑定源码 `74590d4a4d43a66c7a3296943da9205bc6ff65e0`，M01–M08 原生 Windows 11 复验及部署门禁为 PASS。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45740807294) · [M08-V 原证据](../evidence/m08-v/README.md)

| 批准事项 | 范围 |
|---|---|
| EDITION-V1 | Personal 为完整 M01–M15 功能规划，Business 使用同一研究引擎、Schema、三层关系、统计、模型适配和准确性标准。产品版本与本机或云部署两个维度独立 |
| G-1-P-A | Personal 独立门禁、可信 Owner、逐项目和用途批准、可记录非强制 UNKNOWN、同批六项及实际证据。Business 保留原 G-1 与正式授权边界 |
| G-1-R-B-F | 仅将原始 CSV 的两条目标记录脱敏附证，历史 SQL 账本和实机材料按实际可得范围核验。原合成请求额度保持耗尽 |
| 冻结与安全 | M06 五项政策、M06-B-F.1、PDT、原 G-1 历史和 ROADMAP-V2 管理范围沿用。第三方许可、合法处理、隐私、实际模型与校准继续各自核定 |
| 下阶段 | G-1-P-B 之后按 C、D、R 顺序分别授权。个人版完成准入后才启动 M09。Business G-1 为单独验收 |
| 本期范围 | 仅文档及脱敏取证。当前统一工作库 v8，真实研究及真实供应商 API 调用均为 0 |

```text
DUAL_EDITION_STRATEGY = APPROVED_AND_DOCUMENTED
PERSONAL_EDITION = FULL_ACCESS_PLANNED
BUSINESS_EDITION = PLANNED
G1_PERSONAL_POLICY = DOCUMENTED
G1_PERSONAL_IMPLEMENTATION = NOT_STARTED
G-1-PERSONAL = NOT_EVALUATED
G-1 = BLOCKED
G-1-R-B-F_CSV = CSV_VERIFIED
G-1-R-B-F_LOCAL_LEDGER = LOCAL_VERIFICATION_PENDING
M06_ENGINEERING_BASELINE = FROZEN
ROADMAP-V2 = 39/79
M09 = NOT_STARTED
REAL_RESEARCH_API_CALLS = 0
```

[双版本政策](../architecture/edition-policy.md) · [个人门禁](../architecture/personal-research-gate.md) · [商用门禁](../architecture/business-research-gate.md) · [实施与测试](../planning/g1-personal-implementation-plan.md) · [CSV 补证](../evidence/g1-rb-f/README.md)
