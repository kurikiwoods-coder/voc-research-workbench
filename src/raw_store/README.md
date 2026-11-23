# L2 Raw Store (原始层)

Original text, links, publication dates and engagement numbers land unchanged and are never overwritten. Any analysis step can re-run from the raw store.

- `store.py` — unified-table records (see schemas/unified-table.schema.json).
- `snapshot.py` — snapshot management: once collected, analysis uses the snapshot, never the live source.
- `dedupe.py` — cross-link repost / duplicate-comment grouping (dedupe_group).

Status: design + interface definitions only. Not yet implemented (PDT v1.2 §5).
