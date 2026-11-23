"""One outbound boundary for every connector, with an auditable offline drill."""
from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

ENDPOINTS = {
    "typesafe": "https://api.typesafe.ai/v1/systemone",
    "jevmodel": "https://jevmodel.org/v1/systemone",
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


class Denied(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def number(value):
    if type(value) is int and value >= 0:
        return value
    return None


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {str(k): redact(v, secrets) for k, v in value.items()
                if str(k).lower() not in {"authorization","x-subscription-token","api_key","access_token","email","access-token","cookie","set-cookie"}}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[REDACTED]", value)
    return value


def network(method, url, body, headers):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method, headers={**headers,"Accept":"application/json","User-Agent":"VOC-Connectivity/1.0 (public API verification)"})
    try:
        try:
            response = build_opener(NoRedirect()).open(req, timeout=12)
        except HTTPError as exc:
            response = exc
        with response:
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                return Response(response.status, {"error":"response_too_large"})
            try:
                obj = json.loads(data)
            except (ValueError, UnicodeError):
                obj = {"error":"non_json_response"}
            header = response.headers.get("X-Tokens-Remaining", "")
            remaining = int(header) if re.fullmatch(r"\d{1,18}", header) else None
            return Response(response.status, obj, remaining, response.headers.get("Retry-After"))
    except (URLError, TimeoutError, ConnectionError, OSError):
        return Response(None, {"error":"connection_interrupted"})


def failure(code):
    return {None:"offline",401:"invalid_key",402:"insufficient_balance",403:"permission_denied",
            422:"invalid_contract",429:"rate_limited",502:"upstream_error"}.get(code, "provider_error")


def outbound(channel, *, labels, method="GET", path="", query=None, body=None, headers=None, transport=network):
    labels = frozenset(labels)
    if labels != {"public_approved"}:
        raise Denied("仅可外发已许可的公开输入")
    if channel not in ENDPOINTS:
        raise Denied("来源未登记")
    if path and (channel != "stackexchange" or not re.fullmatch(r"[0-9]{1,12}", path)):
        raise Denied("原文接口路径不在许可范围")
    url = ENDPOINTS[channel] + path
    if query:
        url += "?" + urlencode(query)
    assert urlsplit(url).scheme == "https"
    return transport(method, url, body, headers or {})
