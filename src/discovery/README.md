# L3 Discovery (发现层 · P0-1)

Proposes new-intent candidates from unlabelled raw material.

- `bertopic.py` — BERTopic clustering (clusters are not intents).
- `topicgpt.py` — TopicGPT four steps: generate → refine → assign with quote → correct.
- `open_coding.py` — open coding drafts candidate intents (name, definition, inclusion/exclusion, triggering quotes, difference from existing intents).
- `residual_queue.py` — IntentGPT residual mechanism: known intents are recalled first (KNN / Jev), residuals + low-confidence items feed the candidate pool; human confirmation writes to the registry.

M09-A implements the isolated embedding path in `embedding_inputs.py`, `embedding_backend.py`, and
`embeddings.py`. See the [M09-A run and handover contract](../../docs/evidence/m09-a/README.md).
BERTopic clustering starts with M09-B.
