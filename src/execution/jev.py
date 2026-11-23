import math
import time
import json
from src.config import MODEL, PROVIDERS
from src.raw_store.store import Conflict
from src.execution.transport import outbound, network, number, failure, redact

VERSION = "connectivity-questions-1"
REGISTRY = "connectivity-intents-1"
PUBLIC = {"public_approved"}


def intent_question(options):
    if "None" in options or not 1 <= len(options) <= 19:
        raise ValueError("Jev Choice 允许 1 至 19 个已知意图和一个 None")
    return {
        "type": "choice",
        "instructions": "Which intent is expressed in the passage?",
        "criteria": {**options, "None": "None of these intents"},
    }


def questions():
    items = {
        "intent": intent_question(
            {"use": "Complete the immediate task", "maintain": "Care for an item"}
        ),
        "in_registry": {
            "type": "noul",
            "instructions": "Does the passage express any of these intents: complete the immediate task or care for an item?",
        },
        "friction": {
            "type": "score",
            "instructions": "How much difficulty does the speaker describe?",
            "criteria": ["No difficulty", "Some difficulty", "High difficulty"],
        },
    }
    prompts = (
        "Is the speaker requesting help?",
        "Does the speaker mention a tool?",
        "Is the account first person?",
        "Does the speaker describe a previous attempt?",
        "Is time pressure explicit?",
        "Is a proposed solution mentioned?",
        "Is a specific material mentioned?",
        "Is the desired outcome explicit?",
    )
    items.update({f"signal_{i}": {"type": "noul", "instructions": q} for i, q in enumerate(prompts, 1)})
    return items


def split(items):
    seq = list(items.items())
    return [dict(seq[start : start + 8]) for start in range(0, len(seq), 8)]


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def distribution(probs, keys):
    return (
        isinstance(probs, dict)
        and set(probs) == set(keys)
        and all(probability(v) for v in probs.values())
        and math.isclose(sum(probs.values()), 1, abs_tol=0.005)
    )


def validate(asked, obj):
    if not isinstance(obj, dict) or not isinstance(obj.get("answers"), dict):
        return False, ["answers"]
    answers = obj["answers"]
    identity = obj.get("model") == MODEL and set(answers) == set(asked)
    gaps = []
    for key, question in asked.items():
        answer = answers.get(key)
        kind = question["type"]
        if not isinstance(answer, dict) or answer.get("type") != kind:
            gaps.append(f"{key}.type")
            continue
        if kind == "noul":
            if not probability(answer.get("noul")):
                gaps.append(f"{key}.noul")
            continue
        if not probability(answer.get("confidence")):
            gaps.append(f"{key}.confidence")
        criteria, probs = question["criteria"], answer.get("probabilities")
        if kind == "choice":
            if answer.get("choice") not in criteria:
                gaps.append(f"{key}.choice")
            valid = distribution(probs, criteria)
        else:
            val = answer.get("score")
            if (
                type(val) not in (int, float)
                or not math.isfinite(val)
                or not 0 <= val <= len(criteria) - 1
            ):
                gaps.append(f"{key}.score")
            valid = distribution(probs, [str(i) for i in range(len(criteria))])
        if not valid:
            gaps.append(f"{key}.probabilities")
    return identity, gaps


def call_shards(settings, store, run, attempt, quote, transport=network, sleep=time.sleep):
    if (transport is network) == store.fixture:
        raise ValueError("在线传输和合成测试必须使用独立数据库")
    refs, checks, gaps = [], [], []
    review = settings.review_status()
    admission = {
        "provider": settings.provider,
        "model": MODEL,
        "key_configured": bool(settings.keys.get(settings.provider)),
        "public_source_verified": bool(quote and quote["verified"]),
        "review": review,
        "planned_shards": [len(group) for group in split(questions())],
    }
    refs.append(
        store.record(
            attempt, "jev_admission", "configuration",
            {"question_set_version": VERSION, "method":"POST", "endpoint":PROVIDERS[settings.provider][0],
             "model":MODEL, "planned_question_ids":[list(group) for group in split(questions())],
             "request_kind":"local_preflight_only"}, admission
        )
    )
    reasons = []
    if not admission["key_configured"]:
        reasons.append(PROVIDERS[settings.provider][1] + " 未配置")
    if not review["approved"]:
        reasons.append("缺少该供应商的公开语料留存审查记录")
    if not admission["public_source_verified"]:
        reasons.append("未取得可核验公开原话")
    if reasons:
        return refs, checks, gaps, "；".join(reasons)
    for i, asked in enumerate(split(questions()), 1):
        payload = {"model": MODEL, "state": quote["text"], "questions": asked}
        try:
            key, prev = store.reserve(run, i, payload)
        except Conflict as exc:
            return refs, checks, gaps, str(exc)
        if prev and prev["state"] == "received":
            obj = json.loads(prev["response_json"])
            refs.append(prev["evidence_id"])
        elif prev and prev["state"] not in ("retryable",):
            return refs, checks, gaps, "上次请求的计费或契约状态待核对，请查看原始证据。"
        else:
            for n in range(3):
                response = outbound(
                    settings.provider,
                    labels=PUBLIC,
                    method="POST",
                    body=payload,
                    headers={
                        "Authorization": "Bearer " + settings.keys[settings.provider],
                        "Content-Type": "application/json",
                        "Idempotency-Key": key,
                    },
                    transport=transport,
                )
                obj = redact(response.body, list(settings.keys.values()))
                meta = {
                    "endpoint": PROVIDERS[settings.provider][0],
                    "provider": settings.provider,
                    "body": payload,
                    "split_index": i,
                    "idempotency_key": key,
                    "registry_version": REGISTRY,
                    "question_set_version": VERSION,
                    "mention_id": "forum-" + quote["post_id"],
                }
                evid = store.record(
                    attempt,
                    "jev_shard",
                    "live_http",
                    meta,
                    {
                        "body": obj,
                        "X-Tokens-Remaining": response.remaining,
                        "retry_after": response.retry_after,
                    },
                    response.status,
                )
                refs.append(evid)
                if response.status == 200:
                    usage = obj.get("usage") if isinstance(obj, dict) else None
                    tokens = number(usage.get("input_tokens")) if isinstance(usage, dict) else None
                    store.save_shard(key, "received", obj, tokens, response.remaining, evid)
                    break
                # Ambiguous upstream failures on accounts without documented idempotency need review.
                safe_retry = response.status == 429 or (
                    settings.provider == "jevmodel" and response.status == 502
                )
                wait = (
                    int(response.retry_after)
                    if response.retry_after and response.retry_after.isdecimal()
                    else 2**n
                )
                if n < 2 and safe_retry and wait <= 8:
                    sleep(max(1, wait))
                    continue
                state = (
                    "retryable" if safe_retry or response.status in (401, 402, 403, 422) else "uncertain"
                )
                store.save_shard(key, state, obj, None, None, evid)
                return (
                    refs,
                    checks,
                    gaps,
                    f"分片 {i} · {failure(response.status)}（HTTP {response.status or '无响应'}）",
                )
        version_ok, missing = validate(asked, obj)
        checks.append(version_ok)
        gaps.extend(missing)
        if not version_ok:
            break
    return refs, checks, gaps, None
