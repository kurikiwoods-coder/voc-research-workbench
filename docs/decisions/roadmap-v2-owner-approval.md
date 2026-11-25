# ROADMAP-V2 负责人批准记录

2026-11-25，项目负责人授权将完整开发路线图及多模型接口协议登记为正式规划。补充授权以开发分支 `3bd705befb98ee108b77603763c5571ceb7fdc44` 的 M06-R 复审冻结为起点。草稿 PR #1 的同提交 CI 三项通过。M01–M06 为 ENGINEERING_PASS，M06-R 为 PASS，Windows 11 实机及部署门禁 PASS。现有实机证据绑定源码 `9c27231376fcc32aae39a9b63df6fa9b9b98c4c6`。[冻结审计](../audits/m06-final-engineering-audit.md) · [基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45585265229)

| 批准事项 | 范围与依据 |
|---|---|
| 核心路线 | 15 个主模块，74 个功能与设计单元及 5 个审查节点。已进入工程或复审完成范围 31 个，待推进 48 个。 |
| 通用模型架构 | 批准 Decision、LLM、Embedding 三类规划接口。M12 为通用决策引擎，首个正式实现仍固定 `jev-1.14.0`。未来第二决策模型、复核、备用及模型中心按后续授权。 |
| 保留政策 | PDT v1.3.1、原验收矩阵、六层架构、三层关系、五项冻结裁定和 `M06-B-F.1` 沿用。正式变更验收标准或口径需要单独批准。 |
| 工程遗留 | M06-R 工程结论及原证据保留。100K 合成查询样本 P95 39.073 秒，M13 接手优化，15 秒为探索目标。 |
| 版本与日期 | 核心 79 项和 P2 后可选产品化 15 项独立管理。12 月 6 日和 12 月 10 日登记为计划目标，发布和正式验收按实际证据。 |
| 本轮边界 | 规划文档、协议与证据核对。真实研究 API 调用 0。M07–M15 业务实施及 G-1-R 都待另行授权。 |

```text
ROADMAP_V2 = APPROVED_AND_DOCUMENTED
MULTI_MODEL_DIRECTION = APPROVED
MODEL_ADAPTER_CONTRACT = PLANNED
MODEL_ADAPTER_IMPLEMENTATION = NOT_STARTED
M06_ENGINEERING_BASELINE = FROZEN
G-1 = BLOCKED
G-1-R = NOT_STARTED
M07–M15 = NOT_STARTED
```

[完整路线图](../planning/ROADMAP-V2.md) · [实施顺序](../planning/development-sequence.md) · [模型接口](../architecture/ai-model-adapter-contract.md) · [五项冻结裁定](../architecture/m06-owner-approval.md) · [需求矩阵](../requirements-matrix.md)
