# VOC 研究工作台 PDT v1.2.1 — 摘要

> 完整版以 `PDT-v1.2.1.docx`（Ryan 原稿）为准。本文件是忠实摘要，只做导航，不代替原文。
> 版本：v1.2.1｜技术连通性、Jev API 契约与复现性修订版（待评审），2026-11-23。
> 在 v1.2 基础上修订，不改产品定位、六层架构、全网搜索方向或 Jev 强制执行原则。

## 目的

用站外真实用户原话发现清单外的新意图，用 Jev（强制，`jev-1.14.0`）规模化编码，
再把发现变成能投放的验证问卷，闭环回流。Amazon 只作初步来源，主线是论坛、
讨论声量与期刊。

## 六层

| 层 | 职责 |
|---|---|
| L1 采集层 | Tavily + Brave 双搜索发现 URL，YouTube / 论坛适配器，Reddit 备用，CSV 保底 |
| L2 原始层 | 原文原样落盘，永不覆盖，可重跑 |
| L3 发现层 P0-1 | BERTopic + TopicGPT 双轨提候选，开放编码，人工确认入注册表 |
| L4 执行层 P0-2（Jev，强制） | Choice / Score / Noul 规模化编码，金标准校准，Token Center |
| L5 仪表盘层 | 情感 / 问题 / 趋势 / 推荐四模块，待审队列 |
| L6 输出层 | 问卷生成器（导出 Google Forms）、洞察报告、回收回灌 |

## v1.2 → v1.2.1 改动

### 1. 新增 P0-0 连通性 Gate（§12.0，G-1）

P0 之前先做真实接口验证，不通过不得进入 P0，不得用模拟数据绕过：

| 测试 | 内容 | 不通过 |
|---|---|---|
| C0-1 Jev 版本与限额 | model=`jev-1.14.0` 真实请求 1 条公开短评论，核对返回 model；11 项判断真实执行 8+3 自动分片 | 不支持固定版本即 BLOCKED，禁别名静默回退 |
| C0-2 Score 概率字段 | 分别调用 Choice / Score / Noul，保存脱敏原始 JSON，核对 Score 每档 probabilities | 第三方无 probabilities 标 schema_gap，改走符合要求的另一供应商 |
| C0-3 搜索原话 | 至少一个搜索 API 找 URL，再经允许的页面 / 官方接口取得 ≥1 条真实用户原话 | 仅搜索摘要不通过 |
| C0-4 本地持久化 + 额度 | 真实 API 结果与分片 token 写入 SQLite；显示响应头余额或明确“未同步”；重启复查 | 数据不可恢复、重试重复计费、密钥进日志 / 浏览器 / 仓库 |
| C0-5 CX 隔离演练 | 合成 CX 标志样本验证外部发送闸门，断网 / 401 / 402 / 422 / 429 / 502 故障模拟 | 带 cx_internal 或 internal_confidential 标志的记录未在客户端调用前 100% 拦截 |

### 2. Jev API 分批与兼容性硬规则（§6.2、§6.5）

- jevmodel.org 每次 `/v1/systemone` 最多 8 个问题，Choice 最多 20 个选项、Score 2–10 档。
  一个语义片段若有 11 项判断，按确定性顺序拆成 8+3 两个请求；问题名全局唯一，
  固定 record_id、mention_id、registry_version、question_set_version、model_id、
  split_index 与 request_id。Choice + “是否属于现有意图” Noul 守门优先同批。
- 每批分别记录 usage.input_tokens、响应状态与 Idempotency-Key；全部成功且字段校验
  通过才合并，否则整条标记 partial / queued，禁止将部分结果纳入正式统计。
  重试同一分片用同一幂等键，不允许不同输入复用同一键。
- 1.14 的图片、Box、长上下文属实验性；文本 P0 禁用 Box / 图像。

### 3. Score 供应商契约检查（§6.2、J-12）

- TypeSafe 官方接口文档声明 Score 可含 probabilities；jevmodel.org 公开示例仅展示
  score 和 confidence。P0-0 必须用真实 Score 请求保存脱敏 JSON 样例。
- 第三方不返回 probabilities：先联系服务商确认是否可启用 / 透传；否则该适配器
  不得通过 J-4 和 G4，需切换真正支持完整字段的接口，不允许修改统计方法掩盖缺失。
- 缺失时原样保存 score / confidence、写 schema_gap=true、转为待验收，
  不允许从分数推算概率或冒充完成 J-4。

### 4. 隐私与留存（§6.9、§8.2、§13.2、D3）

- CX 绝对隔离：内部客诉（CX）、非公开公司数据、未获外部处理授权的上传内容，
  一律仅本地 / 人工处理，禁止调用 TypeSafe、jevmodel.org、外部 LLM 或任何第三方模型 API；
  不接受“已匿名化”作为自动解除禁令的条件；第 14 章审批也不解除。
- TypeSafe 官方 Help Center（2026-11-03 更新）：Jev 不用客户输入 / 输出训练；
  Zero Data Retention（ZDR）对每个组织免费，但需要在官方控制台主动开启，
  不等于默认开启，也不等于全部遥测被删除。标准模式不公开固定保留期。
  实施前须记录组织的 ZDR 实际开关、数据处理地区与适用条款。
- jevmodel.org 是独立第三方，其留存、转发链路、二级处理与 ZDR 不得套用 TypeSafe 的承诺，
  未核验不得发送任何内部 CX / 非公开公司数据。
  依据：https://help.typesafe.ai/articles/5974925716

### 5. 发现层复现性定义修订（§7.4）

- 不再要求两次运行逐字完全一致。必须留痕：同一批经许可保存的原文快照、来源集、
  清洗 / 切分规则、向量模型、BERTopic 参数与随机种子、LLM 模型版本 / 提示词版本、
  Jev model_id、阈值和注册表版本。
- 系统要能从快照恢复“已保存的候选池及其审核决策”（确定性回放）；
  重新调用外部 LLM / 聚类属于“重新计算”，结果允许合理波动，须比较簇匹配率、
  候选意图覆盖变化和差异清单。波动超过团队预定容差需人工复核，不能覆盖旧批次。

### 6. 验收新增 J-11 / J-12 / J-13（§6.6）

| 编号 | 验收项 | 通过标准 |
|---|---|---|
| J-11 | 分片与幂等成功 | 真实构造 11 道判断自动拆为 8+3；所有问题无丢失 / 重复，Token 合计正确；第二分片失败时整条不得进入正式统计；同键重试不重复入账 |
| J-12 | Score 契约核验 | 保留第三方和官方各一份（如能取得）脱敏真实响应样本；只有返回每档 probabilities 且符合范围 / 归一化校验的服务商才可通过 J-4；缺失显示 BLOCKED / schema_gap |
| J-13 | P0-0 连通性与隐私门 | 固定 jev-1.14.0 真实请求且响应模型核验通过；从合规原文到 SQLite、Jev 编码和 Token Center 的链路通过；测试资料不得包含内部 CX |

J-1 至 J-10 保留（版本锁定 jev-1.14.0、Box 排除、每个 Choice 必配 None + Noul 守门
“是否属于现有意图清单”、中文单独校准、CX 绝不进 Jev、完整分布落库等）。
G0–G7 保留，新增 G-1 P0-0 连通性。

### 7. 成本口径修正（§6.7、§6.9）

- 额度按每个成功分片的 usage.input_tokens 单独入账，再依 record_id 合计完整编码单位；
  相同幂等请求去重；“可处理数量”按最近 20 个完整编码单位的分片 Token 合计均值计算，
  不得把“每个分片的均值”误算为每条评论的成本。
- TypeSafe 官方公开价每百万输入 Token $0.042、输出免费；正式成本必须按实际分片汇总
  的 usage.input_tokens × 单价计算，不能用“每条评论约 300 tokens”假设整套判断的总成本。
  第三方免费赠额与官方美元计费不可混算。

## 待拍板 D1–D5（未变，见原稿 §14）

D1 首批研究域 / 搜索引擎；D2 Jev 金标准标注责任；D3 外部 API 与内部数据边界
（v1.2.1 已把 CX 禁令写成硬规则，D3 只决定公开内容经哪些第三方通道发出）；
D4 问卷先行还是链通后行；D5 Jev 默认服务商、余额同步口径、充值审批与预算上限
（v1.2.1：P0-0 用真实响应核验 jev-1.14.0 和 Score 概率；若第三方不符合契约，
改用官方 Jev 适配器并重校准）。

## 已知待修（评审意见，2026-11-23）

- 封面“评审时先定这四件事”与“评审先定五件事：D1–D5”并存，待统一为五件。
- §6.2 Choice 示例仍写“其他（进发现队列）”，按硬规则应写成 None 选项。
- 附录 F 的 src 目录命名（collect / store / discover / execute / dashboard / output）
  与仓库现有目录（ingestion / raw_store / discovery / execution / dashboard / outputs）
  不一致，待对齐一处。

## 核验来源

- jevmodel.org API 文档：https://jevmodel.org/zh/docs/（每次最多 8 题；Choice 2–20、Score 2–10；
  Score 示例仅 score / confidence；2026-11-18 更新）
- jevmodel.org Jev 1.14 页：https://jevmodel.org/jev-1-14/（jev-latest 仍指向 jev-1.13.0；
  1.14 经 jev-preview 或固定 jev-1.14.0 可达；图片 / Box / 长上下文为实验性）
- TypeSafe 官方文档：https://docs.typesafe.ai/introduction（Score 返回 score、probabilities、confidence）
- TypeSafe 数据使用与 ZDR：https://help.typesafe.ai/articles/5974925716
