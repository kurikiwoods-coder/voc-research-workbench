# L3 Discovery (发现层 · P0-1)

Proposes new-intent candidates from unlabelled raw material.

- `bertopic.py` — BERTopic clustering (clusters are not intents).
- `topicgpt.py` — TopicGPT four steps: generate → refine → assign with quote → correct.
- `open_coding.py` — open coding drafts candidate intents (name, definition, inclusion/exclusion, triggering quotes, difference from existing intents).
- `residual_queue.py` — IntentGPT residual mechanism: known intents are recalled first (KNN / Jev), residuals + low-confidence items feed the candidate pool; human confirmation writes to the registry.

Status: design + interface definitions only. Not yet implemented (PDT v1.2 §7).
