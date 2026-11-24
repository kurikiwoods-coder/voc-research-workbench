# M06 本机 API 与界面契约

以下为拟议接口。已存在的入口是 `CorpusStore.qualified_record(study_id, record_id)`、`GET /api/corpus/{study_id}/records/{record_id}/eligible` 与 M03 的 `GET /api/studies/{study_id}/scopes/{scope_id}`。M06 工程实施须复用前两者同一资格逻辑。PDT §6.9 的 scope 查看需求沿用 M03 的冻结路径，查询指定版本，不另存范围副本。

## 通用约定

- 关系定义以 registry_version 精确定位。项目证据接口必须给 study_id，固定 segment_revision；首次浏览可解析当前版并把确切版返回，翻页必须带回。scope_id、scope_version 成对；可选 batch_id、source、time_field、from、to、product_category_id、category_id、intent_id、confidence_band、index_version。多选同维为并集，维间取交集，时间为 UTC 半开区间。具体见[统计契约](m06-statistics-contract.md)。
- 全局及历史定义端点均使用获准共享字段的显式投影，包括定义、公开生命周期、版本及主次边。正反例须是独立编写的合成示例或经独立治理批准共享的内容。项目来源、使用和发现批次、项目证据计数、私有评审理由、依赖和撤销提示均按独立项目权限读取。跨项目对象查询统一 404，项目选择器只给出可访问项目，遗漏 study_id 不从界面状态补取。
- 所有新增路径（含 /api/intents、/api/categories、/api/product-categories 及各自集合根路径）须显式纳入现有本机私有路由保护。只从真实回环客户端接受，忽略代理头冒充的地址，复用现有 Host 检查与 API no-store。带副作用或 POST 校验请求遵守同源 Origin 和 X-VOC-Action: connectivity。读、项目操作、全局审核分别校验；API 不接受调用者自行声明的角色。当前工作台尚无完整的全局审核授权流程，M11 接管写命令前须确定可信操作者来源。
- 成功读返回 200。集合返回 items、next_cursor、resolved_versions、filter_echo、mode、as_of_utc；稳定排序指定 ID，游标绑定相同筛选、项目和版本；页大小建议默认 25、上限 100。游标每次重核项目权限和 M05 资格，长查询需在交付前用新快照复核实际依赖。对失效视图重新开始查询，客户端清除旧结果和已打开的原文抽屉。空结果返回 []。无正式结果为 200 unavailable + reasons + counts:null。
- 400 参数组合冲突，422 无效 ID 格式/枚举/坐标或校验失败，403 回环、同源或操作权限不满足，404 查无或越项目，409 版本过时/已失格/幂等冲突，503 存储忙或资格不可检查（不返回旧值）。错误体含 code、message、可选 reason_codes、current_version、retryable；不带原文、路径、凭证、源 URL 或其他项目标识。写入幂等键及载荷摘要见[事务设计](m06-data-model.md)。

## 路由

下表省略 /api 前缀；S、M、E、P、C、A 为 study、mention、evidence、product、task、intent 的稳定 ID。路径中 categories 专指任务大类。

| 方法与路径 | 请求与权限 | 响应及边界 |
|---|---|---|
| GET /product-categories、/product-categories/{P} | 定义读取，按版本、parent_id、status、q | P、名称、描述、可空 parent_id、status、实体/注册表版本。失效节点可按历史版本查看。 |
| GET /categories、/categories/{C} | 定义读取，按版本、lifecycle_status、q | C、可操作定义、纳入/排除、发现方式、状态、版本。 |
| GET /intents、/intents/{A} | 定义读取，按版本、候选/确认、任务 ID | 名称、获准共享定义与例子、lifecycle_status、获准共享的 survey_validation_status、primary_category_id、category_ids 及公开变更引用。候选允许 primary=null。代表支持及私有理由须从受权限控制的项目入口读取。 |
| GET /categories/{C}/intents、/intents/{A}/categories | 定义读取，registry_version，role=primary/secondary/all | 同一 intent_task 生成两方向，返回 ID、role 和版本；列表状态过滤对称。 |
| GET /product-categories/{P}/intents | 必填 study_id 与解析版；可按范围、批次、来源等筛选 | 项目内按 P 对有证据且有有效归属的 A 分组。每项给 distinct_mention_n、source_breakdown、可下钻证据引用和版本。正式模式只含 published_classified，工程模式仅列已存在的可核关系并注明资格。 |
| GET /intents/{A}/product-categories | 同上；同一证据谓词、时间及版本 | 每个产品给 P、distinct_mention_n、支持它的 evidence_refs；无产品证据返回空。纯定义读另取 /intents/{A}/categories。 |
| GET /studies/{S}/mentions、/studies/{S}/mentions/{M} | 本项目读取，固定版、过滤，同批可按 counting_bucket 查 | 片段 ID、当前身份/处理状态、允许展示的 evidence_refs、替代版与主次关联、判定理由。只在明确工程/合成/正式模式下提供对应状态。无有效源时仅向获准审计者给 tombstone，不返回原文。 |
| GET /studies/{S}/mentions/{M}/evidence/{E} | 同项目 + 指定 R，检查 support 成员资格，再逐次调用 M05 | 成功含 record_id、E、码点起止、合法摘录与原出处、scope_id/scope_version、batch_id、许可状态、分段版本、当前重复组提示。部分撤销只屏蔽对应 E；指定已失格边返回 409，不暴露旧原文或定位信息。 |
| POST /studies/{S}/relations/validate | 同源项目操作。传 operation、候选 ID、expected_registry_version、expected_segment_revision、主次与证据引用 | 200 valid 布尔值、violations、可确认条件及所用版本。预检无写入，不能作为发布凭据。对“缺父候选”区分允许保存与阻止确认。 |
| GET /studies/{S}/denominators | 必填 mode=engineering/synthetic/formal，附上述筛选与版本 | availability、reasons、counts、by_primary_category、excluded_by_reason、reconciliation、filter_echo；各阶段 null 说明缺项。正式未放行时 counts 与正式对账均 null。 |
| POST /studies/{S}/registry/joint-confirmation（M11 后续命令） | 可信全局审核权限 + 项目证据权，Idempotency-Key。传 expected_registry_version、expected_segment_revision、candidate_intent_id、candidate_category_id、primary_category_id、secondary_ids、representative_refs、reason；证据引用精确绑定 R/M/E。若批准跨项目支持，每条另核对应项目与版本，跨项目引用不允许通过单一 S 的授权。 | 201 新发行，200 同载荷重放（重核授权后只返回原 ID 与版本）；同键异载荷或旧版本 409。锁内校验同一 UTC 日的 M05 资格、唯一有效主边、至少三次独立代表发生和冻结范围；必要关系、版本与审核结果原子写入。返回 command_id、registry_version、确认的两 ID，数据不足 422。M06 基础界面只提供预检。 |

**响应示例（合成，仅示协议）**

```http
GET /api/studies/S-demo/denominators?mode=formal&registry_version=1.0.0&segment_revision=2
```

```json
{"mode":"formal","availability":"unavailable","reasons":["G1_BLOCKED","RESEARCH_NOT_ADMITTED","M12_RECEIPTS_MISSING"],"counts":null,"reconciliation":null,"by_primary_category":null,"excluded_by_reason":null,"filter_echo":{"study_id":"S-demo","registry_version":"1.0.0","segment_revision":2}}
```

```http
POST /api/studies/S-demo/relations/validate
Content-Type: application/json
Origin: http://127.0.0.1:8765
X-VOC-Action: connectivity
```

```json
{"operation":"confirm","candidate_intent_id":"INT-demo","primary_category_id":null,"expected_registry_version":"1.0.0","expected_segment_revision":2,"representative_refs":[]}
```

返回 200 及 `{"valid":false,"violations":["PRIMARY_REQUIRED","REPRESENTATIVES_INSUFFICIENT"],"candidate_allowed":true,"registry_version":"1.0.0","segment_revision":2}`。证据查看也不开放外发，沿用 research_eligible=false、outbound_allowed=false。内部 CX、附件、历史 verified、import_rows 与 import_candidates 均不能用作此 API 的数据捷径。

M05 资格 GET 仍按现有接口独立读取当前快照。M06 写入时必须在同一 SQLite 写事务内使用同源资格实现。项目内证据接口先核项目与精确成员键，再取原话投影；产品、编码和统计调用均不得使用另一条 evidence 的产品/许可来替换实际依赖。历史 URL、指定 V/R、游标及幂等结果都不授予数据访问权。失格后正式结果无有效依赖即停止展示或按仍成立的关系重新核算；审计读仅向有权者提供脱敏元数据。重新授权后，从重新核验与复核入口生成新结果。展示、下载与发送前分别检查当前政策，已分发文件遵循适用的撤销处置流程。

## 召回消费者接口

M06 提供指定 V 的已封版共享定义、主次任务和版本索引。M07 管理获准发行，M12 在明确的许可和放行检查下构造召回及编码回执。权威消费接口禁止把另一项目的原话、链接、依赖计数、研究状态或编码回执混入共享清单。M12 保存 mention_id、代表 record_id、R、V、index_version、算法版本、排序后的候选 ID 与相似度、K、模型及题组版本、None 与独立 Noul 回执，并精确绑定实际输入。产品/任务只作解释维度。已知候选达到 20 项时先全局缩至最多 19；1–19 可全列再加 None；0 项、异常或低相似入发现/人审。None 或 Noul 否不得用第一名替代。参见[验收口径](m06-test-plan.md)。本机查看界面不能触发模型调用。

## 中文线框

沿用现有工作台项目选择、导航、筛选条、主内容列表与证据抽屉，焦点关闭后回到触发项。

```text
桌面  当前项目 ▾    冻结范围 v2 ▾    注册表 1.0.0 ▾    片段版 2
      [关系查看] [分母对账]       模式：工程 ▾
      产品 ▾  主任务 ▾  意图 ▾  来源 ▾  批次 ▾  时间窗 ▾
      产品品类       有证据的意图      主任务 / 次任务      片段数
      空气炸锅       离线完成操作      离线操作 / 连续使用     1   查看证据
      右侧抽屉：片段 → 支持本品类的证据 → 允许的原话与来源
                行号 / 批次 / 冻结范围 / 核验时间 / 查看历史版

窄屏  项目 ▾  关系查看 ▾  筛选(2)
      空气炸锅 › 离线完成操作
      主任务  离线操作       合格片段 1
      查看证据 › 独立证据页 › 返回（保留筛选和滚动位置）
```

关系查看可切任务→意图或反向。范围品类、证据品类与次任务分别标明。候选行显示“缺主任务/待审”和原因，禁用正式统计入口。对账页并列分母链、六桶、排除原因和主类差值，展示筛选版本；差异时给出可下钻的异常 ID。低置信、撤销、访问受限、无数据、加载、失败重试、正式未准入均有中文文字状态；撤销后清空旧抽屉明文。窄屏分步呈现明细，键盘可打开、返回、重新核验，无需横向对照宽表。
