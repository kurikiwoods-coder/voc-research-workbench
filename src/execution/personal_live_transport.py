"""Fixed outbound operations for the Personal live execution ledger."""

from dataclasses import dataclass, field
from datetime import date
from gzip import GzipFile
from hashlib import sha256
from http.client import HTTPException
from io import BytesIO
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener
from zlib import decompressobj, error as ZlibError

from src.config import MODEL
from src.edition_policy import REFERENCE
from src.execution import jev
from src.execution.transport import ENDPOINTS, NoRedirect, Response, finite_float, redact
from src.ingestion.public_source import DOMAIN, SITE, post_id
from src.raw_store.personal_validation import Budget
from src.raw_store.store import dump


MAX_RESPONSE_BYTES = 2_000_000
MAX_SYSTEM_ONE_REQUEST_BYTES = 32_768
REQUEST_TIMEOUT_SECONDS = 12
SEARCH_SETTINGS = {
    "topic": "general",
    "search_depth": "basic",
    "max_results": 5,
    "auto_parameters": False,
    "include_answer": False,
    "include_raw_content": False,
    "include_images": False,
    "include_usage": True,
    "include_domains": [DOMAIN],
    "include_domains_mode": "restrict",
}
SEARCH_OPTIONAL = {
    "exact_match", "language", "filter_by_language",
    "start_date", "end_date", "filter_by_published_date",
}


class LiveTransportError(ValueError):
    """Invalid or unsupported operation, detected before a request can be sent."""


@dataclass(frozen=True)
class SystemOnePolicy:
    """The provider and exact payload approved by the owner-only admission path."""

    provider: str
    payload_sha256: str


@dataclass(frozen=True)
class PreparedLiveRequest:
    operation: str
    slot: int
    budget: Budget
    payload_json: str = field(repr=False)
    model_policy: SystemOnePolicy | None = field(default=None, repr=False)


@dataclass(frozen=True)
class LiveReply:
    response: Response = field(repr=False)
    provider_request_id: str | None = None


def _search_ok(payload):
    query = payload.get("query")
    if (not isinstance(query, str) or not 1 <= len(query) <= 400 or not query.strip()
            or not query.isprintable() or redact(query) != query):
        return False
    if set(payload) - SEARCH_SETTINGS.keys() - SEARCH_OPTIONAL - {"query"}:
        return False
    if any(type(payload.get(key)) is not type(value) or payload[key] != value
           for key, value in SEARCH_SETTINGS.items()):
        return False
    if "exact_match" in payload and payload["exact_match"] is not True:
        return False
    language = payload.get("language")
    if "language" in payload:
        if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,24}(?:-[a-z]{2,8})?", language):
            return False
        if payload.get("filter_by_language") is not True:
            return False
    elif "filter_by_language" in payload:
        return False
    dates = []
    for key in ("start_date", "end_date"):
        if key in payload:
            try:
                parsed = date.fromisoformat(payload[key])
            except (ValueError, TypeError):
                return False
            if parsed.isoformat() != payload[key]:
                return False
            dates.append(parsed)
    if dates:
        return payload.get("filter_by_published_date") is True and dates == sorted(dates)
    return "filter_by_published_date" not in payload


def _model_payload_ok(payload, slot):
    if (not isinstance(payload, dict) or payload.keys() != {"model", "state", "questions"}
            or payload["model"] != MODEL):
        return False
    state, questions = payload["state"], payload["questions"]
    expected = jev.split(jev.questions())[slot - 1]
    if (not isinstance(state, str) or not 12 <= len(state) <= 400 or not state.isprintable()
            or not isinstance(questions, dict) or questions.keys() != expected.keys()
            or redact(payload) != payload):
        return False
    if slot == 2:
        return questions == expected
    intent, registry = questions["intent"], questions["in_registry"]
    criteria = intent.get("criteria") if isinstance(intent, dict) else None
    if (not isinstance(criteria, dict) or len(criteria) != 12
            or criteria.get("None") != expected["intent"]["criteria"]["None"]):
        return False
    options = {key: label for key, label in criteria.items() if key != "None"}
    if any(not REFERENCE.fullmatch(key) or not isinstance(label, str) or not 1 <= len(label) <= 240
           or not label.isprintable() for key, label in options.items()):
        return False
    instructions = registry.get("instructions") if isinstance(registry, dict) else None
    return (
        intent == jev.intent_question(options)
        and isinstance(instructions, str) and 1 <= len(instructions) <= 2_720 and instructions.isprintable()
        and registry == {"type": "noul", "instructions": instructions}
        and all(questions[key] == value for key, value in expected.items() if key not in {"intent", "in_registry"})
    )


def _request_parts(operation, payload, slot, budget, model_policy, payload_bytes):
    if not isinstance(budget, Budget) or budget.requests != 1 or type(slot) is not int:
        raise LiveTransportError("LIVE_OPERATION_LIMIT_INVALID")
    if operation == "model" and slot in (1, 2):
        if model_policy is None:
            raise LiveTransportError("LIVE_MODEL_HARD_BUDGET_UNVERIFIED")
        if (type(model_policy) is not SystemOnePolicy or model_policy.provider != "packycode"
                or sha256(payload_bytes).hexdigest() != model_policy.payload_sha256):
            raise LiveTransportError("LIVE_MODEL_POLICY_MISMATCH")
        if (budget.credits or not budget.input_tokens or not budget.output_tokens
                or budget.total_tokens != budget.input_tokens + budget.output_tokens):
            raise LiveTransportError("LIVE_MODEL_LIMIT_INVALID")
        if len(payload_bytes) > MAX_SYSTEM_ONE_REQUEST_BYTES or not _model_payload_ok(payload, slot):
            raise LiveTransportError("LIVE_MODEL_PAYLOAD_INVALID")
        return "POST", ENDPOINTS["packycode"]
    if model_policy is not None:
        raise LiveTransportError("LIVE_MODEL_POLICY_MISMATCH")
    if slot != 1 or not isinstance(payload, dict):
        raise LiveTransportError("LIVE_OPERATION_INVALID")
    if operation == "search":
        if budget.credits != 1 or any((budget.input_tokens, budget.output_tokens, budget.total_tokens)):
            raise LiveTransportError("LIVE_SEARCH_LIMIT_INVALID")
        if not _search_ok(payload):
            raise LiveTransportError("LIVE_SEARCH_PAYLOAD_INVALID")
        return "POST", ENDPOINTS["tavily"]
    if operation == "source":
        if budget != Budget(1, 0, 0, 0, 0, 0):
            raise LiveTransportError("LIVE_SOURCE_LIMIT_INVALID")
        source_url = payload.get("url")
        ident = post_id(source_url)
        if ident is None or payload != {
            "url": f"https://{DOMAIN}/questions/{ident}", "site": SITE, "filter": "withbody",
        }:
            raise LiveTransportError("LIVE_SOURCE_PAYLOAD_INVALID")
        query = urlencode({"site": SITE, "filter": "withbody"})
        return "GET", ENDPOINTS["stackexchange"] + ident + "?" + query
    raise LiveTransportError("LIVE_OPERATION_INVALID")


def _unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("duplicate JSON key")
    return obj


def _response_body(reply, *, strict_utf8=False):
    raw = reply.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        return {"error": "response_too_large"}
    encoding = reply.headers.get("Content-Encoding", "").strip().lower()
    try:
        if encoding == "gzip" or (not encoding and raw.startswith(b"\x1f\x8b")):
            with GzipFile(fileobj=BytesIO(raw)) as compressed:
                raw = compressed.read(MAX_RESPONSE_BYTES + 1)
        elif encoding == "deflate":
            decoder = decompressobj()
            raw = decoder.decompress(raw, MAX_RESPONSE_BYTES + 1)
            if not decoder.eof and len(raw) <= MAX_RESPONSE_BYTES:
                raise ValueError("incomplete deflate stream")
        elif encoding not in ("", "identity"):
            raise ValueError("unsupported response encoding")
    except (ValueError, EOFError, OSError, ZlibError):
        return {"error": "invalid_response_encoding"}
    if len(raw) > MAX_RESPONSE_BYTES:
        return {"error": "response_too_large"}
    try:
        if strict_utf8:
            raw = raw.decode("utf-8")
        return json.loads(raw, parse_float=finite_float, parse_constant=finite_float,
                          object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        return {"error": "non_json_response"}


def _provider_request_id(operation, body, headers, secret):
    if operation == "search" and isinstance(body, dict):
        identifier = body.get("request_id")
    else:
        identifier = headers.get("X-Request-Id")
    if (isinstance(identifier, str) and REFERENCE.fullmatch(identifier)
            and redact(identifier, (secret,)) == identifier):
        return identifier
    return None


class PersonalLiveTransport:
    """Prepare before reservation, then send once after the ledger grants the claim."""

    def prepare(self, operation, payload, *, slot, budget, model_policy=None):
        try:
            payload_json = dump(payload)
            payload_bytes = payload_json.encode("utf-8")
        except (ValueError, TypeError, RecursionError):
            raise LiveTransportError("LIVE_OPERATION_PAYLOAD_INVALID") from None
        _request_parts(operation, payload, slot, budget, model_policy, payload_bytes)
        return PreparedLiveRequest(operation, slot, budget, payload_json, model_policy)

    def send(self, prepared, *, secret, model_policy=None):
        if model_policy != prepared.model_policy:
            raise LiveTransportError("LIVE_MODEL_POLICY_MISMATCH")
        try:
            payload_bytes = prepared.payload_json.encode("utf-8")
            payload = json.loads(prepared.payload_json, object_pairs_hook=_unique_object)
        except (ValueError, TypeError, RecursionError):
            raise LiveTransportError("LIVE_OPERATION_PAYLOAD_INVALID") from None
        method, url = _request_parts(prepared.operation, payload, prepared.slot, prepared.budget,
                                     model_policy, payload_bytes)
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "VOC-Workbench/1.0 (Personal pre-admission evidence)",
        }
        if method == "POST":
            if (not isinstance(secret, str) or not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", secret)
                    or redact(payload, (secret,)) != payload):
                raise LiveTransportError("LIVE_CREDENTIAL_INVALID")
            headers.update({"Authorization": "Bearer " + secret, "Content-Type": "application/json"})
            data = payload_bytes
        else:
            if secret is not None:
                raise LiveTransportError("LIVE_SOURCE_ANONYMOUS_REQUIRED")
            data = None
        request = Request(url, method=method, data=data, headers=headers)
        try:
            try:
                reply = build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=REQUEST_TIMEOUT_SECONDS)
            except HTTPError as exc:
                reply = exc
            with reply:
                body = _response_body(reply, strict_utf8=prepared.operation == "model")
                provider_id = _provider_request_id(prepared.operation, body, reply.headers, secret)
                # Leave the source body intact for the existing license and
                # source-quote privacy checks. Only licensed projections are
                # eligible for archival by the caller.
                if prepared.operation != "source":
                    body = redact(body, (secret,))
                return LiveReply(Response(reply.status, body), provider_id)
        except (URLError, OSError, HTTPException):
            return LiveReply(Response(None, {"error": "connection_interrupted"}))
