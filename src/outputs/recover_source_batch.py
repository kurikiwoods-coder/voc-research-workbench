"""Recover the reviewed P0-0 source batch without replaying its Tavily search."""

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from src.config import ROOT, Settings
from src.execution.transport import network
from src.ingestion.public_source import fetch_forum_post, post_id
from src.outputs.audit_receipt import fingerprint, verify
from src.raw_store.store import Busy, Store

RECEIPT_PATH = Path("docs/evidence/p0-0/tavily-live")
RECEIPT_SHA256 = "c9381f28e8b494993327b30b6dd0df5aa29241aba87ee78d47409296142ecec8"


def restore_public_source_batch(settings, store, folder=ROOT / RECEIPT_PATH, *, transport=network):
    """Recover C0-3 from the shipped archive after checking the actual source again."""
    if store.diagnostic or (transport is network) == store.fixture:
        raise ValueError("归档恢复须使用匹配的独立数据库和传输方式。")

    folder = Path(folder)
    verified = verify(folder)
    receipt = json.loads((folder / "run.json").read_text("utf-8"))
    if verified["receipt_sha256"] != RECEIPT_SHA256 or fingerprint(receipt) != RECEIPT_SHA256:
        raise ValueError("归档与仓库锁定的可信凭据摘要不符。")
    run = receipt["run"]
    if (
        run["state"] != "paused"
        or verified["checks"].get("C0-3") != "PASS"
        or verified["checks"].get("G-1") != "BLOCKED"
        or receipt["usage_ledger"]
        or any(row["name"] == "jev_shard" for row in receipt["evidence"])
    ):
        raise ValueError("仅可恢复已通过 C0-3 且尚未发送 Jev 分片的暂停批次。")

    c03 = next(check for check in receipt["checks"] if check["requirement_id"] == "C0-3")
    refs = {
        row["name"]: row for row in receipt["evidence"]
        if row["id"] in c03["evidence"] and row["mode"] == "live_http" and row["status_code"] == 200
    }
    search, source = refs.get("tavily"), refs.get("forum_post")
    if not search or not source or search["attempt_id"] != source["attempt_id"]:
        raise ValueError("该批缺少同次 Tavily 搜索和原帖证据。")
    original = source["response"]
    ident = original["post_id"]
    if (
        post_id(original["url"]) != ident
        or original["search"] != "tavily"
        or not original["verified"]
        or not any(
            hit["id"] == ident and post_id(hit["url"]) == ident for hit in search["response"]["hits"]
        )
    ):
        raise ValueError("归档的回源编号与搜索命中不符。")

    with store.writer():
        if store.one("SELECT id FROM runs WHERE id=?", (run["id"],)):
            return {"run_id": run["id"], "status": "ALREADY_PRESENT", "tavily_requests": 0}
        status, request, citation = fetch_forum_post(
            ident, "tavily", secrets=list(settings.keys.values()), transport=transport
        )
        if status != 200 or not citation["verified"]:
            raise ValueError(f"公开原帖未完成许可回源核验（HTTP {status or '无响应'}）。")
        if (
            citation["license"] != original["license"]
            or citation["published_at"] != original["published_at"]
            or sha256(citation["text"].encode()).hexdigest() != original["quote_utf8_sha256"]
        ):
            raise ValueError("公开原帖的许可、发布日期或摘录已变化，恢复已停止。")
        account_tag = Settings(store.directory, provider=run["provider"]).account_tag()
        proof_id = store.restore_search_batch(
            run, account_tag, search, request, citation,
            {
                "archive_path": RECEIPT_PATH.as_posix(),
                "receipt_sha256": RECEIPT_SHA256,
                "original_run_id": run["id"],
                "archived_search_id": search["id"],
                "archived_post_id": source["id"],
                "archived_quote_sha256": original["quote_utf8_sha256"],
            },
        )
    return {
        "run_id": run["id"], "status": "RESTORED", "gate": "BLOCKED",
        "evidence_id": proof_id, "tavily_requests": 0,
    }


if __name__ == "__main__":
    try:
        settings = Settings.load()
        result = restore_public_source_batch(settings, Store(settings.directory))
    except (Busy, OSError, sqlite3.Error):
        raise SystemExit("恢复失败。请确认本机归档可读、数据目录可用且没有批次正在运行。") from None
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))
