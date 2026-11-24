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
LICENSE_STATES = {"authorized", "pending", "denied", "revoked", "expired", "unknown"}
_ZH_VARIANTS = str.maketrans("許權銷審獲經確認無過屆後隨態書錄還發現廢從沒", "许权销审获经确认无过届后随态书录还发现废从没")
_WITHDRAWAL = re.compile(
    r"撤销|撤回|吊销|废止|\b(?:revok(?:ed|e)|withdraw(?:n|al)|rescinded)\b|"
    r"\b(?:licen[cs]e|permission|consent)\b[^.;\n]{0,64}\b(?:cancelled|canceled)\b"
)
_DENIAL = re.compile(
    r"未(?:曾|获|经|取得|得到)?(?:许可|授权)|(?:许可|授权)(?:尚|还)?未(?:取得|获取|获得|批准)|"
    r"(?:尚未|还未|未曾|未能|未)(?:获取|获得|取得|得到).{0,24}(?:许可|授权)|"
    r"无(?:许可|授权)|拒绝(?:许可|授权)|禁止(?:收录|保存|留存)|"
    r"\bnot(?:\s+(?:yet|been)){0,2}\s+(?:granted|approved|permitted|authori[sz]ed)\b|"
    r"\b(?:unlicensed|unauthori[sz]ed|no permission|no licen[cs]e|without permission|not authori[sz]ed|"
    r"not granted|not approved|permission denied|licen[cs]e denied)\b"
)
_EXPIRY = re.compile(
    r"已(?:到期|过期|届满|失效)|(?:许可|授权|期限)[：:\s]*(?:到期|过期|届满|失效)|\b(?:expired|lapsed)\b"
)
_PENDING = re.compile(
    r"待(?:核|审|确认|审批)|审批(?:流程)?中|等待.{0,8}(?:审批|确认|授权)|未知|不明|无法判断|"
    r"\b(?:has|have|had)\s+yet\s+to\s+be\s+(?:granted|approved|authori[sz]ed)\b|"
    r"\b(?:pending|unknown|unconfirmed|unclear|awaiting approval)\b"
)
_LOCAL_EVIDENCE = re.compile(r"local:[\w][\w.-]{2,126}")
_OLD_EVIDENCE = re.compile(r"""local:[\w.-]+|https?://[^\s<>"'，。；）】]+""", re.IGNORECASE)
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
    # A fragment locates a place in the same document; it cannot supply a separate license.
    return json.dumps((parts.scheme, host, port, parts.path or "/", parts.query))


def safe_metadata(raw_fields):
    fields = json.loads(raw_fields)
    result = {k: fields[k] for k in METADATA_FIELDS if k in fields
              and not SENSITIVE.search(str(fields[k])) and not CONTROL.search(str(fields[k]))}
    if "source_url" in result and not safe_source_url(result["source_url"]):
        del result["source_url"]
    return result


def license_note_state(value):
    """Historical text can signal a restriction. Authorization requires a review event."""
    note = normalize("NFKC", value).casefold().translate(_ZH_VARIANTS).strip()
    still_valid = re.sub(
        r"(?:尚未|从未|未曾|没有|未)(?:被)?(?:撤销|撤回|到期|过期|届满|失效|吊销|废止)|"
        r"\b(?:not|never)\s+(?:yet\s+)?(?:been\s+)?(?:revoked|withdrawn|expired|lapsed|cancelled|canceled)\b", "", note,
    )
    for state, pattern, text in (
        ("revoked", _WITHDRAWAL, still_valid), ("denied", _DENIAL, note),
        ("expired", _EXPIRY, still_valid), ("pending", _PENDING, note),
    ):
        if pattern.search(text):
            return state
    return "unknown"


def source_permission_revoked(reason):
    return license_note_state(reason) == "revoked"


def evidence_identity(value):
    if not isinstance(value, str):
        return None
    value = normalize("NFKC", value).strip()
    if _LOCAL_EVIDENCE.fullmatch(value) and not SENSITIVE.search(value):
        return value.casefold()
    return source_identity(value) if safe_source_url(value) else None


def legacy_evidence_identities(text):
    return {evidence_identity(ref.rstrip(").;,]")) for ref in _OLD_EVIDENCE.findall(text)}


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


def snapshot_content_valid(privacy, raw_text, role, fields_json, scope_json):
    row = {"privacy": privacy, "raw_text": raw_text, "fields_json": fields_json}
    try:
        validate_snapshot(row, role, safe_metadata(fields_json), json.loads(scope_json))
    except ValueError:
        return False
    return True


def legacy_snapshot_recheckable(privacy, raw_text, role, fields_json, scope_json):
    note = json.loads(fields_json).get("access_policy", "")
    return license_note_state(note) == "unknown" and snapshot_content_valid(
        privacy, raw_text, role, fields_json, scope_json,
    )


def valid_snapshot_source(privacy, raw_text, role, fields_json, scope_json, license_state, evidence_ref,
                          restored_withdrawal_id):
    if license_state != "authorized" or evidence_identity(evidence_ref) is None:
        return False
    if restored_withdrawal_id is None:
        return legacy_snapshot_recheckable(privacy, raw_text, role, fields_json, scope_json)
    return snapshot_content_valid(privacy, raw_text, role, fields_json, scope_json)


def snapshot_requires_restriction(privacy, raw_text, role, fields_json, scope_json, license_state, evidence_ref,
                                  restored_withdrawal_id):
    if license_state is None:
        # A legacy record awaiting proof should not block its copies from being reviewed.
        return not legacy_snapshot_recheckable(privacy, raw_text, role, fields_json, scope_json)
    return not valid_snapshot_source(privacy, raw_text, role, fields_json, scope_json, license_state,
                                     evidence_ref, restored_withdrawal_id)
