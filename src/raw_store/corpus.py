"""Local review and replay of immutable M04 import records."""

from datetime import date
import hashlib
import json
import re
from unicodedata import normalize
from urllib.parse import parse_qsl, urlsplit

from src.ingestion.import_mapping import date_value, key, scope_issues, url_valid
from src.raw_store.imports import RESTRICTED_SOURCE_ROWS
from src.raw_store.store import Conflict, dump, now
from src.raw_store.studies import StudyStore


PAGE_SIZE = 20
ROLES = {"user_quote", "background", "internal", "synthetic"}
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

# The v3 view excludes revoked rows; reviewed rows remain visible for local audit.
ROW_SOURCE = """
    FROM import_rows r
    JOIN import_batches b ON b.batch_id=r.batch_id
    JOIN import_files f ON f.file_id=b.file_id
    JOIN study_scopes s ON s.study_id=b.study_id AND s.scope_id=b.scope_id
    JOIN study_projects p ON p.study_id=b.study_id
    LEFT JOIN corpus_snapshots snap ON snap.record_id=r.record_id
    LEFT JOIN corpus_reviews v ON v.review_id=(
        SELECT MAX(h.review_id) FROM corpus_reviews h WHERE h.record_id=r.record_id
    )
"""
CANDIDATE = "(v.review_id IS NOT NULL OR r.status IN ('staged', 'pending_review'))"
SOURCE_ALIAS_RESTRICTED = f"""EXISTS (
    SELECT 1 {RESTRICTED_SOURCE_ROWS}
    AND restricted_file.study_id=f.study_id AND restricted_file.sha256=f.sha256
    AND restricted_batch.sheet_index=b.sheet_index AND restricted_row.line_number=r.line_number
    AND restricted_row.record_id<>r.record_id
)"""
ROW_COLUMNS = f"""
    r.record_id, r.line_number, r.privacy, r.fields_json,
    b.revoked_at, p.status AS project_status,
    v.decision, v.role, v.retention_until, {SOURCE_ALIAS_RESTRICTED} AS alias_restricted
"""


def checksum(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_source_url(value):
    if not value or not url_valid(value):
        return False
    parts = urlsplit(value)
    parameters = parse_qsl(parts.query, keep_blank_values=True) + parse_qsl(parts.fragment, keep_blank_values=True)
    return all(key(name) not in SECRET_QUERY_KEYS and not SENSITIVE.search(value) for name, value in parameters)


def safe_metadata(raw_fields):
    fields = json.loads(raw_fields)
    result = {k: fields[k] for k in METADATA_FIELDS if k in fields and not SENSITIVE.search(str(fields[k]))}
    if "source_url" in result and not safe_source_url(result["source_url"]):
        del result["source_url"]
    return result


def permission_recorded(metadata):
    permission = key(metadata.get("access_policy", ""))
    return bool(permission) and not any(permission.endswith(value) for value in UNCONFIRMED_PERMISSIONS)


def require_review_text(value, label, max_length, *, required):
    if not isinstance(value, str):
        raise ValueError(f"{label}必须是文本。")
    value = value.strip()
    if (required and not value) or len(value) > max_length:
        raise ValueError(f"请填写有效的{label}（最多 {max_length} 字）。")
    if CONTROL.search(value) or SENSITIVE.search(value):
        raise ValueError(f"请先从{label}中移除个人识别信息。")
    return value


def review_retention(value, today, *, required):
    if value in (None, "") and not required:
        return None
    try:
        valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value and value >= today
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("请提供有效的保留截止日期（YYYY-MM-DD，UTC，且未到期）。")
    return value


def effective_status(row, today):
    if row["revoked_at"]:
        return "revoked"
    if row["retention_until"] and row["retention_until"] < today:
        return "retention_expired"
    if row["alias_restricted"] and row["decision"] != "excluded":
        return "source_restricted"
    return row["decision"] or "pending_review"


def record_summary(row, today):
    metadata = {} if row["alias_restricted"] else safe_metadata(row["fields_json"])
    status = effective_status(row, today)
    return {
        "record_id": row["record_id"], "line_number": row["line_number"], "privacy": row["privacy"],
        "role": row["role"], "status": status, "source_type": metadata.get("source_type"),
        "published_at": metadata.get("published_at"),
        "can_review": status not in {"revoked", "retention_expired", "source_restricted"}
        and row["project_status"] != "archived",
    }


def dedupe_key(study_id, text, metadata):
    quote = " ".join(normalize("NFC", text).split())
    if len(quote) >= 24:
        # Match exact, substantial quotes across sources. A short reply needs a shared source identity.
        return checksum(dump([study_id, "public", "user_quote", quote]))
    if metadata.get("external_id"):
        return checksum(dump([study_id, "public", "user_quote", quote, metadata["source_url"], metadata["external_id"]]))
    return None


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
    if source in REVIEW_SOURCES and not {"rating", "verified", "product_model"} <= metadata.keys():
        raise ValueError("评价类原话需要原始评分、购买验证和产品型号。")
    host = urlsplit(metadata["source_url"]).hostname
    if source == "amazon" or AMAZON_HOST.search(host):
        if metadata.get("verified") is not True or key(metadata.get("market", "")) not in US_MARKETS:
            raise ValueError("Amazon 产品体验原话只收录已验证购买的美国市场评价。")


class CorpusStore:
    def __init__(self, store):
        if store.fixture or store.diagnostic:
            raise ValueError("原文库只允许使用工作台主库。")
        self.store = store

    def batches(self, study_id, offset=0):
        with self.store.db() as db:
            db.execute("BEGIN")
            StudyStore.project_row(db, study_id)
            rows = db.execute(
                """SELECT b.batch_id, f.filename, b.sheet_name, b.scope_id, 'v' || s.version_no AS scope_version,
                          b.created_at AS collected_at, b.revoked_at,
                          (SELECT COUNT(*) FROM import_rows r WHERE r.batch_id=b.batch_id
                           AND r.status IN ('staged', 'pending_review')) AS candidate_count,
                          (SELECT COUNT(*) FROM import_rows r WHERE r.batch_id=b.batch_id AND EXISTS
                           (SELECT 1 FROM corpus_reviews h WHERE h.record_id=r.record_id)) AS reviewed_count
                   FROM import_batches b JOIN import_files f ON f.file_id=b.file_id
                   JOIN study_scopes s ON s.study_id=b.study_id AND s.scope_id=b.scope_id
                   WHERE b.study_id=? ORDER BY b.created_at DESC, b.rowid DESC LIMIT ? OFFSET ?""",
                (study_id, PAGE_SIZE + 1, offset),
            ).fetchall()
            return {"batches": [dict(row) for row in rows[:PAGE_SIZE]], "more": len(rows) > PAGE_SIZE}

    def candidates(self, study_id, batch_id, offset=0):
        with self.store.db() as db:
            db.execute("BEGIN")
            if db.execute("SELECT 1 FROM import_batches WHERE study_id=? AND batch_id=?",
                          (study_id, batch_id)).fetchone() is None:
                raise KeyError(batch_id)
            today = now()[:10]
            rows = db.execute(
                f"""SELECT {ROW_COLUMNS} {ROW_SOURCE}
                    WHERE b.study_id=:study_id AND b.batch_id=:batch_id AND {CANDIDATE}
                    ORDER BY r.line_number LIMIT :limit OFFSET :offset""",
                {"study_id": study_id, "batch_id": batch_id, "today": today,
                 "limit": PAGE_SIZE + 1, "offset": offset},
            ).fetchall()
            return {"batch_id": batch_id, "records": [record_summary(row, today) for row in rows[:PAGE_SIZE]],
                    "more": len(rows) > PAGE_SIZE}

    @staticmethod
    def source_row(db, study_id, record_id, today):
        row = db.execute(
            f"""SELECT {ROW_COLUMNS}, r.raw_text, r.issues_json, r.status AS import_status,
                       b.batch_id, b.study_id, b.scope_id, 'v' || s.version_no AS scope_version,
                       b.file_id, f.filename, f.kind, f.sha256 AS file_sha256, b.sheet_name,
                       b.created_at AS collected_at, s.content_json, snap.raw_sha256, v.dedupe_group
                {ROW_SOURCE} WHERE b.study_id=:study_id AND r.record_id=:record_id AND {CANDIDATE}""",
            {"study_id": study_id, "record_id": record_id, "today": today},
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return row

    @staticmethod
    def duplicate(db, row, today):
        if not row["dedupe_group"] or row["role"] != "user_quote" or effective_status(row, today) != "verified":
            return None
        group = db.execute(
            f"""SELECT r.record_id, COUNT(*) OVER () AS record_count {ROW_SOURCE}
                WHERE b.study_id=:study_id AND v.dedupe_group=:dedupe_group AND b.revoked_at IS NULL
                    AND v.decision='verified' AND v.role='user_quote' AND v.retention_until>=:today
                    AND NOT {SOURCE_ALIAS_RESTRICTED}
                ORDER BY snap.created_at, snap.record_id LIMIT 1""",
            {"study_id": row["study_id"], "dedupe_group": row["dedupe_group"], "today": today},
        ).fetchone()
        return {"group_id": row["dedupe_group"], "canonical_record_id": group["record_id"],
                "record_count": group["record_count"], "is_duplicate": group["record_id"] != row["record_id"]}

    def describe(self, db, row, today):
        summary = record_summary(row, today)
        raw_text = row["raw_text"]
        metadata = {} if row["alias_restricted"] else safe_metadata(row["fields_json"])
        visible = summary["status"] == "verified" or (
            summary["status"] == "pending_review" and row["privacy"] == "public"
            and permission_recorded(metadata) and not SENSITIVE.search(raw_text) and not CONTROL.search(raw_text)
        )
        trace = {key_: row[key_] for key_ in (
            "batch_id", "study_id", "scope_id", "scope_version", "file_id", "filename",
            "file_sha256", "sheet_name", "line_number", "collected_at",
        )}
        trace.update({"time_window": json.loads(row["content_json"])["date_window"],
                      "extraction_method": "csv_upload" if row["kind"] == "csv" else "manual_import",
                      "extraction_rule": "按导入字段映射保存原单元格文本", "query_terms": None})
        history = db.execute(
            """SELECT decision, role, reason, basis, retention_until, reviewed_at FROM corpus_reviews
               WHERE record_id=? ORDER BY review_id DESC LIMIT 20""",
            (row["record_id"],),
        ).fetchall()
        return {**summary, "raw_text": raw_text if visible else None, "raw_sha256": row["raw_sha256"],
                "metadata": metadata, "trace": trace,
                "import_status": row["import_status"], "import_issues": json.loads(row["issues_json"]),
                "duplicate": self.duplicate(db, row, today), "history": [dict(event) for event in history],
                "decision": row["decision"], "retention_until": row["retention_until"], "revoked_at": row["revoked_at"],
                "research_eligible": False, "outbound_allowed": False}

    def detail(self, study_id, record_id):
        with self.store.db() as db:
            db.execute("BEGIN")
            today = now()[:10]
            return self.describe(db, self.source_row(db, study_id, record_id, today), today)

    def review(self, study_id, record_id, decision, role, reason, basis="", retention_until=None):
        if decision not in {"verified", "excluded"} or role not in ROLES:
            raise ValueError("核验处理和内容角色无效。")
        verified = decision == "verified"
        reason = require_review_text(reason, "处理原因", 500, required=True)
        basis = require_review_text(basis, "核验依据", 1000, required=verified)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            at = now()
            today = at[:10]
            retention_until = review_retention(retention_until, today, required=verified)
            row = self.source_row(db, study_id, record_id, today)
            if not record_summary(row, today)["can_review"]:
                raise Conflict("项目或原文当前受归档、批次撤销、审核结论或保留期限限制。")
            payload = (decision, role, reason, basis, retention_until)
            previous = db.execute(
                """SELECT decision, role, reason, basis, retention_until FROM corpus_reviews
                   WHERE record_id=? ORDER BY review_id DESC LIMIT 1""", (record_id,),
            ).fetchone()
            if previous and tuple(previous) == payload:
                return self.describe(db, row, today)
            group_id = None
            if verified:
                metadata = safe_metadata(row["fields_json"])
                validate_snapshot(row, role, metadata, json.loads(row["content_json"]))
                group_id = dedupe_key(study_id, row["raw_text"], metadata) if role == "user_quote" else None
                db.execute(
                    """INSERT INTO corpus_snapshots (record_id, study_id, scope_id, raw_sha256, created_at)
                       VALUES (?, ?, ?, ?, ?) ON CONFLICT(record_id) DO NOTHING""",
                    (record_id, study_id, row["scope_id"], checksum(row["raw_text"]), at),
                )
            db.execute(
                """INSERT INTO corpus_reviews (record_id, decision, role, reason, basis, retention_until, dedupe_group, reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (record_id, *payload, group_id, at),
            )
            return self.describe(db, self.source_row(db, study_id, record_id, today), today)
