# M09-D 历史指标复核

复核基线为 `112474a9225b979d00d5f969403f9b012f8dcbb3`。输入是原有中英双语合成留出集，包含混合批 32 条和负例批 18 条。本次只读取原始输入、金标和已封存的分配结果，用 Python 标准库对所有可能的合法一对一配对进行枚举。既有评分使用 SciPy 的最大权重匹配。盲测数据和历史结果继续作为只读证据。[原始报告](../m09-d/blind-report.md) · [原始评分代码](../../../tests/test_m09d_blind.py) · [逐条台账](error-ledger.md)

## 计算口径

对每批分别统计每个非离群簇与每个已定义意图的样本交集。每簇最多配一个意图，每意图最多配一个簇，使交集总数最大，零重叠项视为未匹配。模糊和孤立样本参与整批覆盖与各簇分母。

| 指标 | 分子 | 分母 | 范围 |
| --- | --- | --- | --- |
| 匹配簇纯度，历史 JSON 字段 `precision` | 同时属于配对意图与簇的样本数 | 这个簇的全部样本数，含模糊、孤立和其他意图 | 指定方案下的一个配对意图 |
| 召回 | 同一交集样本数 | 这一意图在该批的全部金标样本数，含离群和错簇 | 同一意图 |
| 分配覆盖 | 分配到任一非离群簇的样本数 | 同批全部样本数 | 同一方案的整批，包含错误分配 |
| 离群率 | 指派为 `-1` 的样本数 | 同批全部样本数 | 整批，与分配覆盖互补 |

## 独立复算

每个意图单元格为「匹配簇纯度 · 召回」。意图未匹配时，纯度为「—」，召回为零。

| 批次及方案 | 定时启动 | 自动关闭 | 掉电恢复 | 分配覆盖 | 离群率 | 未匹配簇 |
| --- | --- | --- | --- | --- | --- | --- |
| 混合，原始 | 5/10 · 5/8 | — · 0/8 | 6/15 · 6/8 | 25/32 | 7/32 | 0/2 |
| 混合，余弦 ≥ 0.60 | 5/10 · 5/8 | — · 0/8 | **6/11 · 6/8** | **21/32** | 11/32 | 0/2 |
| 负例，原始，按历史并列取法 | — · 0/6 | 6/13 · 6/6 | — | 18/18 | 0/18 | 1/2 |
| 负例，余弦 ≥ 0.60 | 6/10 · 6/6 | — · 0/6 | — | 15/18 | 3/18 | 1/2 |

`6/11` 与 `6/8` 都针对过滤后混合批的掉电恢复簇 0。交集为 `MX17`、`MX18`、`MX20`、`MX22`、`MX23`、`MX24`。其余五条是一个定时启动和四个自动关闭。另两条掉电恢复在原始及过滤方案中均为离群。`21/32` 是混合批覆盖。过滤前的 `25/32` 是原始 BERTopic 分配覆盖，过滤移除了 `MX07`、`MX26`、`MX29`、`MX30`。这四条中含一个错分的真实目标意图、一个模糊表达和两个孤立需求，历史原始记录全部可查。[原始结果](../m09-d/blind-results-v1.json)

| 混合批簇 | 定时启动 原始/过滤 | 自动关闭 原始/过滤 | 掉电恢复 原始/过滤 | 模糊 原始/过滤 | 孤立 原始/过滤 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 2/1 | 4/4 | 6/6 | 1/0 | 2/0 |
| 1 | 5/5 | 4/4 | 0/0 | 1/1 | 0/0 |
| 离群 `-1` | 1/2 | 0/0 | 2/2 | 2/3 | 2/4 |

## 发现与解释边界

- 四个批次与方案组合的覆盖、配对交集、各分母、残差和新候选诊断数均与原始结果一致。混合批的最大重叠配对在两种方案中均唯一，只有簇 0 配掉电恢复、簇 1 配定时启动能达到 11 条匹配。自动关闭的八条全部进入聚类，却按品类分裂成两个四条子组，混入两簇。仅看 `0/8` 会遗漏这层结构。
- 负例原始簇 0 内有 6 条定时启动、6 条自动关闭和 1 条孤立样本。最大重叠有两个等价最优解。历史 SciPy 路径返回自动关闭，若选择定时启动，也得到相同的 `6/13` 与 `6/6`。过滤拿掉两条自动关闭和一条孤立样本后，簇 0 才唯一配到定时启动。历史逐意图表看似从 0 召回跳到 100% 召回，但 6 条定时启动原来就都在簇 0。这是配对与报告解释问题，非新增发现。
- 历史评分的「未匹配候选」只记录无金标配对的非离群簇。混合批两簇均配到一个意图，仍有明显误分。负例两种方案的独立误发现均为簇 1，包含 `NG13`、`NG14`、`NG16`、`NG17`、`NG18`。报告误发现时应同时给出未匹配簇的数量与成员清单，以及匹配簇的污染。
- 历史诊断条件验证纯度和召回各至少 75%，且命中覆盖两种语言与两个品类。条件只检查语言及品类的边际集合，允许部分语言×品类组合缺席。混合批掉电恢复命中两品类及两语种，但其中两条英文炸锅样本 `MX19`、`MX21` 均离群，该组合为 0/2。后续应同时公布各组合的计数。
- 历史候选人工驳回后的 13/18 是负例原始聚类的候选成员覆盖。负例探索过滤后的 15/18 是研究诊断中的分配覆盖。两者来自不同操作。
- 原始盲测没有达标的未知候选。M09-B 的既有纯度诊断 8/11、8/12 和 8/13 继续有效。0.60 是探索阈值，G3 为 `PENDING`。[M09-B 复验](../m09-b/README.md) · [M09-D 预设方案](../m09-d/blind-plan.md)

## 复算脚本

从仓库根目录用 Python 3.12 运行下列代码。脚本独立枚举合法配对，同时逐条从原始余弦分数复算过滤分配。未进行新推理。

~~~python
from collections import Counter
from hashlib import sha256
from itertools import product
from pathlib import Path
from unicodedata import normalize
import json

root = Path("docs/evidence/m09-d")
hashes = {
    "input": "38a0f4be20804a4fe9f6ea32f2c8532ceb5d2eae04040bb2317e7989083c2eb4",
    "gold": "3efb13bb905bb215ad9df91a7e6fb01194d2ed6da7519c1804d8b74db05e5e7e",
    "results": "2f38569bfbbf5a0b6fb5faabb590e27c44d35481c85016a661af54f080f88461",
}
parsed = {}
for kind, expected in hashes.items():
    text = (root / f"blind-{kind}-v1.json").read_text(encoding="utf-8")
    assert sha256(text.encode()).hexdigest() == expected
    parsed[kind] = json.loads(text)
gold = parsed["gold"]

for batch in parsed["results"]["batches"]:
    entries = parsed["input"]["batches"][batch["batch"]]
    inputs = {sample: (category, language, raw) for sample, category, language, raw in entries}
    labels = {sample: gold["labels"][sample] for sample in inputs}
    theme_counts = Counter(labels.values())
    themes = sorted(gold["themes"].keys() & theme_counts.keys())
    documents = batch["documents"]
    assert len(entries) == len(labels) and set(documents) == set(labels)
    raw_assignment = {sample: row["raw_topic_id"] for sample, row in documents.items()}
    filtered = {}
    for sample, row in documents.items():
        raw = inputs[sample][2]
        assert (row["lineage"]["start_cp"], row["lineage"]["end_cp"]) == (0, len(raw))
        assert sha256(raw.encode()).hexdigest() == row["original_excerpt_sha256"]
        model_input = " ".join(normalize("NFKC", raw).split())
        assert sha256(model_input.encode()).hexdigest() == row["model_input_sha256"]
        similarity = row["centroid_similarity"]
        filtered[sample] = (
            raw_assignment[sample]
            if similarity is not None and similarity >= gold["centroid_cutoff"] else -1
        )
    for mode, assignments in (("raw", raw_assignment), ("centroid_exploratory", filtered)):
        result = batch["results"][mode]
        assert assignments == result["assignments"]
        sizes = Counter(assignments.values())
        topics = sorted(topic for topic in sizes if topic >= 0)
        overlap = Counter((labels[sample], topic) for sample, topic in assignments.items())
        choices = [[None] + [topic for topic in topics if overlap[theme, topic]] for theme in themes]
        scores = {}
        for choice in product(*choices):
            used = [topic for topic in choice if topic is not None]
            if len(used) == len(set(used)):
                scores[choice] = sum(overlap[theme, topic] for theme, topic in zip(themes, choice))
        optima = [choice for choice, score in scores.items() if score == max(scores.values())]
        historical = tuple(result["themes"][theme]["topic_id"] for theme in themes)
        assert historical in optima
        assert result["coverage"] == [len(labels) - sizes[-1], len(labels)]
        assert result["candidate_count"] == len(topics)
        assert result["unmatched_candidates"] == {
            str(topic): sorted(sample for sample in inputs if assignments[sample] == topic)
            for topic in topics if topic not in historical
        }
        assert result["residual"] == {
            label: [overlap[label, -1], theme_counts[label]] for label in ("ambiguous", "singleton")
        }
        novel = 0
        for theme, topic in zip(themes, historical):
            item = result["themes"][theme]
            hits = sorted(sample for sample in inputs if labels[sample] == theme and assignments[sample] == topic)
            misses = sorted(sample for sample in inputs if labels[sample] == theme and assignments[sample] != topic)
            unrelated = sorted(sample for sample in inputs if labels[sample] != theme and assignments[sample] == topic)
            precision = len(hits) / sizes[topic] if topic is not None else None
            recall = len(hits) / theme_counts[theme]
            categories = sorted({inputs[sample][0] for sample in hits})
            languages = sorted({inputs[sample][1] for sample in hits})
            meets_diagnostic = (
                precision is not None and precision >= gold["diagnostic_precision"]
                and recall >= gold["diagnostic_recall"] and len(categories) == len(languages) == 2
            )
            novel += gold["themes"][theme]["familiarity"] == "unknown" and meets_diagnostic
            assert (item["hits"], item["out_of_cluster"], item["unrelated_members"]) == (hits, misses, unrelated)
            assert (item["cluster_size"], item["gold_size"]) == (sizes[topic], theme_counts[theme])
            assert (item["precision"], item["recall"]) == (precision, recall)
            assert (item["products"], item["languages"], item["diagnostic_threshold_met"]) == (
                categories, languages, meets_diagnostic
            )
            purity = (len(hits), sizes[topic]) if topic is not None else None
            print(batch["batch"], mode, theme, "purity", purity, "recall", (len(hits), theme_counts[theme]))
        assert result["supported_novel_candidate_count"] == novel
        print("coverage", result["coverage"], "optimal matchings", [dict(zip(themes, c)) for c in optima])
~~~
