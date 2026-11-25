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
    summary = store.one(
        """SELECT e.response_json FROM evidence e JOIN attempts a ON a.id=e.attempt_id
           WHERE a.run_id=? AND e.name='packycode_preflight_receipt'""", (run["id"],),
    )
    return {
        **result, "status": "INTERRUPTED_OR_RUNNING", "run_id": run["id"],
        "posts_reserved": len(ledger),
        "ledger": [{"shard": row["shard_no"], "state": row["state"], "evidence_id": row["evidence_id"]}
                   for row in ledger],
        **(json.loads(summary["response_json"]) if summary else {}),
    }


def run_preflight(store, key, evidence_path, *, vault_revision, recheck_vault=None,
                  reconcile=None, transport=network):
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
    with store.writer():
        run, attempt = store.begin(REQUEST_KEY, Settings(store.directory, PROVIDER, {PROVIDER: key}))
        if attempt is None:
            return receipt(store)
        store.record(attempt, "packycode_preflight_permission", "synthetic_interface_preflight",
                     FIXED, {"evidence_sha256": proof_hash, "token_quota_usd": str(quota),
                             "token_remaining_usd": str(starting_balance),
                             "input_budget_target": INPUT_LIMIT, "expires_at": expires.isoformat()})
        shards, combined = [], {}
        settlement = None
        total = 0
        stop_reason = None
        for shard_no, asked in enumerate(planned, 1):
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
            payload = {"model": MODEL, "state": SYNTHETIC_STATE, "questions": asked}
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
                try:
                    charge, remaining = map(usd, reconcile(shards[-1]) if reconcile else ())
                    expected_remaining = starting_balance - charge
                    if charge <= 0 or expected_remaining < 0 or (
                        abs(remaining - expected_remaining) > BALANCE_DISPLAY_ROUNDING
                    ):
                        raise ValueError
                except (TypeError, ValueError, EOFError):
                    stop_reason = "first_shard_billing_unverified"
                    break
                settlement = {"charged_usd": str(charge), "token_remaining_usd": str(remaining)}
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
    parser.add_argument("--execute", action="store_true", help="Use the single live authorization.")
    parser.add_argument("--account-evidence", type=Path, help="Local verification record, without credentials.")
    args = parser.parse_args()
    if args.execute != (args.account_evidence is not None):
        parser.error("--execute and --account-evidence must be given together")
    try:
        if args.execute:
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
                reconcile=reconcile_first,
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
