# M09-B exploratory clustering diagnostics

The runs used the approved local multilingual model and the pinned Windows Python 3.12 CPU runtime. The frozen and holdout fixtures, their cue words, and the frozen configuration are defined in `tests/test_m09_actual_topics.py`. The holdout contains distinct themes about delayed start and adjustable alert volume. Each fixture contains two eight-document themes and six designated noise documents. Theme columns show recall followed by precision. The quality gate requires at least 75% in both measures, distinct clusters with both languages and products, theme keywords, exact replay, and at least one designated noise document assigned to `-1`.

## Standard HDBSCAN configuration

Changing the HDBSCAN constructor's `cluster_selection_method` from the default `eom` to `leaf` gave identical counts for each tested configuration. The four leaf runs reproduced the full topic result when evidence references were reversed.

| Fixture | Configuration | First theme | Second theme | Designated noise assigned to `-1` |
| --- | --- | --- | --- | --- |
| Frozen | Production defaults | Offline 8/8, 8/10 | Washing 8/8, 8/10 | 2/6 |
| Frozen | Frozen gate parameters | Offline 8/8, 8/11 | Washing 8/8, 8/10 | 1/6 |
| Holdout | Production defaults | Delay 8/8, 8/8 | Sound 8/8, 8/13 | 1/6 |
| Holdout | Frozen gate parameters | Delay 8/8, 8/9 | Sound 8/8, 8/12 | 1/6 |

Additional one-parameter probes used the frozen gate configuration as their baseline.

| Fixture | Changed parameter | First theme | Second theme | Designated noise assigned to `-1` |
| --- | --- | --- | --- | --- |
| Frozen | `min_samples=6` | 8/8, 8/10 | 8/8, 8/11 | 1/6 |
| Frozen | `min_samples=7` | 8/8, 8/10 | 8/8, 8/11 | 1/6 |
| Frozen | `min_samples=8` | 8/8, 8/10 | 7/8, 7/10 | 1/6 |
| Frozen | `n_neighbors=4` | 7/8, 7/9 | 8/8, 8/10 | 2/6 |
| Frozen | `n_neighbors=5` | 8/8, 8/11 | 8/8, 8/10 | 1/6 |
| Frozen | `n_neighbors=8` | 7/8, 7/10 | 8/8, 8/9 | 2/6 |
| Frozen | `n_components=3` | 8/8, 8/10 | 8/8, 8/10 | 2/6 |
| Holdout | `n_neighbors=4` | 8/8, 8/10 | 7/8, 7/11 | 0/6 |
| Holdout | `n_components=3` | 8/8, 8/9 | 8/8, 8/12 | 1/6 |

## Post-fit score inspection

The diagnostic captured HDBSCAN's `probabilities_` and `outlier_scores_` and aligned them with BERTopic's assignments in embedding-batch order. BERTopic preserved HDBSCAN's original `-1` labels. Three of the four cases contained a false assignment with membership 1.0 and GLOSH outlier score 0.0. The highest membership cutoff sampled was 0.90. Applying it to the existing labels reduced coverage for several themes while improving precision.

| Fixture | Configuration | First theme at membership ≥0.90 | Second theme at membership ≥0.90 | Designated noise assigned to `-1` |
| --- | --- | --- | --- | --- |
| Frozen | Production defaults | Offline 7/8, 7/7 | Washing 8/8, 8/8 | 6/6 |
| Frozen | Frozen gate parameters | Offline 6/8, 6/7 | Washing 7/8, 7/7 | 5/6 |
| Holdout | Production defaults | Delay 7/8, 7/7 | Sound 6/8, 6/8 | 4/6 |
| Holdout | Frozen gate parameters | Delay 6/8, 6/6 | Sound 6/8, 6/8 | 4/6 |

A separate post-fit probe normalized the source embeddings and averaged the unit vectors for each cluster's members with HDBSCAN probability of at least 0.95. It used all assigned members if fewer than two met that probability. A 0.60 cosine cutoff against the normalized mean retained all eight documents in each theme and sent all six designated noise documents to `-1` in the four evaluated cases.

The cutoff calculations operated on existing labels. They did not recompute keywords, run the full production flow with the resulting assignments, or validate cutoff selection on a third fixture. These scores remain exploratory. The Python audit reported zero non-loopback socket or DNS attempts for these runs.
