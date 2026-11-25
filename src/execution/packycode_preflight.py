"""One-shot local SystemOne check with a fixed, synthetic request."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from src.config import MODEL, PACKYCODE_CONTRACT, PROVIDERS, ROOT, Settings
from src.execution.jev import input_tokens, output_tokens, probability, questions, split, validate
from src.execution.transport import Denied, failure, network
from src.raw_store.credentials import CredentialVault, VaultError
from src.raw_store.store import Busy, Store, dump


PROBE_DIRECTORY = ROOT / "runtime" / "packycode-preflight"
REQUEST_KEY = "g1-r-b-p-owner-2026-11-25"
INPUT_LIMIT = 100_000
NEXT_INPUT_ESTIMATE = 65_536
TOKEN_QUOTA_LIMIT = Decimal("2")
NEXT_COST_ESTIMATE = Decimal("0.02")
BALANCE_DISPLAY_ROUNDING = Decimal("0.005")
PROVIDER = "packycode"
ENDPOINT = "https://cf.api.fan/v1/systemone"
SYNTHETIC_STATE = "Fictional test scene: a paper robot asks for help removing a purple sticker from an imaginary measuring cup."
FIXED = {
    "provider": PROVIDER, "group": "typesafe-officially", "model": "jev-1.14.0",
    "endpoint": ENDPOINT, "protocol": "SystemOne",
}
REQUIRED_CHECKS = ("synthetic_use_permitted", "current_key_entitled", "quota_available")


def usd(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}(?:\.\d{1,8})?", value, re.ASCII):
        raise ValueError("Invalid USD amount")
    return Decimal(value)


def read_evidence(path, vault_revision):
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(8193)
        if len(raw) > 8192:
            raise ValueError
        evidence = json.loads(raw)
        expires = datetime.fromisoformat(evidence["expires_at"])
        quota = usd(evidence["token_quota_usd"])
        remaining = usd(evidence["token_remaining_usd"])
        reference = evidence["evidence_reference"]
        if (
            set(evidence) == set(FIXED) | set(REQUIRED_CHECKS) | {
                "expires_at", "evidence_reference", "vault_sha256", "token_quota_usd",
                "token_remaining_usd", "quota_resets",
            }
            and all(evidence[field] == value for field, value in FIXED.items())
            and all(evidence[field] is True for field in REQUIRED_CHECKS)
            and isinstance(vault_revision, str) and re.fullmatch(r"[0-9a-f]{64}", vault_revision)
            and evidence["vault_sha256"] == vault_revision
            and NEXT_COST_ESTIMATE <= remaining <= quota <= TOKEN_QUOTA_LIMIT
            and evidence["quota_resets"] is False
            and isinstance(reference, str) and reference.strip()
            and expires.tzinfo is not None and expires > datetime.now(timezone.utc)
        ):
            return quota, remaining, expires, sha256(raw).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        pass
    raise Denied("缺少当前账户和独立小额一次性令牌的额度证据。")


def confirmed_legend(answer, criteria):
    legend = answer.get("legend")
    return legend == {str(index): label for index, label in enumerate(criteria)}


def inspect_body(asked, body):
    identity_ok, gaps = validate(asked, body)
    if not identity_ok:
        gaps.append("model_or_question_ids")
    body = body if isinstance(body, dict) else {}
    answers = body.get("answers")
    answers = answers if isinstance(answers, dict) else {}
    kept = {}
    for name, question in asked.items():
        answer = answers.get(name)
        kind = question["type"]
        if not isinstance(answer, dict) or answer.get("type") != kind:
            continue
        item = {"type": kind}
        if kind == "noul":
            if probability(answer.get("noul")):
                item["noul"] = answer["noul"]
        else:
            criteria = question["criteria"]
            codes = criteria if kind == "choice" else [str(index) for index in range(len(criteria))]
            probs = answer.get("probabilities")
            if isinstance(probs, dict):
                item["probabilities"] = {
                    code: probs[code] for code in codes if probability(probs.get(code))
                }
            if probability(answer.get("confidence")):
                item["confidence"] = answer["confidence"]
            if kind == "choice" and isinstance(answer.get("choice"), str) and answer["choice"] in criteria:
                item["choice"] = answer["choice"]
            if kind == "score":
                score = answer.get("score")
                if type(score) in (float, int) and 0 <= score <= len(criteria) - 1:
                    item["score"] = score
                if confirmed_legend(answer, criteria):
                    item["legend"] = answer["legend"]
                else:
                    gaps.append(f"{name}.legend")
        kept[name] = item
    model = body.get("model")
    model = model if isinstance(model, str) and re.fullmatch(r"jev-(?:\d{1,4}\.){1,3}\d{1,4}", model, re.ASCII) else None
    return {
        "model": model,
        "answers": kept,
        "usage": {"input_tokens": input_tokens(body), "output_tokens": output_tokens(body)},
    }, gaps


def latest_receipt(store, run_id):
    row = store.one(
        """SELECT e.response_json FROM evidence e JOIN attempts a ON a.id=e.attempt_id
           WHERE a.run_id=? AND e.name='packycode_preflight_receipt'
           ORDER BY e.id DESC LIMIT 1""", (run_id,),
    )
    return json.loads(row["response_json"]) if row else {}


def receipt(store):
    run = store.one("SELECT id FROM runs WHERE request_key=?", (REQUEST_KEY,))
    result = {
        **FIXED, "status": "NOT_TESTED", "scope": "synthetic_interface_preflight",
        "planned_shards": [8, 3], "input_budget_target": INPUT_LIMIT,
        "actual_charge": None, "balance": None, "research_denominator": 0,
    }
    if run is None:
        return result
    ledger = store.ledger(run["id"])
    summary = latest_receipt(store, run["id"])
    if len(ledger) > len(summary.get("shards", [])):
        summary.update(status="INTERRUPTED_OR_RUNNING", stop_reason=None)
    return {
        **result, "status": "INTERRUPTED_OR_RUNNING", "run_id": run["id"],
        "posts_reserved": len(ledger),
        "ledger": [{"shard": row["shard_no"], "state": row["state"], "evidence_id": row["evidence_id"]}
                   for row in ledger],
        **summary,
    }


def fixed_payload(asked):
    return {"model": MODEL, "state": SYNTHETIC_STATE, "questions": asked}


def billing_settlement(reconcile, shard, starting_balance, quota):
    try:
        charge, remaining = map(usd, reconcile(shard) if reconcile else ())
    except (TypeError, ValueError, EOFError):
        return None
    expected = starting_balance - charge
    if (charge <= 0 or expected < 0 or remaining > quota
            or abs(remaining - expected) > BALANCE_DISPLAY_ROUNDING):
        return None
    return charge, remaining, expected


def settlement_record(charge, remaining):
    return {"charged_usd": str(charge), "token_remaining_usd": str(remaining)}


def first_shard_checkpoint(store, run, asked, proof_hash):
    ledger = store.ledger(run)
    summary = latest_receipt(store, run)
    if (len(ledger) != 1 or ledger[0]["shard_no"] != 1 or ledger[0]["state"] != "received"
            or summary.get("status") != "BLOCKED"
            or summary.get("stop_reason") != "first_shard_billing_unverified"):
        raise Denied("原账本须停在首片对账点，且第二片从未预约。")
    first = ledger[0]
    success = store.recorded_shard_success(run, first["request_key"])
    proof = store.one(
        """SELECT p.response_json FROM evidence p JOIN evidence s ON s.attempt_id=p.attempt_id
           WHERE s.id=? AND p.name='packycode_preflight_permission'""", (first["evidence_id"],),
    )
    payload = fixed_payload(asked)
    if (not success or success["id"] != first["evidence_id"] or not proof
            or json.loads(proof["response_json"])["evidence_sha256"] != proof_hash
            or json.loads(success["request_json"]) != {
                **FIXED, "body": payload, "idempotency_key": f"{run}-shard-1",
            }):
        raise Denied("首片请求或本机账户核验材料与原账本不一致。")
    archived = json.loads(success["response_json"])
    body, gaps = inspect_body(asked, archived["body"])
    if (archived["schema_gaps"] or gaps or not body["usage"]["input_tokens"]
            or body["usage"]["input_tokens"] != first["tokens"]
            or body["usage"]["output_tokens"] is None):
        raise Denied("首片响应或用量证据不完整。")
    shard = {"shard": 1, "question_ids": list(asked), "http_status": 200,
             "response_model": body["model"], "schema_gaps": [], "evidence_id": success["id"],
             **body["usage"]}
    if summary.get("shards") != [shard] or summary.get("answers") != body["answers"]:
        raise Denied("首片总回执与分片证据不一致。")
    return shard, body["answers"]


def run_preflight(store, key, evidence_path, *, vault_revision, recheck_vault=None,
                  reconcile=None, resume_second=False, transport=network):
    if not store.diagnostic or (transport is network) == store.fixture:
        raise Denied("预检传输必须使用独立诊断库。")
    if transport is network and (
        recheck_vault is None or store.path != PROBE_DIRECTORY / "api-diagnostics" / "connectivity.sqlite3"
    ):
        raise Denied("真实预检必须使用本机凭证库和固定账本。")
    if not isinstance(key, str) or not re.fullmatch(r"[\x21-\x7e]+", key):
        raise Denied("当前本机 PackyCode 凭证不可用。")
    if (PROVIDERS[PROVIDER][0] != ENDPOINT or MODEL != FIXED["model"]
            or PACKYCODE_CONTRACT["group"] != FIXED["group"]):
        raise Denied("连接器配置与预检授权不一致。")
    planned = split(questions())
    if [len(group) for group in planned] != [8, 3]:
        raise Denied("合成题组与批准的 8+3 分片不一致。")
    quota, starting_balance, expires, proof_hash = read_evidence(evidence_path, vault_revision)
    settings = Settings(store.directory, PROVIDER, {PROVIDER: key})
    with store.writer():
        shards, combined = [], {}
        settlement = None
        total = 0
        stop_reason = None
        if resume_second:
            original = store.one("SELECT id, account_tag FROM runs WHERE request_key=?", (REQUEST_KEY,))
            if not original or original["account_tag"] != settings.account_tag():
                raise Denied("未找到同一凭证绑定的原合成批次。")
            first, combined = first_shard_checkpoint(store, original["id"], planned[0], proof_hash)
            shards.append(first)
            total = first["input_tokens"]
            if total + NEXT_INPUT_ESTIMATE > INPUT_LIMIT:
                raise Denied("首片实报用量加第二片预算超过本地目标。")
            billed = billing_settlement(reconcile, first, starting_balance, quota)
            if billed is None:
                raise Denied("首片实扣与测试令牌当前余额尚未对账。")
            charge, remaining, expected = billed
            if min(remaining, expected) < NEXT_COST_ESTIMATE:
                raise Denied("测试令牌额度不足以执行第二片。")
            run, attempt = store.begin(REQUEST_KEY, settings, resume_id=original["id"])
            if attempt is None:
                return receipt(store)
            settlement = settlement_record(charge, remaining)
            store.record(attempt, "packycode_preflight_first_settlement", "synthetic_interface_preflight",
                         {"shard_evidence_id": first["evidence_id"]}, settlement)
        else:
            run, attempt = store.begin(REQUEST_KEY, settings)
            if attempt is None:
                return receipt(store)
            store.record(attempt, "packycode_preflight_permission", "synthetic_interface_preflight",
                         FIXED, {"evidence_sha256": proof_hash, "token_quota_usd": str(quota),
                                 "token_remaining_usd": str(starting_balance),
                                 "input_budget_target": INPUT_LIMIT, "expires_at": expires.isoformat()})
        for shard_no, asked in enumerate(planned[len(shards):], len(shards) + 1):
            if datetime.now(timezone.utc) >= expires:
                stop_reason = "account_evidence_expired"
                break
            if recheck_vault is not None:
                try:
                    current_revision = recheck_vault()
                except (OSError, Denied):
                    current_revision = None
                if current_revision != vault_revision:
                    stop_reason = "account_configuration_changed"
                    break
            payload = fixed_payload(asked)
            shard_key, existing = store.reserve(run, shard_no, payload)
            if existing is not None:
                raise Denied("分片已登记。本授权不允许重发。")
            try:
                response = transport("POST", ENDPOINT, payload, {
                    "Authorization": "Bearer " + key, "Content-Type": "application/json",
                    "Idempotency-Key": shard_key,
                })
                status, body = response.status, response.body
            except Exception:
                status, body = None, None
            safe_body, gaps = inspect_body(asked, body if status == 200 else None)
            used = safe_body["usage"]["input_tokens"]
            if status != 200:
                stop_reason = failure(status)
                gaps = []
            else:
                if not used:
                    gaps.append("usage.input_tokens")
                if safe_body["usage"]["output_tokens"] is None:
                    gaps.append("usage.output_tokens")
                if gaps:
                    stop_reason = "response_contract"
            evidence_id = store.record_shard_response(
                attempt, shard_key, {**FIXED, "body": payload, "idempotency_key": shard_key},
                {"body": safe_body, "schema_gaps": gaps}, status,
                state="received" if status == 200 else "uncertain", tokens=used,
            )
            shards.append({"shard": shard_no, "question_ids": list(asked), "http_status": status,
                           "response_model": safe_body["model"], "schema_gaps": gaps,
                           "evidence_id": evidence_id, **safe_body["usage"]})
            if stop_reason:
                break
            total += used
            combined.update(safe_body["answers"])
            if total + (NEXT_INPUT_ESTIMATE if shard_no == 1 else 0) > INPUT_LIMIT:
                stop_reason = "input_budget_projection"
                break
            if shard_no == 1:
                billed = billing_settlement(reconcile, shards[-1], starting_balance, quota)
                if billed is None:
                    stop_reason = "first_shard_billing_unverified"
                    break
                charge, remaining, expected_remaining = billed
                settlement = settlement_record(charge, remaining)
                store.record(attempt, "packycode_preflight_first_settlement", "synthetic_interface_preflight",
                             {"shard_evidence_id": evidence_id}, settlement)
                if min(remaining, expected_remaining) < NEXT_COST_ESTIMATE:
                    stop_reason = "token_quota_insufficient_for_second_shard"
                    break
        passed = len(shards) == 2 and stop_reason is None
        store.record(attempt, "packycode_preflight_receipt", "synthetic_interface_preflight", {}, {
            "status": "PASS" if passed else "BLOCKED", "stop_reason": stop_reason,
            "shards": shards, "answers": combined, "first_shard_settlement": settlement,
            **{
                field: sum(shard[field] for shard in shards)
                if all(shard[field] is not None for shard in shards) else None
                for field in ("input_tokens", "output_tokens")
            },
        })
        store.finish(run, attempt, passed)
        return receipt(store)


def encrypted_vault_revision(vault):
    with vault.path.open("rb") as handle:
        ciphertext = handle.read(4 * 1024 * 1024 + 1)
    if not 0 < len(ciphertext) <= 4 * 1024 * 1024:
        raise Denied("无法核对本机 DPAPI 凭证库版本。")
    return sha256(ciphertext).hexdigest()


def reconcile_first(shard):
    print(dump({"status": "FIRST_SHARD_BILLING_CHECK", "shard": shard}), flush=True)
    return input("PackyAPI 消费明细的首片扣费和令牌余额（USD，用空格分隔。未知时回车）：").split()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true", help="Use the single live authorization.")
    action.add_argument("--resume-second", action="store_true", help="Continue only the unused second shard.")
    parser.add_argument("--account-evidence", type=Path, help="Local verification record, without credentials.")
    args = parser.parse_args()
    live = args.execute or args.resume_second
    if live != (args.account_evidence is not None):
        parser.error("A live action and --account-evidence must be given together")
    try:
        if live:
            if os.name != "nt":
                raise Denied("真实预检需要本机 Windows 普通用户会话与 DPAPI 凭证。")
            vault = CredentialVault(Path(os.getenv("VOC_DATA_DIR") or ROOT / "runtime").resolve())
            revision = encrypted_vault_revision(vault)
            read_evidence(args.account_evidence, revision)
            creds = vault.read()
            if encrypted_vault_revision(vault) != revision:
                raise Denied("本机 DPAPI 凭证库在核对期间发生变化。")
            if creds.get("provider") != PROVIDER:
                raise Denied("请先在本机 API 配置中心选择 PackyCode。")
            store = Store(PROBE_DIRECTORY, diagnostic=True)
            result = run_preflight(
                store, creds["keys"].get(PROVIDER), args.account_evidence, vault_revision=revision,
                recheck_vault=lambda: encrypted_vault_revision(vault),
                reconcile=reconcile_first, resume_second=args.resume_second,
            )
        else:
            result = receipt(Store(PROBE_DIRECTORY, diagnostic=True))
    except (Denied, Busy, VaultError) as exc:
        result = {"status": "BLOCKED", "message": str(exc)}
    except (OSError, ValueError, sqlite3.Error):
        result = {"status": "BLOCKED", "message": "无法读取本机配置或账本，请先核对本机状态。"}
    print(dump(result))
    return 0 if result["status"] in ("NOT_TESTED", "PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
