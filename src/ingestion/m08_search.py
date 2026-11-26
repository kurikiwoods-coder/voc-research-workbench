"""Offline URL discovery for M08 using the registered search endpoints."""

from datetime import date, datetime, timezone
from html import unescape
from http.client import HTTPException
import re

from src.execution.transport import ENDPOINTS, Denied, Response, failure, network, number, outbound, redact

PROVIDERS = ("tavily", "brave")
MAX_RESULTS = {"tavily": 20, "brave": 20}
COUNTRY_NAMES = {
    "AR": "argentina", "AU": "australia", "AT": "austria", "BE": "belgium",
    "BR": "brazil", "CA": "canada", "CL": "chile", "CN": "china",
    "DK": "denmark", "FI": "finland", "FR": "france", "DE": "germany",
    "GR": "greece", "HK": "hong kong", "IN": "india", "ID": "indonesia",
    "IT": "italy", "JP": "japan", "KR": "south korea", "MY": "malaysia",
    "MX": "mexico", "NL": "netherlands", "NZ": "new zealand", "NO": "norway",
    "PH": "philippines", "PL": "poland", "PT": "portugal", "RU": "russia",
    "SA": "saudi arabia", "SG": "singapore", "ZA": "south africa", "ES": "spain",
    "SE": "sweden", "CH": "switzerland", "TW": "taiwan", "TR": "turkey",
    "GB": "united kingdom", "US": "united states",
}
BRAVE_COUNTRY_CODES = frozenset(COUNTRY_NAMES) - {"GR", "SG"} | {"ALL"}
BRAVE_LANGUAGE_CODES = frozenset(
    "ar bg bn ca cs da de el en en-gb es et eu fi fr gl gu he hi hr hu is it ja jp kn ko lv lt "
    "ml mr ms nb nl pa pl pt-br pt-pt ro ru sk sl sr sv ta te th tr uk vi zh-hans zh-hant".split()
)
BRAVE_LANGUAGE_ALIASES = {"zh": "zh-hans", "zh-cn": "zh-hans", "zh-tw": "zh-hant"}
DOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z0-9-]+", re.ASCII)
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
FALLBACK_ERRORS = frozenset({"offline", "rate_limited", "quota_exhausted", "insufficient_balance", "upstream_error",
                             "invalid_schema", "no_valid_urls"})
TAVILY_BASIC_COST_USD = "0.008"
BRAVE_WEB_COST_USD = "0.005"


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _phrase(term):
    return '"' + term.replace('"', ' ').replace('\\', ' ').strip() + '"'


def _terms(query, key):
    value = query.get(key, [])
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(term, str) or not term.strip() or any(ord(char) < 32 for char in term)
        for term in value
    ):
        raise ValueError("Invalid discovery search terms")
    return [term.strip() for term in value]


def _date(query, key):
    value = query.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not DATE.fullmatch(value):
        raise ValueError("Search dates must use YYYY-MM-DD")
    return date.fromisoformat(value).isoformat()


def _query_parameters(provider, query, limit):
    keywords = _terms(query, "keywords")
    include = _terms(query, "include_terms")
    exclude = _terms(query, "exclude_terms")
    domains = [domain.lower() for domain in _terms(query, "allowed_domains")]
    if not keywords or any(not DOMAIN.fullmatch(domain) for domain in domains):
        raise ValueError("Search requires keywords and bare allowlisted hostnames")
    language, country = query.get("language") or "", query.get("country") or ""
    if not all(isinstance(text, str) for text in (language, country)):
        raise ValueError("Invalid search locale")
    language, country = language.strip().lower(), country.strip()
    date_from, date_to = _date(query, "date_from"), _date(query, "date_to")
    if date_from and date_to and date_from > date_to:
        raise ValueError("Search date window is reversed")
    unsupported, notes = [], {}
    maximum = MAX_RESULTS[provider]
    if limit > maximum:
        notes["limit"] = f"provider_maximum_{maximum}"
    count = min(limit, maximum)
    terms = [_phrase(term) for term in keywords]
    if provider == "tavily":
        params = {
            "query": " ".join([*keywords, *(_phrase(term) for term in include)]),
            "topic": "general", "search_depth": "basic", "max_results": count,
            "auto_parameters": False, "include_answer": False, "include_raw_content": False,
            "include_images": False, "include_usage": True,
        }
        if include:
            params["exact_match"] = True
        if exclude:
            unsupported.append("exclude_terms")
        if domains:
            if len(domains) > 300:
                raise ValueError("Tavily supports at most 300 included domains")
            params.update(include_domains=domains, include_domains_mode="restrict")
        if language:
            params.update(language=language, filter_by_language=True)
        if country:
            name = COUNTRY_NAMES.get(country.upper())
            if name and name != "hong kong":
                params["country"] = name
                notes["country"] = "ranking_boost_only"
            else:
                unsupported.append("country")
        if date_from or date_to:
            params["filter_by_published_date"] = True
        if date_from:
            params["start_date"] = date_from
        if date_to:
            params["end_date"] = date_to
        if len(params["query"]) > 400:
            notes["query"] = "query_too_long"
        return params, unsupported, notes

    terms.extend(_phrase(term) for term in include)
    terms.extend("-" + _phrase(term) for term in exclude)
    if domains:
        terms.append(" OR ".join("site:" + domain for domain in domains))
        if len(domains) > 1:
            notes["allowed_domains"] = "provider_site_operators_and_local_filter"
    params = {"q": " ".join(terms), "count": count, "result_filter": "web", "spellcheck": "false",
              "text_decorations": "false", "extra_snippets": "false", "operators": "true",
              "operators_fallback": "false"}
    if country:
        code = country.upper()
        if code in BRAVE_COUNTRY_CODES:
            params["country"] = code
        else:
            unsupported.append("country")
    if language:
        code = BRAVE_LANGUAGE_ALIASES.get(language, language)
        if code in BRAVE_LANGUAGE_CODES:
            params["search_lang"] = code
        else:
            unsupported.append("language")
    if date_from and date_to:
        params["freshness"] = date_from + "to" + date_to
        notes["freshness"] = "indexed_page_age_may_use_modification_date"
    elif date_from or date_to:
        unsupported.append("date_from" if date_from else "date_to")
    if len(params["q"]) > 600 or len(params["q"].split()) > 75:
        notes["query"] = "query_too_long"
    return params, unsupported, notes


def _result_list(provider, body):
    if provider == "tavily":
        return body.get("results")
    web = body.get("web")
    if isinstance(web, dict):
        return web.get("results")
    if web is None and body.get("type") == "search":
        return []
    return None


def _hits(provider, rows, limit, discovered_at, secrets):
    hits = []
    for rank, item in enumerate(rows[:limit], start=1):
        if not isinstance(item, dict):
            continue
        url, title = item.get("url"), item.get("title")
        if not isinstance(url, str) or not url.strip() or redact(url, secrets) != url:
            continue
        hits.append({
            "provider": provider, "rank": rank, "url": url,
            "title": redact(unescape(title), secrets)[:240] if isinstance(title, str) else "",
            "discovered_at": discovered_at,
        })
    return hits


def _usage(provider, reply, sent):
    body = reply.body if isinstance(reply.body, dict) else {}
    usage = body.get("usage")
    tavily = provider == "tavily"
    reported = number(usage.get("credits")) if tavily and isinstance(usage, dict) and reply.status == 200 else None
    remaining = number(reply.monthly_remaining) if not tavily and reply.status in (200, 429) else None
    quota_limit = number(reply.monthly_limit) if not tavily and reply.status in (200, 429) else None
    if quota_limit is None or remaining is None or remaining > quota_limit:
        remaining, quota_limit = None, None
    if not sent:
        cost, basis = None, None
    elif tavily:
        cost = TAVILY_BASIC_COST_USD
        basis = "Tavily Pay As You Go list price for one basic-search credit before plan allowances"
    else:
        cost = BRAVE_WEB_COST_USD
        basis = "Brave Search list price for one Web Search request before plan allowances"
    return {
        "unit": "credit" if tavily else "request",
        "actual_requests": 0, "simulated_requests": int(sent),
        "reported_usage": reported, "estimated_usage": 1 if sent else None,
        "actual_cost": None, "estimated_cost": cost, "estimated_cost_basis": basis,
        "cost_currency": "USD" if cost is not None else None,
        "remaining": remaining, "quota_limit": quota_limit,
        "balance_status": "fixture_reported" if remaining is not None else "unsynced",
    }


def _provider_error(provider, reply):
    if reply.status in (400, 422):
        return "invalid_request"
    if provider == "tavily":
        if reply.status in (432, 433):
            return "quota_exhausted"
        if reply.status == 434:
            return "upstream_error"
    if provider == "brave" and reply.status == 429 and isinstance(reply.body, dict):
        detail = reply.body.get("error")
        if isinstance(detail, dict) and detail.get("code") == "QUOTA_LIMITED":
            return "quota_exhausted"
    return failure(reply.status)


def preview_queries(query, *, providers, limit):
    """Build the provider request plan without loading credentials or sending requests."""
    if type(limit) is not int or limit < 1:
        raise ValueError("Search limit must be a positive integer")
    plans = []
    for provider in providers:
        if provider not in PROVIDERS:
            raise ValueError("Unknown search provider")
        params, unsupported, notes = _query_parameters(provider, query, limit)
        plans.append({
            "provider": provider,
            "request": {"endpoint": ENDPOINTS[provider], "method": "POST" if provider == "tavily" else "GET",
                        "parameters": params},
            "unsupported_filters": unsupported, "filter_notes": notes,
        })
    return plans


def _attempt(settings, plan, limit, labels, transport, secrets, clock):
    provider, request = plan["provider"], plan["request"]
    params = request["parameters"]
    if redact(params, secrets) != params:
        raise Denied("Search parameters contain restricted data")
    key = settings.keys.get(provider)
    sent, error = False, None
    reply = Response(None, None)
    if not key:
        error = "missing_key"
    elif plan["filter_notes"].get("query") == "query_too_long":
        error = "query_too_long"
    else:
        sent = True
        try:
            if provider == "tavily":
                reply = outbound(provider, labels=labels, method="POST", body=params,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                                 transport=transport)
            else:
                reply = outbound(provider, labels=labels, query=params,
                                 headers={"X-Subscription-Token": key}, transport=transport)
        except (TimeoutError, OSError, HTTPException):
            error = "offline"
    hits, result_count = [], None
    if sent and error is None:
        if not isinstance(reply, Response) or (
            reply.status is not None and (type(reply.status) is not int or not 100 <= reply.status < 600)
        ):
            reply, error = Response(None, None), "invalid_schema"
        elif reply.status != 200:
            error = _provider_error(provider, reply)
        else:
            body = reply.body if isinstance(reply.body, dict) else {}
            listings = _result_list(provider, body)
            if not isinstance(listings, list):
                error = "invalid_schema"
            else:
                result_count = len(listings)
                hits = _hits(provider, listings, min(limit, MAX_RESULTS[provider]), clock(), secrets)
                if listings and not hits:
                    error = "no_valid_urls"
    retry_after = reply.retry_after
    return {
        **plan, "endpoint": request["endpoint"], "method": request["method"],
        "sent": sent, "status": reply.status, "error": error, "result_count": result_count,
        "retry_after": retry_after if isinstance(retry_after, str) and redact(retry_after, secrets) == retry_after else None,
        "usage": _usage(provider, reply, sent), "hits": hits,
    }


def search(settings, query, *, mode, providers, labels, limit, transport, eligible=None, clock=_utc_now):
    """Run each selected provider once through a caller-supplied offline fixture."""
    if transport is network or not callable(transport):
        raise Denied("M08 search requires an offline fixture transport")
    labels = frozenset(labels)
    if labels != {"public_approved"}:
        raise Denied("Search accepts only approved public input")
    providers = tuple(providers)
    if mode not in ("independent", "merge", "fallback") or len(providers) != (1 if mode == "independent" else 2):
        raise ValueError("Invalid search mode or provider count")
    if any(provider not in PROVIDERS for provider in providers) or len(set(providers)) != len(providers):
        raise ValueError("Unknown or duplicate search provider")
    secrets = tuple(key for key in settings.keys.values() if key)
    attempts, hits = [], []
    for plan in preview_queries(query, providers=providers, limit=limit):
        attempt = _attempt(settings, plan, limit, labels, transport, secrets, clock)
        attempts.append(attempt)
        hits.extend(hit for hit in attempt["hits"] if eligible is None or eligible(hit))
        if mode == "fallback" and attempt["error"] not in FALLBACK_ERRORS:
            break
    return {"mode": mode, "attempts": attempts, "hits": hits}
