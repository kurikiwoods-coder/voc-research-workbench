"""Live provider diagnostics with separate storage and a zero research denominator."""

from dataclasses import replace
from hashlib import sha256
import json
import re

from src.config import MODEL, PACKYCODE_LIVE_BLOCK, PROVIDERS
from src.edition_policy import Edition, legacy_execution_allowed
from src.execution.jev import call_shards, output_tokens
from src.execution.transport import failure, network
from src.ingestion.public_source import DOMAIN, discover
from src.raw_store.store import Conflict

SUMMARY = "provider_diagnostic"
SYNTHETIC_INPUT = {
    "text": "Synthetic connectivity example. I rinsed the measuring cup and would like help removing a sticky residue.",
    "verified": False,
    "role": "synthetic_api_probe",
}
ERROR_GUIDE = {
    "offline": "检查网络及供应商状态。请求可能已被接收，重新测试前请先核对用量。",
    "invalid_key": "密钥可能无效或已撤销。请从供应商控制台取得新密钥后更换。",
    "insufficient_balance": "请在供应商控制台查看余额和套餐，然后再试。",
    "permission_denied": "请检查 API 是否启用、当前密钥所属组织及模型或搜索权限。",
    "invalid_contract": "供应商拒绝了字段或固定模型。请核对当前账户是否支持该请求。",
    "rate_limited": "供应商正在限流。请查看控制台的配额或等待限流窗口结束。",
    "upstream_error": "供应商暂时无法完成请求。再次测试前请检查服务状态及账单。",
    "provider_error": "供应商拒绝请求。请按 HTTP 状态核对控制台与官方文档。",
}


def outcome(status, message, **details):
    return {"status": status, "message": message, **details}


def request_error(status_code):
    code = failure(status_code)
    return outcome("ERROR", ERROR_GUIDE[code], error_code=code)


def probe_jev(cfg, store, run, attempt, transport):
    refs, versions, gaps, reason = call_shards(
        cfg, store, run, attempt, SYNTHETIC_INPUT, transport
    )
    ledger = store.ledger(run)
    shards = []
    for row in ledger:
        record = store.one("SELECT * FROM evidence WHERE id=?", (row["evidence_id"],))
        if record is None:
            continue
        response = json.loads(record["response_json"])["body"]
        response = response if isinstance(response, dict) else {}
        request = json.loads(record["request_json"])["body"]
        model = response.get("model")
        if not isinstance(model, str) or not re.fullmatch(r"jev-[A-Za-z0-9.\-]{1,38}", model):
            model = None
        answers = response.get("answers")
        answers = answers if isinstance(answers, dict) else {}
        fields = ("type", "choice", "confidence", "score", "probabilities", "noul")
        shards.append({
            "number": row["shard_no"],
            "questions": len(request["questions"]),
            "http_status": record["status_code"],
            "checked_at": record["checked_at"],
            "response_model": model,
            "evidence_id": row["evidence_id"],
            "input_tokens": row["tokens"],
            **({"output_tokens": output_tokens(response)} if cfg.provider == "packycode" else {}),
            "remaining_tokens": row["remaining"] if cfg.provider == "jevmodel" else None,
            "idempotency_key": row["request_key"],
            "ledger_state": row["state"],
            "response_fields": {
                name: [field for field in fields if isinstance(answer, dict) and field in answer]
                for name, answer in ((name, answers.get(name)) for name in request["questions"])
            },
        })
    status = shards[-1]["http_status"] if shards else None
    if reason:
        if status == 422:
            gaps.append("fixed_model_or_request_contract")
            result = outcome("CAPABILITY_BLOCKED", ERROR_GUIDE["invalid_contract"], error_code="invalid_contract")
        else:
            result = request_error(status)
    else:
        if versions != [True, True]:
            gaps = ["model_or_question_ids", *gaps]
        if len(shards) != 2 or any(shard["input_tokens"] is None for shard in shards):
            gaps.append("usage.input_tokens")
        if cfg.provider == "packycode" and (
            len(shards) != 2 or any(shard["output_tokens"] is None for shard in shards)
        ):
            gaps.append("usage.output_tokens")
        result = (
            outcome("CAPABILITY_BLOCKED", "固定模型、问题键或响应字段未通过，请查看 Schema 缺口。")
            if gaps else outcome("READY", "合成文本的两片响应及本机账本已核验。")
        )
    return {
        **result,
        "http_status": status,
        "model": MODEL,
        "evidence_refs": refs,
        "schema_gap": gaps,
        "schema_status": "BLOCKED" if reason else "FAIL" if gaps else "PASS",
        "planned_shards": [8, 3],
        "shards": shards,
    }


def probe_search(cfg, store, attempt, transport):
    name = cfg.provider
    quote, refs, _, _ = discover(cfg, store, attempt, transport, engines=(name,))
    records = store.rows("SELECT * FROM evidence WHERE attempt_id=? ORDER BY id", (attempt,))
    search, *posts = records
    data = json.loads(search["response_json"])
    status = search["status_code"]
    followups = [json.loads(record["response_json"]) for record in posts]
    schema_ok = data["result_list_valid"]
    gaps = ["search_result_list"] if status == 200 and not schema_ok else []
    if status != 200:
        result = request_error(status)
    elif gaps:
        result = outcome("CAPABILITY_BLOCKED", "搜索响应缺少可识别的结果列表。")
    elif quote:
        result = outcome("READY", "已通过该搜索引擎发现可核对来源，并核验许可和原话。")
    else:
        result = outcome("CONNECTED", "搜索 API 已响应，暂无同时通过回源、许可和原话核验的命中。")
    return {
        **result,
        "http_status": status,
        "model": None,
        "evidence_refs": refs,
        "schema_gap": gaps,
        "schema_status": "PASS" if status == 200 and schema_ok else "FAIL" if gaps else "BLOCKED",
        "source": {
            "result_count": data["result_count"],
            "eligible_links": len(data["hits"]),
            "original_fetched": any(p.get("verified") or p.get("content_received") for p in followups),
            "source_http": [record["status_code"] for record in posts],
            "license_verified": any(p.get("verified") or p.get("license_recognized") for p in followups),
            "excerpt_verified": bool(quote),
            "post_id": quote["post_id"] if quote else None,
            "license": quote["license"] if quote else None,
            "source_url": f"https://{DOMAIN}/questions/{quote['post_id']}" if quote else None,
            "quote_sha256": sha256(quote["text"].encode()).hexdigest() if quote else None,
        },
        "credits": data["credits"] if status == 200 else None,
        "monthly_remaining": data["monthly_remaining"] if status in (200, 429) else None,
        "monthly_limit": data["monthly_limit"] if status in (200, 429) else None,
    }


def diagnostic_report(row):
    return {
        **json.loads(row["response_json"]),
        "run_id": row["run_id"], "evidence_id": row["id"], "checked_at": row["checked_at"],
    }


def run_probe(settings, store, provider, request_key, transport=network):
    if not store.diagnostic or (transport is network) == store.fixture:
        raise ValueError("诊断与正式验收必须使用独立的记录库")
    policy_block = not legacy_execution_allowed(settings) or store.edition != Edition.BUSINESS
    if policy_block or (provider == "packycode" and not store.fixture):
        reason = "当前运行模式尚未开放真实供应商诊断。" if policy_block else PACKYCODE_LIVE_BLOCK
        return outcome(
            "LIVE_TEST_BLOCKED", reason, provider=provider, model=MODEL if provider in PROVIDERS else None,
            http_status=None, schema_status="NOT_TESTED", schema_gap=[], evidence_refs=[],
            research_denominator=0,
        )
    cfg = replace(settings, provider=provider)
    run, attempt = store.begin(request_key, cfg)
    if attempt is None:
        bound = store.one("SELECT provider,account_tag FROM runs WHERE id=?", (run,))
        if bound["provider"] != provider or bound["account_tag"] != cfg.account_tag():
            raise Conflict("诊断密钥已绑定前一次操作，请重新发起检查。")
        old = store.one(
            "SELECT r.id AS run_id,e.* FROM evidence e JOIN attempts a ON a.id=e.attempt_id "
            "JOIN runs r ON r.id=a.run_id WHERE r.id=? AND e.name=?", (run, SUMMARY),
        )
        if not old:
            raise Conflict("上次测试结果待确认。请先核对供应商用量与账单。")
        return diagnostic_report(old)
    default = {"http_status": None, "model": MODEL if provider in PROVIDERS else None,
               "schema_status": "NOT_TESTED", "schema_gap": [], "evidence_refs": []}
    try:
        if not cfg.keys.get(provider):
            data = outcome("NOT_CONFIGURED", "请先在本机工作台保存该供应商的 API Key。")
        elif provider in PROVIDERS and not cfg.review_status()["approved"]:
            data = outcome("REVIEW_REQUIRED", "请先导入此供应商的留存审查记录及对应附件。")
        elif provider in PROVIDERS:
            data = probe_jev(cfg, store, run, attempt, transport)
        else:
            data = probe_search(cfg, store, attempt, transport)
    except Exception as exc:
        data = outcome("ERROR", "检查中断，请查看本机状态并先核对供应商用量。", error_code=type(exc).__name__)
    summary = {
        **default, **data, "provider": provider,
        "scope": "engineering_fixture" if store.fixture else "provider_connection_diagnostic",
        "research_denominator": 0,
    }
    ref = store.record(attempt, SUMMARY, summary["scope"], {}, summary, summary["http_status"])
    store.finish(run, attempt, summary["status"] == "READY")
    return diagnostic_report(store.one("SELECT ? AS run_id,* FROM evidence WHERE id=?", (run, ref)))
