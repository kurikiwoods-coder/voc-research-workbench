# PackyCode 通道与准入准备

PackyCode 是 M02 中独立的 Jev 候选供应商。当前记录为 `PACKYCODE_LIVE_CONTRACT = NOT_TESTED`、`PACKYCODE_PROVIDER_APPROVAL = PENDING`、`G1_RB = NOT_STARTED`、`G-1 = BLOCKED`。工程阶段使用隔离合成夹具，真实研究 API 调用为 0。

## 契约及证据

2026-11-25 核对了下列公开文档和元数据。实际返回的模型、字段和用量仍待受控实测。

| 项目 | 公开证据及实测范围 |
| --- | --- |
| 地址、分组、模型 | 通用生产网关为 `https://cf.api.fan`。分组说明和公开模型目录列出 `typesafe-officially`、`jev-1.14.0` 和 `POST /v1/systemone`。本地固定完整端点 `https://cf.api.fan/v1/systemone`。[网关说明](https://docs.packyapi.com/docs/register/6-cli.html) · [分组说明](https://docs.packyapi.com/docs/token/2-group.html) · [公开模型元数据](https://www.packyapi.ai/api/pricing) |
| 认证及请求 | 连接器采用 `Authorization: Bearer`，发送固定 `model`、`state` 和 `questions`，沿用 Choice、Score、Noul 和 8+3 分片。上游 OpenAPI 描述了相应认证、类型和输入输出用量字段。PackyCode 经该账户接受同样认证、返回全部字段及处理幂等键的行为仍待实测。[TypeSafe OpenAPI](https://api.typesafe.ai/openapi.json) |
| 公开计费参数 | PackyCode 元数据列出模型倍率 `0.021`、输出倍率 `0`、分组倍率 `7` 和每计价单位配额 `500000`。按 New API 公开公式可复算负责人提供的候选报价，每百万输入 token **USD 0.294**，输出 **USD 0**。账户实际计价、折算、舍入、扣费和余额需单独核验。[公开模型元数据](https://www.packyapi.ai/api/pricing) · [公开平台元数据](https://www.packyapi.ai/api/status) · [计量公式](https://docs.newapi.pro/zh/docs/guide/console/settings/rate-settings#额度计算公式) |
| 独立账户审核 | PackyCode 有公开服务条款及数据处理协议入口。需取得适用于当前账户、分组和实际上游的书面材料。TypeSafe 的组织级 ZDR 审批由 TypeSafe 单独确认，分组文字不作为账户审核依据。[服务条款](https://www.packyapi.ai/service-specific-terms) · [数据处理协议](https://www.packyapi.ai/dpa) · [TypeSafe ZDR 说明](https://help.typesafe.ai/articles/9520184411-do-you-offer-zdr) |

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
4. 连接和接口契约保留当前实际状态。工程版本的 PackyCode 真实诊断由服务端拒绝，G-1 正式批次也在发现、研究调用和持久化新批次前被拦截。

## 账户材料及下一轮

- 准备适用当前组织和账户的条款、证据出处和审查日期。材料应能核对请求及响应留存、训练用途、删除机制、处理地区、分处理商、公开语料处理授权、实际转发的上游，以及组织级 ZDR 的适用结果。
- 审查记录包含审核人、时间、地区、条款引用、上游引用、供应商、分组、固定模型、完整端点、公开语料授权、审核项目记录及附件 SHA-256。现行接口要求保留审查附件并与当前密钥绑定。可按[连接性文档](connectivity.md)查看共用字段。
- 负责人补充授权限一次小额合成真实预检。单次预检使用 8+3 问题分片，对登记端点发送两次 POST，累计最多 **100,000 输入 token**，执行后停止。输入仅使用独立合成文本，排除真实原话、内部资料、CX 数据和个人信息。当前账户级审核缺失，本机密钥尚未配置，真实调用门禁仍关闭，预检输入用量为 0。
- 放行后在工作台受控入口核对账户、端点、用量上限和固定模型，再记录两片实测响应、问题 ID 对齐、合并结果以及 Choice、Score、Noul 的完整字段和分布。单独登记实际用量、扣费、余额、Schema 缺项和正式准入缺口。限流、传输中断或扣费不明时停止发送并核对账户账单，保留已有证据。
- G-1-R-B 需记录固定模型、按真实阶段要求完成的 8+3 分片、三类实际响应、各片用量和经账户证据核对的余额或扣费。保留原 C0-1 至 C0-6 同批标准及 G-1 正式放行条件。单次合成预检用于连接取证，正式研究数据和流程由下一轮授权及准入条件控制。
