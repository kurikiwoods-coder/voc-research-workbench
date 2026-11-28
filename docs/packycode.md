# PackyCode 通道与准入准备

PackyCode 是 M02 中独立的 Jev 候选供应商。独立合成预检 `PACKYCODE_LIVE_CONTRACT = PASS`，两片共 11 题通过契约校验。两片实际费用已据原始 CSV 补证为 $0.000238，个人 Windows 10 的原始账本待本机独立核对。[G-1-R-B-F 费用证据](evidence/g1-rb-f/README.md)`PACKYCODE_PROVIDER_APPROVAL = PENDING`、`G1_RB = BLOCKED`、`G-1 = BLOCKED`。[安全决定](decisions/packycode-synthetic-preflight.md) · [工程证据](evidence/g1-rb-p/README.md)

## 契约及证据

2026-11-25 核对了公开文档和元数据，并完成固定合成输入的实际响应实测。真实研究用途须按各版准入单独验收。[原实际接口结项](evidence/g1-rb-p/README.md#实际接口结项)

| 项目 | 公开证据及实测范围 |
| --- | --- |
| 地址、分组、模型 | 通用生产网关为 `https://cf.api.fan`。分组说明和公开模型目录列出 `typesafe-officially`、`jev-1.14.0` 和 `POST /v1/systemone`。本地固定完整端点 `https://cf.api.fan/v1/systemone`。[网关说明](https://docs.packyapi.com/docs/register/6-cli.html) · [分组说明](https://docs.packyapi.com/docs/token/2-group.html) · [公开模型元数据](https://www.packyapi.ai/api/pricing) |
| 认证及请求 | 连接器采用 `Authorization: Bearer`，发送固定 `model`、`state` 和 `questions`。该账户 8+3 分片均返回 HTTP 200 和 `jev-1.14.0`，Choice、Score、Noul 字段完整。客户端每片只预约并发送一次，网关如何处理幂等键仍未核实。[TypeSafe OpenAPI](https://api.typesafe.ai/openapi.json) |
| 公开计费参数 | PackyCode 元数据列出模型倍率 `0.021`、输出倍率 `0`、分组倍率 `7` 和每计价单位配额 `500000`。按 New API 公开公式可复算负责人提供的候选报价，每百万输入 token **USD 0.294**，输出 **USD 0**。账户实际计价、折算、舍入、扣费和余额需单独核验。[公开模型元数据](https://www.packyapi.ai/api/pricing) · [公开平台元数据](https://www.packyapi.ai/api/status) · [计量公式](https://docs.newapi.pro/zh/docs/guide/console/settings/rate-settings#额度计算公式) |
| 独立账户审核 | 商用版需取得适用于当前账户、分组和实际上游的书面材料，TypeSafe 组织级 ZDR 由 TypeSafe 单独确认。个人版使用现有账户信息、适用的公开条款及 Owner 基础核验。通道分组只能证明通道配置。[个人准入政策](architecture/personal-research-gate.md) · [服务条款](https://www.packyapi.ai/service-specific-terms) · [数据处理协议](https://www.packyapi.ai/dpa) · [TypeSafe ZDR 说明](https://help.typesafe.ai/articles/9520184411-do-you-offer-zdr) |

Token Center 分别显示供应商实际返回的输入、输出用量，以及按候选报价计算的估算费用。现行接口无法核实实际扣费或余额，用量结果可以为空，余额显示未同步。控制面用量查询另需系统令牌和用户 ID，负责人可在供应商控制台核对。[PackyCode 用量查询说明](https://docs.packyapi.com/docs/ccswitch/4-usage-query.html)

## Windows 10 本机配置

在普通 Windows PowerShell 中进入 [项目目录](../README.md)，使用现有 Python 3.12 虚拟环境。

```powershell
Set-Location -LiteralPath 'C:\Users\kurik\Documents\Codex\VOC Workbench 研究'
.\.venv\Scripts\python.exe -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765 --no-proxy-headers
```

1. 打开 [工作台](http://127.0.0.1:8765/)，进入 **API 配置中心**，找到 **PackyCode** 卡片并核对分组、固定模型和登记端点。可从卡片打开[注册](https://www.packyapi.ai/register)及[定价](https://www.packyapi.ai/pricing)页面。
2. 负责人在该本机卡片录入 PackyCode 密钥并保存。Windows 使用当前用户的 DPAPI 保存。轮换及删除也通过该卡片处理。密钥和未脱敏账户材料留在授权设备。
3. 账户及通道审查完成后，经卡片导入审查 JSON 和对应附件。审查绑定当前账户。更换或删除 PackyCode 密钥会撤销原审查绑定，新密钥需重新导入审核。
4. 工作台原有诊断和正式批次继续执行 PackyCode 阻断。一次性合成接口预检使用下列本机命令。

## 一次性合成接口预检

历史批次的两次 POST 已完成，发送授权已耗尽。以下保留原执行步骤供审计，当前用不含启动标志的查询命令回读既有记录。[原授权](decisions/packycode-synthetic-preflight.md)

普通 Windows PowerShell 在项目目录运行 `.\.venv\Scripts\python.exe -m src.execution.packycode_preflight` 查询独立账本。

1. 在 [PackyAPI 令牌管理](https://docs.packyapi.com/docs/register/4-token.html)核对本机凭证对应独立测试令牌，并核对分组、固定模型、有效期、金额限额及余额。本轮使用最多 2 美元的一次性限额令牌，额度关闭无限及自动重置。100,000 输入 Token 是本地预算目标。网关对单次在途扣费或上游重试的处理尚未获得证明。
2. 记录可追溯的材料出处。在工作台普通用户会话计算默认 DPAPI 凭证文件密文的 SHA-256，执行 `(Get-FileHash -LiteralPath .\runtime\credentials\local-api.json -Algorithm SHA256).Hash.ToLowerInvariant()`。使用自定义数据目录时，将 `$env:VOC_DATA_DIR` 指向工作台实际目录，并用该目录下的凭证文件计算哈希。
3. 在 Git 忽略的本机目录（如 `runtime`）准备 JSON。用控制台实证填写额度、余额及重置字段。三个许可字段仅在负责人核实后填写 `true`。

   ```json
   {
     "provider": "packycode",
     "group": "typesafe-officially",
     "model": "jev-1.14.0",
     "endpoint": "https://cf.api.fan/v1/systemone",
     "protocol": "SystemOne",
     "synthetic_use_permitted": false,
     "current_key_entitled": false,
     "quota_available": false,
     "token_quota_usd": "",
     "token_remaining_usd": "",
     "quota_resets": null,
     "evidence_reference": "",
     "expires_at": "",
     "vault_sha256": ""
   }
   ```

4. 证据完整后运行 `.\.venv\Scripts\python.exe -m src.execution.packycode_preflight --execute --account-evidence .\runtime\packycode-preflight-account.json`。有效期用带时区的 ISO 8601 时间，以证据及凭证到期时间较早者为准。保留 `runtime/packycode-preflight` 下账本及其 SQLite 辅助文件。此授权限当前个人电脑的工作台安装，更换目录也不得重发。
5. 首片返回后，如模型、字段和用量均通过，命令暂停，等待输入消费明细中的首片实际扣费与当前令牌余额（美元，用空格分隔）。命令用首片实报输入加第二片 65,536 Token 估算核对预算。缺项、金额不明或预计超预算时停止。第二片完成后，单独从控制台核对最终实际扣费与余额，只留存脱敏结果。
6. 已在首片对账点以 `first_shard_billing_unverified` 停止时，先取得首片的单笔扣费和原限额令牌当前余额，再用原账户证据文件运行下列命令。用同一 Windows 用户和原凭证，保留账户材料的原始内容及有效期。命令在账本写锁内核对原回执、首片证据和预算，追加第二片预约。第二片存在任何预约即拒绝再次发送。历史回执保留，查询默认显示最新结果。

   ```powershell
   .\.venv\Scripts\python.exe -m src.execution.packycode_preflight --resume-second --account-evidence .\runtime\packycode-preflight-account.json
   ```

## 费用补证

控制台原始 CSV 核对 22:08:59 与 22:44:50 两条单笔费用，分别 $0.000144 和 $0.000094，累计 **$0.000238**，809 输入、220 输出及零缓存读写。原账本和历史截图留在授权设备，个人 Windows 10 原始 SQLite 仍需本机复验。Token Center 的程序投影仍按现有估算、真实用量和余额状态显示。账单转录沿用原合成批次，仅保留脱敏两行。[费用补证与本机步骤](evidence/g1-rb-f/README.md)

## 账户材料及下一轮

- 准备适用当前组织和账户的条款、证据出处和审查日期。材料应能核对请求及响应留存、训练用途、删除机制、处理地区、分处理商、公开语料处理授权、实际转发的上游，以及组织级 ZDR 的适用结果。
- 审查记录包含审核人、时间、地区、条款引用、上游引用、供应商、分组、固定模型、完整端点、公开语料授权、审核项目记录及附件 SHA-256。现行接口要求保留审查附件并与当前密钥绑定。可按[连接性文档](connectivity.md)查看共用字段。
- 本机 DPAPI 凭证与负责人截图中的限额测试令牌掩码一致。实际接口结果见[验收证据](evidence/g1-rb-p/README.md)。
- G-1-R-B 需记录固定模型、按真实阶段要求完成的 8+3 分片、三类实际响应、各片用量和经账户证据核对的余额或扣费。保留原 C0-1 至 C0-6 同批标准及 G-1 正式放行条件。单次合成预检用于连接取证，正式研究数据和流程依所用版本分别获准。原 `run_checks` 及真实传输的 PackyCode 阻断继续生效；个人版将由独立服务端策略审批。[商用 G-1](architecture/business-research-gate.md) · [个人版审批](architecture/personal-approval-workflow.md)
