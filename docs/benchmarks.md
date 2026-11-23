# 对标借鉴清单

两批共 16 个对标（开源项目、机制论文与商业工作台）的共同结论：市面方案几乎都只做「执行」——分类、情感、汇总；做到「发现新意图」的只有机制级参考，做到「发现转问卷」的只有一个（ProductWeaver）。本工作台的差异化就定在这两处，其余环节全部借现成形状，不重复造轮子。

| 参照 | 借什么 | 不借什么 |
|---|---|---|
| AWS sample-voice-of-customer-datalake（MIT-0，36 stars，2026-01） | 三段管线（存原始 → 富化 → 聚合）、插件化来源、自家与竞品 Radar 分开算、CSV 导入留痕、改分类后可重跑 | 整套 5 个 CDK 栈 + Cognito + Bedrock 的重量；管理员预定义的通用客服分类法（它没有发现层） |
| Dialog Reddit Research MCP（MIT，约 267 stars） | 直接用作 Reddit 接入层：语义发现未知社区、拉帖 + 评论树、feed 持续监控、引用溯源 | 不作唯一站外来源（只有 Reddit）；托管数据过第三方的口径需拍板 |
| jordanburke reddit-mcp-server（346 stars） | 作第二接入：官方通道失效时经 Arctic Shift 档案兜底 | 不改变快照原则，不依赖任何 Reddit 通道长期在线 |
| BERTopic（7,969 stars，MIT） | 作发现层聚类引擎（无监督、开源、可本地跑） | 聚类结果不直接当意图发布，簇 ≠ 意图 |
| TopicGPT（426 stars，MIT，NAACL'24） | 发现层四步流程：生成 → 理顺 → 带引用分配 → 自检纠错 | 主题不直接当意图 / JTBD 发布，仍过开放编码与人工确认 |
| IntentGPT（机制参考） | 机制定版：已知意图先召回分掉，残差提新意图，分类体系在运行中生长 | 无开箱实现，按此机制自建，阈值按自有语料校准 |
| ProductWeaver Plugin（Apache-2.0，2026-11-08） | 问卷层三条纪律：ODI 重要性 × 满意度定先问什么、引用逐字核对、预估答案标「估计」 | 不套它的需求分类，意图来自本工作台发现层 |
| Waters Sentiment Engine（MIT，2026-10） | 四条治理规则：mention 级编码、无引用丢弃、20 条抽查 80% 阈值、细格 <10 显示数据不足；拒绝 marketplace 页面的来源立场 | 不替代 Jev 执行层，它是编码纪律参考 |
| Qiaomu App Review Insights（232 stars，MIT） | 洞察报告模板：痛点 + 机会 + 风险 + 行动四段、每条带代表性引用、趋势 + 热图 | App 版本维度换成时间窗与来源维度 |
| Obsei（1,454 stars） | 接入插件形态与新主题提醒机制 | 其隐私聚合阈值（k-anonymity 5）不进发现层——小众新意图刚冒头时条数少，会被聚合误杀；小众意图走人工复核 |
| Consensus / Straitly-ai | 声量 → 投票选项 + 逐条引用，作问卷题项候选来源 | 站内投票结果不当问卷结论 |
| Automated Questionnaire Pretesting（Societal-Computing） | 问卷发布前加一道模拟人格预检，抓题面歧义 | 不取消真人试填门槛 |
| ProduckAI MCP Server（MIT） | 形态参考：工作台核心动作工具化，留程序接口供自动化调用 | 其 SaaS 反馈场景的打分维度与假设 |
| Dovetail | 证据链标准：任何结论点回原话 | 不采购，自建轻量版 |
| Thematic / Chattermill | 意图注册表治理方式：版本、合并、拆分留记录 | 不采购，体量与预算不匹配试点阶段 |
| Productboard / Canny | 推荐模块的形态：洞察落到带状态的行动项 | 路线图功能 |

星数与日期为 2026-11-23 调研时点数，接入前复核。来源链接见 PDT v1.2 附录 B。
