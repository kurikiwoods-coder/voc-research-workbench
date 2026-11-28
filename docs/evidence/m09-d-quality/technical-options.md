# M09-D 开源方案与本地兼容性

## 嵌入模型与文本表示

现有基线使用已审核的 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`，Apache-2.0。已固定本地 safetensors、CPU、384 维归一化、128 token 截断及批大小 4。本轮使用同一模型、向量和输入比较各聚类方法，避免把向量变化误归因于聚类。Windows x64 CPython 3.12.9 环境的现有依赖包括 Sentence Transformers 5.1.2、Transformers 4.57.1、PyTorch 2.8.0+cpu。模型和版本的本机校验依据见 [M09-A](../m09-a/README.md) 与 [模型卡](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/tree/e8f8c211226b894fcb81acc59f3b34ba3efd5f42)。

| 替代模型 | 厂商资料与评估重点 | 本轮证据 |
| --- | --- | --- |
| Multilingual E5 Small | MIT，384 维。模型发布者对聚类等对称任务规定 `query: ` 前缀。优先作为短文本的后续 CPU 对照。需审核指定 revision 的 tokenizer、safetensors、池化模块和前缀配置，记录实际输入摘要。维数相同也需独立校准距离。 [模型卡](https://huggingface.co/intfloat/multilingual-e5-small) | 文档选型，当前比较仅使用已审核 MiniLM。E5 权重、兼容性及效果待验证。 |
| BGE-M3 | MIT，密集向量 1024 维，模型支持长达 8192 token。若短片段的主要缺口来自上下文，再评估密集向量路径及 CPU 资源。发布者还提供稀疏和多向量路径，后两种需要不同的表示契约和依赖审查。 [模型卡](https://huggingface.co/BAAI/bge-m3) | 文档选型。BGE-M3 权重、兼容性及效果待验证。 |

现有适配器校验资产哈希与允许的 Transformer、Pooling、Normalize 模块，按 CPU、离线及禁用远程代码加载。替代模型需在指定本地资产上验证架构、tokenizer 和模块检查，记录 revision、清单、许可证、依赖版本、实际 CPU 峰值内存与耗时。E5 的前缀应作为显式、版本化输入变换。审核模型兼容性时沿用现有安全检查。 [适配器](../../../src/discovery/embedding_backend.py)

## 聚类与候选筛选

| 方案 | 本地依赖与许可证 | 比较范围和风险 |
| --- | --- | --- |
| 原始 BERTopic | BERTopic 0.17.4，MIT。UMAP 0.6.0 与 HDBSCAN 0.8.44，BSD-3-Clause。许可依据为当前已安装包的 LICENSE。 [BERTopic 算法](https://maartengr.github.io/BERTopic/algorithm/algorithm.html) | 基线先在 2 维 UMAP 空间做密度聚类，再从成员生成主题表示。保留原始成员、离群及运行身份。 |
| UMAP/HDBSCAN 参数敏感性 | 同一依赖链。 [UMAP 可复现性](https://umap-learn.readthedocs.io/en/latest/reproducibility.html) · [HDBSCAN 参数选择](https://hdbscan.readthedocs.io/en/latest/parameter_selection.html) | 定向比较 UMAP 5 维、8 邻域与 HDBSCAN 最小簇 4、最小样本 2 的组合。多个参数同时变化时，结果只支持对组合进行比较。若需要根因归因，再在开发集做单因素消融。依据固定种子重跑及跨种子一致性评估稳定性。 |
| 直接余弦平均链接 | scikit-learn 1.9.1，BSD-3-Clause。本机 CPU 接口冒烟测试用五个二维向量得到分组标签 `[2, 2, 0, 0, 1]`。 [AgglomerativeClustering](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.AgglomerativeClustering.html) | 以 0.55 距离切分，少于 4 个成员的簇归为残余。使用同一批归一化向量绕开降维，便于检验原始嵌入空间的结构。全量两两距离的成本随样本量呈二次增长，合成小样本结果不能代表长批次的成本。平均链接仍可能合并语义近邻和同类产品词汇。 |
| 中心相似度与拒判 | 复用 NumPy 和聚类向量。 [历史筛选诊断](../m09-b/exploratory-clustering.md) | 保留历史 0.60 实验。另一对照在平均链接结果上使用留一法评估成员与本簇中心的相似度，再检查与最接近竞争簇的差值。若候选筛选改善纯度，同时损失召回和覆盖，完整报告保留与拒判两侧的数量及语义错误。 |

HDBSCAN 已在历史测试出现误归类成员概率为 1.0、GLOSH 离群分数为 0.0 的情况。原始分配、密度指标、中心相似度与筛选决策各自保留。中心相似度可提供审核排序，候选提交需同时检查独立证据支持、近邻冲突和覆盖损失。合并或拆分候选须保留父子关系和残余记录，并从筛选后的成员重新生成关键词与代表片段。 [历史反例](../m09-b/exploratory-clustering.md)

## 分词、短片段与证据约束

当前嵌入输入执行 NFKC、标识符去除和空白归一化，分别记录原文与模型输入摘要。jieba 0.42.1（MIT）使用项目验证过的字典和关闭 HMM 的分词路径，配合英文停词过滤生成主题词。对于错误样本，应分别检查嵌入输入、分组和主题词三个层面。对于否定、对比、时间条件及中英混写，先保留原句语义关系，观察模型截断及分词对主题名称的影响，之后再比较最小归一化控制。 [嵌入预处理](../../../src/discovery/embeddings.py) · [主题表示](../../../src/discovery/topics.py) · [jieba](https://github.com/fxsjy/jieba)

本轮最小簇阈值以合成样本行计数。接入研究证据后，保留近重复文本的原始成员和证据引用，按去重组另计独立支持数。对缺上下文的短片段保留残余和审核状态。上下文实验仅加入同一来源版本中有资格且允许读取的邻近文本，记录上下文证据 ID、范围和截断边界，以独立版本与单片段对照比较。训练标签、类别提示和外部生成文本都排除在本轮聚类输入之外。

本轮实验沿用已有 Windows CPU 依赖，第三方替代模型停留在技术选型，实测覆盖以本轮结果为准。批准进入业务候选管线前，需要独立留出验证、多语言和跨品类分层结果、候选支持与覆盖复核、重放证据及资格撤销回归。
