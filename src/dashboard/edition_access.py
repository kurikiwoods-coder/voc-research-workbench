"""ASGI boundary for edition policy and the narrowly scoped Personal local API."""

from base64 import b64decode
from dataclasses import asdict, replace
from functools import partial
import sqlite3

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from src.edition_policy import Deployment, Domain, Edition, Permission, canonical_uuid


STATUS_ROUTES = {"/", "/api/health", "/api/edition"}
CLAIM_HEADERS = {"x-voc-edition", "x-voc-deployment", "x-voc-owner", "x-voc-role", "x-voc-actor",
                 "x-product-edition", "x-voc-gate-status"}
CLAIM_PARAMS = {"edition", "product_edition", "deployment", "deployment_mode", "owner", "actor_ref",
                "owner_ref", "is_owner", "gate_status", "role"}

STUDY = "/api/studies/{study_id}"
IMPORT = "/api/imports/{study_id}"
CORPUS = "/api/corpus/{study_id}"
BATCH = "/batches/{batch_id}"
UPLOAD = "/uploads/{file_id}"
RECORD = "/records/{record_id}"
GOVERNANCE_PREFIX = "/api/personal/governance/"
GOVERNANCE = GOVERNANCE_PREFIX + "{study_id}"
APPROVALS = GOVERNANCE + "/approvals"
CREDENTIAL = GOVERNANCE + "/credential"
PERSONAL_ROUTES = {
    ("GET", APPROVALS): Permission.READ_PERSONAL_APPROVALS,
    ("POST", APPROVALS): Permission.WRITE_PERSONAL_APPROVALS,
    ("POST", APPROVALS + "/{event_id}/approve"): Permission.WRITE_PERSONAL_APPROVALS,
    ("POST", APPROVALS + "/{event_id}/revoke"): Permission.WRITE_PERSONAL_APPROVALS,
    ("PUT", CREDENTIAL): Permission.MANAGE_PERSONAL_CREDENTIALS,
    ("DELETE", CREDENTIAL): Permission.MANAGE_PERSONAL_CREDENTIALS,
    ("GET", STUDY + "/scopes/{scope_id}"): Permission.READ_SCOPE,
    ("GET", STUDY + "/denominators"): Permission.READ_FORMAL_STATUS,
    ("GET", "/api/edition/projects/{study_id}"): Permission.READ_SCOPE,
    ("GET", IMPORT + "/batches"): Permission.IMPORT_LOCAL,
    ("POST", IMPORT + "/scopes/{scope_id}/uploads"): Permission.IMPORT_LOCAL,
    ("GET", IMPORT + UPLOAD): Permission.IMPORT_LOCAL,
    ("DELETE", IMPORT + UPLOAD): Permission.IMPORT_LOCAL,
    ("POST", IMPORT + UPLOAD + "/preview"): Permission.IMPORT_LOCAL,
    ("POST", IMPORT + UPLOAD + "/confirm"): Permission.IMPORT_LOCAL,
    ("GET", IMPORT + BATCH): Permission.IMPORT_LOCAL,
    ("GET", IMPORT + BATCH + "/errors.csv"): Permission.EXPORT_ISSUES,
    ("POST", IMPORT + BATCH + "/revoke"): Permission.IMPORT_LOCAL,
    ("GET", CORPUS + "/batches"): Permission.READ_CORPUS,
    ("GET", CORPUS + BATCH): Permission.READ_CORPUS,
    ("GET", CORPUS + RECORD): Permission.READ_CORPUS,
    ("GET", CORPUS + RECORD + "/eligible"): Permission.READ_CORPUS,
    ("POST", CORPUS + RECORD + "/review"): Permission.REVIEW_CORPUS,
}

TARGETS = {
    "file_id": ("import_files", "file_id"),
    "batch_id": ("import_batches", "batch_id"),
    "record_id": ("import_rows JOIN import_batches USING(batch_id)", "record_id"),
}


def request_proof(request):
    values = request.headers.getlist("authorization")
    if len(values) != 1 or len(values[0]) > 160:
        return ""
    scheme, _, encoded = values[0].partition(" ")
    if scheme.lower() != "basic":
        return ""
    try:
        subject, _, secret = b64decode(encoded, validate=True).decode("ascii").partition(":")
        return secret if subject == "owner" else ""
    except (UnicodeError, ValueError):
        return ""


def owner_proof(request):
    secret = request_proof(request)
    owner = request.app.state.edition_policy.owner
    if owner is None or not owner.authenticates(secret):
        raise HTTPException(401, "需要本机 Owner 身份证明。",
                            headers={"WWW-Authenticate": 'Basic realm="VOC Personal"'})
    return secret


def has_scope(db, scope):
    return db.execute(
        """SELECT 1 FROM study_scope_freezes f
           JOIN study_scopes s USING(study_id, scope_id)
           JOIN study_projects p USING(study_id)
           WHERE f.study_id=? AND f.scope_id=? AND 'v' || s.version_no=? AND p.status<>'archived'""",
        (scope.study_id, scope.scope_id, scope.scope_version),
    ).fetchone() is not None


def same_target(db, scope, params):
    if "scope_id" in params and canonical_uuid(params["scope_id"]) != scope.scope_id:
        return False
    for parameter, (source, column) in TARGETS.items():
        value = params.get(parameter)
        if value is not None:
            if parameter != "record_id":
                value = canonical_uuid(value)
            return db.execute(
                f"SELECT 1 FROM {source} WHERE study_id=? AND scope_id=? AND {column}=?",
                (scope.study_id, scope.scope_id, value),
            ).fetchone() is not None
    return True


def scoped_decision(request, permission, proof, study_id, params=None):
    state = request.app.state
    try:
        with state.store.db() as db:
            db.execute("BEGIN")
            decision = state.edition_policy.decide(
                permission, Domain.LOCAL_WORKSPACE, proof=proof, study_id=study_id,
                current_scope=lambda scope: has_scope(db, scope),
            )
            if decision.allowed and not same_target(db, decision.scope, params or {}):
                return replace(decision, allowed=False, reason="PROJECT_SCOPE_NOT_AUTHORIZED",
                               scope=None, purpose=None, evidence_refs=(), data_permissions=())
            return decision
    except sqlite3.Error:
        raise HTTPException(503, "无法核对当前工作区授权，请重试。") from None


def permits(request, permission):
    decision = getattr(request.state, "edition_decision", None)
    return decision is None or permission in decision.data_permissions


def scope_id(request):
    decision = getattr(request.state, "edition_decision", None)
    return decision.scope.scope_id if decision is not None else None


def transaction_authorizer(request):
    decision = getattr(request.state, "edition_decision", None)
    return partial(recheck, request, decision) if decision is not None else None


def recheck(request, decision, db):
    policy = request.app.state.edition_policy
    fresh = policy.decide(
        decision.operation, decision.domain, proof=request_proof(request), study_id=decision.scope.study_id,
        current_scope=lambda scope: has_scope(db, scope) and same_target(db, scope, request.path_params),
    )
    if fresh != decision or not fresh.allowed:
        raise HTTPException(403, "当前项目授权已变化，请重新核对后操作。")


def edition_access(request: Request):
    if not getattr(request.state, "edition_policy_checked", False):
        check_route(request)
        request.state.edition_policy_checked = True


def check_route(request):
    policy = request.app.state.edition_policy
    path = request.scope["route"].path
    if policy.deployment == Deployment.LOCAL and policy.edition == Edition.BUSINESS:
        if path.startswith(GOVERNANCE_PREFIX):
            raise HTTPException(403, "当前部署未开放个人审批。")
        return
    if CLAIM_HEADERS.intersection(request.headers) or CLAIM_PARAMS.intersection(request.query_params):
        raise HTTPException(403, "版本和身份只由本机服务端授权。")
    if path in STATUS_ROUTES:
        return
    if policy.deployment == Deployment.CLOUD:
        raise HTTPException(403, "当前云端模式只提供状态查询。")

    proof = owner_proof(request)
    if path == "/api/edition/projects":
        return
    if (request.method, path) == ("GET", "/api/imports/templates/{kind}"):
        return
    operation = PERSONAL_ROUTES.get((request.method, path))
    study = canonical_uuid(request.path_params.get("study_id"))
    if operation is None:
        if "study_id" in request.path_params:
            # Never confirm a foreign project through an unavailable operation.
            decision = scoped_decision(request, request.method, proof, study, request.path_params)
            if decision.reason == "PROJECT_SCOPE_NOT_AUTHORIZED":
                raise HTTPException(404, "找不到获准的项目、范围或记录。")
        raise HTTPException(403, "当前个人版策略未开放此操作。")
    decision = scoped_decision(request, operation, proof, study, request.path_params)
    if decision.reason == "PROJECT_SCOPE_NOT_AUTHORIZED":
        raise HTTPException(404, "找不到获准的项目、范围或记录。")
    if not decision.allowed:
        raise HTTPException(403, "当前 Owner 授权未包含此权限。")
    request.state.edition_decision = decision


class EditionRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def guarded(request):
            # Run edition authorization before FastAPI parses a request body.
            policy = request.app.state.edition_policy
            governance = self.path.startswith(GOVERNANCE_PREFIX)
            if governance or policy.edition != Edition.BUSINESS or policy.deployment != Deployment.LOCAL:
                await run_in_threadpool(edition_access, request)
            try:
                return await handle(request)
            except RequestValidationError:
                if governance:
                    raise HTTPException(422, "INVALID_GOVERNANCE_REQUEST") from None
                raise

        return guarded


def register_edition(app, business_gate):
    @app.get("/api/edition")
    def status(request: Request):
        state = request.app.state
        return state.edition_policy.status(business_gate(state))

    def require_personal(request):
        policy = request.app.state.edition_policy
        if policy.edition != Edition.PERSONAL or policy.deployment != Deployment.LOCAL:
            raise HTTPException(403, "当前部署未开放个人工作区。")

    @app.get("/api/edition/projects")
    def projects(request: Request):
        require_personal(request)
        proof = owner_proof(request)
        owner = request.app.state.edition_policy.owner
        permitted = []
        for grant in owner.grants:
            decision = scoped_decision(request, Permission.READ_SCOPE, proof, grant.scope.study_id)
            if decision.allowed:
                permitted.append(asdict(decision))
        return {"projects": permitted}

    @app.get("/api/edition/projects/{study_id}")
    def project(request: Request):
        require_personal(request)
        return asdict(request.state.edition_decision)
