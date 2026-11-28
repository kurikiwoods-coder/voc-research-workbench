"""Bind Personal pre-admission operations to local, scoped DPAPI credentials."""

import re
from uuid import uuid4

from src.edition_policy import Decision, Deployment, Domain, Edition, Permission, REFERENCE
from src.raw_store.credentials import VaultError
from src.raw_store.personal_credentials import PersonalCredentials
from src.raw_store.personal_validation import BatchContext, OPERATIONS, ValidationLedger
from src.raw_store.store import Conflict


ANONYMOUS_REVISION = re.compile(r"anonymous-[0-9a-f]{32}")


def _require_workspace(store):
    if store.edition != Edition.PERSONAL or store.fixture or store.diagnostic:
        raise VaultError("VALIDATION_CREDENTIAL_WORKSPACE_REQUIRED")


def _value(grant, field):
    return grant[field] if isinstance(grant, dict) else getattr(grant, field)


def _vault(store, context, operation):
    scoped = (
        {"validation_operation": operation, "scope_version": context.scope_version} if operation != "model" else {}
    )
    return PersonalCredentials(store.directory, study_id=context.study_id, scope_id=context.scope_id, **scoped)


def _model_revision(db, context):
    anchor = db.execute(
        "SELECT credential_revision FROM personal_credential_binding WHERE study_id=? AND scope_id=?",
        (context.study_id, context.scope_id),
    ).fetchone()
    return anchor["credential_revision"] if anchor is not None else None


def validation_binding(store, db, context, grant):
    """Return a secret only after checking the authoritative operation and DPAPI binding."""
    _require_workspace(store)
    operation, provider, account_ref, channel_ref, revision = (
        _value(grant, field) for field in ("operation", "provider", "account_ref", "channel_ref", "credential_revision")
    )
    _validate_operation(operation, provider, channel_ref)
    current = ValidationLedger(store).current_credential(db, context, operation, provider)
    if current is None or not revision or (account_ref, channel_ref, revision) != (
        current["account_ref"], current["channel_ref"], current["credential_revision"]
    ):
        raise VaultError("VALIDATION_CREDENTIAL_CHANGED")
    if operation == "source" and ANONYMOUS_REVISION.fullmatch(revision):
        return None
    if operation == "model" and _model_revision(db, context) != revision:
        raise VaultError("VALIDATION_CREDENTIAL_CHANGED")
    return _vault(store, context, operation).secret(
        revision, provider=provider, channel_ref=channel_ref, account_ref=account_ref,
    )


def _validate_operation(operation, provider, channel_ref):
    if (not isinstance(operation, str) or operation not in OPERATIONS or OPERATIONS[operation] != provider
            or (operation == "model" and channel_ref != "typesafe-officially")):
        raise VaultError("INVALID_VALIDATION_CREDENTIAL_OPERATION")


def _authorized_context(db, authorize):
    decision = authorize(db)
    if (
        not isinstance(decision, Decision) or not decision.allowed or decision.scope is None
        or decision.edition != Edition.PERSONAL or decision.deployment != Deployment.LOCAL
        or decision.domain != Domain.LOCAL_WORKSPACE or decision.operation != Permission.MANAGE_PERSONAL_CREDENTIALS
        or Permission.MANAGE_PERSONAL_CREDENTIALS not in decision.data_permissions or len(decision.evidence_refs) != 1
    ):
        raise Conflict("VALIDATION_CREDENTIAL_AUTHORITY_REQUIRED")
    scope = decision.scope
    if db.execute(
        """SELECT 1 FROM study_scope_freezes f JOIN study_scopes s USING(study_id, scope_id)
           JOIN study_projects p USING(study_id)
           WHERE f.study_id=? AND f.scope_id=? AND 'v' || s.version_no=? AND p.status<>'archived'""",
        (scope.study_id, scope.scope_id, scope.scope_version),
    ).fetchone() is None:
        raise Conflict("VALIDATION_CREDENTIAL_SCOPE_CHANGED")
    return BatchContext(
        scope.study_id, scope.scope_id, scope.scope_version, decision.actor_ref, decision.owner_ref,
        decision.evidence_refs[0], decision.policy_version,
    )


def _credential_change(store, authorize, operation, provider, account_ref, channel_ref, evidence_ref, api_key, revoke):
    _require_workspace(store)
    _validate_operation(operation, provider, channel_ref)
    if api_key is not None and not isinstance(api_key, str):
        raise VaultError("INVALID_VALIDATION_CREDENTIAL_REFERENCE")
    if any(not isinstance(value, str) or not REFERENCE.fullmatch(value) or (api_key and api_key in value)
           for value in (account_ref, channel_ref, evidence_ref)):
        raise VaultError("INVALID_VALIDATION_CREDENTIAL_REFERENCE")
    ledger = ValidationLedger(store)
    with store.writer():
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            context = _authorized_context(db, authorize)
            vault = _vault(store, context, operation)
            if revoke:
                current = ledger.current_credential(db, context, operation, provider)
                if current is None or (account_ref, channel_ref) != (current["account_ref"], current["channel_ref"]):
                    raise Conflict("VALIDATION_CREDENTIAL_CHANGED")
                revision = None
            elif operation == "model":
                if api_key is not None:
                    raise VaultError("VALIDATION_MODEL_USES_SCOPED_APPROVAL_CREDENTIAL")
                revision = _model_revision(db, context)
                vault.secret(revision, provider=provider, channel_ref=channel_ref, account_ref=account_ref)
            elif operation == "source" and api_key is None:
                revision = f"anonymous-{uuid4().hex}"
            else:
                revision = vault.put(provider, channel_ref, account_ref, api_key)["credential_revision"]
            if _authorized_context(db, authorize) != context:
                raise Conflict("VALIDATION_CREDENTIAL_AUTHORITY_CHANGED")
            binding = ledger.bind_credential_in_transaction(
                db, context, operation, provider, account_ref, channel_ref, revision, evidence_ref,
            )
        if operation != "model":
            try:
                vault.discard_unbound(revision)
            except (OSError, ValueError):
                raise VaultError("VALIDATION_CREDENTIAL_CLEANUP_UNAVAILABLE") from None
    return binding


def put_validation_credential(store, *, authorize, operation, provider, account_ref, channel_ref, api_key, evidence_ref):
    return _credential_change(
        store, authorize, operation, provider, account_ref, channel_ref, evidence_ref, api_key, False,
    )


def revoke_validation_credential(store, *, authorize, operation, provider, account_ref, channel_ref, evidence_ref):
    return _credential_change(
        store, authorize, operation, provider, account_ref, channel_ref, evidence_ref, None, True,
    )
