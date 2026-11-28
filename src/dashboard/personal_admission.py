"""Local read and stop controls for Personal synthetic acceptance batches."""

from contextlib import contextmanager
from datetime import UTC, datetime
import sqlite3
from uuid import UUID

from fastapi import HTTPException, Request

from src.dashboard.edition_access import PRE_ADMISSION, VALIDATION_BATCH, transaction_authorizer
from src.dashboard.personal_governance import governance_decision
from src.edition_policy import Permission
from src.raw_store.personal_validation import ACTIVE, CHANGES, LIMIT_FIELDS, BatchContext, Budget, ValidationLedger
from src.raw_store.store import Busy, Conflict


SCOPE_KEYS = {"scope_id", "scope_version"}
BUDGET_FIELDS = tuple(Budget.__dataclass_fields__)
PUBLIC_REASONS = frozenset({
    "batch_created", "operation_authorized", "send_authority_committed", "owner_paused", "owner_revoked",
    "send_outcome_unknown", "receipt_commit_unknown", "receipt_conflict", "charge_reconciled", "usage_over_budget",
    "restored_batch_requires_new_authorization",
})


def _bound_decision(decision, owner):
    try:
        return governance_decision(decision, owner)
    except (AttributeError, StopIteration):
        raise HTTPException(403, "当前项目授权已变化，请重新核对后操作。") from None


@contextmanager
def _access(request, target):
    decision = request.state.edition_decision
    scope = decision.scope
    if target.keys() != SCOPE_KEYS:
        raise HTTPException(422, "INVALID_GOVERNANCE_REQUEST")
    if target != {"scope_id": scope.scope_id, "scope_version": scope.scope_version}:
        raise HTTPException(404, "找不到获准的项目、范围或记录。")

    state = request.app.state
    authorize = transaction_authorizer(request)
    bound = _bound_decision(decision, state.edition_policy.owner)

    def recheck(db, _batch, _grant):
        authorize(db)
        if _bound_decision(decision, state.edition_policy.owner) != bound:
            raise HTTPException(403, "当前项目授权已变化，请重新核对后操作。")
        return True

    try:
        context = BatchContext(scope.study_id, scope.scope_id, scope.scope_version, bound.actor_ref,
                               bound.owner_ref, bound.evidence_refs[0], bound.policy_version)
        yield ValidationLedger(state.store), context, recheck
    except KeyError:
        raise HTTPException(404, "找不到获准的项目、范围或记录。") from None
    except Busy:
        raise HTTPException(409, "VALIDATION_BUSY") from None
    except Conflict:
        raise HTTPException(409, "VALIDATION_BATCH_CONFLICT") from None
    except sqlite3.Error:
        raise HTTPException(503, "VALIDATION_UNAVAILABLE") from None


def _authorization(batch, grant, binding, now):
    credential_current = binding is not None and all(
        binding[key] == grant[key] for key in ("account_ref", "channel_ref", "credential_revision")
    )
    window_open = (batch["starts_at"] <= now < batch["expires_at"]
                   and grant["valid_from"] <= now < grant["expires_at"])
    status = "inactive"
    if credential_current and window_open and batch["state"] in ACTIVE:
        status = "requires_execution_recheck"
    return {key: grant[key] for key in ("grant_id", "operation", "provider", "channel_ref", "account_ref")} | {
        "status": status, "credential_current": credential_current,
    }


def _request(request, receipt, reconciliation):
    actual = None
    if reconciliation is not None:
        actual = reconciliation["actual_units"]
        status = "settled"
    elif receipt is not None and receipt["actual_units"] is not None:
        actual = receipt["actual_units"]
        status = "recorded"
    elif request["state"] in {"claimed", "reconciliation", "settled"}:
        status = "unverified"
    else:
        status = "not_applicable"
    return {
        "request_id": request["request_id"], "operation": request["operation"], "status": request["state"],
        "reconciliation_status": status, "estimated_units": str(request["units"]),
        "actual_units": None if actual is None else str(actual),
    }


def _projection(view, writable, now):
    batch = view["batch"]
    writable = writable and batch["mode"] == "engineering_fixture"
    state = batch["state"]
    reason = batch["state_reason"]
    if reason not in PUBLIC_REASONS:
        reason = "blocked_reason_restricted" if state in {"blocked", "reconciliation"} else None
    bindings = {(item["operation"], item["provider"]): item for item in view["credentials"]}
    receipts = {item["request_id"]: item for item in view["receipts"]}
    reconciliations = {item["request_id"]: item for item in view["reconciliations"]}
    return {
        "batch_id": batch["batch_id"], "status": state, "reason": reason, "mode": batch["mode"],
        "can_pause": writable and "paused" in CHANGES[state], "can_revoke": writable and "revoked" in CHANGES[state],
        "budget": {key: str(batch[column]) for key, column in zip(BUDGET_FIELDS, LIMIT_FIELDS, strict=True)},
        "used": {key: str(value) for key, value in view["spent"].items()},
        "currency": batch["currency"], "decimals": batch["decimals"], "single_cost": str(batch["single_cost"]),
        "authorizations": [
            _authorization(batch, grant, bindings.get((grant["operation"], grant["provider"])), now)
            for grant in view["grants"]
        ],
        "requests": [_request(item, receipts.get(item["request_id"]), reconciliations.get(item["request_id"]))
                     for item in view["requests"]],
        "evidence": [{"check_id": item["requirement"], "kind": item["kind"], "evidence_ref": item["evidence_ref"],
                      "status": "MISSING" if item["kind"] == "missing" else "ENGINEERING_EVIDENCE"}
                     for item in view["evidence"]],
    }


def register_personal_admission(app):
    @app.get(PRE_ADMISSION)
    def batches(request: Request):
        query = request.query_params
        if any(len(query.getlist(key)) != 1 for key in SCOPE_KEYS):
            raise HTTPException(422, "INVALID_GOVERNANCE_REQUEST")
        with _access(request, dict(query)) as (ledger, context, recheck):
            views = ledger.views(context, recheck)
            writable = Permission.WRITE_PERSONAL_APPROVALS in request.state.edition_decision.data_permissions
            now = datetime.now(UTC).isoformat(timespec="microseconds")
            projected = [_projection(view, writable, now) for view in views]
            with ledger.store.db() as db:
                recheck(db, None, None)
        mode = "formal_owner_command" if any(item["mode"] == "formal_live" for item in projected) else "synthetic_only"
        return {"batches": projected, "mode": mode, "formal_gate": "NOT_EVALUATED"}

    def stop(request, validation_batch_id, body, state, reason):
        with _access(request, body) as (ledger, context, recheck):
            batch = ledger.transition(str(validation_batch_id), context, state, reason, recheck)
        return {"batch_id": batch["batch_id"], "status": batch["state"]}

    @app.post(VALIDATION_BATCH + "/pause")
    def pause(request: Request, validation_batch_id: UUID, body: dict):
        return stop(request, validation_batch_id, body, "paused", "owner_paused")

    @app.post(VALIDATION_BATCH + "/revoke")
    def revoke(request: Request, validation_batch_id: UUID, body: dict):
        return stop(request, validation_batch_id, body, "revoked", "owner_revoked")
