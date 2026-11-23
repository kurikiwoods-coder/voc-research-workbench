# L1 Ingestion (采集层)

One adapter per source; a failure in one adapter never blocks the others or the CSV path.

- `tavily.py`, `brave.py` — dual search discovery (Tavily + Brave). Search finds URLs only; summaries are clues, never user voice.
- `youtube.py` — YouTube Data API commentThreads / replies.
- `forum.py` — licensed forum / Discourse adapters; never bypass login walls.
- `reddit_adapter.py` — Reddit backup adapter (Dialog MCP; Arctic Shift archive as fallback). Snapshot-only: quote + URL + date + counts land in the raw store at collection time.
- `csv_import.py` — manual CSV import; minimum fields raw_text, source_type, published_at, source_url.

Status: design + interface definitions only. Not yet implemented (PDT v1.2 §5, §12.1).
