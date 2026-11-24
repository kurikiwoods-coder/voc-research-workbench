# VOC 研究工作台

> **当前处于 P0-0，G-1 为 BLOCKED。** 本地工作台可运行，正式验收等待供应商密钥和留存审查。[本轮工程与验收证据](docs/evidence/p0-0/closeout/README.md) · [历史验收记录](docs/evidence/p0-0/README.md)

## 目的

VOC 工作台用于研究任意产品、服务或跨品类用户需求。一个研究项目可选择多个品类，也可以只指定研究问题。原话、用户任务和意图分别建模。营养秤是历史试点之一。

## 启动当前版本

开发分支交付 P0-0 本机工作台，包含 API 接入、连通性检查、验收矩阵、批次记录和 Jev 额度中心。浏览器通过 FastAPI 访问本地 SQLite。没有供应商凭证也能启动并完成配置向导。

**Windows** 安装 Python 3.12 后双击 `scripts/start-windows.cmd`，浏览器打开 **http://127.0.0.1:8765/**。Linux 或 macOS 可在 Python 虚拟环境执行以下命令。

```sh
python -m pip install -r requirements.txt
python -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
```

首次启动可跟随向导，也可以从「设置 → API 接入」继续。选择 TypeSafe 或 JevModel，配置 Tavily 或 Brave 中的至少一家。粘贴密钥后点「保存密钥」，立即生效。导入所选 Jev 通道的留存审查，再逐服务点「检查连接」。[用户操作说明](docs/connectivity.md#从工作台配置-api) · [供应商注册与取钥](docs/connectivity.md#注册与创建密钥)

点「运行正式验收」执行原有六项检查。可在「运行记录」恢复批次或导出脱敏证据。YouTube 和 Google Forms 当前提供接入资料，分别等待 P0 和 P1。[阶段验收记录](docs/evidence/p0-0/README.md) · [需求与冲突矩阵](docs/requirements-matrix.md)

## 工程回归

安装 Python 3.12、Node 24 和 `requirements-dev.txt`，执行 `bash scripts/smoke-test.sh`。本地 Chromium 回归执行 `python -m playwright install chromium` 和 `python tests/browser_e2e.py`。GitHub Actions 在 PR 上运行 Linux、Windows Server 和 Chromium 工程测试，保存日志和截图。Windows 10/11 真机验收单独登记。[CI 工作流](.github/workflows/p0-0-ci.yml) · [Actions 运行记录](https://github.com/kurikiwoods-coder/voc-research-workbench/actions/workflows/p0-0-ci.yml)

## 研究闭环的目标产出

1. **意图注册表** — 发现了什么意图、定义、包含/排除标准、代表原话、版本号。
2. **洞察仪表盘** — 情感 / 问题 / 趋势 / 推荐四模块，数字按来源分开报。
3. **验证问卷与回流记录** — 由发现直接生成题项，可导出到 Google Forms；回收数据回灌验证发现。

## 六层架构

| 层 | 职责 | 关键组件 | 输入 → 输出 |
|---|---|---|---|
| L1 采集层 Ingestion | 每个来源一个接入器，互不影响；任一来源失效不阻塞 CSV 主路径 | Tavily + Brave 双搜索发现、AI 查询规划器、YouTube Data API、论坛适配器、Reddit 备用适配器（Dialog MCP / Arctic Shift 兜底）、CSV 人工导入 | 研究问题 → URL 候选 → 经许可的原文批次 |
| L2 原始层 Raw Store | 原文原样落盘，永不覆盖；可重跑 | 原始语料库、采样日志、去重组、许可状态 | 批次 → 可重跑的原始语料库 |
| L3 发现层 Discovery · P0-1 | 从无标签语料提出清单外新意图候选 | BERTopic 聚类 + TopicGPT 四步（generate → refine → assign with quote → correct）、开放编码、IntentGPT 残差机制（已知意图先 KNN/Jev 召回分掉，残差进候选池）、人工确认 | 原始语料 → 候选意图 → 意图注册表新版本 |
| L4 执行层 Execution · P0-2（Jev，强制） | 意图给定后规模化编码 | Jev 客户端（`jev-1.14.0`，Choice/Score/Noul，None + Noul 守门）、金标准校准、Token Center（额度条、X-Tokens-Remaining 同步、预算闸门、购买跳转）、低置信复核队列 | 语料 + 注册表 → 带完整概率分布的编码结果 |
| L5 仪表盘层 Dashboard | 情感 / 问题 / 趋势 / 推荐四模块集中一页 | 意图 × 情感矩阵、问题 Top 榜、同口径周趋势、智能推荐（触发条件 + 证据 + 动作 + 验证方法）、待审队列视图、采样漏斗 | 编码结果 → 洞察页面与推荐清单 |
| L6 输出层 Outputs | 问卷生成器 + 洞察报告 + 回流 | 问卷生成器（发现类型 → 题型映射，ODI 排序，模拟预检 + 2–3 人真人试填）、Google Forms 导出、洞察报告（痛点/机会/风险/行动）、回收回灌 | 发现与洞察 → 问卷/报告 → 回收数据回流到 L2 |

架构原则：先存原始、再谈分析；自家与竞品数据分开算（Radar 独立）；改注册表后可全量重跑；核心动作（检索、编码、汇总、出题）都留程序/MCP 接口，不锁在一个网页里。

## P0 准入后的研究流程

1. 冻结研究主题与范围，登记来源权限和采样规则。
2. CSV + Tavily/Brave 搜索发现 → 至少 100 条去重且可核验的真实用户语义片段入库（尽量 ≥3 个独立站点/批次）。
3. 发现层试点：BERTopic + TopicGPT 双轨提候选，人工确认入注册表。
4. Jev 校准：100–200 条人工金标准，中文单独校准，通过 J-1～J-14 后放量。
5. 问卷生成器 v1：按发现类型映射出题，模拟预检 → 2–3 人真人试填 → 导出 Google Forms。

## Jev 强制项

- **模型锁定 `jev-1.14.0`**（2026-10-14），禁止 `jev-latest`；换任何版本必须重跑 100–200 条金标准并重定阈值。
- **只用 Choice / Score / Noul 三种**；Jev 1.14 新增的 Box（图片框选）明确排除出 P0。
- **每个 Choice 必须配 None 选项**（「以上都不是」）**+ 一道 Noul 守门**「是否属于现有意图清单」；答否即进发现队列，即使 Choice 第一名概率很高。依据：独立评测（EurekaLeo，2026-10-07 截止，101 项核心研究）显示，即使给了明确的 None 选项，Jev 也只在 7% 的缺失正确答案菜单上拒绝作答。
- **中文单独校准**：中文与英文金标准分开建、分开报一致率；不要用英文翻译后跑分代替中文原文跑分（Chinese-Jev，arXiv:2609.36965）。
- **CX 内部客诉绝不进 Jev**：Jev 走 TypeSafe 托管 API，同样算第三方 API；CX 只做本地/人工编码。TypeSafe 由组织管理员在控制台启用并留存 ZDR 凭据。独立第三方服务单独审查。
- **成本**：官方价输入 $0.042/百万 tokens、输出免费；每条约 300 输入 tokens 时，1,000 条跑一整套问题约 $0.013。P0 真正成本是人工标注与复核。
- 详见 [PDT v1.3.1](docs/pdt/PDT-v1.3.1.docx) §7 与 [docs/checks/jev-pdt-check-2026-11-23.md](docs/checks/jev-pdt-check-2026-11-23.md)。

## 数据源与口径

| 来源 | 证据等级 | 口径红线 |
|---|---|---|
| Tavily/Brave 搜索发现 + 许可论坛/YouTube 原话 | 条件 A（原话可核验） | 搜索摘要是线索不是原话；每个站点/时间窗分别报 n |
| Reddit（备用适配器） | 条件 A；来源内独立报告 | 只信快照：RSS 自 2026-11-13 起停止支持；2027-01-12 未注册应用被撤访问权；2027-03 公开 Data API 全面关闭 |
| 研究期刊与公开调查（IFIC / CDC / KFF） | B | 人群层面证据，不直接证明本品类用户占比 |
| GitHub 开源生态 | C | 只作领先用户信号，不进漏斗、不推规模与付费意愿 |
| Amazon 评价 | 初步 | 只走四条窄路（自有后台导出 / 公开页人工采样 / 只取聚合数 / Shulex API）；只用 US verified 评价作产品体验依据 |
| 内部客诉（CX） | C，只做痛点排序 | 原始表绝不进仓库、不喂任何第三方工具 |
| 自有问卷回收 | A（验证依据） | 样本来源与招募方式必须登记 |

详见 [docs/sources/source-map.md](docs/sources/source-map.md)、[docs/sources/amazon-narrow-paths.md](docs/sources/amazon-narrow-paths.md)、[docs/sources/reddit-timeline.md](docs/sources/reddit-timeline.md)。

## 统一数据表与 Schemas

所有来源先进一张统一表再谈分析，字段分四组：溯源 / 原文 / 编码 / 治理。CSV 导入最小字段：`raw_text`、`source_type`、`published_at`、`source_url`。机器可读定义见 [schemas/](schemas/)。

## 问卷输出

发现类型 → 题型映射（见 [schemas/questionnaire-mapping.json](schemas/questionnaire-mapping.json)）：新意图候选→场景多选；优先级不明→二选一/排序；高严重度问题→经历+困扰度量表；换用/放弃信号→换秤意愿+触发条件；清单外空白→每份问卷固定 1–2 道开放题。出题红线：选项来自原话归纳；一道题只验证一个发现；预估答案标「估计」；发布四道门：模拟预检 → 2–3 人真人试填 → 正式投放 → 回收回灌。

## 对标与借鉴

16 个对标，借/不借一句话，见 [docs/benchmarks.md](docs/benchmarks.md)。共同结论：市面方案几乎都只做「执行」，做到「发现新意图」的只有机制级参考，做到「发现转问卷」的只有一个（ProductWeaver）——这两块正是本工作台自建的差异点。

## 分期与验收

- **P0-0** 先用同一批次和真实证据验收 G-1。
- **P0** 实现发现、编码、基础仪表盘与问卷草稿，逐项验收 J、CAT、G 系列。G6 的真实回流按矩阵归入 P1。
- **P1**：仪表盘四模块 + 声量基线 + 问卷回流。
- **P2**：竞品 Radar + Amazon 窄路常态化 + GitHub 信号三角验证。

## 红线

- 定性不推比例：论坛与评价的定性结论不能推断各类用户占比，不能当完整买家画像；所有汇总按来源分开报 n、日期与分母。
- Jev 概率 ≠ 准确率：confidence 0.9 不等于 90% 正确；低置信先进复核队列。
- CX 不出境：内部客诉不直喂任何第三方 API，只做痛点排序。
- Amazon 不爬：不建爬虫、不买代爬服务，只走四条窄路。
- GitHub 只作信号：不进漏斗、不推规模与付费意愿。
- 口径一致才可比；证据可点回；旧款结论不套新款。
- 详见 [docs/methodology.md](docs/methodology.md)。

## 贡献与决策

待拍板事项 D1–D5（状态均为待定，2026-11-23），见 [docs/decisions/](docs/decisions/)。PR 要求见 [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)：改 Jev 版本必须附重跑金标准记录；改注册表必须升版本并留变更记录。

## 许可证

MIT License，见 [LICENSE](LICENSE)。Copyright (c) 2026 Ryan Han。
