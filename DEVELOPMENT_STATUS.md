# VOC Research Workbench 开发状态

核查日期 2026-11-24。初始远端基线 `a650478dc6cc4a0a0baf66debddf141ed4763b0f`，分支 `codex/p0-0-connectivity`，PR #1 为草稿。

## 本轮 M01 基础工程与连通性

工程范围为恢复已经归档的认证 Tavily 来源证据并支持同批续测。现有原运行库已清理。恢复入口只处理 P0-0 受信归档，保留来源边界，待原正式检查重新计算其余项。

工程测试待 GitHub Actions 执行。基线 47 项 Python、2 项 Node、Linux 和 Windows Server 的空库冷启动及 Chromium E2E 已通过。[基线 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45322408935)

## 正式验收

| 要求 | 状态 | 现有证据 |
|---|---|---|
| C0-1 | BLOCKED | 固定版本和 8 + 3 实发分片需要符合审核的 Jev 调用 |
| C0-2 | BLOCKED | 等待 Choice、Score、Noul 完整真实响应 |
| C0-3 | PASS | Tavily 认证搜索一次，HTTP 200、实报 1 credit，原帖 94603 许可回源成功 |
| C0-4 | BLOCKED | SQLite 归档通过核对，真实 Jev 用量及余额回填待验证 |
| C0-5 | PASS | 36 次限制案例在传输前拦截，六种故障演练 |
| C0-6 | PASS | 两个产品品类及 30 个意图的跨品类召回冒烟 |
| G-1 | BLOCKED | 等待供应商留存审查及 C0-1、C0-2、C0-4 |

[正式批次 `89b0c2d1-576d-420f-9046-9e55878159be`](docs/evidence/p0-0/tavily-live/README.md) · [需求矩阵](docs/requirements-matrix.md) · [15 个模块](MODULE_ROADMAP.md)

## 后续依赖

M01 业务部分继续等待经核验的 Jev 留存政策、处理链和实际响应。M02 后续正式额度能力另按 TC 与 G5 验收。M03 研究项目和范围可以作为下一单模块候选，其正式投入使用仍依赖 G-1，独立预开发需有明确范围和授权。
