# Jev + Reddit 核查包（给正在写的 PDT 用）

日期：2026-11-23（周一）15:15 Asia/Taipei 核查。PDT 正在主聊里写，Jev 已定为强制项。
本文件只核查 PDT 会写死的外部事实，不改专案结论，不重复 §11 的四件待拍板。

## 已核实：Jev 本体（与专案/对话一致）

- TypeSafe Jev，2026-09-15 发布，System One 决策模型；训练方式 RLCD（Reinforcement Learning for Calibrated Decisions）。
- 三种问题类型：Choice（固定选项选一，返回各选项概率 + confidence）、Score（有序量表，返回概率加权分，可为小数）、Noul（是否成立，返回 0–1 概率，**没有 confidence 字段**，阈值直接打在概率上）。
- 调用：`POST https://api.typesafe.ai/v1/systemone`，body 为 `state` + keyed `questions` 对象（不是 list，list 会报 422）；API key 经 `TYPESAFE_API_KEY`。
- 价格：输入 $0.042 / 百万 tokens，输出免费（不生成文本）。上下文：整请求 64k tokens、单个问题 32k；加 `TypeSafe-Danger-Zone-Long-Context: true` 可提到 262k，但官方说明更慢、更不准。
- 来源：Cloudflare Workers AI 文档（Jev 1.13，`https://developers.cloudflare.com/ai/models/typesafe/jev/`）、DZone 综述（`https://dzone.com/articles/typesafe-jev-typed-ai-model`）、Zenn 实测（`https://zenn.dev/mk404/articles/2026-11-17-jev-choice-score-noul-box-notes?locale=en`）。

## PDT 应写死的 5 处修正 / 补充

### 1. 锁定模型版本：`jev-1.14.0`（2026-10-14），不用 `jev-latest`
- Jev 1.14 于 2026-10-14 发布；别名 `jev-latest` 会随版本变而改变行为，已调好的阈值可能失效。PDT 应写：P0 锁定 `jev-1.14.0`，换版本要重跑金标准。
- 注意口径差：Cloudflare 文档页仍写 Jev 1.13，Zenn 实测称固定为 `jev-1.14.0`；上线前以 TypeSafe 控制台为准复核一次。

### 2. Jev 1.14 新增第 4 种类型 Box（图片框选），P0 明确不用
- Box 用于在图片里定位物体并返回边框分数。VOC 文本分析用不到，PDT 应写明 Box 不在 P0 范围内，避免执行层误把它当图片理解能力。

### 3. 每个 Choice 必须配 “以上都不是 / None” 选项 + 一道 Noul 守门
- Jev 的 Choice 一定会选一个，即使正确答案不在选项里；独立评测（EurekaLeo 调查，2026-10-07 截止，101 项核心研究）发现：即使给了明确的 None 选项，Jev 也只在 7% 的缺失正确答案菜单上拒绝作答。
- 这正是 Ryan 已有的纪律（投票表 Q5/Q6/Q7 的 None/Neither 兜底），PDT 应把它写成执行层硬规则：每个 Choice 加 None 选项；另加 Noul 问“是否属于现有意图清单”，答否则进发现队列。否则新意图会被硬塞进旧框，P0-1 发现失效。
- 另两条同源限制也应进 PDT：Jev 计数与日期比较不可靠；放在 `state` 里的原文可能左右判断（论坛帖含诱导性文字时），低置信复核不能只看不确定、也要抽查高置信答案。

### 4. 中文必须单独校准——已有论文证据支持，不是谨慎措辞
- 多方来源一致：TypeSafe 称英语最强，CJK 等语言支持但准确度不等；中文内容需单独评估。
- arXiv 论文 Chinese-Jev（`https://arxiv.org/pdf/2609.36965`）称现有 Jev 模型中文决策准确度有限，并为此另训了中文模型。PDT 应写：中文与英文金标准分开建、分开报一致率；不要用英文翻译后跑分代替中文原文跑分。

### 5. 内部客诉（CX）不能进 Jev——Jev 也是第三方 API
- 专案 §10 已定“CX 不直喂任何第三方 API”，PDT 必须点名：Jev 走 TypeSafe 托管 API，同样算第三方。CX 数据只做本地/人工编码，不进 Jev；Jev 只跑公开站外内容与公开来源 CSV。
- 补充（二级来源，待控制台复核）：有 2026-09-23 的核查记录称“零留存（zero retention）仅限企业版计划”。PDT 不要把“Jev 不训练用客户数据”写成“数据不留存”，上线前在 TypeSafe 控制台确认留存条款。

## 成本粗算（PDT 可用，量级正确即可）
- 按 $0.042 / 百万输入 tokens：每条样本约 300 输入 tokens（含问题文本）时，1,000 条跑一整套问题 ≈ $0.013；10,000 条 ≈ $0.13。P0 试点（100–200 条金标准 + 几千条批量）的 Jev 直接成本可忽略，成本不在 PDT 的决策项里；真正成本是人工标注与复核。

## 竞品已出现，但不改“Jev 强制”的决定
- 2026-10 起 OpenAI 上线 Decisions API（`gpt-6-luna`），2026-11-11 Google 上线 Gemini Decision 1；三者同构（typed 问题 + 概率）。对比文章称 Jev 仍是最便宜的（`https://dev.to/ahmad_dogar_7d098f5e48f72/jev-vs-openai-decisions-vs-gemini-decision-1-three-decision-apis-one-adapter-565k`）。
- Ryan 已定 Jev 必须用（2026-11-23 对话），PDT 不重开选型；建议只加一行：锁定 Jev 的理由（已评估、最便宜、先行者）+ 重访触发条件（如 Jev 涨价、中文校准不达标）。

## Reddit 时间线核实：专案说法基本对，有两处要改措辞
- 核实成立：未登录 `.json` 自约 2026-05-30 起返回 403；2026-09-30 官宣、2026-10-31 起不再接受新的公开 API 接入申请；2027-03 公开 Data API 全面关闭。
- 需改措辞 1：专案写“RSS 已于 2026-11-13 停用”。实际情况是 2026-11-13 起**停止支持**，而非当天断流——2026-11-16 实测仍有 feed 返回内容，但限流严重（约每 30 秒 1 次即频繁 429），且官方不再承诺可用。PDT 应写“停止支持、无可用性承诺”，不要写“已关闭”。
- 需改措辞 2：补一个更近的 deadline——**2027-01-12** 起，未在开发者平台注册的应用开始被撤访问权。P0 若依赖 Dialog MCP / Arctic Shift 兜底，1 月 12 日前要确认通道状态，不能只盯 3 月。
- 备选（未深入核查，仅记录）：FetchLayer 称其 Reddit API 每 1,000 请求 $1.99，可作 Dialog MCP 失效时的付费备选；是否采用由 PDT 评审时定，不建议现在写进 P0。
- 来源：`https://medium.com/@scraperfinder/reddit-stopped-supporting-rss-on-13-november-three-days-later-the-feeds-still-answer-26eacceb6aac`、`https://fetchlayer.dev/blog/how-to-scrape-reddit`、`https://aitoolsforapps.com/ai-tools-for-reddit-post-checker-and-community-kit-246/blog/reddit-shuts-down-rss-feeds-november-13-2026-monitor-subreddit-mentions`。

## 未核查（PDT 不要写死）
- 专案 §4 其余 14 个对标项目的星数与日期未逐项复核；AWS VoC Data Lake、Reddit Research MCP 两条 Ryan 自己贴的链接，沿用对话里的已有描述，未在本轮重查。
- Jev 在 Ryan 的具体语料（营养秤中文讨论）上的实际一致率未知——仍需 P0 的 100–200 条金标准实测，这是 PDT 验收项，不是本核查能代替的。
