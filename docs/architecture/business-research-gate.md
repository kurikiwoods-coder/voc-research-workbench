# Business Edition 原 G-1

商用版正式入口沿用 G-1、PDT v1.3.1 和原验收矩阵。当前 **G-1 = BLOCKED**，PackyCode 账户审批 **PENDING**。同一正式批次 C0-1 至 C0-6 全部通过，并取得实际账户、实际通道、用途及公开语料处理审批后才可放行。保留原供应商的商业授权、地区、留存、分处理商和 TypeSafe 组织 ZDR 等适用条件。P0 正式 Jev 固定 `jev-1.14.0`，后续模型继续按独立审查、实测和金标准流程。[原验收矩阵](../requirements-matrix.md#当前验收快照) · [模型协议](ai-model-adapter-contract.md)

## 当前阻断及扩展边界

| 现有代码 | 实际行为与后续边界 |
|---|---|
| [run_checks](../../src/execution/checks.py) | `run_checks` 在 `store.writer()` 内更新本机配置。PackyCode 分支在 `store.begin()` 前抛出 `Conflict(PACKYCODE_LIVE_BLOCK)`。该入口及既有 G-1 同批六项逻辑继续保留 |
| [通用外发](../../src/execution/transport.py) · [Jev 分片](../../src/execution/jev.py) | 公开数据标签和端点白名单先验，PackyCode 在真实传输层拒绝。在非夹具的分片编排中也存在 PackyCode 阻断。后续个人策略使用服务端独立准入上下文，保留通用路径的防护 |
| [供应商审查](../../src/config.py) · [API 配置](../../src/dashboard/api_setup.py) | `review_status`、`validate_review` 按提供商及当前账户绑定实际记录，PackyCode 的专门字段继续用于商用。凭证变更清除匹配审批。个人风险决定另存 |
| [一次性预检](../../src/execution/packycode_preflight.py) | 固定端点、合成正文、两片预约和单独账本，历史发送资格已用完。正式个人或商用使用经各自门禁重新取证 |
| [正式采集](../../src/dashboard/acquisition_api.py) · [统计](../../src/raw_store/denominators.py) | 当前正式采集被拒，正式统计的准入缺项表现为 `unavailable` 和 `counts: null`。后续消费当前有效的商用门禁及 M05/M06 真实资格 |

商用运行绑定 `edition=BUSINESS` 与既有 G-1 命名空间。按版本、策略、项目、用途、供应商和实际通道、凭证版本、审批时间和有效期、证据、风险记录及验收批次独立记录。既有 G-1 历史结果继续可审计，个人账本和个人接受风险只在其原作用域可用。商业采集、正式编码、发表、导出、历史读取和出队仍复核组织权限、真实来源和 M06 精确条件。结论失格时执行原遮蔽、失效与重算机制。

[个人门禁](personal-research-gate.md) · [源码接入计划](../planning/g1-personal-implementation-plan.md) · [PackyCode 账户审查](../packycode.md)
