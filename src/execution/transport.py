"""One outbound boundary for every connector, with an auditable offline drill."""

from dataclasses import dataclass
from http.client import HTTPException as HTTPProtocolError
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from src.config import PACKYCODE_LIVE_BLOCK, PROVIDERS
from src.edition_policy import legacy_execution_allowed

ENDPOINTS = {
    **{name: config[0] for name, config in PROVIDERS.items()},
    "tavily": "https://api.tavily.com/search",
    "brave": "https://api.search.brave.com/res/v1/web/search",
    "stackexchange": "https://api.stackexchange.com/2.3/questions/",
    "forum_search": "https://api.stackexchange.com/2.3/search/advanced",
}


@dataclass(frozen=True)
class Response:
    status: int | None
    body: object
    remaining: int | None = None
    retry_after: str | None = None
    monthly_remaining: int | None = None
    monthly_limit: int | None = None


class Denied(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def number(value):
    if type(value) is int and 0 <= value <= 2**63 - 1:
        return value
    return None


def finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite JSON number")
    return result


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {
            redact(str(k), secrets): redact(v, secrets)
            for k, v in value.items()
            if str(k).lower()
            not in {
                "authorization",
                "x-subscription-token",
                "api_key",
                "access_token",
                "email",
                "access-token",
                "cookie",
                "set-cookie",
                "api-key",
                "x-api-key",
                "token",
            }
        }
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[REDACTED]", value)
    return value


def brave_monthly_quota(headers):
    def integers(header):
        return [int(v.strip()) if re.fullmatch(r"\d{1,18}", v.strip()) else None
                for v in headers.get(header, "").split(",")]

    limits = integers("X-RateLimit-Limit")
    remaining = integers("X-RateLimit-Remaining")
    policies = headers.get("X-RateLimit-Policy", "").split(",")
    if len(policies) != len(remaining) or len(limits) != len(remaining):
        return None, None
    for policy, limit, left in zip(policies, limits, remaining):
        if re.fullmatch(r"\s*\d{1,18}\s*;\s*w=2592000\s*", policy) and limit and left is not None and left <= limit:
            return left, limit
    return None, None


def network(method, url, body, headers):
    if not legacy_execution_allowed(environment=os.environ):
        raise Denied("此运行模式尚未开放真实供应商传输。")
    data = json.dumps(body).encode() if body is not None else None
    req = Request(
        url,
        data=data,
        method=method,
        headers={
            **headers,
            "Accept": "application/json",
            "User-Agent": "VOC-Connectivity/1.0 (public API verification)",
        },
    )
    try:
        try:
            response = build_opener(NoRedirect()).open(req, timeout=12)
        except HTTPError as exc:
            response = exc
        with response:
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                return Response(response.status, {"error": "response_too_large"})
            try:
                obj = json.loads(data, parse_float=finite_float, parse_constant=finite_float)
            except (ValueError, UnicodeError):
                obj = {"error": "non_json_response"}
            header = response.headers.get("X-Tokens-Remaining", "")
            remaining = int(header) if re.fullmatch(r"\d{1,18}", header) else None
            monthly = brave_monthly_quota(response.headers) if urlsplit(url).hostname == "api.search.brave.com" else (None, None)
            return Response(response.status, obj, remaining, response.headers.get("Retry-After"), *monthly)
    except (URLError, TimeoutError, ConnectionError, OSError, HTTPProtocolError):
        return Response(None, {"error": "connection_interrupted"})


def failure(code):
    if code is not None and 500 <= code <= 599:
        return "upstream_error"
    return {
        None: "offline",
        401: "invalid_key",
        402: "insufficient_balance",
        403: "permission_denied",
        422: "invalid_contract",
        429: "rate_limited",
    }.get(code, "provider_error")


def outbound(
    channel, *, labels, method="GET", path="", query=None, body=None, headers=None, transport=network
):
    labels = frozenset(labels)
    if labels != {"public_approved"}:
        raise Denied("仅可外发已许可的公开输入")
    if channel not in ENDPOINTS:
        raise Denied("来源未登记")
    if channel == "packycode":
        if transport is network:
            raise Denied(PACKYCODE_LIVE_BLOCK)
        if method != "POST" or path or query:
            raise Denied("PackyCode 仅接受登记的 SystemOne 请求。")
    if path and (channel != "stackexchange" or not re.fullmatch(r"[0-9]{1,12}", path)):
        raise Denied("原文接口路径不在许可范围")
    url = ENDPOINTS[channel] + path
    if query:
        url += "?" + urlencode(query)
    assert urlsplit(url).scheme == "https"
    return transport(method, url, body, headers or {})
