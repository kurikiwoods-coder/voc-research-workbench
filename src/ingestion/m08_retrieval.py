"""Normalize discovered URLs and verify fixed Stack Exchange page fixtures."""

from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import ipaddress
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from src.execution.transport import Response, failure, network
from src.ingestion.public_source import DOMAIN, LICENSES, PlainText, fetch_forum_post, published_at


NORMALIZATION_VERSION = "m08-url-v1"
MAX_URL_LENGTH = 2048
MAX_REDIRECTS = 5
MAX_BODY_BYTES = 2_000_000
STACK_METHOD = "Stack Exchange API /questions/{id} (fixture)"
DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DNS_NAME = re.compile(rf"(?:{DNS_LABEL}\.)+[a-z][a-z0-9-]{{0,62}}", re.ASCII)
QUESTION_PATH = re.compile(r"/(?:q/[1-9][0-9]{0,11}|questions/[1-9][0-9]{0,11}(?:/[a-z0-9-]{1,240})?)/?")
PERMISSIONS = {"approved", "pending", "denied", "restricted", "expired", "revoked", "background"}


class UnsafeUrl(ValueError):
    pass


class _ExcerptText(PlainText):
    def __init__(self):
        super().__init__()
        self.hidden_tag = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden_tag = tag

    def handle_endtag(self, tag):
        if tag == self.hidden_tag:
            self.hidden_tag = None

    def handle_data(self, data):
        if self.hidden_tag is None:
            super().handle_data(data)

    def as_html_text(self, value):
        self.feed(value)
        self.close()
        return escape("".join(self.fragments), quote=False)


def _check_url_text(value):
    if (
        not isinstance(value, str) or not 0 < len(value) <= MAX_URL_LENGTH
        or not value.isprintable() or any(char.isspace() for char in value) or "\\" in value
        or re.search(r"%(?![0-9a-fA-F]{2})", value)
    ):
        raise UnsafeUrl("invalid_url")


def normalize_url(raw_url, allowed_domains):
    """Canonical HTTP resource identity for offline discovery, preserving path and query."""
    _check_url_text(raw_url)
    try:
        parsed = urlsplit(raw_url)
        host, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise UnsafeUrl("invalid_url") from exc
    default_port = {"http": 80, "https": 443}.get(parsed.scheme)
    if default_port is None or not host:
        raise UnsafeUrl("unsupported_scheme")
    if (
        not parsed.netloc.isascii() or not re.fullmatch(r"[a-zA-Z0-9.-]+(?::[0-9]{1,5})?", parsed.netloc)
        or (port is not None and port != default_port)
    ):
        raise UnsafeUrl("unsafe_authority")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeUrl("ip_literal_disallowed")
    if (
        len(host) > 253 or not DNS_NAME.fullmatch(host) or host.endswith("-")
        or host.endswith((".localhost", ".local", ".localdomain", ".internal", ".lan", ".home.arpa"))
    ):
        raise UnsafeUrl("unsafe_host")
    try:
        allowed = not isinstance(allowed_domains, (str, bytes)) and host in allowed_domains
    except TypeError as exc:
        raise UnsafeUrl("invalid_url_configuration") from exc
    if not allowed:
        raise UnsafeUrl("domain_not_allowed")
    return urlunsplit((parsed.scheme, host, parsed.path or "/", parsed.query, ""))


def validate_redirect_chain(original_url, locations, allowed_domains):
    """Check each recorded fixture Location; the existing live connector does not follow redirects."""
    current = normalize_url(original_url, allowed_domains)
    chain = []
    seen = {current}
    for location in locations:
        if len(chain) >= MAX_REDIRECTS:
            raise UnsafeUrl("too_many_redirects")
        _check_url_text(location)
        if location.startswith("///"):
            raise UnsafeUrl("invalid_url")
        if "#" in location:
            raise UnsafeUrl("redirect_fragment_unsupported")
        target = normalize_url(urljoin(current, location), allowed_domains)
        if current.startswith("https://") and target.startswith("http://"):
            raise UnsafeUrl("redirect_scheme_downgrade")
        if target in seen:
            raise UnsafeUrl("redirect_cycle")
        chain.append(target)
        seen.add(target)
        current = target
    return tuple(chain)


def _question_id(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or parsed.netloc != DOMAIN or parsed.query
        or not QUESTION_PATH.fullmatch(parsed.path)
    ):
        return None
    return parsed.path.split("/")[2]


def _permission(value):
    return value if isinstance(value, str) and value in PERMISSIONS else "pending"


def _permission_result(value):
    return "permission_pending" if value == "pending" else "permission_denied"


def retrieve_stackexchange(
    url, *, allowed_domains, access_status="pending", excerpt_status="pending",
    transport, redirect_locations=(), clock=lambda: datetime.now(timezone.utc),
):
    """Return page evidence separately from permission-gated synthetic extract evidence."""
    access_status, excerpt_status = _permission(access_status), _permission(excerpt_status)
    result = {
        "status": "discovered", "accessible": False, "original_url": None, "canonical_url": None,
        "redirect_chain": [], "final_url": None, "normalization_version": NORMALIZATION_VERSION,
        "http_status": None, "fetched_at": None, "published_at": None, "method": STACK_METHOD,
        "content_sha256": None, "license_reference": None, "license_status": "pending",
        "access_permission_status": access_status, "excerpt_permission_status": excerpt_status,
        "permission_status": access_status, "quote": None, "reason": None, "synthetic": True,
        "research_denominator": 0,
    }
    try:
        allowed_domains = frozenset(allowed_domains) if not isinstance(allowed_domains, (str, bytes)) else ()
        canonical = normalize_url(url, allowed_domains)
        result.update(original_url=url, canonical_url=canonical)
        redirects = validate_redirect_chain(canonical, redirect_locations, allowed_domains)
    except (UnsafeUrl, TypeError) as exc:
        reason = str(exc) if isinstance(exc, UnsafeUrl) else "invalid_url_configuration"
        return {**result, "status": "permission_denied", "reason": reason, "permission_status": "denied"}
    final = redirects[-1] if redirects else canonical
    result.update(redirect_chain=list(redirects), final_url=final)
    if access_status != "approved":
        return {**result, "status": _permission_result(access_status), "reason": "access_permission"}
    identifier = _question_id(final)
    if (
        not identifier or any(_question_id(target) != identifier for target in (canonical, *redirects))
        or urlsplit(url).fragment
    ):
        return {
            **result, "status": "permission_denied", "permission_status": "denied",
            "reason": "unapproved_source_route",
        }
    if transport is network or not callable(transport):
        return {
            **result, "status": "permission_denied", "permission_status": "denied",
            "reason": "fixture_transport_required",
        }

    content = {}

    def fixture_request(method, endpoint, body, headers):
        reply = transport(method, endpoint, body, headers)
        if not isinstance(reply, Response) or (
            reply.status is not None and (type(reply.status) is not int or not 100 <= reply.status < 600)
        ):
            return Response(None, {})
        if reply.status != 200 or not isinstance(reply.body, dict):
            return Response(reply.status, {})
        items = reply.body.get("items")
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            return Response(200, {})
        item = items[0]
        try:
            link = normalize_url(item.get("link"), allowed_domains)
        except UnsafeUrl:
            return Response(200, {})
        post = item.get("body")
        if (
            _question_id(link) != identifier or urlsplit(item["link"]).fragment
            or type(item.get("question_id")) is not int
            or str(item["question_id"]) != identifier or not isinstance(post, str)
            or len(post) > MAX_BODY_BYTES
        ):
            return Response(200, {})
        post_bytes = post.encode("utf-8", errors="replace")
        if len(post_bytes) > MAX_BODY_BYTES:
            return Response(200, {})
        license_name = item.get("content_license")
        license_name = license_name if isinstance(license_name, str) and license_name in LICENSES else None
        owner = item.get("owner")
        name = owner.get("display_name") if isinstance(owner, dict) else None
        date = item.get("creation_date")
        date = date if type(date) is int else None
        content.update(
            content_sha256=sha256(post_bytes).hexdigest(),
            license_reference=LICENSES.get(license_name),
            license_status="approved" if license_name else "pending",
            published_at=published_at(date),
        )
        return Response(200, {"items": [{
            "question_id": item["question_id"], "link": link,
            "body": _ExcerptText().as_html_text(post) if license_name and excerpt_status == "approved" else "",
            "content_license": license_name,
            "owner": {"display_name": name if isinstance(name, str) and len(name) <= 240 else ""},
            "creation_date": date,
        }]})

    try:
        status, _, citation = fetch_forum_post(identifier, "m08_fixture", transport=fixture_request)
    except (TimeoutError, OSError):
        return {**result, "status": "inaccessible", "fetched_at": clock().isoformat(), "reason": "offline"}
    result.update(http_status=status, fetched_at=clock().isoformat())
    if status != 200 or not content:
        reason = "redirect_refused" if status in {301, 302, 303, 307, 308} else failure(status)
        return {**result, "status": "inaccessible", "reason": reason if status != 200 else "unverified_page"}
    result.update(
        content, status="accessible", accessible=True,
        permission_status=excerpt_status if excerpt_status != "approved" else content["license_status"],
    )
    if excerpt_status == "pending":
        return result
    if result["permission_status"] != "approved":
        return {
            **result, "status": _permission_result(result["permission_status"]),
            "reason": "excerpt_permission" if excerpt_status != "approved" else "source_license_unknown",
        }
    if not citation["verified"]:
        return {**result, "status": "extraction_failed", "reason": "unverified_excerpt"}
    quote = {key: citation[key] for key in ("text", "author", "license", "published_at")}
    quote.update(synthetic=True, research_denominator=0, extraction_rule="stackexchange-first-sentence-v1")
    return {**result, "status": "quote_extracted", "quote": quote}
