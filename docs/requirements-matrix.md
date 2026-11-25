# 开发与验收矩阵

基线为 PDT v1.3.1（§6–15、附录 C–F）与 27 页专案 v2.2（§1–12）。附件 PDT 与库内 Word 的 SHA-256 均为 `09edf47c95151276b39c4b375cd1e7e1f805591fb8d65b8f2c512087283a11b7`。专案 PDF 指纹为 `c613c7465d7a754e1e9b97032ae13c2b571564bd9dc76cd5d6a9691f33e0e88c`。开始开发时 main 为 `f849242`，49 个已跟踪文件，六层仅有 README。已有 JSON Schema、示例、决策记录和两份旧 shell 检查均保留。

## 文档差异与采用口径

| 分歧 | 专案或旧记录 | 实现与验收依据 |
|---|---|---|
| 前置门 | 专案 §5/§9 和 PDT 附录 C 的 G-1 仍列五项 | PDT §13.0 有六项。G-1 汇总同一批次 C0-1 至 C0-6，逐项通过并留存适用服务商的公开语料处理审批和留存审查才可放行。 |
| C0 编号 | 专案 1 版本、2 分片、3 概率、4 搜索、5 额度 | PDT 1 版本及分片、2 三类字段、3 搜索原话、4 SQLite 与账本、5 CX 隔离及故障、6 三层召回。来源、请求、响应及编号均能回查。 |
| G0 | 专案冻结范围 | PDT G0 是 Windows 三次冷启动。范围冻结另列 BIZ-SCOPE。 |
| G1 | 专案统一表、快照、采样 | PDT G1 是三批/100 条/故障回退；快照与采样由 G1、G2、RAW 保存。 |
| G2 | 专案发现有效 | PDT G2 是 30 条抽样审计；专案发现对应 PDT G3。 |
| G3 | 专案 Jev 校准 | PDT G3 是盲测发现；专案校准对应 G4/J-2/J-3。 |
| G4 | 专案 None + Noul | PDT G4 是完整 Jev 编码和召回校准；守门单列 J-10。 |
| G5 | 两者都涉及额度，专案强调余额头 | 保留 provider、单位及同步来源。PDT C0-4 允许明确未同步。J-7 的响应头回填须单独实证。 |
| G6 | 专案为生成和真人试填，PDT 附录 C 包含真实回收 | P0 检查草稿、审批、2–3 人试填及导出/授权；P1 完成 G6 的真实发布、回收与回写。分项留证，完整 G6 等待真实回流。 |
| G7 | 专案是回灌，PDT 是故障与安全 | 保留 PDT G7；专案回灌落 P1-REFLOW/G6。 |
| 产品目标同名 | PDT §2 的 G1–G5 与附录 C 编号复用 | 验收中心 G 均指附录 C；产品目标由 DISCOVERY、J、P1、SURVEY、CAT 实现。 |
| 新意图 | 专案 §9 第 21 页要求真实产出 ≥1；第 23 页允许未发现 | PDT §2.3/§8.4 用盲测验证发现/拒绝/合并；真实样本允许无新意图及无新大类，以已有确认痛点出题。 |
| 大类与主归属 | 专案 §5A 两层，所有意图要求主大类 | PDT §6 三层；待父类的候选可缺主归属，正式意图唯一主任务大类；品类取证据，StudyScope 可不含产品。 |
| 超过 20 选项 | 专案给出分组分级 | PDT §7.2.1 全局向量召回最多 19 项，加 None、独立 Noul；无按产品硬筛。C0-6 本地冒烟与 J-14 人工盲测分项。 |
| 分母与字段 | PDT §6.6 用展示名，§9.3/Schema 用桶枚举；摘要 Schema 部分仍旧 | 存储以 §9.3 六个互斥桶为准；另算重复/无证据/无许可。主大类和产品过滤均按 distinct mention_id。 |
| 缺概率及隐私 | 专案有记录缺口后接受、未开 ZDR 可发公开内容等旧措辞 | 缺字段保持 BLOCKED；真实语料先核验所选服务商留存边界与证据。第三方单独审查。内部内容无条件只走本地。 |
| C0 搜索范围 | PDT §13.0 接受至少一个搜索 API；专案 §5 点名 Tavily / Brave | 分别记录公开论坛检索、许可正文与指定引擎。仅论坛成功时显示 PDT 通路实证，C0-3 综合验收保持 BLOCKED，直至任一指定引擎发现可核验原址。双引擎完整集成在 P0 验收。 |
| 来源与复现 | 专案来源表称 Reddit 主粮，其他小节已降级；旧稿按次调用复算 | 双引擎发现，Reddit 备用，许可原话按批落盘；回放已有输出，重算单存差异。 |
| 里程碑及旧脚本 | 专案为 37 文件；旧 smoke 只查样例，PDT 一处封面仍称 11 节 | 版本以附件指纹和提交为准；旧脚本不生成验收结果。P1/P2 受前序阶段约束。 |

## 当前验收快照

2026-11-24 执行批次 `89b0c2d1-576d-420f-9046-9e55878159be`。Tavily 认证搜索和许可原帖回源已通过。正式准入为 **BLOCKED**。[本轮证据](evidence/p0-0/tavily-live/README.md) · [配置中心验证](evidence/p0-0/api-setup/README.md)

| 项目 | 状态 | 可核验结果 |
|---|---|---|
| C0-1 | BLOCKED | JevModel 临时凭证已载入。因缺留存审查，固定版本和 8+3 题仅记录请求计划。 |
| C0-2 | BLOCKED | 尚无真实的 Choice、Score、Noul 响应，完整逐档概率待核验。 |
| C0-3 | PASS | 一次 Tavily 认证搜索 HTTP 200，返回 5 个合规候选链接和 1 个 credit。原帖 94603 回源 HTTP 200，许可、署名和原话通过核验。 |
| C0-4 | BLOCKED | 实际 SQLite 与 JSON 归档一致。没有模型请求，Jev 用量和余额回填待验证。 |
| C0-5 | PASS | 36 次外发拦截，0 次内部传输，六种合成故障演练在工程回归中复测通过。 |
| C0-6 | PASS | 2 个产品品类、3 个任务大类、30 个合成意图，两次跨品类 Top-12 命中。 |
| G-1 | BLOCKED | C0-1、C0-2、C0-4 和供应商留存审查待完成。下一阶段等待准入。 |

该历史批次的 Windows Server 2022 工程 CI 完成三次空库冷启动和中文、空格路径下的启动器验证。Windows 11 平台的后续实机结果见下文部署工程验收。G-1 以正式认证批次的状态汇总。[原帖复核](evidence/p0-0/closeout/public-source.json) · [API 配置](connectivity.md#注册与创建密钥)

P0-0 补充的设置向导、本机凭证保存与诊断均有独立工程测试。诊断使用单独的 SQLite，Jev 合成句子、搜索回源和脱敏证据的正式研究分母为零。真实 Jev 账本、指定搜索源和 G-1 继续按下表原有要求验收。[API 接入操作](connectivity.md#从工作台配置-api) · [工程测试用例](../tests/test_api_setup.py)

每项的时间、证据 ID、请求与响应可由 [JSON 与 SQLite 验收包](evidence/p0-0/README.md) 复核。下方映射表定义验收标准；重新运行页面将读取本机当前批次的结果。

## M06-C2 工程验收

M06-C2 = **ENGINEERING_PASS**。实现提交 `965a4b8` 的[三平台 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45532356340) 已通过。

| 对应条款 | 本轮实测 | 保留条件 |
|---|---|---|
| SOURCE-POLICY、PRIVACY；A07–09、A21 | Python、GET 及同连接写入复用实时资格，项目隔离、WAL 锁顺序、UTC 到期、副本、新授权及 M04 撤销回执兼容实测通过 | 仅本机工程资格。正式统计、外发及 G-1 依原矩阵 |
| CAT-8、CAT-10 的资格前提；B04、B08、B09、B13、B14 | 核对全部传入原话及上下文、拒绝已撤销依赖，读取/错误导出/暂存回查已检查 | M/E、版次发行、编码回执、历史报告及正式分母仍待后续阶段。逐案见[C2 证据](evidence/m06-c2/README.md) |
| Windows 11 平台 | 基线 `6ef5b2e` 的 M06-C2-V、实机和部署门禁均为 **PASS**。四项独立撤销及到期反例、四项事务探针、全量回归与平台专项均通过。[Windows 11 验收证据](evidence/m06-c2/windows11-closeout.md) | Windows Server 2022 CI 单独记录。正式研究 G-1 BLOCKED，C3 NOT_STARTED |

## C1 历史 Windows 11 部署工程验收

2026-11-25 在公司 Windows 11 Enterprise 25H2 x64 实机验收 C1 代码基线 `29dd1ffec595dccb3fad08b1194f5151b12decda`。实机和 Windows 11 部署门禁均为 **PASS**。证据覆盖原版启动器、三次空库冷启动、DPAPI 凭证生命周期、完整回归及 SQLite v7 迁移恢复。真实研究 API 调用 0 次。G-1 仍为 **BLOCKED**，正式语料、许可、审计及研究验收仍按矩阵既有条款核定。[Windows 11 实机证据](evidence/m06-c1/windows11-closeout.md)


## 技术路线与数据设计

1. P0-0 在现有六层目录内落地本地 FastAPI、SQLite 迁移、固定地址的后端适配器和浏览器检查台。所有外发先校验数据来源类别。浏览器只能触发预定义探针，刷新和查看历史不触发外部请求。
2. P0 在 G-1 通过后完成多源采集、不可覆盖的快照、双轨发现、Jev 编码与人工确认、基础仪表盘和问卷草稿。P1 在核心验收后增加四周趋势、滚动校准与真实回流。P2 在 P1 运营验收后增加 Radar、受限来源、调度和历史对照。
3. 连通性数据库按 runs → results → evidence 记录执行；shards 按请求键持久化供应商响应和去重用量；正式研究数据库与诊断/合成语料隔离。请求不存认证头，响应按许可/脱敏保存。连接重新打开验证持久化。状态由真实结果计算，空历史为 NOT_TESTED。
4. 三层关系为 StudyScope → 范围品类；Mention → 原话证据 → 产品品类；编码结果 → Intent → 主/次 Task Category。冻结批次所用范围、注册表、索引版本。P0 发表事务与主大类分母对账另行验收。
5. 前端采用同源 HTML/CSS/JavaScript，无框架脚手架迁移。连接页以六项核查和证据抽屉为中心。使用墨蓝 #182E40、蓝绿 #087D78、浅雾 #F3F6F7、白 #FFFFFF、琥珀 #965713。中文系统无衬线搭配 Barlow / 系统后备，数据等宽数字。桌面常驻侧栏，窄屏改折叠导航。用带标签的检查分布条替代装饰性 KPI 卡，状态同时有文字和图形。
6. P0-0 测试顺序为建空库、运行独立探针、直接取得许可来源、验证固定模型分片和字段、独立回读账本，再汇总同批状态。无授权记录实际缺项与空 HTTP 状态。故障注入及 C0-6 合成夹具明确标识，绝不充当远端成功。单元/接口测试使用独立临时库。浏览器测试走真实本机服务并保存截图。

## 可机读的需求映射

下表由 Web 验收中心直接读取。阶段中列出的后续模块为计划实现路径；每项实时的 evidence、status、blocker、last_checked_at 由本地 SQLite 运行记录提供。没有执行时间时返回 null。不跨批次拼出通过。P1 的历史数据与真实答卷在条件未具备时显示 PENDING。

| requirement_id | stage | description | implementation | test_case |
|---|---|---|---|---|
| C0-1 | P0-0 | 固定模型与 8+3 分片。真实返回模型与锁定版本一致；字段对齐、合并完整；不支持固定版本则 BLOCKED，禁止自动用别名回退。 | src/execution/jev.py | test_live_model_and_shards |
| C0-2 | P0-0 | Choice、Score 与 Noul 返回契约。完整分布符合契约才通过；第三方无 probs 标 schema_gap，改走符合要求的另一供应商。 | src/execution/jev.py | test_live_answer_contract |
| C0-3 | P0-0 | 搜索命中与许可原话。原话/原址/采集方式/许可状态齐全；仅搜索摘要则不通过。 | src/ingestion/public_source.py | test_live_discovery_and_quote |
| C0-4 | P0-0 | SQLite 回读与分片用量。数据可恢复、额外重试不重复计费、密钥不进入日志/浏览器/仓库。 | src/raw_store/store.py | test_live_ledger_readback |
| C0-5 | P0-0 | CX 隔离与故障演练。携带 cx_internal 或 internal_confidential 标志的记录 100% 在客户端调用前被拦截。 | src/execution/transport.py | test_isolation_drill |
| C0-6 | P0-0 | 三层关系与全局向量召回。所有 ID/关联有效；意图不会因产品品类不同被硬过滤；版本与候选可追踪。 | src/discovery/recall.py | test_cross_category_recall |
| G-1 | P0-0 | 同一批六项检查均通过，所选供应商真实语料处理审核可追溯 | src/execution/checks.py | test_gate_requires_all_six |
| J-1 | P0 | 三类判断全部上线。Choice / Score / Noul 三种判断均在试点语料上实际运行，缺一类不算完成 | src/execution/ | 业务验收 J-1 |
| J-2 | P0 | 金标准校准完成。100–200 条金标准标注完成，一致率有书面记录，阈值已设定并与注册表版本绑定 | src/execution/ | 业务验收 J-2 |
| J-3 | P0 | 中文单独校准。中文语料有独立金标准子集与独立阈值（试点语料无中文时，在首批中文语料入库前补齐并记录） | src/execution/ | 业务验收 J-3 |
| J-4 | P0 | 完整分布落库。抽查编码结果：Choice 每项概率、Score 每档概率、Noul 概率均完整、范围有效；缺失为 schema_gap，不得以仅 score/confidence 通过。 | src/execution/ | 业务验收 J-4 |
| J-5 | P0 | 复核队列运转。低置信条目 100% 进队列，无低置信条目直接进入仪表盘统计 | src/execution/ | 业务验收 J-5 |
| J-6 | P0 | 引用可点回。抽查 20 条编码，每条可点回原文片段与来源链接；点不回的已按规则丢弃 | src/execution/ | 业务验收 J-6 |
| J-7 | P0 | 额度条可用。真实成功请求后以 X-Tokens-Remaining 更新余额；没有数据则显示“未同步”；单次 usage.input_tokens 正确落库。 | src/execution/ | 业务验收 J-7 |
| J-8 | P0 | 补充额度与预算保护。跳转供应商购买页；402 停止新任务，支持批量预计成本、告警、Key/限流/上游错误分流与幂等重试。 | src/execution/ | 业务验收 J-8 |
| J-9 | P0 | 版本锁定执行。全部 P0 编码实际使用固定 model_id=jev-1.14.0，服务商接受且返回确认的实际 model 一致；无别名静默回退。切版本必须重新标注/复核金标准并校准。 | src/execution/ | 业务验收 J-9 |
| J-10 | P0 | None + Noul 守门生效。抽查全部 Choice 配置均含 None 选项；守门 Noul 已上线，答否条目 100% 进发现队列、无一按 Choice 第一名直接入库 | src/execution/ | 业务验收 J-10 |
| J-11 | P0 | 分片与幂等成功。真实构造 11 道判断自动拆为 8+3；所有问题无丢失/重复，Token 合计正确；第二分片失败时整条不得进入正式统计；同键重试不重复入账。 | src/execution/ | 业务验收 J-11 |
| J-12 | P0 | Score 契约核验。保留第三方和官方各一份（如能取得）脱敏真实响应样本；只有返回每档 probabilities 且符合范围/归一化校验的服务商才可通过 J-4；缺失显示 BLOCKED/schema_gap。 | src/execution/ | 业务验收 J-12 |
| J-13 | P0 | P0-0 连通性与隐私门。固定 jev-1.14.0 真实请求且响应模型核验通过；从合规原文到 SQLite、Jev 编码和 Token Center 的链路通过；测试资料不得包含内部 CX。 | src/execution/ | 业务验收 J-13 |
| J-14 | P0 | 全局意图召回正确。在 ≥30 个已确认意图且至少 2 个产品品类的盲测集上验证 Top-K+None 不超过 20；报告 Recall@K、未知拒绝率与跨品类漏召；目标 Recall@K≥95%（试点指标，未达到不得放量）；索引/注册表版本可追溯。 | src/execution/ | 业务验收 J-14 |
| CAT-1 | P0 | 注册表完整。抽查全部已确认意图：category_ids 非空，primary_category_id 有且唯一且在列表内，通过率 100% | src/discovery/、src/raw_store/ | 业务验收 CAT-1 |
| CAT-2 | P0 | 双向一致。任选 10 个意图与 5 个大类双向跳转：意图页列出的大类，其大类页必含该意图，反之亦然，无单边挂靠 | src/discovery/、src/raw_store/ | 业务验收 CAT-2 |
| CAT-3 | P0 | 计数不重复。限定同一 study/batch/source/window、仅对 published 且已归类的唯一 mention_id 对账：主任务大类合计 = N_published_classified；None/待审/重复不混入分母。 | src/discovery/、src/raw_store/ | 业务验收 CAT-3 |
| CAT-4 | P0 | 大类发现演练。盲测集中预置一个不属于现有大类的意图簇，能提出候选大类并走完确认 / 驳回留痕；真实研究允许「本轮未发现新大类」 | src/discovery/、src/raw_store/ | 业务验收 CAT-4 |
| CAT-5 | P0 | 禁止硬塞。无主任务大类的意图只能处于 candidate/pending_parent；候选与驳回均留痕；联合确认失败能事务回滚，无静默硬塞。 | src/discovery/、src/raw_store/ | 业务验收 CAT-5 |
| CAT-6 | P0 | 跨品类可迁移。第二个真实或合成产品品类的测试集，新增或复用 Product Category、StudyScope、关联证据，完成意图与任务大类各≥2 条，不改 schema 和代码。 | src/discovery/、src/raw_store/ | 业务验收 CAT-6 |
| CAT-7 | P0 | 产品品类注册表。Product Category 拥有唯一 product_category_id、名称、可选 parent_id、状态和版本；已发布研究的 scope 引用不得指向已停用节点。 | src/discovery/、src/raw_store/ | 业务验收 CAT-7 |
| CAT-8 | P0 | 三层双向查询。产品品类→有合格原话的意图，以及意图→相关产品品类与任务大类两条链可反查；10 条证据逐条核对，不从 Task Category 推断产品归属。 | src/discovery/、src/raw_store/ | 业务验收 CAT-8 |
| CAT-9 | P0 | 候选事务一致性。构造“候选意图+候选任务大类”联合确认案例；主大类缺失时阻止发布；事务失败回滚，成功后关系完整且版本号变化。 | src/discovery/、src/raw_store/ | 业务验收 CAT-9 |
| CAT-10 | P0 | 分母状态对账。混入 None/低置信/分片失败/无父类/重复等样本；确保 N_published_classified 与各主任务大类之和精确相等，状态互斥、过滤前后分母重算。 | src/discovery/、src/raw_store/ | 业务验收 CAT-10 |
| TC-01 | P0 | 全局顶部常驻 Jev 额度条：供应商、模型、余额、最近同步时间、状态点与进度条。运行或刷新页面始终可见；未知余额展示“— / 未同步”，不显示 0。 | src/execution/、src/dashboard/ | 业务验收 TC-01 |
| TC-02 | P0 | 余额同步：优先解析成功响应头 X-Tokens-Remaining；记录 usage.input_tokens；首次无成功调用时支持用户手动输入控制台可信余额基线并标“手动”。成功请求后自动更新；Playground/其他应用共用余额时提示“本地用量≠账户总消耗”。 | src/execution/、src/dashboard/ | 业务验收 TC-02 |
| TC-03 | P0 | 点击「刷新状态」：已有最近响应时刷新本地显示；若供应商公开独立余额接口可用才真实调用。否则打开账户控制台人工核对，不做隐性扣费探测。不存在可验证 balance API 时不得伪造“实时刷新”请求；可手动同步账面余额。 | src/execution/、src/dashboard/ | 业务验收 TC-03 |
| TC-04 | P0 | 点击「补充额度」：打开 https://jevmodel.org/zh/pricing/ 或该供应商的账户购买页；购买在第三方网页完成。工作台不收款、不保存银行卡、不声称已充值；用户返回后主动同步/核对余额。 | src/execution/、src/dashboard/ | 业务验收 TC-04 |
| TC-05 | P0 | 额度闸门：批量任务开始前估算所需 tokens，展示预计单条成本、批次总额、可用预算及安全余量。不足时阻止新批次并允许缩小批量；已完成记录不受影响。 | src/execution/、src/dashboard/ | 业务验收 TC-05 |
| TC-06 | P0 | 余额预警：<20% 提示；<5% 高危；402 标“余额不足”；401 标“Key 异常”；429 按限流；502 上游错误重试。所有状态有明确文案与操作入口；余额提示阈值可配置。 | src/execution/、src/dashboard/ | 业务验收 TC-06 |
| TC-07 | P0 | 本地用量明细：每批、每模型、每注册表版本、每次重试的输入 tokens、状态、时间与来源。重复提交使用 Idempotency-Key；展示成功/失败/重试计数，不重复记账。 | src/execution/、src/dashboard/ | 业务验收 TC-07 |
| TC-08 | P0 | 安全：Key 只保存在服务端环境变量/密钥存储；支持多提供商适配器，预算隔离。不在 HTML、日志、导出 CSV、GitHub 中暴露 Key。 | src/execution/、src/dashboard/ | 业务验收 TC-08 |
| G0 | P0 | 运行与源码。Windows 本地部署；启动脚本、README、.env.example、测试用例；从空库启动。3 次连续冷启动成功；无假按钮、无模拟结果冒充真实调用；失败有可读日志。 | PDT 附录 C / 六层模块 | 真实验收 G0 |
| G1 | P0 | 数据获取。3 个来源批次、至少 100 条真实语义片段；模拟源故障。合格原话可回源；跨网站去重；CSV 兜底；禁止用网页摘要替代正文。 | PDT 附录 C / 六层模块 | 真实验收 G1 |
| G2 | P0 | 抽样可审计。抽查 30 条含来源 URL、原话、时间窗、采集方式、抽取规则。30/30 记录可追溯；比例按来源分开；来源不足则降级结论。 | PDT 附录 C / 六层模块 | 真实验收 G2 |
| G3 | P0 | 发现有效。已知/未知意图盲测集+真实小样本审核。能发现/驳回新候选；人工审定；真实批次可报告“无新意图”。 | PDT 附录 C / 六层模块 | 真实验收 G3 |
| G4 | P0 | Jev 编码。先执行 P0-0 固定模型及 Score 字段核查，再跑 100–200 条金标准，含 11 道问题自动拆批测试；中文样本另测。Choice/Score/Noul 必须完整保存分布；每分片入账且合并成功，未返回 Score 每档概率则 J-4/G4 不通过；分类 F1/分档一致性/问题 F1 完整报告。 ≥30 意图时全局候选 Recall@K 验证并满足 J-14。 | PDT 附录 C / 六层模块 | 真实验收 G4 |
| G5 | P0 | Token Center。真实 API 调用→解析头；402/401/429/502 模拟错误；不同客户端占用余额。真实余额或明确未同步；购买跳转有效；其他客户端消耗后的估算不冒充最新余额。 | PDT 附录 C / 六层模块 | 真实验收 G5 |
| G6 | P1 | 问卷闭环。生成一份问卷→人工改题→Forms 发布→测试回收。每题回链证据；人工审批；回收数据写入验证状态；无样本不宣称普遍率。 | PDT 附录 C / 六层模块 | 真实验收 G6 |
| G7 | P0 | 故障与安全。断网、搜索源超额、Jev Key 错误、余额耗尽、安全扫描。既有数据可读；暂停新编码；Key 不外泄；内部数据无未经允许外发。 | PDT 附录 C / 六层模块 | 真实验收 G7 |
| BIZ-SCOPE | P0 | 冻结研究范围、公开站点及第二品类，文本判断只用 Choice、Score、Noul | docs/decisions/、src/raw_store/studies.py、src/dashboard/study_api.py | D1–D5 记录；M03 工程回归 test_studies.py |
| INGEST | P0 | Tavily/Brave 双源、YouTube、论坛、备用 Reddit 和 CSV；记录许可与漏斗 | src/ingestion/、src/dashboard/import_api.py | 一源故障后切换、CSV 离线复跑；M04 工程回归 test_imports.py |
| RAW | P0 | 不可变原文、去重、时间窗、来源角色、批次；≥100 条、三批次 | src/raw_store/ | 快照回放与真实来源抽查 |
| DISCOVERY | P0 | BERTopic 与 TopicGPT 四步、单轨留痕、残差、新意图人工开放编码与回滚 | src/discovery/ | 隐藏未知的盲测、重算差异 |
| BASIC-DASH | P0 | 正式互斥桶、采样漏斗、基础情感与问题、主次归属下钻、原话与复核 | src/dashboard/ | 同口径筛选后对账、每个指标回链 |
| SURVEY | P0 | 五类映射、ODI 排序、每题一个证据发现、1–2 开放题、匿名、人工审题与 2–3 人试填 | src/outputs/ | 草稿编辑导出、Forms 授权、试填记录 |
| PRIVACY | P0 | 非公开/内部只在本地；公开许可、脱敏、各供应商留存审核；原始答卷隔离 | src/ingestion/、src/execution/ | 传播标签与出口审计 |
| P1-ANALYSIS | P1 | 满意/挫败/信任、问题严重度、研究建议四要素、7 维筛选下钻；n<10 隐去均值/比例 | src/dashboard/ | 来源/时间/批次/双类别/意图/置信度 |
| P1-TREND | P1 | 同来源、查询、采样规则、真实发布日期按周积满四周；异常触发重跑 | src/dashboard/ | 四周正式快照与事件 |
| P1-SOURCES | P1 | 第二论坛、YouTube 和研究期刊背景分别标级展示 | src/ingestion/ | 文献与原话并列且分母独立 |
| P1-GOLD | P1 | 逐批抽查 20 条、高低置信均覆盖，滚动校准、记录队列等待及积压 | src/execution/ | 随注册表升版重新校准 |
| P1-REFLOW | P1 | 真实问卷回收关联证据与预设阈值、更新注册表验证状态 | src/outputs/ | 实际招募/答卷/回写 |
| P2-RADAR | P2 | 竞品/自有独立语料和统计，报告痛点/机会/风险/行动 | src/dashboard/、src/outputs/ | 同口径双样本客观对照 |
| P2-AMAZON | P2 | 自有导出、公开人工采样、聚合数、Shulex 授权批次；已购体验保留型号及 verified | src/ingestion/ | 四类通道批次、许可、聚合与原话分流 |
| P2-GITHUB | P2 | Issues/讨论作技术信号，季度三角验证独立于主统计 | src/ingestion/ | GitHub、问卷和评价三方来源 |
| P2-SCHEDULE | P2 | 授权源定期巡检、暂停、恢复、运行日志 | src/ingestion/ | 重试不重采、巡检连续 |
| P2-HISTORY | P2 | 跨产品品类与历史报告：版本、时间窗、来源、口径、引用 | src/outputs/ | 多品类去重、版本回放与四段报告 |
| D1 | P0 | 冻结首批主题、第二品类与来源范围 | docs/decisions/D1-first-sites.md | 研究负责人签署范围版本 |
| D2 | P0 | 落实 100–200 条金标准与首批 50 条对齐的人选 | docs/decisions/D2-gold-standard-owner.md | 标注负责人及记录 |
| D3 | P0 | 复核外发边界、许可、留存和处理地区 | docs/decisions/D3-external-boundary.md | 对照实际供应商与凭据 |
| D4 | P0 | 决定问卷试填与正式出题时机 | docs/decisions/D4-survey-first-or-after.md | 审批链接与真实试填 |
| D5 | P0 | 确认默认服务商、预算上限、补额审批与余额来源 | docs/decisions/D5-token-budget.md | 账户额度及负责人审批 |
| SOURCE-POLICY | P0 | 来源许可、访问限制、上下文、保留期限和删除审计 | src/ingestion/、src/raw_store/ | 逐源许可与清理记录 |
| RAW-ROLES | P0 | 用户原话、背景证据、内部材料与合成样本分库或分域 | src/raw_store/ | 检查样本资格、数据角色与正式统计隔离 |
| BATCH-RECOVERY | P0 | 持久化暂停、幂等恢复、离线读取已有证据 | src/raw_store/、src/execution/ | 故障注入与重启回读 |
| UI-EVIDENCE | P0 | 所有研究指标可下钻来源、实际时间、分母与原话 | src/dashboard/ | 逐页核对同一过滤范围 |
| UI-STATES | P0 | 响应式桌面及移动布局，加载、空、错误、配额及上游故障状态均可辨认 | src/dashboard/ | 桌面移动端操作并留存截图 |
| RESEARCH-REPORT | P0 | 结论记录来源差异、偏差、置信度与样本局限，报告可复现 | src/outputs/ | 抽样回放与建议引用 |


## M03 独立预开发工程映射

PDT §6.9 的 StudyScope 框定研究边界。项目、当前及历史范围、冻结与复合引用已落地，[工程测试](evidence/m03/README.md)涵盖产品和非产品课题。BIZ-SCOPE 的许可来源、第二品类和正式范围确认继续按 D1–D5 执行。CAT-6 正式跨品类全流程和 CAT-7 注册表验证仍在各自模块验收。G-1 保持 BLOCKED。


## M04 独立预开发工程映射

CSV / XLSX 暂存绑定冻结项目范围，记录原文、文件行、工作表、字段映射、许可与隐私状态。[工程证据](evidence/m04/README.md)包含数据隔离、审计、幂等和回滚。INGEST 的线上来源、G1 的三批真实数据与≥100 条语义片段、RAW 的正式原文治理与去重继续按原条款验收。导入暂存、错误报告和合成测试均不进入正式研究分母。G-1 保持 BLOCKED。

## M05 本机原始语料库工程证据

本机导入候选可核验原文、记录来源许可和保留条件、按角色隔离，并在项目内跨批次精确去重。快照绑定原文摘要与冻结范围。排除、到期及已审核批次撤销后，原话在工作台受限。G1、G2、RAW、RAW-ROLES 和 SOURCE-POLICY 的正式判定仍须分别提交对应业务证据，其中 SOURCE-POLICY 包括逐源许可及实际清理和删除审计。[本机工程记录](evidence/m05/README.md)

| 要求 | M05-R2 工程覆盖 | 剩余正式证据 |
|---|---|---|
| RAW、INGEST | 重试只复用既有回执，已审核批次撤销后仍保留审计和固定计数。跨批次和跨项目、并发、事务回滚及旧库有回归。 | 线上采集和故障应对按原矩阵执行。 |
| SOURCE-POLICY、PRIVACY | 遮蔽覆盖原话、来源字段、自由文本审核和受限批次的来源类型汇总。到期、排除和撤销继续受限。明确撤销的来源按同项目 URL 限制跨文件历史、预览和确认。SQLite v5 追加结构化许可与不可变撤销记录。含否定、未知或冲突的描述不能放行。有效新授权须凭独立材料和明确人工复核。 | 逐源许可和撤销记录、来源受限全文的清理、SQLite 和备份的物理清理、删除审计及供应商留存审核。 |
| RAW-ROLES、G1、G2 | 区分用户原话、背景证据、内部材料与合成夹具。正式研究资格与外发资格关闭。 | 三个真实来源批次、至少 100 条合格真实语义片段、30/30 含原话及采集规则的溯源抽查。 |
| CAT-6、CAT-7、§6.6、§9.3 | 已记录原始行、冻结范围、来源证据和后续稳定标识的交接约束。下游读取经过统一的当前资格服务，导入暂存仅供状态和定位。 | 按后续模块验收证据支持的三层关系、统计与正式发布。 |

M05-R2 工程状态为 **ENGINEERING_PASS**。许可、撤销及旧库副本复核通过最终实现的 Ubuntu、Windows Server 2022 与 Chromium 检查。正式验收依上表证据核定，G-1 保持 **BLOCKED**，C0-1、C0-2、C0-4 和供应商审查沿用原标准。[最终实现 `62a7c1c`](https://github.com/kurikiwoods-coder/voc-research-workbench/commit/62a7c1c132b72a8e07679f1713e6834aa7893c91) · [实现 CI](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/runs/45367761470) · [修复前后证据](evidence/m05/permissions-review.md) · [M05 → M06 数据契约](../HANDOVER.md#m05--m06-数据契约)

## Pre-M06 独立工程审计

M01–M05 的接口隔离、生命周期回滚、CSV/XLSX、许可与撤销迁移、冻结范围及当前资格契约均有合成回归。原审计结论为 **PRE_M06_GATE_BLOCKED**，当时 Windows 11 实机为 NOT_TESTED。现行开发与部署放行见负责人门禁调整记录。工程 CI 与 G-1 的正式连通性、G0 和 G1/G2 的业务验收分别记录。G-1 保持 BLOCKED，正式条款照原标准执行。[审计范围](audits/pre-m06-audit.md) · [Bug 台账](audits/bug-register.md) · [试验记录](evidence/pre-m06/README.md) · [门禁调整](decisions/pre-m06-development-gate.md)
