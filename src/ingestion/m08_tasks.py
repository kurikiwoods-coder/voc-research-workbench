"""Persistent, synthetic-only M08 acquisition tasks and checkpoint receipts."""

from collections import Counter
from contextlib import closing, contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from src.execution.transport import redact
from src.raw_store.store import SQLITE_TIMEOUT, dump, now


SCHEMA_VERSION = 1
APPLICATION_ID = 0x4D303844
TERMINAL = {"completed", "failed", "cancelled"}
RUNNABLE = {"queued", "running", "partial"}
STOPPED = {"paused", "permission_blocked", "budget_blocked"}
OUTCOMES = {"completed", "skipped", "partial", "paused", "permission_blocked", "budget_blocked", "failed"}
KINDS = {"query", "page", "import", "audit"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", re.ASCII)
CONFIG_LIMIT = 1_000_000
RECEIPT_LIMIT = 256_000
CHECKPOINT_LIMIT = 256
LIST_LIMIT = 100

SCHEMA = (
    """CREATE TABLE acquisition_tasks (
        task_id TEXT PRIMARY KEY NOT NULL,
        project_id TEXT NOT NULL,
        actor TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        work_fingerprint TEXT NOT NULL,
        config TEXT NOT NULL CHECK(json_valid(config)),
        state TEXT NOT NULL CHECK(state IN (
            'draft','queued','running','paused','partial','completed','failed',
            'cancelled','permission_blocked','budget_blocked'
        )),
        reason TEXT,
        next_checkpoint INTEGER NOT NULL DEFAULT 0 CHECK(next_checkpoint >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        UNIQUE(project_id, idempotency_key),
        UNIQUE(project_id, work_fingerprint),
        UNIQUE(task_id, project_id)
    ) STRICT""",
    """CREATE TABLE acquisition_attempts (
        request_id TEXT PRIMARY KEY NOT NULL,
        task_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        checkpoint_index INTEGER NOT NULL CHECK(checkpoint_index >= 0),
        idempotency_key TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        actor TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('reserved','received','reconciled')),
        unit TEXT,
        reserved_units INTEGER NOT NULL CHECK(reserved_units >= 0),
        used_units INTEGER CHECK(used_units >= 0 AND used_units <= reserved_units),
        outcome TEXT,
        reason TEXT,
        receipt TEXT CHECK(receipt IS NULL OR json_valid(receipt)),
        reserved_at TEXT NOT NULL,
        received_at TEXT,
        persisted_at TEXT,
        reconciled_at TEXT,
        FOREIGN KEY(task_id, project_id) REFERENCES acquisition_tasks(task_id, project_id),
        UNIQUE(task_id, idempotency_key),
        UNIQUE(task_id, checkpoint_index),
        UNIQUE(task_id, request_id),
        CHECK((state = 'reserved' AND used_units IS NULL AND receipt IS NULL
               AND received_at IS NULL AND persisted_at IS NULL AND reconciled_at IS NULL)
              OR (state = 'received' AND used_units IS NOT NULL AND receipt IS NOT NULL
                  AND received_at IS NOT NULL AND persisted_at IS NULL AND reconciled_at IS NULL)
              OR (state = 'reconciled' AND used_units IS NOT NULL AND receipt IS NOT NULL
                  AND received_at IS NOT NULL AND persisted_at IS NOT NULL AND reconciled_at IS NOT NULL))
    ) STRICT""",
    """CREATE UNIQUE INDEX acquisition_unsettled_requests
       ON acquisition_attempts(project_id, request_fingerprint) WHERE state <> 'reconciled'""",
    """CREATE TABLE acquisition_receipt_recoveries (
        task_id TEXT NOT NULL,
        request_id TEXT NOT NULL UNIQUE,
        idempotency_key TEXT NOT NULL,
        actor TEXT NOT NULL,
        PRIMARY KEY(task_id, idempotency_key),
        FOREIGN KEY(task_id, request_id) REFERENCES acquisition_attempts(task_id, request_id)
    ) STRICT""",
    """CREATE TABLE acquisition_history (
        sequence INTEGER PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES acquisition_tasks(task_id),
        request_id TEXT REFERENCES acquisition_attempts(request_id),
        event TEXT NOT NULL,
        state TEXT NOT NULL,
        reason TEXT,
        actor TEXT NOT NULL,
        event_at TEXT NOT NULL
    ) STRICT""",
    "CREATE INDEX acquisition_history_task ON acquisition_history(task_id, sequence)",
    "CREATE INDEX acquisition_tasks_project ON acquisition_tasks(project_id, created_at DESC, task_id)",
)


class TaskError(ValueError):
    """A safe acquisition error code suitable for a local API response."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class AuthorizationBlocked(TaskError):
    """The current permission or frozen binding prohibits this operation."""


@dataclass(frozen=True)
class CheckpointResult:
    receipt: dict
    used_units: int = 0
    outcome: str = "completed"
    reason: str | None = None


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise TaskError("invalid_identifier")
    return value


def _integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 1_000_000_000


def _json_object(value, limit, code):
    if not isinstance(value, dict):
        raise TaskError(code)
    try:
        encoded = dump(value)
        normalized = json.loads(encoded)
        if len(encoded.encode("utf-8")) > limit or redact(normalized) != normalized:
            raise TaskError(code)
        return encoded
    except (ValueError, TypeError, RecursionError) as exc:
        raise TaskError(code) from exc


def _day(value):
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise TaskError("invalid_window") from exc
    if day.isoformat() != value:
        raise TaskError("invalid_window")
    return day


def _normalize(project_id, config):
    if not isinstance(config, dict) or "authorization_refs" in config or "acquisition_task_id" in config:
        raise TaskError("invalid_task_config")
    validation = {**config}
    validation["authorization_refs"] = validation.pop("authorization", None)
    config = json.loads(_json_object(validation, CONFIG_LIMIT, "invalid_task_config"))
    config["authorization"] = config.pop("authorization_refs")
    if config.get("mode") != "synthetic":
        raise AuthorizationBlocked("formal_collection_blocked")
    if config.get("study_id") != project_id:
        raise AuthorizationBlocked("project_binding_mismatch")
    for name in ("study_id", "scope_id", "scope_version"):
        _identifier(config.get(name))
    if _day(config.get("window_start")) > _day(config.get("window_end")):
        raise TaskError("invalid_window")
    for name in ("query_plan", "authorization"):
        if not isinstance(config.get(name), dict) or not config[name]:
            raise TaskError("invalid_task_binding")
    goal = config.get("research_goal")
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 2000:
        raise TaskError("invalid_research_goal")
    if not _integer(config.get("sample_target"), 1):
        raise TaskError("invalid_sample_target")

    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise TaskError("invalid_sources")
    source_ids = set()
    for source in sources:
        if not isinstance(source, dict):
            raise TaskError("invalid_sources")
        source_id = _identifier(source.get("source_id"))
        _identifier(source.get("adapter_version"))
        if source_id in source_ids:
            raise TaskError("duplicate_source")
        source_ids.add(source_id)
    source_limits = config.get("source_limits")
    if (
        not isinstance(source_limits, dict) or not set(source_limits) <= source_ids
        or not source_limits or any(not _integer(limit, 1) for limit in source_limits.values())
    ):
        raise TaskError("invalid_source_limits")

    budgets = config.get("budgets")
    if not isinstance(budgets, dict):
        raise TaskError("invalid_budget")
    for unit, budget in budgets.items():
        _identifier(unit)
        if (
            not isinstance(budget, dict) or set(budget) != {"authorized", "available"}
            or not _integer(budget["authorized"])
            or (budget["available"] is not None and not _integer(budget["available"]))
        ):
            raise TaskError("invalid_budget")
    real_cost = config.get("real_cost_budget_micros", 0)
    if not _integer(real_cost) or real_cost != 0:
        raise AuthorizationBlocked("formal_collection_blocked")
    config["real_cost_budget_micros"] = 0

    checkpoints = config.get("checkpoints")
    if not isinstance(checkpoints, list) or not 1 <= len(checkpoints) <= CHECKPOINT_LIMIT:
        raise TaskError("invalid_checkpoints")
    keys = set()
    counts = Counter()
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            raise TaskError("invalid_checkpoint")
        key = _identifier(checkpoint.get("key"))
        kind = checkpoint.get("kind")
        if key in keys or not isinstance(kind, str) or kind not in KINDS:
            raise TaskError("invalid_checkpoint")
        source_id = _identifier(checkpoint.get("source_id"))
        if source_id not in source_ids or not isinstance(checkpoint.get("input"), dict):
            raise TaskError("invalid_checkpoint")
        keys.add(key)
        if kind in {"query", "page"}:
            request_count = checkpoint.get("request_count", 1)
            if not _integer(request_count, 1):
                raise TaskError("invalid_request_count")
            unit = _identifier(checkpoint.get("unit"))
            if unit not in budgets or not _integer(checkpoint.get("units"), 1):
                raise TaskError("invalid_budget")
            counts[kind] += request_count
        elif checkpoint.get("unit") is not None or checkpoint.get("units", 0) != 0 or "request_count" in checkpoint:
            raise TaskError("invalid_checkpoint_units")
    for kind in ("query", "page"):
        limit = config.get(f"{kind}_limit")
        if not _integer(limit) or counts[kind] > limit:
            raise TaskError(f"{kind}_limit_exceeded")
    return config


def _fingerprint(config, checkpoints, *, plan=False):
    identity = {
        "scope_id": config["scope_id"], "scope_version": config["scope_version"],
        "checkpoints": [
            {name: checkpoint[name] for name in ("kind", "source_id", "input")}
            for checkpoint in checkpoints
        ],
    }
    if plan:
        identity.update({key: config.get(key) for key in (
            "query_plan", "window_start", "window_end", "fixture_scenario", "fallback_format",
        )})
    return sha256(dump(identity).encode("utf-8")).hexdigest()


def _authorize(config, authorize):
    if not callable(authorize) or authorize(deepcopy(config)) is False:
        raise AuthorizationBlocked("current_authorization_required")


class AcquisitionTaskStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction(write=True) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            application = db.execute("PRAGMA application_id").fetchone()[0]
            if version == application == 0:
                if db.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone() is not None:
                    raise sqlite3.DatabaseError("Unexpected database at acquisition ledger path")
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif (version, application) != (SCHEMA_VERSION, APPLICATION_ID):
                raise sqlite3.DatabaseError("Unsupported acquisition ledger database")

    @contextmanager
    def _transaction(self, *, write=False):
        with closing(sqlite3.connect(self.path, timeout=SQLITE_TIMEOUT)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db

    @staticmethod
    def _row(db, project_id, task_id):
        row = db.execute(
            "SELECT * FROM acquisition_tasks WHERE project_id=? AND task_id=?", (project_id, task_id),
        ).fetchone()
        if row is None:
            raise TaskError("task_not_found")
        return row

    @staticmethod
    def _attempts(db, task_id, *, detail=True):
        if detail:
            return db.execute("""SELECT * FROM acquisition_attempts WHERE task_id=?
                                 ORDER BY checkpoint_index""", (task_id,)).fetchall()
        return db.execute("""SELECT state, unit, reserved_units, used_units
                             FROM acquisition_attempts WHERE task_id=?""", (task_id,)).fetchall()

    @staticmethod
    def _event(db, task_id, actor, event, state, at, *, request_id=None, reason=None):
        db.execute("""INSERT INTO acquisition_history(task_id, request_id, event, state, reason, actor, event_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?)""", (task_id, request_id, event, state, reason, actor, at))

    def _state(self, db, row, actor, state, *, event, reason=None, request_id=None):
        stamp = now()
        db.execute("""UPDATE acquisition_tasks SET state=?, reason=?, updated_at=?,
                      started_at=coalesce(started_at, ?), completed_at=coalesce(completed_at, ?)
                      WHERE task_id=?""",
                   (state, reason, stamp, stamp if state == "running" else None,
                    stamp if state in TERMINAL else None, row["task_id"]))
        self._event(db, row["task_id"], actor, event, state, stamp, request_id=request_id, reason=reason)

    @staticmethod
    def _usage(config, attempts):
        used = Counter()
        reserved = Counter()
        for attempt in attempts:
            if attempt["unit"] is None:
                continue
            if attempt["state"] != "reconciled":
                reserved[attempt["unit"]] += attempt["reserved_units"]
            else:
                used[attempt["unit"]] += attempt["used_units"]
        return {
            unit: {**budget, "used": used[unit], "reserved": reserved[unit], "simulated": True}
            for unit, budget in config["budgets"].items()
        }

    @staticmethod
    def _attempt_view(attempt, config):
        return {
            **{name: attempt[name] for name in (
                "request_id", "checkpoint_index", "actor", "state", "unit", "reserved_units",
                "used_units", "outcome", "reason", "reserved_at", "received_at",
                "persisted_at", "reconciled_at",
            )},
            "checkpoint": config["checkpoints"][attempt["checkpoint_index"]],
            "receipt": json.loads(attempt["receipt"]) if attempt["receipt"] else None,
        }

    def _view(self, db, row, *, detail):
        config = json.loads(row["config"])
        attempts = self._attempts(db, row["task_id"], detail=detail)
        index = row["next_checkpoint"]
        view = {
            "acquisition_task_id": row["task_id"], "project_id": row["project_id"],
            "study_id": config["study_id"], "scope_id": config["scope_id"],
            "scope_version": config["scope_version"], "actor": row["actor"], "mode": config["mode"],
            "state": row["state"], "reason": row["reason"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], "started_at": row["started_at"],
            "completed_at": row["completed_at"], "next_checkpoint": index,
            "checkpoint_count": len(config["checkpoints"]), "usage": self._usage(config, attempts),
            "reconciliation_required": any(attempt["state"] == "reserved" for attempt in attempts),
            "real_api_calls": 0, "real_cost_micros": 0,
        }
        if detail:
            view["config"] = config
            view["attempts"] = [self._attempt_view(attempt, config) for attempt in attempts]
            view["history"] = [dict(event) for event in db.execute(
                """SELECT sequence, request_id, event, state, reason, actor, event_at
                   FROM acquisition_history WHERE task_id=? ORDER BY sequence""", (row["task_id"],),
            )]
        return view

    def create(self, project_id, config, *, actor, idempotency_key):
        for value in (project_id, actor, idempotency_key):
            _identifier(value)
        config = _normalize(project_id, config)
        encoded = dump(config)
        fingerprint = _fingerprint(config, config["checkpoints"], plan=True)
        with self._transaction(write=True) as db:
            prior = db.execute(
                "SELECT * FROM acquisition_tasks WHERE project_id=? AND idempotency_key=?",
                (project_id, idempotency_key),
            ).fetchone()
            if prior is not None:
                if prior["actor"] != actor or prior["config"] != encoded:
                    raise TaskError("idempotency_conflict")
                return self._view(db, prior, detail=True)
            if db.execute(
                "SELECT 1 FROM acquisition_tasks WHERE project_id=? AND work_fingerprint=?",
                (project_id, fingerprint),
            ).fetchone() is not None:
                raise TaskError("duplicate_acquisition_plan")
            task_id = str(uuid4())
            stamp = now()
            db.execute("""INSERT INTO acquisition_tasks(
                          task_id, project_id, actor, idempotency_key, work_fingerprint,
                          config, state, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
                       (task_id, project_id, actor, idempotency_key, fingerprint, encoded, stamp, stamp))
            self._event(db, task_id, actor, "created", "draft", stamp)
            return self._view(db, self._row(db, project_id, task_id), detail=True)

    def list(self, project_id, *, limit=50, offset=0):
        if not _integer(limit, 1) or limit > LIST_LIMIT or not _integer(offset):
            raise TaskError("invalid_task_pagination")
        with self._transaction() as db:
            rows = db.execute("""SELECT * FROM acquisition_tasks WHERE project_id=?
                                 ORDER BY created_at DESC, task_id LIMIT ? OFFSET ?""",
                              (project_id, limit, offset)).fetchall()
            return [self._view(db, row, detail=False) for row in rows]

    def get(self, project_id, task_id):
        with self._transaction() as db:
            return self._view(db, self._row(db, project_id, task_id), detail=True)

    def action(self, project_id, task_id, action, *, actor, authorize=None):
        _identifier(actor)
        with self._transaction(write=True) as db:
            row = self._row(db, project_id, task_id)
            current = row["state"]
            if action == "queue" and current == "draft":
                self._queue(db, row, actor, action, authorize)
            elif action == "pause" and current in RUNNABLE:
                self._state(db, row, actor, "paused", event="pause", reason="user_paused")
            elif action == "resume" and current in STOPPED:
                if any(attempt["state"] == "reserved" for attempt in self._attempts(db, task_id, detail=False)):
                    raise TaskError("request_reconciliation_required")
                self._queue(db, row, actor, action, authorize)
            elif action == "cancel" and current not in TERMINAL:
                self._state(db, row, actor, "cancelled", event="cancel", reason="user_cancelled")
            else:
                raise TaskError("invalid_task_transition")
            return self._view(db, self._row(db, project_id, task_id), detail=True)

    def _queue(self, db, row, actor, action, authorize):
        try:
            _authorize(json.loads(row["config"]), authorize)
        except AuthorizationBlocked as exc:
            self._state(db, row, actor, "permission_blocked", event=action, reason=_identifier(exc.code))
        else:
            self._state(db, row, actor, "queued", event=action)

    def _reserve(self, db, row, config, checkpoint, actor, idempotency_key, *, skip_result=None):
        unit = checkpoint.get("unit")
        units = checkpoint.get("units", 0) if skip_result is None else 0
        if units:
            budget = self._usage(config, self._attempts(db, row["task_id"], detail=False))[unit]
            spent = budget["used"] + budget["reserved"]
            if budget["available"] is None or spent + units > min(budget["authorized"], budget["available"]):
                reason = "budget_unknown" if budget["available"] is None else "budget_exhausted"
                self._state(db, row, actor, "budget_blocked", event="budget_check", reason=reason)
                return None
        fingerprint = _fingerprint(config, [checkpoint])
        if db.execute("""SELECT 1 FROM acquisition_attempts
                         WHERE project_id=? AND request_fingerprint=? AND state <> 'reconciled'""",
                      (row["project_id"], fingerprint)).fetchone() is not None:
            raise TaskError("request_reconciliation_required")
        request_id = str(uuid4())
        db.execute("""INSERT INTO acquisition_attempts(
                      request_id, task_id, project_id, checkpoint_index, idempotency_key,
                      request_fingerprint, actor, state, unit, reserved_units, reserved_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?, ?)""",
                   (request_id, row["task_id"], row["project_id"], row["next_checkpoint"],
                    idempotency_key, fingerprint, actor, unit, units, now()))
        event = "reserved" if skip_result is None else "not_dispatched"
        self._state(db, row, actor, "running", event=event, request_id=request_id)
        return request_id

    def step(self, project_id, task_id, *, actor, authorize, worker, idempotency_key, should_dispatch=None,
             recover=None):
        """Reserve at most one checkpoint before invoking the injected offline worker."""
        _identifier(actor)
        _identifier(idempotency_key)
        with self._transaction(write=True) as db:
            row = self._row(db, project_id, task_id)
            config = json.loads(row["config"])
            attempts = db.execute("""SELECT * FROM acquisition_attempts
                                     WHERE task_id=? AND (state <> 'reconciled' OR idempotency_key=?)""",
                                  (task_id, idempotency_key)).fetchall()
            previous = next((attempt for attempt in attempts if attempt["idempotency_key"] == idempotency_key), None)
            if previous is not None and previous["actor"] != actor:
                raise TaskError("idempotency_conflict")
            if previous is not None and previous["state"] == "reconciled":
                return self._view(db, row, detail=True)
            recovery = db.execute("""SELECT actor FROM acquisition_receipt_recoveries
                                      WHERE task_id=? AND idempotency_key=?""", (task_id, idempotency_key)).fetchone()
            if recovery is not None:
                if recovery["actor"] != actor:
                    raise TaskError("idempotency_conflict")
                return self._view(db, row, detail=True)
            reserved = next((attempt for attempt in attempts if attempt["state"] == "reserved"), None)
            if reserved is not None:
                checkpoint = config["checkpoints"][reserved["checkpoint_index"]]
                if recover is None or checkpoint["kind"] != "import" or reserved["unit"] is not None:
                    receipt = None
                else:
                    _authorize(config, authorize)
                    worker_config = {**deepcopy(config), "acquisition_task_id": task_id}
                    receipt = recover(worker_config, deepcopy(checkpoint), reserved["request_id"])
                if receipt is None:
                    if previous is not None:
                        return self._view(db, row, detail=True)
                    raise TaskError("request_reconciliation_required")
                self._record_receipt(db, row, reserved["request_id"], receipt)
                attempts = db.execute("SELECT * FROM acquisition_attempts WHERE request_id=?",
                                      (reserved["request_id"],)).fetchall()
            pending = next((attempt for attempt in attempts if attempt["state"] == "received"), None)
            if pending is not None:
                if previous is None:
                    db.execute("""INSERT INTO acquisition_receipt_recoveries(
                                      task_id, request_id, idempotency_key, actor
                                  ) VALUES (?, ?, ?, ?)""", (task_id, pending["request_id"], idempotency_key, actor))
                    self._event(db, task_id, actor, "receipt_recovered", row["state"], now(),
                                request_id=pending["request_id"])
                self._settle(db, row, pending, config)
                return self._view(db, self._row(db, project_id, task_id), detail=True)
            if row["state"] not in RUNNABLE or row["next_checkpoint"] >= len(config["checkpoints"]):
                raise TaskError("invalid_task_transition")
            try:
                _authorize(config, authorize)
            except AuthorizationBlocked as exc:
                self._state(db, row, actor, "permission_blocked", event="authorization_check",
                            reason=_identifier(exc.code))
                return self._view(db, self._row(db, project_id, task_id), detail=True)
            checkpoint = config["checkpoints"][row["next_checkpoint"]]
            worker_config = {**deepcopy(config), "acquisition_task_id": task_id}
            decision = True
            if should_dispatch is not None:
                history = [self._attempt_view(attempt, config) for attempt in self._attempts(db, task_id)]
                decision = should_dispatch(deepcopy(worker_config), deepcopy(checkpoint), deepcopy(history))
            if decision is False:
                decision = CheckpointResult({"status": "skipped"}, outcome="skipped", reason="dispatch_not_required")
            skip_result = None
            if decision is not True:
                if (
                    not isinstance(decision, CheckpointResult) or decision.outcome != "skipped"
                    or decision.used_units != 0
                ):
                    raise TaskError("invalid_dispatch_decision")
                skip_result = decision
            request_id = self._reserve(db, row, config, checkpoint, actor, idempotency_key, skip_result=skip_result)
            if request_id is None:
                return self._view(db, self._row(db, project_id, task_id), detail=True)
            if skip_result is not None:
                row = self._row(db, project_id, task_id)
                self._record_receipt(db, row, request_id, skip_result)
                received = db.execute("SELECT * FROM acquisition_attempts WHERE request_id=?", (request_id,)).fetchone()
                self._settle(db, row, received, config)
                return self._view(db, self._row(db, project_id, task_id), detail=True)

        try:
            result = worker(worker_config, deepcopy(checkpoint), request_id)
            self._receive(project_id, task_id, request_id, result)
        except Exception as exc:
            with self._transaction(write=True) as db:
                row = self._row(db, project_id, task_id)
                attempt = db.execute("SELECT state FROM acquisition_attempts WHERE request_id=?",
                                     (request_id,)).fetchone()
                if row["state"] not in TERMINAL and attempt["state"] == "reserved":
                    self._state(db, row, actor, "paused", event="worker_interrupted",
                                reason="request_reconciliation_required", request_id=request_id)
            raise TaskError("request_reconciliation_required") from exc
        with self._transaction(write=True) as db:
            row = self._row(db, project_id, task_id)
            received = db.execute("SELECT * FROM acquisition_attempts WHERE request_id=?", (request_id,)).fetchone()
            if received["state"] == "received":
                self._settle(db, row, received, config)
            return self._view(db, self._row(db, project_id, task_id), detail=True)

    def _receive(self, project_id, task_id, request_id, result):
        with self._transaction(write=True) as db:
            row = self._row(db, project_id, task_id)
            self._record_receipt(db, row, request_id, result)

    def _record_receipt(self, db, row, request_id, result):
        if (
            not isinstance(result, CheckpointResult) or not _integer(result.used_units)
            or result.outcome not in OUTCOMES
            or (result.outcome == "skipped" and result.used_units != 0)
            or (result.outcome != "completed" and result.reason is None)
        ):
            raise TaskError("invalid_checkpoint_receipt")
        receipt = _json_object(result.receipt, RECEIPT_LIMIT, "invalid_checkpoint_receipt")
        reason = _identifier(result.reason) if result.reason is not None else None
        attempt = db.execute("""SELECT * FROM acquisition_attempts
                                WHERE task_id=? AND request_id=?""",
                             (row["task_id"], request_id)).fetchone()
        if attempt is None:
            raise TaskError("invalid_request_state")
        if attempt["state"] != "reserved":
            if (attempt["used_units"], attempt["receipt"], attempt["outcome"], attempt["reason"]) == (
                    result.used_units, receipt, result.outcome, reason):
                return
            raise TaskError("receipt_conflict")
        if result.used_units > attempt["reserved_units"]:
            raise TaskError("usage_exceeds_reservation")
        stamp = now()
        db.execute("""UPDATE acquisition_attempts SET state='received', used_units=?, receipt=?,
                      reason=?, outcome=?, received_at=? WHERE request_id=?""",
                   (result.used_units, receipt, reason, result.outcome, stamp, request_id))
        self._event(db, row["task_id"], attempt["actor"], "receipt_received", row["state"], stamp, request_id=request_id)

    def _settle(self, db, row, attempt, config):
        index = attempt["checkpoint_index"] + 1
        task_id = row["task_id"]
        request_id = attempt["request_id"]
        stamp = now()
        db.execute("""UPDATE acquisition_attempts SET state='reconciled', persisted_at=?, reconciled_at=?
                      WHERE request_id=?""", (stamp, stamp, request_id))
        db.execute("UPDATE acquisition_tasks SET next_checkpoint=? WHERE task_id=?", (index, task_id))
        self._event(db, task_id, attempt["actor"], "checkpoint_persisted", row["state"], stamp, request_id=request_id)
        current = row["state"]
        outcome = attempt["outcome"]
        reason = attempt["reason"]
        if current == "cancelled" or (current == "paused" and index < len(config["checkpoints"]) and outcome != "failed"):
            state, reason = current, row["reason"]
        elif outcome in STOPPED | {"failed"} and index < len(config["checkpoints"]):
            state = outcome
        elif index < len(config["checkpoints"]):
            state = "partial"
        else:
            state = "completed" if outcome in {"completed", "skipped"} else "failed"
        self._state(db, row, attempt["actor"], state, event="usage_reconciled", reason=reason, request_id=request_id)
