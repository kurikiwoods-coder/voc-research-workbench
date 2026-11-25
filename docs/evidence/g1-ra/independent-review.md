# G-1-R-A 独立复审

复审范围为 PackyCode 候选配置、账户审查、网络准入、分片证据及计费。以现有正式分支工程基线 `a7b1de491c85fb879bed4b2ce25f9f3164add6a0` 为起点。接入公开资料、实验范围及待验证项见[通道文档](../../packycode.md)。

## 缺陷与复验

| 级别 | 发现 | 修复及复验 |
| --- | --- | --- |
| P1 | 在账户未配置时导入供应商审查，随后登记首个密钥，共用流程可将该审查绑定新账户。复用到 PackyCode 时缺少账户级审查证据。 | [配置 API](../../../src/dashboard/api_setup.py)要求 PackyCode 先配置密钥再导入对应审查。轮换及删除时清除旧绑定，[Settings](../../../src/config.py)同时校验当前账户摘要和通道字段。独立复审核查了无账户绑定、轮换、同供应商其他账户及供应商之间的审批隔离。 |
| P1 | 任一分片缺少 `usage.output_tokens` 或为非法值时，诊断仍可能判定通过。 | [诊断](../../../src/execution/provider_diagnostics.py)将该分片用量缺失登记为 Schema 缺口。合成反例覆盖缺字段、负数及合法零值。 |

工程复验使用本机隔离数据库及合成响应，核对固定端点、固定模型、8+3 分片、Choice/Score/Noul、概率缺项、异常状态、幂等恢复、内部数据出站拦截、合成密钥脱敏及估费/账单区分。[新增 Python 专项](../../../tests/test_packycode.py)在 Windows 10 普通用户会话通过 15 项。既有 TypeSafe 和 JevModel 使用各自原有端点。

应用层、正式批次、分片及出站实现分别保留 PackyCode 真实调用拦截。受控代码路径的自动化断言验证诊断不会新建运行记录，正式批次不会触发付费发现，拦截前不会调用网络适配层。文档与公开元数据仅通过公开只读请求核对。

## 待核验

- 开发范围内无未关闭的 P0/P1。账户级书面审核待完成，供应商真实响应、重试表现、可用余额及账单待实测。
- TypeSafe 原生 Score 文档还规定 `legend`。现行工作台 C0-2 确认分数、置信度和逐档概率。真实预检需另核对并记录 PackyCode 返回的档位说明。
- 一次合成预检授权涵盖 8+3 两片，累计上限为 100,000 输入 token。当前未配置测试账户密钥，账户级书面审核未完成。真实调用仍被拦截，实际调用数量为 0。
- `PACKYCODE_LIVE_CONTRACT = NOT_TESTED`，`PACKYCODE_PROVIDER_APPROVAL = PENDING`，`G1_RB = NOT_STARTED`，`G-1 = BLOCKED`。Windows 11 实机结果继续登记 `NOT_TESTED`。
