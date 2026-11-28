# L3 Discovery (发现层 · P0-1)

Proposes new-intent candidates from unlabelled raw material.

- `topics.py` — local BERTopic candidate topics from M09-A embeddings.
- `topicgpt.py` — TopicGPT four steps: generate → refine → assign with quote → correct.
- `open_coding.py` — open coding drafts candidate intents (name, definition, inclusion/exclusion, triggering quotes, difference from existing intents).
- `residual_queue.py` — IntentGPT residual mechanism: known intents are recalled first (KNN / Jev), residuals + low-confidence items feed the candidate pool; human confirmation writes to the registry.

M09-A implements the isolated embedding path in `embedding_inputs.py`, `embedding_backend.py`, and
`embeddings.py`. See the [M09-A run and handover contract](../../docs/evidence/m09-a/README.md).
M09-B adds `cluster_offline` with ordered document assignments, noise labels,
c-TF-IDF keywords and versioned runtime metadata. See the [M09-B evidence and
handover](../../docs/evidence/m09-b/README.md).

M09-C provides the local TopicRuns service for immutable topic runs, membership and
diagnostics, requalified evidence reads, offline recomputation and comparison.
The SQLite topic database lives beside the source workspace. See the [M09-C
contract and acceptance evidence](../../docs/evidence/m09-c/README.md).
