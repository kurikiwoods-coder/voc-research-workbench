"""Validation of the Owner's Personal live batch authorization."""

from dataclasses import astuple

from src.edition_policy import REFERENCE
from src.raw_store.personal_validation import MAX_INTEGER, OPERATIONS, Budget, _hash
from src.raw_store.store import Conflict


BINDING_FIELDS = ("provider", "account_ref", "channel_ref", "credential_revision")
SLOT_FIELDS = {*BINDING_FIELDS, "limit", "account_limit"}
SLOT_KEYS = {"search/1", "source/1", "model/1", "model/2"}
RISK_REFERENCES = {"dedicated_token_ref", "billing_rules_ref", "allowance_ref", "risk_acceptance_ref"}
RISK_NUMBERS = {"rate_basis_tokens", "input_rate_units", "output_rate_units",
                "additional_units_per_request", "allowance_units", "residual_risk_units"}
RISK_FLAGS = {"overdraft", "auto_recharge", "unbounded_charges"}


def _reference(value):
    return isinstance(value, str) and REFERENCE.fullmatch(value)


def _ceil_rate(tokens, rate, basis):
    return (tokens * rate + basis - 1) // basis


def validate_batch_policy(policy, budget, single_cost):
    if (not isinstance(policy, dict) or policy.keys() != {"slots", "search_payload_sha256", "systemone"}
            or not isinstance(policy["slots"], dict) or policy["slots"].keys() != SLOT_KEYS):
        raise Conflict("LIVE_BATCH_POLICY_INVALID")
    _hash(policy["search_payload_sha256"])
    plans, limits = policy["slots"], {}
    for key, plan in plans.items():
        operation = key.split("/")[0]
        if (not isinstance(plan, dict) or plan.keys() != SLOT_FIELDS
                or plan["provider"] != OPERATIONS[operation]
                or not all(_reference(plan[field]) for field in BINDING_FIELDS)):
            raise Conflict("LIVE_BATCH_SLOT_INVALID")
        limit, account = Budget(**plan["limit"]), Budget(**plan["account_limit"])
        if (limit.requests != 1 or not account.accommodates((0,) * 6, limit)
                or limit.total_tokens != limit.input_tokens + limit.output_tokens or limit.units > single_cost):
            raise Conflict("LIVE_BATCH_SLOT_BUDGET_INVALID")
        limits[key] = limit
    search, source = limits["search/1"], limits["source/1"]
    if (search.credits != 1 or search.total_tokens or source != Budget(1, 0, 0, 0, 0, 0)
            or not plans["source/1"]["credential_revision"].startswith("anonymous-")):
        raise Conflict("LIVE_BATCH_SOURCE_LIMIT_INVALID")
    if budget.requests != 4 or not budget.accommodates((0,) * 6, Budget(*map(sum, zip(
            *(astuple(limit) for limit in limits.values()), strict=True)))):
        raise Conflict("LIVE_BATCH_SLOT_BUDGET_INVALID")

    risk = policy["systemone"]
    if (not isinstance(risk, dict) or risk.keys() != RISK_REFERENCES | RISK_NUMBERS | RISK_FLAGS | {"approval_event_id"}
            or not all(_reference(risk[field]) for field in RISK_REFERENCES | {"approval_event_id"})
            or any(type(risk[field]) is not int or not 0 <= risk[field] <= MAX_INTEGER for field in RISK_NUMBERS)
            or any(risk[field] is not False for field in RISK_FLAGS)
            or not risk["rate_basis_tokens"] or not risk["allowance_units"]):
        raise Conflict("LIVE_SYSTEMONE_RISK_UNVERIFIED")
    first, second = limits["model/1"], limits["model/2"]
    model_plan = plans["model/1"]
    account = Budget(**model_plan["account_limit"])
    if (any(model_plan[field] != plans["model/2"][field] for field in BINDING_FIELDS + ("account_limit",))
            or model_plan["channel_ref"] != "typesafe-officially"
            or not account.accommodates(astuple(first), second)
            or account.units > risk["allowance_units"] - risk["residual_risk_units"]):
        raise Conflict("LIVE_SYSTEMONE_ACCOUNT_LIMIT_INVALID")
    for limit in (first, second):
        basis = risk["rate_basis_tokens"]
        required = (
            _ceil_rate(limit.input_tokens, risk["input_rate_units"], basis)
            + _ceil_rate(limit.output_tokens, risk["output_rate_units"], basis)
            + risk["additional_units_per_request"]
        )
        if limit.credits or not limit.input_tokens or not limit.output_tokens or limit.units < required:
            raise Conflict("LIVE_SYSTEMONE_RESERVATION_INSUFFICIENT")
