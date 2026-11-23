# L4 Execution (执行层 · P0-2 — Jev, mandatory)

- `jev_client.py` — Jev client, model locked to `jev-1.14.0` (never `jev-latest`). Choice / Score / Noul only; Box excluded. Every Choice carries a None option plus a Noul gate "是否属于现有意图清单". Full probability distributions are stored, never top-1 only.
- `gold_standard.py` — 100–200 human-labelled gold-standard records; Chinese calibrated separately.
- `token_center.py` — Token Center: balance bar, X-Tokens-Remaining sync, batch estimates, budget gates, purchase redirect. Keys live in server env / secret store only.

CX internal complaints NEVER enter Jev (PDT v1.2 §6.9). Status: design + interface definitions only. Not yet implemented.
