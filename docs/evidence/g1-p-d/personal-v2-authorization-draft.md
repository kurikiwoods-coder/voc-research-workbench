# G-1-PERSONAL V2 本机批次授权草案

**待负责人签发。** 当前正式批次、逐槽授权、外部请求、正式证据纳入和业务分母增量均为 0。适用于原 G-1-P-D 预准入执行路径。完整授权材料与真实证据保存在受保护的本机工作区，仓库保留此空白草案及经批准的脱敏引用。[个人准入政策](../../architecture/personal-research-gate.md) · [历史 D-L 草案](d-l-authorization-draft.md)

## 批次签发

| 审批材料 | Owner 待核及填写 |
| --- | --- |
| 工作区与范围 | 受保护本机 Personal v11 工作区与独立恢复连续性证据。核对当前库身份、撤销水位、已发送预约及对账状态。填写受信 Owner 和操作者引用、项目、冻结范围 ID 和版本、`g1_personal_acceptance` 用途、政策与批准材料版本，以及材料引用与 SHA-256。 |
| UTC 与资产 | 填写签发、开始和到期 UTC，逐槽窗口包含在批次窗口内。Owner 按现有账户信息、适用公开条款核对当前 Tavily 和 PackyCode 的账户、通道、API 权利、用途及凭证版本。Tavily 与 PackyCode 限该次批准的账户与用途。Stack Exchange 回源按批准的匿名官方接口执行。 |
| 逐源许可 | 每一合法公开来源的处理、外发、保留及署名范围、依据、审核者与到期日。本机保存获准的源 URL、允许保留的原话及其摘要。经回源复核后登记脱敏、最小化及拟外发内容摘要。 |
| 预算 | 填写各账户及批次的请求数、credit、输入／输出／总 Token、单槽及累计费用预算、币种及整数精度。记录当前费率、取整规则、可用额度证据与材料有效期。历史估算及账单保持原用途。 |
| 费用及剩余风险 | Owner 单独签署适用于当前账户及固定模型通道的费用和风险记录。登记本机约束、供应商已核实的限制，及尚无硬限额、在途扣款和供应商内部重试边界证明时的影响与处置。费用估算、实际扣费和余额各自留证。批准材料注明风险范围、保护措施、Owner 和复核期限。 |
| 最终批准 | 待填批准引用、摘要、签发／有效窗口、预算、暂停及撤销权限和费用对账责任人。材料变更、账户或凭证轮换后重新核验。 |

### 本机批准包格式

| 字段 | 填写规则 |
| --- | --- |
| `draft` 的批次字段 | `owner_ref`、`study_id`、`scope_id`、`scope_version`、`evidence_ref`、`starts_at`、`expires_at`、`budget`、`currency`、`decimals`、`single_cost`。日期用 UTC，金额使用币种精度对应的整数单位。 |
| `v2.slots` | 键为 `search/1`、`source/1`、`model/1`、`model/2`。每个槽填写 `provider`、`account_ref`、`channel_ref`、`credential_revision`、`limit`、`account_limit`。批次和槽位的预算对象使用 `requests`、`credits`、`input_tokens`、`output_tokens`、`total_tokens`、`units`。两片模型用同一获准的模型账户、通道和凭证版本。 |
| `v2.search_payload_sha256` | 获准搜索的冻结载荷 SHA-256，以实际请求构造和序列化计算。 |
| `v2.systemone` 的批准和取证引用 | `approval_event_id`、`dedicated_token_ref`、`billing_rules_ref`、`allowance_ref`、`risk_acceptance_ref`。均指向适用的受保护本机材料，其中专用令牌填写受控引用，计费规则材料记录已核实费率及尚待确认的收费条件。 |
| `v2.systemone` 的费率和限额 | `rate_basis_tokens`、`input_rate_units`、`output_rate_units`、`additional_units_per_request`、`allowance_units`、`residual_risk_units`。分别记录计价基准、输入及输出费率、已知单次附加费用、已证实的令牌可用额度及 Owner 批准的剩余风险金额。费率、额度和风险金额待实际证据。 |
| `v2.systemone` 的风险三态 | `overdraft`、`auto_recharge`、`unbounded_charges` 各填 JSON `false`（经证据确认不存在）、`null`（未知）或 `true`（已知存在）。任一项为 `true` 时阻断。任一项为 `null` 时，`residual_risk_units` 须为 Owner 批准的正值上限，且 `risk_acceptance_ref` 的本机证据须列出实际未知项、接受理由和批准边界。 |

逐片将输入 Token 上限乘以输入费率、将输出 Token 上限乘以输出费率，再各自除以计价基准并分别向上取整。两项相加后计入已知单次附加费用，所得金额须由该槽预约覆盖。模型两片的金额上限加上批准的剩余风险金额须在已证实的专用令牌额度内。

实际控制台配置为 USD 2 时，额度证据注明它是该专用令牌的配置值，并记录当前适用的账户和凭证。供应商侧硬扣费上限须凭适用于该通道的可执行性证据登记。历史余额、配置额度、已批准费用风险及逐笔实扣各自保留证据。

## 四个唯一操作槽

| 槽 | 本机操作和依赖 | 拟签发上限及证据 |
| --- | --- | --- |
| 1 · Tavily 搜索 | `search/1`，限批准检索词、来源域、账户、通道及凭证版本。冻结检索载荷。 | 最多 1 次、基础搜索拟用 1 credit。核对上限、实际计价、查询及响应摘要、实报 credit 和候选来源。 |
| 2 · 官方回源 | `source/1`，仅用槽 1 已结算合格回执中的同一 canonical 命中。绑定该回执的请求 ID 与摘要。以匿名 Stack Exchange 官方接口回源。 | 最多 1 次。拟用 credit 0、Token 0、费用 0。记录合格来源 URL、时间、用户原话摘要、许可及署名并复核可否外发。 |
| 3 · PackyCode 前 8 题 | `model/1`，依赖槽 2 合格回执。绑定准确的脱敏输入及冻结题组。固定 `typesafe-officially`、`/v1/systemone`、`jev-1.14.0`。 | 最多 1 次。待填输入／输出／总 Token 和金额预算。核对真实模型、题号及 Choice、Score、独立 Noul，记录请求标识、回执及实报用量。 |
| 4 · PackyCode 后 3 题 | `model/2`，依赖槽 3 通过契约校验并实扣对账的回执。使用同一脱敏输入、固定模型、账户、凭证和冻结题组。 | 最多 1 次。按槽 3 的实报及对账核对剩余额度，待填本槽 Token 和金额预算。保存三题完整响应及实报用量，按题号合并 11 题。 |

首次选定命中后，Owner 复核该来源及许可并登记证据。回源和模型操作包的 `source_expires_at` 使用 UTC，覆盖整个操作授权窗口。操作包继续绑定批次、账户、通道、凭证版本、来源及载荷摘要、限额和证据引用。省略 `depends_on` 和 `depends_on_sha256` 时，服务自动绑定本批前序合格且已结算的回执。

两片共享一份 C0-2 脱敏复核。登记回源请求 ID、原话摘要、脱敏模型输入摘要、脱敏复核引用和 `question_version`。`question_version` 用 `"personal-d-live-v1." + digest([pairs, model_payloads(text, options)])` 计算。登记 Choice 的稳定 ID、定义及顺序，确认复核涵盖固定的 11 题和两片载荷。批次批准覆盖两片，按当前许可、预算和回执复核每次发送。

四槽合计最多 4 次。额外探针、余额查询、自动重试、重定向请求或替代模型不在此授权范围。

## 执行、停机与复审

1. 在受保护工作区通过现有 G-1-P-D 入口执行，完成发送前授权重验、预算预约及唯一发送权登记后才可外发。预留金额和 Token 上限是本机接纳约束。供应商侧是否提供可执行限制依签发时的证明登记。发送后实报超额、契约缺项、网络结果未知、权限变动或扣费未明时暂停并保留档案，人工对账后按当前授权决定接续。
2. 每槽核对请求标识、实报用量、本机 SQLite 与受保护回执。支付操作核对供应商逐笔实扣，对账后按原存储与恢复路径复验重启回读、幂等和唯一归属。余额标记为实证或未同步。C0-5、C0-6 的既有离线材料经版本、适用范围及原始产物摘要复核后引用到本批。C0-1 至 C0-4 依适用正式证据逐项判定。
3. 六项均具备合格同批证据后转交 G-1-P-R。独立复核签发、许可及脱敏、实际模型与响应、六项原始产物、预算预约及实扣、故障与恢复。当前个人门禁 `NOT_EVALUATED`，正式编码、发布和研究分母保持关闭，M09 等单独开发授权。

日常 API 的凭证启用、有效期、限额、账单对账、停用和轮换仅登记为 G-1-P-R 与 M02 的后续政策。此次草案签发范围为上表四个验证槽位。[日常 API 生命周期政策](../../architecture/personal-research-gate.md#日常-api-生命周期政策)

[预准入工程](d-l-engineering.md) · [Windows 11 及部署证据](d-l-windows11-deployment.md) · [六项正式验收](README.md#六项正式验收状态)
