from contextlib import contextmanager
from dataclasses import asdict, astuple, dataclass
from datetime import UTC, datetime
import json
import re
import sqlite3
from uuid import uuid4

from src.edition_policy import Edition, REFERENCE, SCOPE_VERSION, canonical_uuid
from src.raw_store.store import Conflict, dump


MAX_INTEGER = 2**63 - 1
OPERATIONS = {"search": "tavily", "source": "stackexchange", "model": "packycode"}
LIMIT_FIELDS = ("request_limit", "credit_limit", "input_limit", "output_limit", "token_limit", "cost_limit")
REQUIREMENTS = tuple(f"C0-{number}" for number in range(1, 7))
ACTIVE = {"approved", "executing"}
CHANGES = {
    "draft": {"paused", "revoked", "blocked"},
    "approved": {"paused", "revoked", "blocked"},
    "executing": {"paused", "revoked", "blocked", "evidence_review"},
    "paused": {"approved", "revoked", "blocked"},
    "blocked": {"approved", "revoked", "paused"},
    "reconciliation": {"revoked", "paused"},
    "evidence_review": {"complete", "revoked", "paused"},
    "complete": {"revoked"},
    "revoked": set(),
}


def _integer(value, *, optional=False):
    if optional and value is None:
        return
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        raise ValueError("INVALID_BUDGET_VALUE")


def _ref(value, *, empty=False):
    if empty and value == "":
        return
    if not isinstance(value, str) or not REFERENCE.fullmatch(value):
        raise ValueError("INVALID_VALIDATION_REFERENCE")


def _hash(value, *, optional=False):
    if optional and value is None:
        return
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("INVALID_VALIDATION_DIGEST")


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_VALIDATION_WINDOW")
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("INVALID_VALIDATION_WINDOW") from None
    if at.utcoffset() != UTC.utcoffset(at):
        raise ValueError("INVALID_VALIDATION_WINDOW")
    return at.isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Budget:
    requests: int
    credits: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    units: int

    def __post_init__(self):
        for value in astuple(self):
            _integer(value)

    def accommodates(self, used, next_budget):
        return all(old + new <= cap for old, new, cap in zip(used, astuple(next_budget), astuple(self), strict=True))


@dataclass(frozen=True)
class BatchContext:
    study_id: str
    scope_id: str
    scope_version: str
    actor_ref: str
    owner_ref: str
    authorization_ref: str
    policy_version: str

    def __post_init__(self):
        if (not isinstance(self.study_id, str) or not isinstance(self.scope_id, str)
                or canonical_uuid(self.study_id) != self.study_id or canonical_uuid(self.scope_id) != self.scope_id
                or not isinstance(self.scope_version, str) or not SCOPE_VERSION.fullmatch(self.scope_version)):
            raise ValueError("INVALID_VALIDATION_SCOPE")
        for value in (self.actor_ref, self.owner_ref, self.authorization_ref):
            _ref(value)
        if (not isinstance(self.policy_version, str)
                or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", self.policy_version)):
            raise ValueError("INVALID_VALIDATION_POLICY")


@dataclass(frozen=True)
class OperationGrant:
    operation: str
    provider: str
    account_ref: str
    channel_ref: str
    credential_revision: str
    model: str
    approval_event_id: str | None
    material_revision: str
    source_ref: str
    source_sha256: str
    payload_sha256: str
    question_version: str
    valid_from: str
    expires_at: str
    limit: Budget
    evidence_ref: str
    slot: int = 1
    account_limit: Budget | None = None
    depends_on: str | None = None
    depends_on_sha256: str | None = None

    def __post_init__(self):
        if OPERATIONS.get(self.operation) != self.provider:
            raise ValueError("INVALID_VALIDATION_OPERATION")
        if type(self.slot) is not int or self.slot not in ({1, 2} if self.operation == "model" else {1}):
            raise ValueError("INVALID_VALIDATION_SLOT")
        for value in (self.account_ref, self.channel_ref, self.material_revision, self.source_ref, self.evidence_ref):
            _ref(value)
        _ref(self.credential_revision)
        _ref(self.question_version, empty=self.operation != "model")
        _hash(self.payload_sha256)
        _hash(self.source_sha256)
        _hash(self.depends_on_sha256, optional=True)
        if self.depends_on is not None and canonical_uuid(self.depends_on) != self.depends_on:
            raise ValueError("INVALID_VALIDATION_DEPENDENCY")
        if (self.depends_on is None) != (self.depends_on_sha256 is None):
            raise ValueError("INVALID_VALIDATION_DEPENDENCY")
        if self.approval_event_id is not None and canonical_uuid(self.approval_event_id) != self.approval_event_id:
            raise ValueError("INVALID_VALIDATION_APPROVAL")
        if self.operation == "model":
            if (self.channel_ref, self.model) != ("typesafe-officially", "jev-1.14.0"):
                raise ValueError("INVALID_VALIDATION_MODEL")
            if self.slot == 2 and self.depends_on is None:
                raise ValueError("INVALID_VALIDATION_DEPENDENCY")
        elif self.model or self.question_version:
            raise ValueError("INVALID_VALIDATION_MODEL")
        if self.operation == "model" and self.approval_event_id is None:
            raise ValueError("INVALID_VALIDATION_APPROVAL")


@dataclass(frozen=True)
class Receipt:
    response_sha256: str
    response_status: int | None
    evidence_ref: str
    provider_request_id: str | None = None
    model: str = ""
    credits: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    actual_units: int | None = None
    balance_status: str = "unsynced"
    valid: bool = False
    reason: str = "schema_gap"
    source_sha256: str | None = None
    quote_sha256: str | None = None

    def __post_init__(self):
        for digest in (self.source_sha256, self.quote_sha256):
            _hash(digest, optional=True)
        _hash(self.response_sha256)
        for value in (self.credits, self.input_tokens, self.output_tokens, self.total_tokens, self.actual_units):
            _integer(value, optional=True)
        if self.response_status is not None and (
            type(self.response_status) is not int or not 100 <= self.response_status <= 599
        ):
            raise ValueError("INVALID_VALIDATION_STATUS")
        for value in (self.evidence_ref, self.reason):
            _ref(value)
        _ref(self.model, empty=True)
        if self.provider_request_id is not None:
            _ref(self.provider_request_id)
        if type(self.valid) is not bool or self.balance_status not in ("unsynced", "verified", "not_applicable"):
            raise ValueError("INVALID_VALIDATION_RECEIPT")


def _one(db, sql, values=()):
    row = db.execute(sql, values).fetchone()
    return dict(row) if row is not None else None


def _insert(db, table, values):
    columns = ", ".join(values)
    placeholders = ", ".join("?" for name in values)
    db.execute(f"INSERT INTO personal_validation_{table} ({columns}) VALUES ({placeholders})", tuple(values.values()))


def _budget(row):
    return Budget(*(row[field] for field in LIMIT_FIELDS))


def _limits(budget):
    return dict(zip(LIMIT_FIELDS, astuple(budget), strict=True))


def _require(recheck, db, batch=None, grant=None):
    if not recheck(db, batch, grant):
        raise Conflict("VALIDATION_AUTHORITY_CHANGED")


def _scope(context):
    return context.study_id, context.scope_id, context.scope_version


REQUEST_QUERY = """
    SELECT q.*, (SELECT state FROM personal_validation_request_events
                 WHERE request_id=q.request_id ORDER BY sequence DESC LIMIT 1) AS state
    FROM personal_validation_requests q
"""
BATCH_QUERY = """
    SELECT b.*, (SELECT state FROM personal_validation_batch_events
                 WHERE batch_id=b.batch_id ORDER BY sequence DESC LIMIT 1) AS state,
                (SELECT reason FROM personal_validation_batch_events
                 WHERE batch_id=b.batch_id ORDER BY sequence DESC LIMIT 1) AS state_reason
    FROM personal_validation_batches b
"""


class ValidationLedger:
    def __init__(self, store, *, engineering_fixture=False, clock=None):
        if store.edition != Edition.PERSONAL or store.fixture or store.diagnostic:
            raise ValueError("PERSONAL_WORKSPACE_REQUIRED")
        self.store = store
        self.engineering_fixture = engineering_fixture is True
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self):
        return self.clock().astimezone(UTC).isoformat(timespec="microseconds")

    @contextmanager
    def _transaction(self):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def batch(self, db, batch_id, context):
        result = _one(db, BATCH_QUERY + " WHERE b.batch_id=? AND b.study_id=? AND b.scope_id=? AND b.scope_version=?",
                      (batch_id, *_scope(context)))
        if result is None:
            raise KeyError(batch_id)
        if any(result[field] != getattr(context, field) for field in (
            "actor_ref", "owner_ref", "authorization_ref", "policy_version"
        )):
            raise Conflict("VALIDATION_AUTHORITY_CHANGED")
        return result

    @staticmethod
    def grant(db, batch_id, grant_id):
        result = _one(db, "SELECT * FROM personal_validation_grants WHERE batch_id=? AND grant_id=?", (batch_id, grant_id))
        if result is None:
            raise KeyError(grant_id)
        return result

    def _batch_event(self, db, batch, state, reason):
        if batch["state"] != state and batch["state"] != "revoked":
            _insert(db, "batch_events", {
                "batch_id": batch["batch_id"], "state": state, "reason": reason,
                "actor_ref": batch["actor_ref"], "occurred_at": self._now(),
            })

    def _request_event(self, db, request_id, state, reason):
        _insert(db, "request_events", {"request_id": request_id, "state": state, "reason": reason, "occurred_at": self._now()})

    def draft(self, context, starts_at, expires_at, budget, currency, decimals, single_cost, evidence_ref, recheck):
        starts_at, expires_at = _utc(starts_at), _utc(expires_at)
        if not starts_at < expires_at or expires_at <= self._now():
            raise ValueError("INVALID_VALIDATION_WINDOW")
        if (not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None
                or type(decimals) is not int or not 0 <= decimals <= 9):
            raise ValueError("INVALID_VALIDATION_CURRENCY")
        _integer(single_cost)
        _ref(evidence_ref)
        if single_cost > budget.units:
            raise ValueError("INVALID_BUDGET_VALUE")
        value = asdict(context) | {
            "batch_id": str(uuid4()), "starts_at": starts_at, "expires_at": expires_at,
            "created_at": self._now(), **_limits(budget), "single_cost": single_cost,
            "currency": currency, "decimals": decimals, "evidence_ref": evidence_ref,
        }
        with self._transaction() as db:
            _require(recheck, db)
            _insert(db, "batches", value)
            self._batch_event(db, value | {"state": None}, "draft", "batch_created")
            return self.batch(db, value["batch_id"], context)

    def _authorize_operation(self, db, context, batch, grant, recheck, *, settling=False):
        at = self._now()
        if not (batch["starts_at"] <= at < batch["expires_at"] and grant["valid_from"] <= at < grant["expires_at"]):
            raise Conflict("VALIDATION_WINDOW_CLOSED")
        continuity = self.current_authority(db, context, "restore-continuity")
        if continuity is not None and continuity["state"] != "current":
            raise Conflict("VALIDATION_RESTORE_HOLD")
        if continuity is not None and grant["created_after_sequence"] < continuity["sequence"]:
            raise Conflict("VALIDATION_REBIND_REQUIRED")
        if settling:
            try:
                _require(recheck, db, batch, grant)
            except Exception as exc:
                raise Conflict("VALIDATION_AUTHORITY_CHANGED") from exc
        else:
            _require(recheck, db, batch, grant)
        binding = self.current_credential(db, context, grant["operation"], grant["provider"])
        if binding is None or any(binding[field] != grant[field] for field in (
            "account_ref", "channel_ref", "credential_revision"
        )):
            raise Conflict("VALIDATION_CREDENTIAL_CHANGED")
        if not self._dependency(db, batch, grant):
            raise Conflict("VALIDATION_DEPENDENCY_NOT_CURRENT")

    @staticmethod
    def _dependency(db, batch, grant):
        if grant["depends_on"] is None:
            return True
        parent = _one(db, """
            SELECT q.batch_id, q.operation, q.slot, r.eligible, r.response_sha256, r.source_sha256, r.quote_sha256
            FROM personal_validation_requests q JOIN personal_validation_receipts r USING(request_id)
            WHERE q.request_id=? AND (SELECT state FROM personal_validation_request_events
                                     WHERE request_id=q.request_id ORDER BY sequence DESC LIMIT 1)='settled'
        """, (grant["depends_on"],))
        expected = {"source": ("search", 1), "model": ("model", 1) if grant["slot"] == 2 else ("source", 1)}
        return (
            parent is not None and parent["batch_id"] == batch["batch_id"] and parent["eligible"]
            and parent["response_sha256"] == grant["depends_on_sha256"]
            and (parent["operation"], parent["slot"]) == expected.get(grant["operation"])
        )

    def authorize(self, batch_id, context, grant, recheck):
        with self._transaction() as db:
            batch = self.batch(db, batch_id, context)
            if batch["state"] not in ACTIVE | {"draft"}:
                raise Conflict("VALIDATION_BATCH_NOT_ACTIVE")
            start, end = _utc(grant.valid_from), _utc(grant.expires_at)
            if not batch["starts_at"] <= start < end <= batch["expires_at"]:
                raise ValueError("INVALID_VALIDATION_WINDOW")
            limit = grant.limit
            account_limit = grant.account_limit or _budget(batch)
            if any(one > cap for one, cap in zip(astuple(limit), astuple(_budget(batch)), strict=True)):
                raise Conflict("VALIDATION_OPERATION_BUDGET_OUTSIDE_BATCH")
            values = {key: value for key, value in asdict(grant).items() if key not in {"limit", "account_limit"}}
            continuity = self.current_authority(db, context, "restore-continuity")
            values |= {
                "grant_id": str(uuid4()), "batch_id": batch_id, "valid_from": start, "expires_at": end,
                **_limits(limit), "account_limits": dump(astuple(account_limit)),
                "created_after_sequence": continuity["sequence"] if continuity else 0,
            }
            self._authorize_operation(db, context, batch, values, recheck)
            incompatible = _one(db, """
                SELECT g.grant_id FROM personal_validation_grants g
                JOIN personal_validation_batches b USING(batch_id)
                WHERE g.provider=? AND g.account_ref=? AND b.starts_at<? AND b.expires_at>?
                  AND (g.account_limits<>? OR b.currency<>? OR b.decimals<>?)
                LIMIT 1
            """, (grant.provider, grant.account_ref, batch["expires_at"], batch["starts_at"],
                  values["account_limits"], batch["currency"], batch["decimals"]))
            if incompatible is not None:
                raise Conflict("VALIDATION_ACCOUNT_LIMIT_CHANGED")
            prior_slot = _one(db, """
                SELECT * FROM personal_validation_grants WHERE batch_id=? AND operation=? AND slot=?
                ORDER BY rowid DESC LIMIT 1
            """, (batch_id, grant.operation, grant.slot))
            if prior_slot is not None and all(prior_slot[key] == value for key, value in values.items() if key != "grant_id"):
                return prior_slot
            if _one(db, REQUEST_QUERY + " WHERE q.batch_id=? AND q.operation=? AND q.slot=?",
                    (batch_id, grant.operation, grant.slot)) is not None:
                raise Conflict("VALIDATION_SLOT_ALREADY_BOUND")
            _insert(db, "grants", values)
            if batch["state"] == "draft":
                self._batch_event(db, batch, "approved", "operation_authorized")
            return self.grant(db, batch_id, values["grant_id"])

    def _latest_grant(self, db, grant):
        current = _one(db, """
            SELECT grant_id FROM personal_validation_grants
            WHERE batch_id=? AND operation=? AND slot=? ORDER BY rowid DESC LIMIT 1
        """, (grant["batch_id"], grant["operation"], grant["slot"]))
        if current["grant_id"] != grant["grant_id"]:
            raise Conflict("VALIDATION_GRANT_SUPERSEDED")

    @staticmethod
    def _budget_spent(db, batch, grant=None):
        batch_costs = [0] * len(LIMIT_FIELDS)
        grant_costs = batch_costs.copy()
        account_costs = batch_costs.copy()
        rows = db.execute("""
            SELECT q.*, g.provider, g.account_ref,
                   r.credits AS observed_credits, r.input_tokens AS observed_input,
                   r.output_tokens AS observed_output, r.total_tokens AS observed_total,
                   coalesce((SELECT c.actual_units FROM personal_validation_reconciliations c
                             WHERE request_id=q.request_id ORDER BY sequence DESC LIMIT 1), r.actual_units) AS observed_units,
                   (SELECT state FROM personal_validation_request_events
                    WHERE request_id=q.request_id ORDER BY sequence DESC LIMIT 1) AS state
            FROM personal_validation_requests q
            JOIN personal_validation_grants g USING(grant_id)
            JOIN personal_validation_batches b ON b.batch_id=q.batch_id
            LEFT JOIN personal_validation_receipts r USING(request_id)
            WHERE q.batch_id=? OR (
                g.provider=? AND g.account_ref=? AND b.starts_at<? AND b.expires_at>?
            )
        """, (
            batch["batch_id"], grant["provider"] if grant else None, grant["account_ref"] if grant else None,
            batch["expires_at"], batch["starts_at"],
        ))
        for row in rows:
            if row["state"] == "released":
                continue
            estimates = (row["credits"], row["input_tokens"], row["output_tokens"], row["total_tokens"], row["units"])
            observed = (row["observed_credits"], row["observed_input"], row["observed_output"],
                        row["observed_total"], row["observed_units"])
            if row["state"] == "settled":
                values = tuple(estimate if actual is None else actual for estimate, actual in zip(estimates, observed, strict=True))
            else:
                values = tuple(max(estimate, actual or 0) for estimate, actual in zip(estimates, observed, strict=True))
            same_account = grant is not None and all(row[field] == grant[field] for field in ("provider", "account_ref"))
            for index, value in enumerate((1, *values)):
                if row["batch_id"] == batch["batch_id"]:
                    batch_costs[index] += value
                if grant is not None and row["grant_id"] == grant["grant_id"]:
                    grant_costs[index] += value
                if same_account:
                    account_costs[index] += value
        return batch_costs, grant_costs, account_costs

    def reserve(self, batch_id, context, grant_id, slot, payload_sha256, estimate, recheck):
        _hash(payload_sha256)
        if not self.engineering_fixture:
            raise Conflict("VALIDATION_TRANSPORT_DISABLED")
        if type(slot) is not int or not 1 <= slot <= 2 or estimate.requests != 1 or (
            estimate.total_tokens != estimate.input_tokens + estimate.output_tokens
        ):
            raise ValueError("INVALID_VALIDATION_RESERVATION")
        with self._transaction() as db:
            batch = self.batch(db, batch_id, context)
            grant = self.grant(db, batch_id, grant_id)
            self._latest_grant(db, grant)
            self._authorize_operation(db, context, batch, grant, recheck)
            if (grant["slot"], grant["payload_sha256"]) != (slot, payload_sha256):
                raise Conflict("VALIDATION_PAYLOAD_CHANGED")
            taken = _one(db, REQUEST_QUERY + " WHERE q.batch_id=? AND q.operation=? AND q.slot=?",
                         (batch_id, grant["operation"], slot))
            if taken is not None:
                if any(taken[field] != value for field, value in (
                    asdict(estimate) | {"payload_sha256": payload_sha256, "grant_id": grant_id}
                ).items()):
                    raise Conflict("VALIDATION_SLOT_ALREADY_BOUND")
                return taken
            if batch["state"] not in ACTIVE:
                raise Conflict("VALIDATION_BATCH_NOT_ACTIVE")
            if _one(db, REQUEST_QUERY + " WHERE q.batch_id=? AND state IN ('claimed', 'reconciliation')", (batch_id,)):
                raise Conflict("VALIDATION_REQUEST_IN_FLIGHT")
            if (grant["operation"] != "search" and estimate.credits != 0
                    or grant["operation"] != "model" and estimate.total_tokens != 0):
                raise ValueError("INVALID_VALIDATION_RESERVATION")
            caps = (_budget(batch), _budget(grant), Budget(*json.loads(grant["account_limits"])))
            spent = self._budget_spent(db, batch, grant)
            if estimate.units > batch["single_cost"] or not all(
                cap.accommodates(costs, estimate) for cap, costs in zip(caps, spent, strict=True)
            ):
                raise Conflict("VALIDATION_BUDGET_EXHAUSTED")
            request = asdict(estimate) | {
                "request_id": str(uuid4()), "batch_id": batch_id, "grant_id": grant_id,
                "operation": grant["operation"], "slot": slot, "payload_sha256": payload_sha256,
                "created_at": self._now(),
            }
            _insert(db, "requests", request)
            self._request_event(db, request["request_id"], "reserved", "budget_reserved")
            return request | {"state": "reserved"}

    def _recheck_reserved_budget(self, db, batch, grant, request):
        limits = (_budget(batch), _budget(grant), Budget(*json.loads(grant["account_limits"])))
        spent = self._budget_spent(db, batch, grant)
        if request["units"] > batch["single_cost"] or any(
            any(value > cap for value, cap in zip(costs, astuple(limit), strict=True))
            for costs, limit in zip(spent, limits, strict=True)
        ):
            raise Conflict("VALIDATION_BUDGET_EXHAUSTED")

    def _request(self, db, request_id, context):
        request = _one(db, REQUEST_QUERY + " WHERE q.request_id=?", (request_id,))
        if request is None:
            raise KeyError(request_id)
        batch = self.batch(db, request["batch_id"], context)
        return request, batch, self.grant(db, batch["batch_id"], request["grant_id"])

    def claim(self, request_id, context, recheck):
        if not self.engineering_fixture:
            raise Conflict("VALIDATION_TRANSPORT_DISABLED")
        with self._transaction() as db:
            request, batch, grant = self._request(db, request_id, context)
            if request["state"] != "reserved":
                return None
            if batch["state"] not in ACTIVE:
                raise Conflict("VALIDATION_BATCH_NOT_ACTIVE")
            if _one(db, REQUEST_QUERY + " WHERE q.batch_id=? AND state IN ('claimed', 'reconciliation')",
                    (batch["batch_id"],)):
                raise Conflict("VALIDATION_REQUEST_IN_FLIGHT")
            self._latest_grant(db, grant)
            self._authorize_operation(db, context, batch, grant, recheck)
            self._recheck_reserved_budget(db, batch, grant, request)
            self._request_event(db, request_id, "claimed", "send_authority_committed")
            self._batch_event(db, batch, "executing", "send_authority_committed")
            return request | {"state": "claimed"}

    def _reconciliation(self, db, request, batch, reason):
        if request["state"] != "reconciliation":
            self._request_event(db, request["request_id"], "reconciliation", reason)
        self._batch_event(db, batch, "reconciliation", reason)

    def mark_unknown(self, request_id, context, reason, recheck):
        _ref(reason)
        with self._transaction() as db:
            request, batch, grant = self._request(db, request_id, context)
            _require(recheck, db, batch, grant)
            if request["state"] == "claimed":
                self._reconciliation(db, request, batch, reason)
            elif request["state"] != "reconciliation":
                raise Conflict("VALIDATION_NO_CLAIM")
            return {"request_id": request_id, "state": "reconciliation"}

    def receipt(self, request_id, context, receipt, recheck):
        with self._transaction() as db:
            request, batch, grant = self._request(db, request_id, context)
            prior = _one(db, "SELECT * FROM personal_validation_receipts WHERE request_id=?", (request_id,))
            value = {name: val for name, val in asdict(receipt).items() if name not in {"valid", "reason"}}
            value |= {
                "request_id": request_id, "provider": grant["provider"], "account_ref": grant["account_ref"],
                "request_sha256": request["payload_sha256"], "estimated_units": request["units"],
            }
            if prior is not None:
                if all(prior[key] == item for key, item in value.items()):
                    return prior
                self._reconciliation(db, request, batch, "receipt_conflict")
                return prior | {"conflict": True}
            if request["state"] not in {"claimed", "reconciliation"}:
                raise Conflict("VALIDATION_NO_CLAIM")
            if receipt.provider_request_id and _one(db, """
                SELECT request_id FROM personal_validation_receipts
                WHERE provider=? AND account_ref=? AND provider_request_id=?
            """, (grant["provider"], grant["account_ref"], receipt.provider_request_id)):
                self._reconciliation(db, request, batch, "provider_receipt_conflict")
                return {"request_id": request_id, "eligible": 0, "conflict": True}
            current = True
            try:
                self._authorize_operation(db, context, batch, grant, recheck, settling=True)
            except (Conflict, KeyError, ValueError, sqlite3.Error, OSError):
                current = False
            amounts = (receipt.credits, receipt.input_tokens, receipt.output_tokens, receipt.total_tokens, receipt.actual_units)
            overflow = any(v is not None and v > request[name] for name, v in zip(
                ("credits", "input_tokens", "output_tokens", "total_tokens", "units"), amounts, strict=True
            ))
            metered = (
                grant["operation"] == "model" and all(v is not None for v in amounts[1:4])
                and receipt.total_tokens == receipt.input_tokens + receipt.output_tokens
                or grant["operation"] == "search" and receipt.credits is not None
                or grant["operation"] == "source"
            )
            valid = (
                receipt.valid and receipt.response_status is not None and 200 <= receipt.response_status < 300
                and receipt.model == grant["model"] and metered
            )
            eligible = valid and not overflow and current and batch["state"] == "executing"
            reason = "accepted" if eligible else (
                "authority_changed" if not current or batch["state"] != "executing"
                else "usage_over_budget" if overflow else receipt.reason
            )
            _insert(db, "receipts", value | {
                "eligible": int(eligible), "reason": reason, "occurred_at": self._now(),
            })
            if (request["state"] == "reconciliation" or receipt.actual_units is None
                    or overflow or not metered or receipt.response_status is None):
                self._reconciliation(db, request, batch, reason if not eligible else "actual_cost_unknown")
            else:
                self._request_event(db, request_id, "settled", reason)
                if not eligible:
                    self._batch_event(db, batch, "blocked", reason)
            return _one(db, "SELECT * FROM personal_validation_receipts WHERE request_id=?", (request_id,))

    def reconcile(self, request_id, context, actual_units, subject_ref, evidence_ref, recheck):
        _integer(actual_units)
        _ref(subject_ref)
        _ref(evidence_ref)
        with self._transaction() as db:
            request, batch, grant = self._request(db, request_id, context)
            _require(recheck, db, batch, grant)
            prior = _one(db, """
                SELECT * FROM personal_validation_reconciliations WHERE request_id=? ORDER BY sequence DESC LIMIT 1
            """, (request_id,))
            if prior is not None:
                if (prior["actual_units"], prior["subject_ref"], prior["evidence_ref"]) != (
                    actual_units, subject_ref, evidence_ref
                ):
                    raise Conflict("VALIDATION_RECONCILIATION_CONFLICT")
                return prior
            if request["state"] != "reconciliation":
                raise Conflict("VALIDATION_NOT_AWAITING_RECONCILIATION")
            receipt = _one(db, "SELECT * FROM personal_validation_receipts WHERE request_id=?", (request_id,))
            if receipt is not None and receipt["actual_units"] is not None and receipt["actual_units"] != actual_units:
                raise Conflict("VALIDATION_RECONCILIATION_CONFLICT")
            _insert(db, "reconciliations", {
                "request_id": request_id, "actual_units": actual_units, "subject_ref": subject_ref,
                "evidence_ref": evidence_ref, "actor_ref": context.actor_ref, "occurred_at": self._now(),
            })
            self._request_event(db, request_id, "settled", "charge_reconciled")
            if batch["state"] == "reconciliation":
                self._batch_event(db, batch, "paused" if actual_units <= request["units"] else "blocked",
                                  "charge_reconciled" if actual_units <= request["units"] else "usage_over_budget")
            return _one(db, """
                SELECT * FROM personal_validation_reconciliations WHERE request_id=? ORDER BY sequence DESC LIMIT 1
            """, (request_id,))

    def release(self, request_id, context, reason, recheck):
        _ref(reason)
        with self._transaction() as db:
            request, batch, grant = self._request(db, request_id, context)
            _require(recheck, db, batch, grant)
            if request["state"] == "reserved":
                self._request_event(db, request_id, "released", reason)
            elif request["state"] != "released":
                raise Conflict("VALIDATION_SEND_ALREADY_CLAIMED")
            return request | {"state": "released"}

    def transition(self, batch_id, context, state, reason, recheck):
        _ref(reason)
        with self._transaction() as db:
            batch = self.batch(db, batch_id, context)
            _require(recheck, db, batch)
            if batch["state"] == state:
                return batch
            if state not in CHANGES[batch["state"]]:
                raise Conflict("VALIDATION_INVALID_TRANSITION")
            pending = _one(db, REQUEST_QUERY + " WHERE q.batch_id=? AND state IN ('claimed', 'reconciliation')",
                           (batch_id,))
            if pending and state not in {"paused", "revoked", "blocked"}:
                raise Conflict("VALIDATION_REQUEST_IN_FLIGHT")
            if state in {"evidence_review", "complete"}:
                problems = _one(db, """
                    SELECT q.request_id FROM personal_validation_requests q
                    LEFT JOIN personal_validation_receipts r USING(request_id)
                    WHERE q.batch_id=? AND (r.eligible IS NULL OR r.eligible=0)
                """, (batch_id,))
                coverage = db.execute("""
                    SELECT COUNT(DISTINCT requirement) FROM personal_validation_evidence
                    WHERE batch_id=? AND kind != 'missing'
                """, (batch_id,)).fetchone()[0]
                settled_models = db.execute("""
                    SELECT COUNT(*) FROM personal_validation_requests q
                    JOIN personal_validation_receipts r USING(request_id)
                    WHERE q.batch_id=? AND q.operation='model' AND r.eligible=1
                """, (batch_id,)).fetchone()[0]
                if problems or settled_models != 2 or coverage != len(REQUIREMENTS):
                    raise Conflict("VALIDATION_EVIDENCE_INCOMPLETE")
            if state == "approved" and _one(db, """
                SELECT q.request_id FROM personal_validation_requests q
                LEFT JOIN personal_validation_receipts r USING(request_id)
                LEFT JOIN personal_validation_reconciliations c USING(request_id)
                WHERE q.batch_id=? AND (MAX(COALESCE(r.actual_units, 0), COALESCE(c.actual_units, 0)) > q.units
                  OR r.credits > q.credits OR r.input_tokens > q.input_tokens
                  OR r.output_tokens > q.output_tokens OR r.total_tokens > q.total_tokens)
            """, (batch_id,)):
                raise Conflict("VALIDATION_USAGE_OVER_BUDGET")
            self._batch_event(db, batch, state, reason)
            if state == "revoked":
                self._close_outstanding(db, batch["batch_id"], "revoked_unclaimed_reservation", None)
            result = self.batch(db, batch_id, context)
            _require(recheck, db, result)
            return result

    def recover(self, batch_id, context, recheck):
        with self._transaction() as db:
            batch = self.batch(db, batch_id, context)
            _require(recheck, db, batch)
            for row in db.execute(REQUEST_QUERY + " WHERE q.batch_id=? AND state='claimed'", (batch_id,)).fetchall():
                self._reconciliation(db, row, batch, "send_outcome_unknown")
                batch = self.batch(db, batch_id, context)
            return batch

    def add_evidence(self, batch_id, context, requirement, kind, evidence_ref, evidence_sha256, reason, recheck):
        if requirement not in REQUIREMENTS or kind not in {"synthetic_fixture", "local_regression", "historical_review", "missing"}:
            raise ValueError("INVALID_VALIDATION_EVIDENCE")
        _ref(evidence_ref)
        _ref(reason)
        _hash(evidence_sha256)
        with self._transaction() as db:
            batch = self.batch(db, batch_id, context)
            _require(recheck, db, batch)
            if batch["state"] in {"revoked", "complete"}:
                raise Conflict("VALIDATION_BATCH_NOT_ACTIVE")
            values = {
                "batch_id": batch_id, "requirement": requirement, "kind": kind, "evidence_ref": evidence_ref,
                "evidence_sha256": evidence_sha256, "reason": reason,
            }
            prior = _one(db, """
                SELECT * FROM personal_validation_evidence WHERE batch_id=? AND requirement=? AND kind=?
                    AND evidence_ref=? AND evidence_sha256=?
            """, tuple(values.values())[:-1])
            if prior is not None:
                if prior["reason"] != reason:
                    raise Conflict("VALIDATION_EVIDENCE_CONFLICT")
                return prior
            _insert(db, "evidence", values | {"actor_ref": context.actor_ref, "occurred_at": self._now()})
            return values

    def current_credential(self, db, context, operation, provider):
        return _one(db, """
            SELECT * FROM personal_validation_credentials
            WHERE study_id=? AND scope_id=? AND scope_version=? AND operation=? AND provider=?
            ORDER BY sequence DESC LIMIT 1
        """, (*_scope(context), operation, provider))

    def bind_credential(self, context, operation, provider, account_ref, channel_ref, credential_revision, evidence_ref, recheck):
        with self._transaction() as db:
            _require(recheck, db)
            return self.bind_credential_in_transaction(
                db, context, operation, provider, account_ref, channel_ref, credential_revision, evidence_ref,
            )

    def bind_credential_in_transaction(self, db, context, operation, provider, account_ref, channel_ref,
                                       credential_revision, evidence_ref):
        if OPERATIONS.get(operation) != provider:
            raise ValueError("INVALID_VALIDATION_OPERATION")
        for value in (account_ref, channel_ref, evidence_ref):
            _ref(value)
        if credential_revision is not None:
            _ref(credential_revision)
        if not db.in_transaction:
            raise RuntimeError("VALIDATION_CREDENTIAL_TRANSACTION_REQUIRED")
        prior = self.current_credential(db, context, operation, provider)
        if prior and (prior["account_ref"], prior["channel_ref"], prior["credential_revision"]) == (
            account_ref, channel_ref, credential_revision
        ):
            return prior
        if credential_revision is not None and _one(db, """
            SELECT sequence FROM personal_validation_credentials
            WHERE study_id=? AND scope_id=? AND scope_version=? AND operation=? AND provider=?
              AND credential_revision=?
        """, (*_scope(context), operation, provider, credential_revision)):
            raise Conflict("VALIDATION_CREDENTIAL_REVISION_RETIRED")
        _insert(db, "credentials", {
            "study_id": context.study_id, "scope_id": context.scope_id, "scope_version": context.scope_version,
            "operation": operation, "provider": provider, "account_ref": account_ref, "channel_ref": channel_ref,
            "credential_revision": credential_revision, "evidence_ref": evidence_ref, "occurred_at": self._now(),
        })
        return self.current_credential(db, context, operation, provider)

    @staticmethod
    def current_authority(db, context, subject):
        return _one(db, """
            SELECT * FROM personal_validation_authority
            WHERE study_id=? AND scope_id=? AND subject=? ORDER BY sequence DESC LIMIT 1
        """, (context.study_id, context.scope_id, subject))

    def record_authority(self, context, subject, revision, state, evidence_ref, recheck):
        for value in (subject, revision, evidence_ref):
            _ref(value)
        if state not in {"current", "revoked", "restore_hold"} or (
            subject == "restore-continuity" and state != "restore_hold"
        ):
            raise ValueError("INVALID_VALIDATION_AUTHORITY")
        with self._transaction() as db:
            _require(recheck, db)
            prior = self.current_authority(db, context, subject)
            if prior and (prior["revision"], prior["state"], prior["evidence_ref"]) == (revision, state, evidence_ref):
                return prior
            if prior and state == "current" and _one(db, """
                SELECT sequence FROM personal_validation_authority
                WHERE study_id=? AND scope_id=? AND subject=? AND revision=?
            """, (context.study_id, context.scope_id, subject, revision)):
                raise Conflict("VALIDATION_AUTHORITY_REVISION_RETIRED")
            return self._authority_event(db, context, subject, revision, state, evidence_ref)

    def _authority_event(self, db, context, subject, revision, state, evidence_ref):
        _insert(db, "authority", {
            "study_id": context.study_id, "scope_id": context.scope_id,
            "subject": subject, "revision": revision, "state": state,
            "evidence_ref": evidence_ref, "occurred_at": self._now(),
        })
        return self.current_authority(db, context, subject)

    def _close_outstanding(self, db, batch_id, release_reason, reconciliation_reason):
        for request in db.execute(REQUEST_QUERY + " WHERE q.batch_id=? AND state IN ('reserved', 'claimed')",
                                  (batch_id,)).fetchall():
            if request["state"] == "reserved":
                self._request_event(db, request["request_id"], "released", release_reason)
            elif reconciliation_reason is not None:
                self._request_event(db, request["request_id"], "reconciliation", reconciliation_reason)

    def rebind_after_restore(self, context, evidence_ref, recheck):
        _ref(evidence_ref)
        with self._transaction() as db:
            _require(recheck, db)
            prior = self.current_authority(db, context, "restore-continuity")
            if not prior or prior["state"] != "restore_hold":
                raise Conflict("VALIDATION_RESTORE_HOLD_REQUIRED")
            for batch in db.execute(
                BATCH_QUERY + " WHERE b.study_id=? AND b.scope_id=?", (context.study_id, context.scope_id),
            ).fetchall():
                self._close_outstanding(db, batch["batch_id"], "restored_unclaimed_reservation",
                                        "restored_send_outcome_unknown")
                self._batch_event(db, batch, "revoked", "restored_batch_requires_new_authorization")
            for operation, provider in OPERATIONS.items():
                binding = self.current_credential(db, context, operation, provider)
                if binding is not None and binding["credential_revision"] is not None:
                    self.bind_credential_in_transaction(
                        db, context, operation, provider, binding["account_ref"], binding["channel_ref"],
                        None, evidence_ref,
                    )
            for authority in db.execute("""
                SELECT a.* FROM personal_validation_authority a
                WHERE a.study_id=? AND a.scope_id=? AND a.subject<>'restore-continuity' AND a.state='current'
                  AND a.sequence=(SELECT MAX(sequence) FROM personal_validation_authority
                                  WHERE study_id=a.study_id AND scope_id=a.scope_id AND subject=a.subject)
            """, (context.study_id, context.scope_id)).fetchall():
                self._authority_event(db, context, authority["subject"], authority["revision"], "revoked", evidence_ref)
            return self._authority_event(db, context, "restore-continuity", uuid4().hex, "current", evidence_ref)

    def view(self, batch_id, context, recheck):
        with self.store.db() as db:
            db.execute("BEGIN")
            batch = self.batch(db, batch_id, context)
            _require(recheck, db, batch)
            return self._view(db, batch, context)

    def views(self, context, recheck):
        with self.store.db() as db:
            db.execute("BEGIN")
            _require(recheck, db)
            views = []
            for row in db.execute(BATCH_QUERY + """
                WHERE b.study_id=? AND b.scope_id=? AND b.scope_version=? AND b.actor_ref=?
                  AND b.owner_ref=? AND b.authorization_ref=? AND b.policy_version=?
                ORDER BY b.rowid DESC
            """, (*_scope(context), context.actor_ref, context.owner_ref, context.authorization_ref,
                  context.policy_version)):
                batch = dict(row)
                _require(recheck, db, batch)
                views.append(self._view(db, batch, context))
            return views

    def _view(self, db, batch, context):
        batch_id = batch["batch_id"]
        requests = [dict(row) for row in db.execute(REQUEST_QUERY + " WHERE q.batch_id=? ORDER BY q.rowid", (batch_id,))]
        grants = [dict(row) for row in db.execute("""
            SELECT g.* FROM personal_validation_grants g WHERE g.batch_id=?
            AND g.rowid=(SELECT MAX(rowid) FROM personal_validation_grants
                         WHERE batch_id=g.batch_id AND operation=g.operation AND slot=g.slot)
            ORDER BY g.rowid
        """, (batch_id,))]
        evidence = [dict(row) for row in db.execute("""
            SELECT * FROM personal_validation_evidence WHERE batch_id=? ORDER BY sequence
        """, (batch_id,))]
        receipts = [dict(row) for row in db.execute("""
            SELECT r.*, (SELECT actual_units FROM personal_validation_reconciliations
                         WHERE request_id=r.request_id ORDER BY sequence DESC LIMIT 1) AS reconciled_units
            FROM personal_validation_receipts r JOIN personal_validation_requests q USING(request_id)
            WHERE q.batch_id=? ORDER BY q.rowid
        """, (batch_id,))]
        reconciliations = [dict(row) for row in db.execute("""
            SELECT c.* FROM personal_validation_reconciliations c JOIN personal_validation_requests q USING(request_id)
            WHERE q.batch_id=? ORDER BY c.sequence
        """, (batch_id,))]
        credentials = [
            binding for operation, provider in OPERATIONS.items()
            if (binding := self.current_credential(db, context, operation, provider)) is not None
        ]
        spent = self._budget_spent(db, batch)[0]
        limits = asdict(_budget(batch))
        used = dict(zip(limits, spent, strict=True))
        remaining = {name: max(0, limit - used[name]) for name, limit in limits.items()}
        return {
            "batch": batch, "grants": grants, "requests": requests, "receipts": receipts, "evidence": evidence,
            "reconciliations": reconciliations, "credentials": credentials, "spent": used, "remaining": remaining,
            "formal_status": dict.fromkeys(REQUIREMENTS, "BLOCKED"), "research_denominator": 0,
        }
