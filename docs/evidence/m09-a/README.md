# M09-A 本机向量接口和复验证据

2026-11-27 在 Windows 11 build 26200、Python 3.12.9 上运行 M09-A 和直接上游回归。使用临时工作库、合成夹具、合成模型资产和替身推理运行时。清除测试进程中的供应商凭证及工作区配置，启用模型库离线环境标志，并用 Python audit hook 拦截非回环 DNS、连接和数据报。真实研究请求与进程内非回环尝试均为 0。

| 范围 | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|
| 本地加载器及运行时契约 | 13 | 0 | 0 |
| 向量、缓存、数据资格与溯源 | 9 | 0 | 0 |
| M05 语料、M06 片段、M07 注册表、M08 采样回归 | 59 | 0 | 0 |
| 合计 | 81 | 0 | 0 |

退出码 0。复跑可使用 `python -m unittest discover -s tests -p test_embedding_backend.py -v` 和 `python -m unittest discover -s tests -p test_m09_embeddings.py -v`。四个直接回归测试文件为 `test_corpus.py`、`test_m06_mentions.py`、`test_m07_registry_versions.py` 和 `test_m08_sampling.py`。Windows 路径拒绝分支在本机执行。完整工程回归和三项 CI 归属模块结项。

## 输入、版本与缓存

- `OfflineEvidence` 固定研究项目、冻结范围及范围版。M06 路径要求可信合成记录登记与精确 `mention_id`、`evidence_id`、片段版本，经原有读取入口核验 M05 资格和依赖。M08 路径要求当前合成采样权限与已对账回执，沿用其读回检查。原有采样回执中缺省的 M06 指针继续为空。
- 保留批次、记录 ID、原文 SHA-256、半开 Unicode 区间、来源与抽取版本。M06 上下文 ID 及 M08 来源对象和响应摘要保留在本机行映射。M07 从现有消费者入口验证精确封版注册表。预处理对派生文本执行 NFKC、空白整理与常见标识剔除，沿用原库的敏感模式。推理接口只接收派生文本。
- 语料原语言、分析语言和输出语言独立配置。语言标签可声明为区域变体。稳定行 ID 基于项目与证据身份，和模型及语言无关。跨语言聚类可消费同一矩阵，语义合并及正式确认依既有人工审核规则。
- 每次运行按稳定 ID 排序。模型身份、运行库版、参数、预处理版、注册表版、语言及输入摘要共同确定运行指纹。可选缓存只保留向量，按运行指纹校验完整性，写入采用临时文件原子替换。复跑读取和推理完成后均核查证据权限。实际 SQLite 版本沿用现有 Personal v11 和 Business v9。

## 本地模型和运行时

本轮使用 Windows x64 CPython 3.12.9 的独立 CPU 虚拟环境。M09-A/B 可选离线锁覆盖 44 个轮包，包括 `sentence-transformers==5.1.2`、`transformers==4.57.1`、`torch==2.8.0+cpu`、`bertopic==0.17.4`、`jieba==0.42.1`、`umap-learn==0.6.0` 和 `hdbscan==0.8.44`。`jieba` 轮包由已校验的 PyPI 源码包经 setuptools 80.9.0 和 wheel 0.45.1 构建。模型资产与轮包保存在本机隔离目录。[哈希锁](requirements-windows-py312-cpu.txt) · [轮包来源与 SHA-256](wheelhouse-provenance.json) · [jieba 源码证据](jieba-source.json)

本机完成仅使用轮包的带哈希安装与 `pip check`。实际导入推理和聚类依赖，CPU 张量运算及 jieba 分词冒烟通过。PyTorch 发出 Microsoft Visual C++ Redistributable 缺失警告，CPU 张量运算及后续实测通过。复验通过 `--app-site-packages` 将原有应用环境的库目录追加到隔离环境的搜索路径，锁定的模型和聚类依赖优先加载。

获准模型为 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，修订 `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`，Apache-2.0，使用本地 safetensors 权重。复验配置固定为 CPU、384 维、`zh` 和 `en`、序列上限 128、批大小 4，并启用归一化。`EmbeddingProfile` 同时记录 `manifest_fingerprint` 和 `local_runtime_version()`。`LocalSentenceTransformer` 按路径和逐文件 SHA-256 验证资产，结束后调用 `close()`。[资产清单](model-assets.json) · [固定修订模型卡](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/tree/e8f8c211226b894fcb81acc59f3b34ba3efd5f42)

## 原生 Windows 11 实际模型复验

2026-11-27，原生 Windows 11 build 26200 上获准模型权重复验 **3/3**，用时 50.622 秒，退出码 0，真实研究 API 和 Python 审计记录的非回环 socket、DNS 尝试均为 0。模型输入为合成中英文本和临时 SQLite 资格夹具。**M09-A = ENGINEERING_PASS**。[复验程序](../../../scripts/verify-m09-offline.py) · [实测用例](../../../tests/test_m09_actual_model.py)

| 复验范围 | 实际结果 |
|---|---|
| 向量约定和语义排序 | 384 维、有限 `float32`、L2 单位范数。余弦相似度为英语同义 0.8252、中英同义 0.8906、英语异义 0.1976、中文异义 0.1667。 |
| 长文本 | 分词长度 706 截断至 128。仅截断位置之后不同的两个输入产生容差内相同的向量。 |
| 证据映射与复跑 | 反转输入顺序后，稳定行 ID、证据映射和运行 ID 一致。命中缓存不触发推理，损坏缓存可重算修复，无缓存复跑在 `rtol=1e-5`、`atol=1e-6` 内一致。 |

从仓库根目录运行下列 PowerShell 命令。将三个路径变量设为独立虚拟环境的 Python、本机获准轮包目录及模型目录。现有应用虚拟环境的包目录以 `.venv/Lib/site-packages` 为例。

```powershell
& $m09Python -m pip install --no-index --find-links $m09Wheelhouse --require-hashes -r docs/evidence/m09-a/requirements-windows-py312-cpu.txt
& $m09Python -m pip check
& $m09Python scripts/verify-m09-offline.py $m09ModelDir docs/evidence/m09-a/model-assets.json test_m09_actual_model.py --app-site-packages .venv/Lib/site-packages
```

复验程序清除供应商与工作区环境变量，启用离线模式和进程内网络审计，并通过 `VOC_M09_MODEL_DIR` 与 `VOC_M09_MODEL_MANIFEST` 选择性启用实际模型测试。

## M09-B 接续

`EmbeddingBatch.rows` 的 `model_text` 顺序与 `EmbeddingBatch.vectors` 的 float32 行完全对应。模型、预处理、准确的注册表版及运行指纹随批交接。M09-B 另行固定降维、聚类与主题提取参数，主题为人工审核候选。回查证据时重新走现行资格入口。M09-A 输出的正式研究分母恒为 0，`outbound_allowed=False`。
