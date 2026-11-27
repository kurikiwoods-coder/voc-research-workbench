# VOC 研究工作台 PDT v1.3.1 — 摘要

> 完整版以 `PDT-v1.3.1.docx`（Ryan 原稿）为准。本文件是忠实摘要，只做导航，不代替原文。
> 版本：v1.3.1｜全品类数据关系与工程验收定版（待评审），2026-11-23。
> v1.3 的局部工程定版：不改变六层架构、全网合规取证、Jev 强制编码、Token Center
> 和问卷回流。主要修正四项：产品品类/任务大类/意图三层关系；候选意图与候选大类的
> 原子确认；超过 20 个意图时的全局向量召回与 Jev 候选重排；正式统计分母与排除项目。

## 现行产品接续

[PRODUCT-REALIGNMENT-V1](../decisions/product-realignment-v1-owner-approval.md) 确认 Personal 优先交付全功能研究体验，两版共享核心与验收。发现和执行同是 P0 核心。Jev 仍以 `jev-1.14.0` 作为首个正式验证，后续通道及模型按适配契约择用。隔离工程按授权推进，正式研究仍须满足原 C0-1 至 C0-6、J-14、金标准及逐源许可。下文为 2026-11-23 规格摘要，现行开发顺序见 ROADMAP-V2。[适配器契约](../architecture/ai-model-adapter-contract.md) · [现行路线](../planning/ROADMAP-V2.md#当前接续顺序)

## 目的

用站外真实用户原话发现清单外的新意图，用 Jev（强制，`jev-1.14.0`）规模化编码，
再把发现变成能投放的验证问卷，闭环回流。Amazon 只作初步来源，主线是论坛、
讨论声量与期刊。工作台是全品类的，不是营养秤专用的；COSORI 营养秤只是第一个
跑通的试点品类。

## v1.3 → v1.3.1 改动

### 1. 三层语义模型（第 6 章）

研究对象拆为三层，不再把产品品类当成一次研究的临时配置：

| 层 | 对象 | 注册表 |
|---|---|---|
| 产品品类 Product Category | 研究对象的商品/服务分类，可多级层次，可为空（非产品课题） | `schemas/product_category.schema.json` |
| 任务大类 Task Category | 跨品类的用户任务域，沿用原 `category_id` / `category_ids` / `primary_category_id` | `schemas/category.schema.json`（专指 Task Category） |
| 用户意图 Intent | 用户在具体场景下想完成的一件事 | 意图注册表（§8.2） |

- 研究项目 StudyScope 确定语料边界（问题、市场、时间窗、语言、产品品类，可版本化），
  见 `schemas/study_scope.schema.json`。
- 产品品类和意图通过合格原话证据形成可追溯关联（`mention_product_categories`，
  见 `schemas/mention_product_category_link.schema.json`），不将某意图永久绑定到
  单一产品；不从搜索词、任务大类或试点默认推断产品归属。
- 产品品类↔意图是第二套双向入口（与任务大类↔意图并列，§6.9、§10.8）；
  两种关系分别展示，不相互替代。

### 2. 候选态与原子确认（§6.5、§8.1、§8.2）

- 意图生命周期与统计资格分开：`lifecycle_status`（candidate / pending_parent /
  confirmed / rejected / merged / retired）与 `survey_validation_status`（未验证 /
  验证中 / 已验证 / 未通过）是两个字段。
- 无主大类的意图只能停留在 candidate/pending_parent，不进正式统计；
  候选意图与候选大类联审，事务性确认后方可发布，任一步失败整组回滚。
- 候选大类发现流程：残差信号 → 候选起草 → 覆盖 / 区分度验证 → 联合审核/原子确认；
  允许“本轮未发现新大类”，禁止硬塞。

### 3. 超过 20 个意图时的全局召回与 Jev 重排（§7.2.1、J-14）

- 候选生成不受当前产品品类限制：先对全局已确认意图注册表建向量索引
  （记录 embedding_model、index_version、registry_version），召回相似意图 Top-K。
- K 初版建议 10–15，最终最多 19 个已知意图 + 1 个 None，总选项不得超过
  Jev Choice 的 20 项上限；问题数量仍按 ≤8 题分片。
- 产品品类/任务大类只能作可解释的软排序信号，不能提前硬排除跨品类正确意图。
- 未知保护：保留 None + 独立 Noul 守门；向量低相似、Noul 判否、Choice None、
  召回异常或候选集为空时进发现/待审，不得强制分进最接近的既有意图。
- 新验收 J-14：≥30 个已确认意图且至少 2 个产品品类的盲测集上验证
  Top-K+None 不超过 20，报告 Recall@K、未知拒绝率与跨品类漏召；
  目标 Recall@K ≥95%（P0 设计目标，须盲测，非已实现结果），不达标不得放量。

### 4. 正式统计分母与排除项目（§6.6、§9.3）

- 正式统计的基本单位是去重后的 mention_id；只有来源有许可、原话可核验、
  编码分片完整、Jev schema 校验通过、审核状态满足校准规则、
  publication_status=published，且其意图 lifecycle_status=confirmed、
  具有唯一有效 intent_id 和 primary_category_id 的语义片段进入
  “已发布已归类分母” N_published_classified。
- 每条合格去重 mention 恰好进入一个互斥 counting_bucket
  （见 `schemas/counting_bucket.schema.json`）：
  published_classified、none_unknown、review_pending、partial_or_schema_gap、
  pending_parent、other_pending；N_excluded 另算在合格去重分母之外。
- 对账：Σ（各主任务大类 published mention 数）= N_published_classified；
  按产品品类筛选时以 distinct mention_id 重新计算，跨品类小计不得直接相加。
- 分母链：N_discovered_urls → N_accessible_pages → N_extracted_mentions →
  N_eligible_dedup → N_published_classified，所有阶段保留剔除原因。

### 5. 验收与编号

- 新增 CAT-7～CAT-10（产品品类注册表、三层双向查询、候选事务一致性、
  分母状态对账）、J-14（全局意图召回）、C0-6（三层模型/召回冒烟，
  P0-0 新增第六项）。
- §7.3 列表编号改为 1–5。

## v1.3 保留内容（未动）

- P0-0 连通性 Gate；Jev 锁定 `jev-1.14.0`、≤8 题/请求、11 项拆 8+3、
  Choice 2–20、Score 2–10；Score 缺 probabilities 只标 schema_gap 不伪造；
  Token Center；ZDR 须主动开启；CX 绝对隔离无豁免；复现 = 确定性回放 + 容差；
  J-1～J-13、G0–G7 与 G-1；D1–D5（D5 仍待拍板）；CAT-1～CAT-6。

## 已知待修（评审意见，2026-11-23，原样推送，修在下一版）

- 附录 C 的 G-1 还写着“C0-1~C0-5 五项测试”，§13.0 已加到 C0-6，共六项。
- §6.6 分母公式里的桶名与 §9.3 的 counting_bucket 不一致：
  N_low_conf_review / N_partial_schema_gap / N_unassigned_parent，
  对应桶名应为 review_pending / partial_or_schema_gap / pending_parent。
- 封面“评审先定五件事”一句话在同一格子里写了两遍。
- 封面“依据专案”还写 11 节，专案现为 v2.2（12 节加 §5A）。
