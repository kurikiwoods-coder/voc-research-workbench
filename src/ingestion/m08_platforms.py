"""M08-C fixed platform capabilities and synthetic original-text projection."""

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

from src.ingestion.m08_retrieval import MAX_BODY_BYTES, UnsafeUrl, normalize_url
from src.ingestion.public_source import DOMAIN, LICENSES, published_at


ADAPTER_VERSION = "m08-platform-v1"
EXTRACTION_VERSION = "m08-visible-lines-v1"
STACK = "m08-stackexchange"
YOUTUBE = "m08-youtube"
REDDIT = "m08-reddit"
FIXTURE_SOURCES = frozenset({STACK, YOUTUBE})
OPERATIONS = ("discover", "access", "store", "research", "transmit")
YOUTUBE_DOMAIN = "www.youtube.com"
FIXTURE_LICENSE = "urn:voc-workbench:m08:synthetic-fixture-v1"
FIXTURE_CAPTURED_AT = "2026-11-25T12:00:00+00:00"
CONTENT_ROLES = frozenset({"user_quote", "background", "product_or_merchant", "internal", "synthetic"})
NUMERIC_ID = re.compile(r"[1-9][0-9]{0,11}")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
COMMENT_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}")
STACK_QUESTION = re.compile(r"/(?:q|questions)/([1-9][0-9]{0,11})(?:/[a-z0-9-]{1,240})?/?")
STACK_ANSWER = re.compile(r"/a/([1-9][0-9]{0,11})/?")
STACK_ANSWER_ON_PAGE = re.compile(r"/questions/([1-9][0-9]{0,11})/[a-z0-9-]{1,240}/([1-9][0-9]{0,11})/?")
STACK_COMMENT = re.compile(r"comment-?([1-9][0-9]{0,11})(?:_([1-9][0-9]{0,11}))?")


@dataclass(frozen=True)
class Capability:
    kind: str
    endpoint: str
    status: str
    content_role: str | None = None
    quota_units: int | None = None
    quota_bucket: str = "request"


CAPABILITIES = {
    STACK: (
        Capability("question", "/questions/{ids}", "offline_fixture", "user_quote"),
        Capability("answer", "/answers/{ids}", "offline_fixture", "user_quote"),
        Capability("comment", "/comments/{ids}", "offline_fixture", "user_quote"),
    ),
    YOUTUBE: (
        Capability("search", "search.list", "offline_fixture", quota_units=1, quota_bucket="search_query"),
        Capability("metadata", "videos.list", "offline_fixture", "background", 1, "quota_unit"),
        Capability("description", "videos.list", "offline_fixture", "product_or_merchant", 1, "quota_unit"),
        Capability("comment", "commentThreads.list", "offline_fixture", "user_quote", 1, "quota_unit"),
        Capability("reply", "comments.list", "deferred", "user_quote", 1, "quota_unit"),
        Capability("caption_track", "captions.list", "authorization_required", None, 50, "quota_unit"),
        Capability("caption_text", "captions.download", "owner_authorization_required", None, 200, "quota_unit"),
    ),
    REDDIT: (
        Capability("search", "GET /search", "blocked_candidate"),
        Capability("metadata", "GET /api/info", "blocked_candidate", "background"),
        Capability("post", "GET /comments/{article}", "blocked_candidate", "user_quote"),
        Capability("comment", "GET /comments/{article}", "blocked_candidate", "user_quote"),
    ),
}


def platform_catalog():
    """Return the registered platform capabilities and unapproved production permissions."""
    catalogue = (
        (STACK, "public_forum", DOMAIN, None, "request", "https://stackoverflow.com/legal/api-terms-of-use",
         "逐对象核对 CC BY-SA 版本、原作者和来源链接", "按逐对象审批、许可条件及本机撤销规则处理",
         "遵守返回的 backoff，检查每日 API 配额和同方法缓存窗口",
         ["正式站点、对象及用途审批", "逐对象许可、署名和留存审核"]),
        (YOUTUBE, "video", YOUTUBE_DOMAIN, "youtube_data_api_project", "quota_unit",
         "https://developers.google.com/youtube/terms/developer-policies",
         "核对 API 数据展示、YouTube 标识及权利人要求", "按适用规则刷新、删除 API 数据并响应撤权或删除",
         "搜索查询使用独立额度；其余已登记操作使用 quota unit",
         ["Google Cloud 项目和有效凭证", "本项目逐用途留存、删除及研究审批", "字幕 OAuth 与视频权限"]),
        (REDDIT, "public_forum", "www.reddit.com", "reddit_data_api_oauth", "request",
         "https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki",
         "待 Reddit 批准及适用协议明确", "按获批条款处理删除、用户撤权和留存",
         "OAuth 客户端额度及商业研究限制以 Reddit 实际授权为准",
         ["Reddit 明确批准、注册客户端和 OAuth", "商业研究、留存、删除与用途协议"]),
    )
    rows = []
    for source_id, source_type, domain, credential, unit, terms, attribution, retention, rate_limit, gaps in catalogue:
        enabled = source_id in FIXTURE_SOURCES
        state = "offline_fixture" if enabled else "blocked_candidate"
        rows.append({
            "source_id": source_id, "provider": source_id[4:], "source_type": source_type,
            "adapter_version": ADAPTER_VERSION, "credential_reference": credential,
            "credential_configured": None, "capability_status": state, "enabled_status": state,
            "permission_status": "unknown", "permissions": dict.fromkeys(OPERATIONS, "unknown"),
            "allowed_operations": ["discover", "access", "store", "research"] if enabled else [],
            "allowed_domains": [domain], "license_reference": terms,
            "attribution_requirement": attribution, "retention_policy": retention, "deletion_policy": retention,
            "rate_limit": rate_limit, "usage_unit": unit, "approval_gaps": gaps,
            "object_capabilities": [asdict(capability) for capability in CAPABILITIES[source_id]],
        })
    return rows


class VisibleText(HTMLParser):
    """Project visible fixture HTML to plain text without executing any markup."""

    blocks = frozenset({"article", "blockquote", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                        "hr", "li", "ol", "p", "pre", "section", "table", "td", "tr", "ul"})
    void = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                      "param", "source", "track", "wbr"})
    excluded = frozenset({"head", "iframe", "noscript", "object", "script", "style", "template"})

    def __init__(self):
        super().__init__()
        self.stack = []
        self.open_tags = Counter()
        self.fragments = []

    @property
    def suppressed(self):
        return bool(self.stack and self.stack[-1][1])

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        style = re.sub(r"\s+", "", attrs.get("style") or "").casefold()
        hidden = (self.suppressed or tag in self.excluded or "hidden" in attrs
                  or (attrs.get("aria-hidden") or "").casefold() == "true"
                  or re.search(r"(?:^|;)(?:display:none|visibility:hidden)(?:!important)?(?:;|$)", style))
        if not hidden and tag in self.blocks:
            self.fragments.append("\n")
        if tag not in self.void:
            self.stack.append((tag, bool(hidden)))
            self.open_tags[tag] += 1

    def handle_endtag(self, tag):
        if self.open_tags[tag] == 0:
            return
        while self.stack:
            open_tag, hidden = self.stack.pop()
            self.open_tags[open_tag] -= 1
            if open_tag == tag:
                if tag in self.blocks and not hidden:
                    self.fragments.append("\n")
                return

    def handle_data(self, data):
        if not self.suppressed:
            self.fragments.append(data)

    def render(self, value):
        self.feed(value)
        self.close()
        lines = [" ".join(line.split()) for line in "".join(self.fragments).splitlines()]
        return "\n".join(line for line in lines if line)


def exact_segments(body):
    """Produce nonblank exact slices indexed in Unicode code points."""
    segments = []
    offset = 0
    for line in body.splitlines(keepends=True):
        text = line.strip()
        if text:
            start = offset + len(line) - len(line.lstrip())
            segments.append({"start": start, "end": start + len(text), "text": text,
                             "extraction_version": EXTRACTION_VERSION})
        offset += len(line)
    return segments


@dataclass(frozen=True)
class FixtureReply:
    status: int | None
    item: dict | list | None = None
    media_type: str = "application/json"
    error: str | None = None


def _safe_name(value):
    return value.strip() if isinstance(value, str) and 0 < len(value) <= 240 and value.isprintable() else None


def _utc_timestamp(value):
    if isinstance(value, str) and len(value) <= 40 and "T" in value:
        try:
            moment = datetime.fromisoformat(value)
            if moment.tzinfo is not None:
                return moment.astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError):
            pass
    return None


def _stack_projection(kind, item, object_id, parent_id):
    provided_id = item.get(f"{kind}_id")
    if not (type(provided_id) is int and str(provided_id) == object_id and NUMERIC_ID.fullmatch(object_id)):
        return None
    try:
        canonical = normalize_url(item.get("link"), (DOMAIN,))
    except UnsafeUrl:
        return None
    parsed = urlsplit(canonical)
    original = urlsplit(item["link"])
    question = STACK_QUESTION.fullmatch(parsed.path)
    if parsed.scheme != "https" or parsed.query:
        return None
    if kind == "question":
        if not question or question[1] != object_id or original.fragment:
            return None
        url = locator = f"https://{DOMAIN}/questions/{object_id}"
    elif kind == "answer":
        direct_answer = STACK_ANSWER.fullmatch(parsed.path)
        answer_on_page = STACK_ANSWER_ON_PAGE.fullmatch(parsed.path)
        linked_question = (question and question[1] == parent_id
                           or answer_on_page and answer_on_page.groups() == (parent_id, object_id))
        if (type(item.get("question_id")) is not int or str(item["question_id"]) != parent_id
                or not ((direct_answer and direct_answer[1] == object_id and not original.fragment)
                        or (linked_question and original.fragment == object_id))):
            return None
        url = f"https://{DOMAIN}/questions/{parent_id}"
        locator = f"https://{DOMAIN}/a/{object_id}"
    else:
        comment = STACK_COMMENT.fullmatch(original.fragment)
        answer = STACK_ANSWER.fullmatch(parsed.path)
        answer_on_page = STACK_ANSWER_ON_PAGE.fullmatch(parsed.path)
        on_question = bool(question and question[1] == parent_id)
        on_answer = bool((answer and answer[1] == parent_id) or (answer_on_page and answer_on_page[2] == parent_id))
        post_type = item.get("post_type")
        parent_matches = (on_question and post_type in (None, "question")) or (on_answer and post_type == "answer")
        if (type(item.get("post_id")) is not int or str(item["post_id"]) != parent_id or not parent_matches
                or not comment or comment[1] != object_id or comment[2] not in {None, parent_id}):
            return None
        post_url = f"https://{DOMAIN}/{('questions' if on_question else 'a')}/{parent_id}"
        url = f"https://{DOMAIN}/questions/{answer_on_page[1]}" if on_answer and answer_on_page else post_url
        locator = f"{post_url}#{original.fragment}"
    owner = item.get("owner")
    name = owner.get("display_name") if isinstance(owner, dict) else None
    name = _safe_name(unescape(name)) if isinstance(name, str) and len(name) <= 480 else None
    license_name = item.get("content_license")
    return {
        "canonical_url": url, "source_locator": locator, "original_url": item["link"],
        "title": _safe_name(item.get("title")) if kind == "question" else None,
        "published_at": published_at(item.get("creation_date")),
        "modified_at": published_at(item.get("last_edit_date")) if kind != "comment" else None,
        "attribution": name, "license_reference": LICENSES.get(license_name) if isinstance(license_name, str) else None,
    }, item.get("body")


def _youtube_projection(kind, item, object_id, parent_id):
    snippet = item.get("snippet")
    if not isinstance(snippet, dict):
        return None
    video_id = parent_id if kind == "comment" else object_id
    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        return None
    url = normalize_url(f"https://{YOUTUBE_DOMAIN}/watch?v={video_id}", (YOUTUBE_DOMAIN,))
    title, locator, raw_text = None, url, None
    if kind == "comment":
        comment = snippet.get("topLevelComment")
        details = comment.get("snippet") if isinstance(comment, dict) else None
        if (snippet.get("videoId") != parent_id or not COMMENT_ID.fullmatch(object_id)
                or not isinstance(details, dict) or details.get("videoId", parent_id) != parent_id
                or comment.get("id") != object_id or details.get("parentId") is not None):
            return None
        snippet = details
        locator = url + f"&lc={object_id}"
        name = snippet.get("authorDisplayName")
        raw_text = snippet.get("textOriginal")
    else:
        identifier = item.get("id")
        if kind == "search":
            if not isinstance(identifier, dict) or identifier.get("kind") != "youtube#video":
                return None
            identifier = identifier.get("videoId")
        if identifier != object_id:
            return None
        title = _safe_name(snippet.get("title"))
        name = snippet.get("channelTitle")
        if kind == "description":
            raw_text = snippet.get("description")
    return {
        "canonical_url": url, "source_locator": locator, "original_url": locator, "title": title,
        "published_at": _utc_timestamp(snippet.get("publishedAt")),
        "modified_at": _utc_timestamp(snippet.get("updatedAt")),
        "attribution": _safe_name(name), "license_reference": FIXTURE_LICENSE,
    }, raw_text


def _reddit_fixture_shape(kind, item):
    if kind in {"post", "comment"}:
        if not isinstance(item, list) or len(item) != 2:
            return False
        item = item[0 if kind == "post" else 1]
    if not isinstance(item, dict) or item.get("kind") != "Listing" or not isinstance(item.get("data"), dict):
        return False
    children = item["data"].get("children")
    expected = {"t1", "more"} if kind == "comment" else {"t1", "t3"} if kind == "metadata" else {"t3"}
    return isinstance(children, list) and all(
        isinstance(child, dict) and isinstance(child.get("kind"), str) and child["kind"] in expected
        and isinstance(child.get("data"), dict) for child in children
    )


def project_fixture(source_id, kind, *, reply, object_id, permissions, fetched_at, parent_id=None,
                    attribution_approved=False, content_role=None):
    """Project one fixed-source fixture reply using grants for this specific object only."""
    capability = next((value for value in CAPABILITIES.get(source_id, ()) if value.kind == kind), None)
    result = {
        "source_id": source_id, "object_kind": kind, "source_object_id": object_id,
        "adapter_version": ADAPTER_VERSION, "fetched_at": _utc_timestamp(fetched_at), "role": "synthetic",
        "method": capability.endpoint if capability else None, "http_status": reply.status, "synthetic": True,
        "accessible": False, "body": None, "segments": [], "raw_sha256": None, "response_body_sha256": None,
    }
    if reply.status in {401, 403, 429} or reply.error in {"quotaExceeded", "dailyLimitExceeded", "commentsDisabled"}:
        reason = ("quota_blocked" if reply.status == 429 or reply.error in {"quotaExceeded", "dailyLimitExceeded"}
                  else "comments_disabled" if reply.error == "commentsDisabled" else "permission_blocked")
        return {**result, "status": reason}
    if not capability or capability.status != "offline_fixture":
        if source_id == REDDIT and capability:
            if reply.status != 200:
                return {**result, "status": "source_unavailable"}
            result["fixture_shape_verified"] = _reddit_fixture_shape(kind, reply.item)
        return {**result, "status": capability.status if capability else "unsupported_object"}

    def allowed(operation):
        return permissions.get(operation) == "approved"

    if not allowed("discover" if kind == "search" else "access"):
        return {**result, "status": "permission_blocked"}
    if not isinstance(object_id, str) or (parent_id is not None and not isinstance(parent_id, str)):
        return {**result, "status": "unverified_object"}
    if reply.status != 200:
        reason = "redirect_refused" if reply.status in {301, 302, 303, 307, 308} else "source_unavailable"
        return {**result, "status": reason}
    if (not isinstance(reply.item, dict) or not result["fetched_at"] or not isinstance(reply.media_type, str)
            or reply.media_type.partition(";")[0].strip().lower() != "application/json"):
        return {**result, "status": "unverified_response"}
    project = _stack_projection if source_id == STACK else _youtube_projection
    projected = project(kind, reply.item, object_id, parent_id)
    if not projected:
        return {**result, "status": "unverified_object"}
    fields, original = projected
    role = capability.content_role
    if role == "user_quote":
        role = content_role if isinstance(content_role, str) and content_role in CONTENT_ROLES else "unclassified"
    result.update(canonical_url=fields["canonical_url"], source_locator=fields["source_locator"],
                  original_url=fields["original_url"], accessible=kind != "search", content_role=role)
    if kind == "search":
        return {**result, "status": "discovered"}
    if not allowed("store") or not fields["license_reference"] or not attribution_approved:
        return {**result, "status": "storage_blocked"}
    if not fields["published_at"] or not fields["attribution"]:
        return {**result, "status": "unverified_attribution_or_timestamp"}
    result.update(fields)
    if kind == "metadata":
        return {**result, "status": "metadata_verified"}
    if source_id == YOUTUBE and kind == "comment" and original is None:
        return {**result, "status": "original_unavailable"}
    if not isinstance(original, str) or len(original) > MAX_BODY_BYTES:
        return {**result, "status": "invalid_body"}
    try:
        original_bytes = original.encode("utf-8")
    except UnicodeEncodeError:
        return {**result, "status": "invalid_body"}
    if len(original_bytes) > MAX_BODY_BYTES or "\x00" in original:
        return {**result, "status": "invalid_body"}
    body = VisibleText().render(original) if source_id == STACK else original
    if not body.strip():
        return {**result, "status": "empty_body"}
    digest = sha256(body.encode("utf-8")).hexdigest()
    result.update(body=body, raw_sha256=digest, body_sha256=digest,
                  response_body_sha256=sha256(original_bytes).hexdigest())
    if role != "user_quote" or not allowed("research"):
        return {**result, "status": "body_verified",
                "extraction_reason": "content_role" if role != "user_quote" else "research_permission"}
    return {**result, "status": "segments_extracted", "segments": exact_segments(body)}


def _fixture_objects(source_id, batch_no, offset, date):
    identity = batch_no * 10_000 + offset
    text = (f"试用记录 {identity} 🧭 我希望断线后可以继续之前的操作。",
            "I want the last change to remain visible after I reconnect.")
    if source_id == STACK:
        question, post = str(9_100_000_000 + identity), str(9_200_000_000 + identity)
        kind = ("question", "answer", "comment")[(offset - 1) % 3]
        item = {"body": "".join(f"<p>{line}</p>" for line in text), "content_license": "CC BY-SA 4.0",
                "creation_date": int(datetime.fromisoformat(date).timestamp()),
                "owner": {"display_name": "M08 合成论坛作者"}}
        if kind == "question":
            item.update(question_id=int(question), title="合成论坛主题", link=f"https://{DOMAIN}/q/{question}")
            return kind, item, question, None
        if kind == "answer":
            item.update(answer_id=int(post), question_id=int(question),
                        link=f"https://{DOMAIN}/questions/{question}/synthetic-topic/{post}#{post}")
        else:
            item.update(comment_id=int(post), post_id=int(question), post_type="question",
                        link=f"https://{DOMAIN}/questions/{question}#comment{post}_{question}")
        return kind, item, post, question
    video = f"m08{batch_no:04d}{offset:04d}"
    comment = f"m08_fixture_{identity}"
    top_level = {"id": comment, "snippet": {"publishedAt": date,
                 "authorDisplayName": "M08 合成视频评论者", "textOriginal": "\n".join(text)}}
    return "comment", {"snippet": {"videoId": video, "topLevelComment": top_level}}, comment, video


def retrieve_fixture(source_id, *, batch_no, limit, published_date="2026-11-23", fetched_at=FIXTURE_CAPTURED_AT):
    """Return deterministic evidence-producing rows without dispatching network requests."""
    if source_id not in FIXTURE_SOURCES:
        return []
    if type(batch_no) is not int or not 1 <= batch_no <= 9999 or type(limit) is not int or not 0 <= limit <= 9999:
        raise ValueError("Invalid fixture batch or limit")
    date = _utc_timestamp(f"{published_date}T00:00:00+00:00")
    if date is None or _utc_timestamp(fetched_at) is None:
        raise ValueError("Invalid fixture publication date or capture time")
    rows = []
    for offset in range(1, limit + 1):
        kind, item, object_id, parent_id = _fixture_objects(source_id, batch_no, offset, date)
        rows.append(project_fixture(
            source_id, kind, reply=FixtureReply(200, item), object_id=object_id, parent_id=parent_id,
            permissions={"access": "approved", "store": "approved", "research": "approved", "transmit": "restricted"},
            fetched_at=fetched_at, attribution_approved=True, content_role="user_quote",
        ))
    return rows
