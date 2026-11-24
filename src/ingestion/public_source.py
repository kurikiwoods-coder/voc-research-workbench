"""P0-0 discovery sample. Search results only identify URLs; the post endpoint supplies the words."""

from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from itertools import chain, zip_longest
import re
from hashlib import sha256
from urllib.parse import urlsplit

from src.execution.transport import ENDPOINTS, network, number, outbound, redact
from src.raw_store.store import dump

SITE = "cooking"
DOMAIN = "cooking.stackexchange.com"
TOPIC = "measuring cups"
QUERY = "site:cooking.stackexchange.com/questions measuring cups sticky honey"
LICENSES = {
    f"CC BY-SA {v}": f"https://creativecommons.org/licenses/by-sa/{v}/" for v in ("2.5", "3.0", "4.0")
}
PUBLIC = {"public_approved"}
ENGINES = ("tavily", "brave", "forum_search")
POST_LIMIT = 4


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fragments = []

    def handle_data(self, data):
        self.fragments.append(data)


def post_id(url):
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    match = re.match(r"^/(?:questions|q)/([1-9]\d{0,11})(?:/|$)", parsed.path)
    if parsed.scheme == "https" and parsed.netloc == DOMAIN and match:
        return match[1]
    return None


def first_sentence(html):
    parser = PlainText()
    parser.feed(html)
    plain = " ".join("".join(parser.fragments).split())
    hit = re.search(r"^.{12,400}?[.!?](?:\s|$)", plain)
    return hit.group().strip() if hit else plain[:360]


def published_at(value):
    if type(value) is int:
        try:
            return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=value)).isoformat()
        except OverflowError:
            pass
    return None


def discover(settings, store, attempt, transport=network, *, engines=ENGINES):
    if (transport is network) == store.fixture:
        raise ValueError("在线传输和合成测试必须使用独立数据库")
    secrets = list(settings.keys.values())
    refs, errors = [], []
    candidates = {engine: [] for engine in ENGINES}
    for engine in engines:
        key = settings.keys.get(engine)
        if engine != "forum_search" and not key:
            errors.append(f"{engine} 未配置")
            refs.append(
                store.record(
                    attempt,
                    engine,
                    "configuration",
                    {"query": QUERY},
                    {"sent": False, "reason": "missing_key"},
                )
            )
            continue
        if engine == "tavily":
            params = {
                "query": QUERY,
                "search_depth": "basic",
                "include_domains": [DOMAIN],
                "max_results": 5,
                "include_answer": False,
                "include_usage": True,
            }
            reply = outbound(
                engine,
                labels=PUBLIC,
                method="POST",
                body=params,
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                transport=transport,
            )
        elif engine == "brave":
            params = {"q": QUERY, "count": 5}
            reply = outbound(
                engine,
                labels=PUBLIC,
                query=params,
                headers={"X-Subscription-Token": key},
                transport=transport,
            )
        else:
            params = {"site": SITE, "title": TOPIC, "sort": "votes", "order": "desc", "pagesize": 4}
            reply = outbound("forum_search", labels=PUBLIC, query=params, transport=transport)
        obj = reply.body if isinstance(reply.body, dict) else {}
        if engine == "brave":
            web = obj.get("web")
            listings = web.get("results") if isinstance(web, dict) else [] if obj.get("type") == "search" and web is None else None
        else:
            listings = obj.get("items" if engine == "forum_search" else "results")
        hits = []
        if reply.status == 200 and isinstance(listings, list):
            for item in listings:
                if not isinstance(item, dict):
                    continue
                link = item.get("url") or item.get("link")
                if ident := post_id(link):
                    hits.append(
                        {"id": ident, "url": link, "title": unescape(str(item.get("title", "")))[:240]}
                    )
                    candidates[engine].append(ident)
        extra = {}
        if engine == "tavily" or store.diagnostic:
            usage = obj.get("usage")
            extra.update({
                "result_list_valid": isinstance(listings, list),
                "result_count": len(listings) if isinstance(listings, list) else None,
                "credits": number(usage.get("credits")) if (
                    engine == "tavily" and reply.status == 200 and isinstance(usage, dict)
                ) else None,
            })
        if store.diagnostic:
            extra.update({
                "monthly_remaining": number(reply.monthly_remaining) if engine == "brave" else None,
                "monthly_limit": number(reply.monthly_limit) if engine == "brave" else None,
            })
        refs.append(
            store.record(
                attempt,
                engine,
                "live_http",
                {
                    "endpoint": ENDPOINTS[engine],
                    "method": "POST" if engine == "tavily" else "GET",
                    "parameters": params,
                },
                redact(
                    {
                        "hits": hits,
                        "response_sha256": sha256(dump(obj).encode()).hexdigest(),
                        "projection": "eligible URLs and titles, no search snippets",
                        "error": obj.get("error") or obj.get("error_message"),
                        "quota_remaining": obj.get("quota_remaining"),
                        **extra,
                    },
                    secrets,
                ),
                reply.status,
            )
        )
        if not hits:
            hint = f"（HTTP {reply.status}）" if reply.status else "（未收到响应）"
            errors.append(f"{engine} 未取得可核验链接{hint}")
    # Share the lookup budget across paid engines and reserve one lookup for an available forum fallback.
    external = (
        (engine, ident)
        for pair in zip_longest(candidates["tavily"], candidates["brave"])
        for engine, ident in zip(ENGINES[:2], pair)
        if ident
    )
    fallback = (("forum_search", ident) for ident in candidates["forum_search"])
    external_limit = POST_LIMIT - bool(candidates["forum_search"])
    tried = set()
    for engine, ident in chain(external, fallback):
        limit = POST_LIMIT if engine == "forum_search" else external_limit
        if ident in tried or len(tried) >= limit:
            continue
        tried.add(ident)
        params = {"site": SITE, "filter": "withbody"}
        reply = outbound("stackexchange", labels=PUBLIC, path=ident, query=params, transport=transport)
        obj = reply.body if isinstance(reply.body, dict) else {}
        items = obj.get("items")
        item = (
            items[0]
            if reply.status == 200 and isinstance(items, list) and items and isinstance(items[0], dict)
            else {}
        )
        license_name = item.get("content_license")
        quote = first_sentence(item.get("body", "")) if isinstance(item.get("body"), str) else ""
        original = item.get("link")
        owner = item.get("owner")
        display_name = owner.get("display_name") if isinstance(owner, dict) else None
        author = unescape(display_name).strip() if isinstance(display_name, str) else ""
        date = published_at(item.get("creation_date"))
        source_matches = post_id(original) == ident and str(item.get("question_id")) == ident
        permitted = source_matches and isinstance(license_name, str) and license_name in LICENSES
        verified = (
            permitted
            and bool(quote and author)
            and date is not None
            and redact(quote, secrets) == quote
        )
        citation = {
            "search": engine,
            "post_id": ident,
            "url": original,
            "text": quote,
            "author": author,
            "license": license_name,
            "license_url": LICENSES.get(license_name) if verified else None,
            "method": "Stack Exchange API /questions/{id}",
            "published_at": date,
            "last_activity_epoch": item.get("last_activity_date"),
            "verified": verified,
            "role": "public_connectivity_sample",
            "research_denominator": 0,
        }
        citation.update(
            response_sha256=sha256(dump(obj).encode()).hexdigest(),
            source_policy="SE-public-API-CC-BY-SA-v1",
            terms_url="https://stackoverflow.com/legal/api-terms-of-use",
            permitted_fields=["source URL", "author attribution", "licensed excerpt", "timestamps"],
            retention="local connectivity evidence; remove the local batch database at end of study",
        )
        ref = store.record(
            attempt,
            "forum_post",
            "live_http",
            {
                "endpoint": ENDPOINTS["stackexchange"] + ident,
                "method": "GET",
                "question_id": ident,
                **params,
            },
            redact(
                citation if verified else {
                    "verified": False, "error": obj.get("error_message") or obj.get("error"),
                    **({
                        "content_received": source_matches,
                        "license_recognized": permitted,
                        "excerpt_confirmed": False,
                    } if store.diagnostic else {}),
                }, secrets
            ),
            reply.status,
        )
        refs.append(ref)
        if verified:
            return citation, refs, engine in {"tavily", "brave"}, errors
        status = f"HTTP {reply.status}" if reply.status else "未收到响应"
        errors.append(f"原帖 {ident} 未核验（{status}）")
    return None, refs, False, errors
