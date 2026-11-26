"""Build M03-bound acquisition plans and run the fixed offline M08 fixtures."""

from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from src.config import SEARCH_KEYS
from src.execution.transport import ENDPOINTS, Response, redact
from src.ingestion.m08_retrieval import NORMALIZATION_VERSION, UnsafeUrl, normalize_url, retrieve_stackexchange
from src.ingestion.m08_search import preview_queries, search
from src.ingestion.public_source import DOMAIN
from src.raw_store.denominators import EARLY, ELIGIBLE, EXTRACTED, PUBLISHED
from src.raw_store.store import SQLITE_TIMEOUT, dump


POLICY_VERSION = "m08-source-policy-v1"
OFFLINE_DOMAINS = (DOMAIN,)
FORMAL_COLLECTION = {
    "enabled": False, "gate": "BLOCKED",
    "reason": "正式采集待来源审批与 G-1 同批验收。当前仅开放本机合成演示。",
}
STAGES = (*EARLY, EXTRACTED, ELIGIBLE, PUBLISHED)
OPERATIONS = ("discover", "access", "store", "research", "transmit")
PERMISSION_STATES = {
    "approved", "unknown", "restricted", "expired", "revoked", "background_only", "internal",
}
QUESTION = f"https://{DOMAIN}/questions/9876543201/synthetic-sample"
UNAVAILABLE = f"https://{DOMAIN}/questions/9876543202/synthetic-unavailable"
DEMO_QUERY = {
    "research_object": "虚构产品 Alpha", "research_goal": "演示来源发现和访问回执",
    "keywords": ["synthetic product experience"], "include_terms": [], "exclude_terms": [],
}
RETENTION_DAYS = 30
RETENTION_ROWS = 100
FIXTURE_KEYS = {provider: f"m08-offline-fixture-{provider}" for provider in SEARCH_KEYS}


@dataclass(frozen=True)
class Source:
    provider: str
    source_type: str
    fixture_operation: str
    usage_unit: str
    license_reference: str | None = None
    attribution_requirement: str | None = None

    def view(self, keys):
        return {
            "source_id": f"m08-{self.provider}", "provider": self.provider,
            "source_type": self.source_type, "adapter_version": "m08-v1",
            "credential_reference": SEARCH_KEYS.get(self.provider),
            "credential_configured": bool(keys.get(self.provider)) if self.provider in SEARCH_KEYS else None,
            "capability_status": "offline_fixture", "permission_status": "unknown",
            "permissions": dict.fromkeys(OPERATIONS, "unknown"),
            "allowed_operations": [self.fixture_operation], "allowed_domains": list(OFFLINE_DOMAINS),
            "retention_policy": f"仅保留本机演示回执，下一次写入清理超过 {RETENTION_DAYS} 天的记录",
            "license_reference": self.license_reference,
            "attribution_requirement": self.attribution_requirement,
            "deletion_policy": f"最多保留最新 {RETENTION_ROWS} 次演示，可删除隔离账本",
            "rate_limit": "每个搜索器最多一次模拟请求，逐个规范 URL 模拟回源",
            "usage_unit": self.usage_unit, "enabled_status": "offline_fixture",
        }


SOURCES = (
    Source("tavily", "search", "discover", "credit"),
    Source("brave", "search", "discover", "request"),
    Source("stackexchange", "public_forum", "access", "request",
           "https://stackoverflow.com/legal/api-terms-of-use", "原作者、来源链接及适用许可"),
)


class PlanError(ValueError):
    """A plan conflicts with its frozen scope or the offline policy."""


def source_catalog(keys):
    return {
        "policy_version": POLICY_VERSION, "sources": [source.view(keys) for source in SOURCES],
        "offline_domains": list(OFFLINE_DOMAINS), "formal_collection": FORMAL_COLLECTION,
    }


def permitted(permissions, operation):
    """No capability, visibility, or permission carries across operations."""
    status = permissions.get(operation)
    return operation in OPERATIONS and status in PERMISSION_STATES and status == "approved"


def build_plan(studies, study_id, data):
    scope = studies.get_scope(study_id, data["scope_id"])
    if not scope["frozen_at"] or data["scope_version"] != scope["scope_version"]:
        raise PlanError("请选择确切的已冻结范围版本。")
    category = data["product_category_id"]
    if category and category not in scope["product_category_ids"]:
        raise PlanError("所选品类不属于该冻结范围。")
    if any(domain not in OFFLINE_DOMAINS for domain in data["allowed_domains"]):
        raise PlanError("当前离线演示仅支持工作台列出的来源域名。")
    window = scope["date_window"]
    start = data["date_from"] or window.get("start")
    end = data["date_to"] or window.get("end")
    if ((start and window.get("start") and start < window["start"])
            or (end and window.get("end") and end > window["end"])
            or (start and end and start > end)):
        raise PlanError("查询日期须在冻结范围的时间窗内。")
    if data["data_class"] != "synthetic":
        raise PlanError("离线演示仅接受纯合成查询。")
    plan = {
        **data, "study_id": study_id, "frozen_at": scope["frozen_at"],
        "date_from": start, "date_to": end, "policy_version": POLICY_VERSION,
        "budget": {"real_requests": 0, "simulated_search_requests": len(data["providers"])},
    }
    if redact(plan) != plan:
        raise PlanError("请移除查询中的敏感内容。")
    return plan


def preview(studies, study_id, data):
    plan = build_plan(studies, study_id, data)
    return {
        "plan": plan, "queries": preview_queries(plan, providers=plan["providers"], limit=plan["limit"]),
        "mode": "offline_fixture", "formal_collection": FORMAL_COLLECTION,
    }


def _search_fixture(method, url, request, headers):
    if method == "POST" and url == ENDPOINTS["tavily"]:
        return Response(200, {"results": [{"url": QUESTION}, {"url": UNAVAILABLE}], "usage": {"credits": 1}})
    if method == "GET" and url.startswith(ENDPOINTS["brave"] + "?"):
        return Response(200, {"web": {"results": [{"url": QUESTION.replace(DOMAIN, DOMAIN.upper())}]}})
    raise ValueError("Unknown synthetic search route")


def _forum_fixture(method, url, request, headers, *, published):
    endpoint = ENDPOINTS["stackexchange"] + "9876543201?"
    if method == "GET" and url.startswith(endpoint):
        return Response(200, {"items": [{
            "question_id": 9876543201, "link": QUESTION,
            "body": "<p>Synthetic sample for the acquisition rehearsal.</p>",
            "content_license": "CC BY-SA 4.0",
            "owner": {"display_name": "Synthetic fixture"}, "creation_date": published,
        }]})
    return Response(404, {})


def _normalize(hit, domains):
    try:
        return normalize_url(hit["url"], domains)
    except UnsafeUrl:
        return None


def demo(studies, study_id, data, directory):
    result = preview(studies, study_id, {**data, **DEMO_QUERY})
    if studies.get(study_id)["status"] == "archived":
        raise PlanError("已归档项目不能运行新的离线演示。")
    plan = result["plan"]
    domains = plan["allowed_domains"]
    found = search(
        SimpleNamespace(keys=FIXTURE_KEYS), plan, mode=plan["mode"], providers=plan["providers"],
        labels={"public_approved"}, limit=plan["limit"], transport=_search_fixture,
        eligible=lambda hit: bool(_normalize(hit, domains)),
    )
    discoveries = []
    for attempt in found["attempts"]:
        query = attempt["request"]["parameters"].get("query") or attempt["request"]["parameters"]["q"]
        for hit in attempt.pop("hits"):
            canonical = _normalize(hit, domains)
            if canonical:
                discoveries.append({
                    "receipt_id": str(uuid4()), "provider": hit["provider"],
                    "rank": hit["rank"], "query": query, "original_url": hit["url"],
                    "canonical_url": canonical, "discovered_at": hit["discovered_at"],
                    "normalization_version": NORMALIZATION_VERSION,
                })
    counts = Counter(item["canonical_url"] for item in discoveries)
    representatives = {item["canonical_url"]: item["original_url"] for item in reversed(discoveries)}
    fixture_day = date.fromisoformat(plan["date_from"] or plan["date_to"] or "2023-11-14")
    published = int(datetime.combine(fixture_day, time.min, timezone.utc).timestamp())
    pages = [retrieve_stackexchange(
        representatives[canonical], allowed_domains=domains, access_status="approved",
        excerpt_status="pending",
        transport=lambda *args: _forum_fixture(*args, published=published),
    ) for canonical in counts]
    complete = all(attempt["error"] is None for attempt in found["attempts"])
    result.update(
        attempts=found["attempts"], discoveries=discoveries, pages=pages,
        urls=[{"canonical_url": url, "discovery_count": count} for url, count in counts.items()],
        engineering_funnel={
            **dict.fromkeys(STAGES),
            EARLY[0]: len(counts) if complete else None,
            EARLY[1]: sum(page["accessible"] for page in pages) if complete else None,
        },
        formal_funnel=dict.fromkeys(STAGES), real_api_calls=0,
        formal_funnel_reason="formal_ledger_unavailable",
        receipt_id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_receipt(directory, result)
    return result


def save_receipt(directory, result):
    """Persist the complete rehearsal atomically in an isolated, bounded ledger."""
    path = directory / "m08-offline"
    path.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path / "acquisition.sqlite3", timeout=SQLITE_TIMEOUT)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            db.execute("""CREATE TABLE receipts (
                receipt_id TEXT PRIMARY KEY NOT NULL, study_id TEXT NOT NULL, scope_id TEXT NOT NULL,
                scope_version TEXT NOT NULL, created_at TEXT NOT NULL,
                payload TEXT NOT NULL CHECK(json_valid(payload))
            ) STRICT""")
            db.execute("PRAGMA user_version=1")
        elif version != 1:
            raise sqlite3.DatabaseError("Unsupported M08 offline ledger version")
        plan = result["plan"]
        db.execute(
            "INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?)",
            (result["receipt_id"], plan["study_id"], plan["scope_id"], plan["scope_version"],
             result["created_at"], dump(result)),
        )
        cutoff = datetime.fromisoformat(result["created_at"]) - timedelta(days=RETENTION_DAYS)
        db.execute("DELETE FROM receipts WHERE created_at < ?", (cutoff.isoformat(),))
        db.execute("""DELETE FROM receipts WHERE receipt_id IN (
            SELECT receipt_id FROM receipts ORDER BY created_at DESC, receipt_id DESC LIMIT -1 OFFSET ?
        )""", (RETENTION_ROWS,))
