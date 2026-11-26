"""Personal local governance API. No endpoint here can dispatch provider requests."""

from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
import sqlite3
from uuid import UUID

from fastapi import HTTPException, Request

from src.dashboard.edition_access import transaction_authorizer
from src.edition_policy import Permission
from src.raw_store.credentials import VaultError
from src.raw_store.personal_approval_evidence import (
    OPTIONAL_RISKS, REQUIRED_EVIDENCE, evidence_projection, read_registry,
)
from src.raw_store.personal_approvals import list_approvals, request_value, write_event
from src.raw_store.personal_credentials import PersonalCredentials
from src.raw_store.store import Busy, Conflict


GOVERNANCE = "/api/personal/governance/{study_id}"
APPROVALS = GOVERNANCE + "/approvals"
CREDENTIAL = GOVERNANCE + "/credential"


@contextmanager
def governed(request, *, writable=False, credential_write=False):
    state = request.app.state
    authorizer = transaction_authorizer(request)
    if authorizer is None:
        raise HTTPException(403, "当前部署未开放个人审批。")
    try:
        with state.store.writer() if credential_write else nullcontext():
            with state.store.db() as db:
                db.execute("BEGIN IMMEDIATE" if writable else "BEGIN")
                authorizer(db)
                decision = request.state.edition_decision
                scope = decision.scope
                owner = state.edition_policy.owner
                grant = next(item for item in owner.grants if item.scope == scope)
                material = (grant.starts_at.isoformat(), grant.expires_at.isoformat(), decision.data_permissions)
                stamp = sha256(repr(material).encode("utf-8")).hexdigest()
                decision = replace(decision, policy_version=f"{decision.policy_version}/G-1-P-C.1/{stamp}")
                vault = PersonalCredentials(state.store.directory, study_id=scope.study_id, scope_id=scope.scope_id)
                yield db, decision, vault
                authorizer(db)
            if credential_write:
                with state.store.db() as db:
                    revision = binding_revision(db, decision)
                vault.discard_unbound(revision)
    except Busy:
        raise HTTPException(409, "GOVERNANCE_BUSY") from None
    except VaultError:
        raise HTTPException(503, "PERSONAL_CREDENTIAL_UNAVAILABLE") from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except sqlite3.IntegrityError:
        raise HTTPException(409, "EVENT_VERSION_CHANGED") from None
    except sqlite3.Error:
        raise HTTPException(503, "GOVERNANCE_UNAVAILABLE") from None
    except (OSError, ValueError):
        raise HTTPException(503, "PERSONAL_CREDENTIAL_CLEANUP_UNAVAILABLE") from None


def credential_projection(binding):
    return {key: binding[key] for key in ("configured", "provider", "channel_ref", "account_ref")}


def binding_revision(db, decision):
    anchor = db.execute(
        "SELECT credential_revision FROM personal_credential_binding WHERE study_id=? AND scope_id=?",
        (decision.scope.study_id, decision.scope.scope_id),
    ).fetchone()
    return anchor["credential_revision"] if anchor is not None else None


def effective_binding(db, decision, vault):
    return vault.read(binding_revision(db, decision))


def register_personal_governance(app):
    @app.get(APPROVALS)
    def approvals(request: Request):
        with governed(request) as (db, decision, vault):
            binding = effective_binding(db, decision, vault)
            registry = read_registry(vault.directory, decision.scope, decision.purpose)
            at = datetime.now(UTC)
            events = list_approvals(db, decision, binding, registry, at)
            ready = any(event["status"] == "ACTIVE" for event in events)
            return {
                "approvals": events, "credential": credential_projection(binding),
                "evidence": evidence_projection(registry, at), "required_evidence": REQUIRED_EVIDENCE,
                "optional_risks": OPTIONAL_RISKS,
                "permissions": {
                    permission.value: permission in decision.data_permissions
                    for permission in (Permission.WRITE_PERSONAL_APPROVALS, Permission.MANAGE_PERSONAL_CREDENTIALS)
                },
                "readiness": {"ready": ready, "reasons": [] if ready else ["NO_CURRENT_ACTIVE_APPROVAL"]},
            }

    def append(request, kind, body, event_id=None):
        try:
            value = request_value(body, kind)
        except (TypeError, ValueError, OverflowError):
            raise HTTPException(422, "INVALID_APPROVAL_REQUEST") from None
        with governed(request, writable=True) as (db, decision, vault):
            binding = {"configured": False} if kind == "revoked" else effective_binding(db, decision, vault)
            registry = {} if kind == "revoked" else read_registry(vault.directory, decision.scope, decision.purpose)
            try:
                return write_event(db, decision, binding, registry, kind, event_id, value, datetime.now(UTC))
            except KeyError:
                raise HTTPException(404, "找不到当前范围内的审批。") from None

    @app.post(APPROVALS, status_code=201)
    def submit(request: Request, body: dict):
        return append(request, "submitted", body)

    @app.post(APPROVALS + "/{event_id}/approve", status_code=201)
    def approve(request: Request, event_id: UUID, body: dict):
        return append(request, "approved", body, str(event_id))

    @app.post(APPROVALS + "/{event_id}/revoke", status_code=201)
    def revoke(request: Request, event_id: UUID, body: dict):
        return append(request, "revoked", body, str(event_id))

    @app.put(CREDENTIAL)
    def put_credential(request: Request, body: dict):
        if body.keys() != {"provider", "channel_ref", "account_ref", "api_key"} or body["provider"] != "packycode":
            raise HTTPException(422, "INVALID_CREDENTIAL_REQUEST")
        with governed(request, writable=True, credential_write=True) as (db, decision, vault):
            transaction_authorizer(request)(db)
            try:
                binding = vault.put(**body)
            except (ValueError, TypeError):
                raise HTTPException(422, "INVALID_CREDENTIAL_REQUEST") from None
            db.execute(
                """INSERT INTO personal_credential_binding VALUES (?, ?, ?)
                   ON CONFLICT(study_id, scope_id) DO UPDATE SET credential_revision=excluded.credential_revision""",
                (decision.scope.study_id, decision.scope.scope_id, binding["credential_revision"]),
            )
            return credential_projection(binding)

    @app.delete(CREDENTIAL)
    def delete_credential(request: Request):
        with governed(request, writable=True, credential_write=True) as (db, decision, vault):
            transaction_authorizer(request)(db)
            binding = vault.delete()
            db.execute("DELETE FROM personal_credential_binding WHERE study_id=? AND scope_id=?",
                       (decision.scope.study_id, decision.scope.scope_id))
            return credential_projection(binding)
