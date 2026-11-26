"""Deterministic field mapping and staging quality rules."""

from collections import Counter
from datetime import date, datetime
import hashlib
import re
from unicodedata import normalize
from urllib.parse import urlsplit

from src.ingestion.import_files import ImportProblem


FIELDS = {
    "raw_text": ("用户原话", "原话|原始文本|评论内容|反馈内容|回答|开放题|访谈原话|正文|text|body|comment|review_text|response"),
    "source_type": ("来源类型", "来源|来源类别|source|platform|source_platform"),
    "source_url": ("来源 URL", "原文链接|来源链接|网址|链接|url|link|permalink"),
    "published_at": ("发布时间", "原文时间|发表时间|发布日期|发表日期|评论日期|timestamp|date|posted_at|review_date"),
    "product_name": ("产品名称", "产品|商品名称|服务名称|item_name|product"),
    "product_category_id": ("产品品类 ID", "品类引用|品类ID|品类编号|产品品类|category_id|product_category_ids"),
    "product_id": ("产品标识 / ASIN", "ASIN|产品标识|产品ID|商品ID|SKU|product_identifier"),
    "product_model": ("产品型号", "型号|模型编号|model"),
    "rating": ("评分", "打分|星级|评分（1-5）|stars|score|star_rating"),
    "verified": ("已验证购买", "是否已验证|已验证|verified_purchase"),
    "market": ("市场", "国家|地区|国家地区|市场地区|country|region|locale"),
    "lang": ("语言", "研究语言|语言代码|language"),
    "external_id": ("外部记录 ID", "外部ID|评论ID|原始编号|记录ID|record_id|review_id|response_id"),
    "access_policy": ("来源许可", "许可|授权|授权说明|来源授权|license|licence|permission"),
    "privacy": ("隐私等级", "隐私|数据等级|保密级别|privacy_level|sensitivity"),
    "content_role": ("内容角色", "内容类型|原话角色|原文类型|role"),
}
ISSUES = {
    "blank_text": ("error", "用户原话为空"),
    "row_width": ("error", "列数与表头不一致"),
    "excel_formula": ("error", "Excel 单元格含公式，请先另存为纯值"),
    "excel_cell_error": ("error", "Excel 单元格含错误值"),
    "bad_date": ("error", "发布时间格式不合法，请使用 ISO 日期或时间"),
    "bad_rating": ("error", "评分必须是 1 至 5 的整数"),
    "bad_url": ("error", "来源 URL 无效，请提供原文的 HTTP(S) 链接"),
    "bad_verified": ("error", "购买验证字段无法识别，请填写是、否或留空"),
    "missing_source": ("warning", "缺少来源类型"),
    "missing_url": ("warning", "缺少原文链接，需用原文件及授权材料人工核对"),
    "missing_date": ("warning", "缺少原文发布时间"),
    "missing_permission": ("warning", "缺少来源许可或授权记录"),
    "unknown_privacy": ("warning", "隐私等级待确认"),
    "missing_product": ("warning", "缺少与研究范围相关的产品或品类引用"),
    "outside_scope": ("warning", "日期或产品品类引用超出所选范围，需人工核对"),
    "review_metadata": ("warning", "评价类记录缺少评分、购买验证或产品型号"),
    "quote_unverified": ("warning", "内容角色需核对，只有真实用户原话可作证据"),
    "duplicate": ("warning", "与本工作表前面的记录疑似重复"),
}
PRIVACY = ("unknown", "public", "private", "internal")
STATUSES = ("staged", "pending_review", "duplicate", "rejected")


def key(value):
    return re.sub(r"[^\w]+|_", "", normalize("NFKC", value).casefold())


def field_catalog():
    return [{"id": name, "label": label, "required": name == "raw_text"} for name, (label, _) in FIELDS.items()]


def suggestions(columns):
    indexes = {}
    for idx, column in enumerate(columns):
        indexes.setdefault(key(column), []).append(idx)
    found = {}
    used = set()
    for field, (label, aliases) in FIELDS.items():
        for alias in [field, label, *aliases.split("|")]:
            options = indexes.get(key(alias), [])
            if len(options) == 1 and options[0] not in used:
                found[field] = options[0]
                used.add(options[0])
                break
    return found


def validate_mapping(mapping, width):
    if "raw_text" not in mapping:
        raise ImportProblem("请将一个文件字段对应到用户原话。")
    if (any(field not in FIELDS or not 0 <= index < width for field, index in mapping.items())
            or len(set(mapping.values())) != len(mapping)):
        raise ImportProblem("字段映射范围无效，或同一列被重复使用。")


def privacy_value(value):
    aliases = {
        "public": "public", "公开": "public", "公开数据": "public",
        "private": "private", "nonpublic": "private", "私有": "private", "非公开": "private",
        "internal": "internal", "cx": "internal", "cxinternal": "internal", "internalcx": "internal",
        "内部": "internal", "内部数据": "internal", "内部cx": "internal", "内部客诉": "internal",
        "机密": "internal", "保密": "internal",
    }
    return aliases.get(key(value), "unknown")


def row_privacy(value, source, floor):
    source_key = key(source)
    if (source_key in {"cx", "cxinternal", "internalcx", "客服记录", "客户投诉", "内部客诉"}
            or "内部" in source_key or "internal" in source_key):
        return "internal"
    selected = privacy_value(value) if value else floor
    if selected == "unknown" and floor == "public":
        return "unknown"
    return max((selected, floor), key=PRIVACY.index)


def date_value(value):
    if not value:
        return None
    simple = re.fullmatch(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", value)
    if simple:
        return date(*(int(group) for group in simple.groups())).isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
        raise ValueError
    return datetime.fromisoformat(value).isoformat()


def url_valid(value):
    if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        return False
    try:
        parts = urlsplit(value)
        return (parts.scheme in {"https", "http"} and bool(parts.hostname)
                and parts.username is None and parts.port != 0)
    except ValueError:
        return False


def source_locator(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value.casefold().startswith(("https://", "http://")) or not url_valid(value):
        return None
    parts = urlsplit(value)
    host = parts.hostname.rstrip(".")
    if not host:
        return None
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.scheme, host, port, parts.path or "/", parts.query


def overlaps(value, ids):
    return bool({item.strip() for item in re.split(r"[;,；，\n]+", value)}.intersection(ids))


def scope_issues(values, scope):
    dates = scope["date_window"]
    published = values.get("published_at")
    if published and (
        (dates.get("start") and published[:10] < dates["start"])
        or (dates.get("end") and published[:10] > dates["end"])
    ):
        yield "outside_scope"
    for field, ids in (("product_category_id", scope["product_category_ids"]), ("product_id", scope["product_ids"])):
        if ids:
            value = values.get(field)
            if not value:
                yield "missing_product"
            elif not overlaps(value, ids):
                yield "outside_scope"


def evaluate_row(row, mapping, scope, privacy):
    mapped = {field: row.values[idx] if idx < len(row.values) else "" for field, idx in mapping.items()}
    raw_text = mapped.pop("raw_text")
    values = {name: value.strip() for name, value in mapped.items() if value.strip()}
    flags = list(row.errors)
    if not raw_text.strip():
        flags.append("blank_text")
    for field, issue in (("source_type", "missing_source"), ("source_url", "missing_url"),
                         ("published_at", "missing_date"), ("access_policy", "missing_permission")):
        if field not in values:
            flags.append(issue)
    if values.get("source_url") and not url_valid(values["source_url"]):
        flags.append("bad_url")
    try:
        if "published_at" in values:
            values["published_at"] = date_value(values["published_at"])
    except ValueError:
        flags.append("bad_date")
        values.pop("published_at")
    if rating := values.get("rating"):
        if re.fullmatch(r"[1-5](?:\.0+)?", rating):
            values["rating"] = int(rating[0])
        else:
            flags.append("bad_rating")
            values.pop("rating")
    if verified := values.get("verified"):
        truth = key(verified)
        if truth in {"true", "yes", "1", "是", "已验证"}:
            values["verified"] = True
        elif truth in {"false", "no", "0", "否", "未验证"}:
            values["verified"] = False
        else:
            flags.append("bad_verified")
            values.pop("verified")
    source = values.get("source_type", "")
    if key(source) in {"amazon", "review", "productreview", "评价", "商品评论", "产品评论"}:
        if not {"rating", "verified", "product_model"} <= values.keys():
            flags.append("review_metadata")
    role = key(values.get("content_role", ""))
    if (role and role not in {"userquote", "用户原话", "原话"}) or key(source) == "searchdiscovery":
        flags.append("quote_unverified")
    level = row_privacy(values.pop("privacy", ""), source, privacy)
    if level == "unknown":
        flags.append("unknown_privacy")
    flags.extend(scope_issues(values, scope))
    return raw_text, values, list(dict.fromkeys(flags)), level


def evaluate(sheet, mapping, scope, privacy):
    validate_mapping(mapping, len(sheet.columns))
    seen_text = {}
    seen_external = {}
    distinct_sources_kept = False
    totals = Counter({status: 0 for status in STATUSES})
    issue_counts = Counter()
    levels = Counter()
    source_types = Counter()
    rows = []
    for row in sheet.rows:
        raw_text, values, flags, level = evaluate_row(row, mapping, scope, privacy)
        normalized = " ".join(normalize("NFC", raw_text).split())
        digest = hashlib.sha256(normalized.encode()).hexdigest() if normalized else None
        declared_role = key(values.get("content_role", ""))
        role = "user_quote" if declared_role in {"", "userquote", "用户原话", "原话"} else declared_role
        text_key = (level, role, digest)
        locator = source_locator(values.get("source_url"))
        external_id = values.get("external_id")
        source_type = values.get("source_type")
        external_key = (level, role, key(source_type), external_id) if external_id and source_type else None
        first_duplicate = None
        if any(ISSUES[flag][0] == "error" for flag in flags):
            status = "rejected"
        else:
            previous = seen_text.setdefault(text_key, {})
            if locator is None:
                first_duplicate = next(iter(previous.values()), None)
            else:
                first_duplicate = previous.get(None) or previous.get(locator)
            if first_duplicate is None and external_key:
                first_duplicate = seen_external.get(external_key)
            if first_duplicate is not None:
                flags.append("duplicate")
                status = "duplicate"
            else:
                status = "pending_review" if flags else "staged"
                distinct_sources_kept |= bool(previous)
                previous[locator] = row.line
                if external_key:
                    seen_external[external_key] = row.line
        issues = [{"code": flag, "severity": ISSUES[flag][0], "message": ISSUES[flag][1]} for flag in flags]
        totals[status] += 1
        issue_counts.update(flags)
        levels[level] += 1
        source_types[values.get("source_type", "未提供")] += 1
        rows.append({
            "line_number": row.line, "raw_text": raw_text, "original_fields": row.values,
            "fields": values, "status": status, "privacy": level, "text_fingerprint": digest,
            "duplicate_of_line": first_duplicate, "issues": issues,
        })
    return rows, {
        "total": len(rows), **totals, "privacy_levels": dict(levels), "source_types": dict(source_types),
        "issues": [{"code": flag, "severity": ISSUES[flag][0], "message": ISSUES[flag][1], "count": n}
                   for flag, n in issue_counts.items()],
    }, distinct_sources_kept
