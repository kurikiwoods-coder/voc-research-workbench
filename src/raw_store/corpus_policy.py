"""Source qualification shared by corpus review and import history."""

import json
import re
from unicodedata import normalize
from urllib.parse import parse_qsl, unquote, urlsplit

from src.ingestion.import_mapping import date_value, key, scope_issues, url_valid


QUOTE_SOURCES = {
    "forum", "youtube", "reddit", "amazon", "review", "productreview",
    "论坛", "社区", "商品评论", "产品评论", "评价",
}
QUOTE_LABELS = {"userquote", "用户原话", "原话"}
REVIEW_SOURCES = {"amazon", "review", "productreview", "商品评论", "产品评论", "评价"}
AMAZON_HOST = re.compile(r"(?:^|\.)amazon\.[a-z]{2,3}(?:\.[a-z]{2})?$|^amzn\.to$")
US_MARKETS = {"us", "usa", "unitedstates", "unitedstatesofamerica", "美国", "美國"}
UNCONFIRMED_PERMISSIONS = {"unknown", "pending", "denied", "unlicensed", "不明", "未知", "待核", "待审", "待确认",
                           "无许可", "无授权", "禁止", "未授权"}
NEGATIVE_PERMISSION = re.compile(
    r"^(?:no\s+(?:permission|licen[cs]e|authori[sz]ation)\b|"
    r"(?:permission|licen[cs]e|authori[sz]ation)[:\s]+(?:denied|pending|unknown|not\s+granted)\b|"
    r"未获(?:许可|授权)|未经授权|无许可|无授权|禁止(?:收录|保存|留存))"
)
WITHDRAWN_PERMISSION = re.compile(
    r"^(?:(?:source\s+)?(?:permission|licen[cs]e|authori[sz]ation)[:\s]+"
    r"(?:(?:has\s+been|was)\s+)?(?:revoked|withdrawn)\b|"
    r"(?:来源|來源)?(?:许可|許可|授权|授權)(?:已被|已|被)?(?:撤[销銷]|撤回))"
)
SENSITIVE = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"(?:\b(?:order(?:\s+(?:id|number|no\.?))?|(?:shipping\s+|mailing\s+)?address|"
    r"api[_ -]?key|access[_ -]?token|password)|订单号|訂單編號|收货地址|收貨地址)\s*[#:=：]\s*[\w-]+",
    re.IGNORECASE,
)
SECRET_QUERY_KEYS = {"apikey", "accesstoken", "auth", "authorization", "credential", "key", "password",
                     "secret", "signature", "token"}
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
METADATA_FIELDS = ("source_type", "source_url", "published_at", "access_policy", "content_role",
                   "external_id", "lang", "rating", "verified", "product_model", "market")


def safe_source_url(value):
    if not value or not url_valid(value):
        return False
    decoded = unquote(value)
    if CONTROL.search(decoded) or SENSITIVE.search(decoded):
        return False
    parts = urlsplit(value)
    parameters = parse_qsl(parts.query, keep_blank_values=True) + parse_qsl(parts.fragment, keep_blank_values=True)
    return all(key(name) not in SECRET_QUERY_KEYS and not SENSITIVE.search(value) for name, value in parameters)


def source_identity(value):
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
    return json.dumps((parts.scheme, host, port, parts.path or "/", parts.query, parts.fragment))


def safe_metadata(raw_fields):
    fields = json.loads(raw_fields)
    result = {k: fields[k] for k in METADATA_FIELDS if k in fields
              and not SENSITIVE.search(str(fields[k])) and not CONTROL.search(str(fields[k]))}
    if "source_url" in result and not safe_source_url(result["source_url"]):
        del result["source_url"]
    return result


def permission_recorded(metadata):
    permission = normalize("NFKC", metadata.get("access_policy", "")).casefold().strip()
    normalized = key(permission)
    return (normalized not in {"", "no", "none", "na"} and not NEGATIVE_PERMISSION.search(permission)
            and not source_permission_revoked(permission)
            and not any(normalized.endswith(value) for value in UNCONFIRMED_PERMISSIONS))


def source_permission_revoked(reason):
    return bool(WITHDRAWN_PERMISSION.search(normalize("NFKC", reason).casefold().strip()))


def validate_snapshot(row, role, metadata, scope):
    privacy = row["privacy"]
    if SENSITIVE.search(row["raw_text"]) or CONTROL.search(row["raw_text"]):
        raise ValueError("请在本机脱敏后重新导入，再核验原文。")
    if privacy in {"internal", "private"} and role != "internal":
        raise ValueError("内部及非公开材料只能归入本机隔离的内部材料。")
    if role == "internal" and privacy not in {"internal", "private"}:
        raise ValueError("内部材料须先按内部或非公开等级重新导入。")
    if privacy == "unknown" and role != "synthetic":
        raise ValueError("请先确认隐私等级，再核验原文。")
    if role == "synthetic":
        return
    if not permission_recorded(metadata):
        raise ValueError("请在导入来源记录填写来源许可或授权依据。")
    if role != "user_quote":
        return

    source = key(metadata.get("source_type", ""))
    label = key(metadata.get("content_role", ""))
    if privacy != "public" or source not in QUOTE_SOURCES or (label and label not in QUOTE_LABELS):
        raise ValueError("原话必须来自明确的公开用户来源。摘要与其他角色不能作为用户原话核验。")
    if not metadata.get("source_url") or not date_value(metadata.get("published_at")):
        raise ValueError("用户原话必须包含可核对的原文 URL 和发布时间。")
    if "outside_scope" in scope_issues(json.loads(row["fields_json"]), scope):
        raise ValueError("原文时间或明确的产品引用超出该批次冻结的研究范围。")
    host = urlsplit(metadata["source_url"]).hostname.rstrip(".")
    amazon = source == "amazon" or AMAZON_HOST.search(host)
    if (source in REVIEW_SOURCES or amazon) and not {"rating", "verified", "product_model"} <= metadata.keys():
        raise ValueError("评价类原话需要原始评分、购买验证和产品型号。")
    if amazon:
        if metadata.get("verified") is not True or key(metadata.get("market", "")) not in US_MARKETS:
            raise ValueError("Amazon 产品体验原话只收录已验证购买的美国市场评价。")


def valid_snapshot_source(privacy, raw_text, role, fields_json, scope_json):
    # Older reviews remain immutable. Current policy controls visibility.
    row = {"privacy": privacy, "raw_text": raw_text, "fields_json": fields_json}
    try:
        validate_snapshot(row, role, safe_metadata(fields_json), json.loads(scope_json))
    except ValueError:
        return False
    return True
