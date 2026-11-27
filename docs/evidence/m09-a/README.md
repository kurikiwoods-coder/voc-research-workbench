# M09-A 本机向量接口和复验证据

2026-11-27 在 Windows 11 build 26200、Python 3.12.9 上运行 M09-A 和直接上游回归。使用临时工作库、合成夹具、合成模型资产和替身推理运行时。清除测试进程中的供应商凭证及工作区配置，启用模型库离线环境标志，并用 Python audit hook 拦截非回环 DNS、连接和数据报。真实研究请求与进程内非回环尝试均为 0。

| 范围 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|
| 本地加载器及运行时契约 | 13 | 0 | 0 |
| 向量、缓存、数据资格与溯源 | 9 | 0 | 0 |
| M05 语料、M06 片段、M07 注册表、M08 采样回归 | 59 | 0 | 0 |
| 合计 | 81 | 0 | 0 |

退出码 0。复跑可使用 `python -m unittest discover -s tests -p test_embedding_backend.py -v` 和 `python -m unittest discover -s tests -p test_m09_embeddings.py -v`。四个直接回归测试文件为 `test_corpus.py`、`test_m06_mentions.py`、`test_m07_registry_versions.py` 和 `test_m08_sampling.py`。Windows 路径拒绝分支在本机执行。真实模型权重与运行时实测待补。完整工程回归和三项 CI 归属正式模块结项。

## 输入、版本与缓存

- `OfflineEvidence` 固定研究项目、冻结范围及范围版。M06 路径要求可信合成记录登记与精确 `mention_id`、`evidence_id`、片段版本，经原有读取入口核验 M05 资格和依赖。M08 路径要求当前合成采样权限与已对账回执，沿用其读回检查。原有采样回执中缺省的 M06 指针继续为空。
- 保留批次、记录 ID、原文 SHA-256、半开 Unicode 区间、来源与抽取版本。M06 上下文 ID 及 M08 来源对象和响应摘要保留在本机行映射。M07 从现有消费者入口验证精确封版注册表。预处理对派生文本执行 NFKC、空白整理与常见标识剔除，沿用原库的敏感模式。推理接口只接收派生文本。
- 语料原语言、分析语言和输出语言独立配置。语言标签可声明为区域变体。稳定行 ID 基于项目与证据身份，和模型及语言无关。跨语言聚类可消费同一矩阵，语义合并及正式确认依既有人工审核规则。
- 每次运行按稳定 ID 排序。模型身份、运行库版、参数、预处理版、注册表版、语言及输入摘要共同确定运行指纹。可选缓存只保留向量，按运行指纹校验完整性，写入采用临时文件原子替换。复跑读取和推理完成后均核查证据权限。实际 SQLite 版本沿用现有 Personal v11 和 Business v9。

## 本地模型准备

实现选择 Sentence Transformers 的 CPU 推理路径。使用与 Python 3.12 和目标系统匹配的离线轮包，按审核清单锁定 `sentence-transformers`、`transformers`、CPU `torch`、`tokenizers`、`safetensors`、`huggingface-hub` 及传递依赖。可在独立虚拟环境以 `python -m pip install --no-index --find-links <wheelhouse> --require-hashes -r <locked-requirements>` 安装，模型载入前保持断网。

多语言候选为 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`。模型卡标注 Apache-2.0 和 384 维。部署时需核对所选精确版本、随附许可证与声明、safetensors 权重及本机资产清单。兼容性以所选本地副本实测为准。[上游模型卡](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) · [Sentence Transformers 接口](https://www.sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html)

配置时建立 `EmbeddingProfile`，记录模型 ID、精确修订、`manifest_fingerprint`、维度、序列长度、批大小、归一化、语言能力及 `local_runtime_version()`。传入可信目录和逐文件 SHA-256 资产清单给 `LocalSentenceTransformer`。用合成中英文执行加载、维度、归一化、有限值和复跑容差验证，结束后调用 `close()`。

## M09-B 接续

`EmbeddingBatch.rows` 的 `model_text` 顺序与 `EmbeddingBatch.vectors` 的 float32 行完全对应。模型、预处理、准确的注册表版及运行指纹随批交接。M09-B 另行固定降维、聚类与主题提取参数，主题为人工审核候选。回查证据时重新走现行资格入口。M09-A 输出的正式研究分母恒为 0，`outbound_allowed=False`。
