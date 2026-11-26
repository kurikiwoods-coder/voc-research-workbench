from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal
from ipaddress import ip_address
import json
import sqlite3
from pathlib import Path
from secrets import token_bytes
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.config import (
    CONNECTOR_ACCOUNTS, CONNECTOR_KEYS, MODEL, PACKYCODE_CONTRACT, PROVIDERS, ROOT, Settings,
)
from src.dashboard.api_setup import register_setup, setup_view
from src.dashboard.edition_access import EditionRoute, edition_access, register_edition
from src.dashboard.personal_governance import register_personal_governance
from src.edition_policy import Deployment, Edition, EditionPolicy, legacy_execution_allowed
from src.dashboard.acquisition_api import register_acquisition
from src.ingestion.m08_sampling import SamplingTasks
from src.dashboard.corpus_api import register_corpus
from src.dashboard.study_api import register_studies
from src.dashboard.import_api import register_imports
from src.dashboard.relations_api import is_relation_path, register_relations, relation_error
from src.dashboard.registry_api import register_registry
from src.execution.checks import run_checks, test_gate_requires_all_six
from src.execution.transport import number
from src.raw_store.corpus import CorpusStore
from src.raw_store.credentials import CredentialVault, VaultError
from src.raw_store.store import Busy, Conflict, Store
from src.raw_store.studies import StudyStore
from src.raw_store.imports import ImportStore

STATIC = Path(__file__).parent / "static"
NAMES = [
    "固定模型与分片",
    "返回字段与概率",
    "搜索与公开原话",
    "持久化与额度",
    "内部数据隔离",
    "三层模型与召回",
]
MATRIX_PATH = ROOT / "docs/requirements-matrix.md"


def catalogue():
    rows = []
    for line in MATRIX_PATH.read_text("utf-8").splitlines():
        cells = [s.strip() for s in line.strip("|").split("|")]
        if len(cells) != 5 or cells[1] not in {"P0-0", "P0", "P1", "P2"}:
            continue
        rid, stage, desc, impl, test = cells
        name = NAMES[int(rid[-1]) - 1] if rid.startswith("C0-") else desc.split("。")[0]
        if rid == "G-1":
            name = "P0 准入验收"
        rows.append(
            dict(
                requirement_id=rid,
                stage=stage,
                title=name,
                description=desc,
                implementation=impl,
                test_case=test,
            )
        )
    return rows


def requirements(db, run=None):
    latest = {r["requirement_id"]: r for r in db.results(run)} if run else {}
    rows = catalogue()
    for row in rows:
        rid = row["requirement_id"]
        operational = rid in ("P1-TREND", "P1-REFLOW", "G6")
        row.update(
            status="PENDING" if operational else "NOT_TESTED",
            evidence=[],
            blocker=(
                "等待连续四周同口径的真实采样"
                if rid == "P1-TREND"
                else "等待真实问卷回收与回写" if operational else None
            ),
            last_checked_at=None,
            detail=None,
        )
        if rid in latest:
            actual = latest[rid]
            row.update(
                status=actual["status"],
                evidence=actual["evidence"],
                blocker=actual["blocker"],
                last_checked_at=actual["checked_at"],
                detail=actual["detail"],
            )
    return rows


def packycode_billing(stores, tag, total_input, has_records):
    query = """SELECT json_extract(s.response_json, '$.usage.output_tokens') AS output,
                      json_type(s.response_json, '$.usage.output_tokens') AS output_type
               FROM shards s JOIN runs r ON r.id=s.run_id
               WHERE r.account_tag=? AND s.state='received'"""
    rows = [row for store in stores for row in store.rows(query, tag)]
    outputs = [number(row["output"]) if row["output_type"] == "integer" else None for row in rows]
    total_output = sum(outputs) if outputs and None not in outputs else None
    rate = Decimal(PACKYCODE_CONTRACT["input_usd_per_million"])
    estimated = format(rate * total_input / 1_000_000, "f") if total_input is not None else None
    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "estimated_usd": estimated,
        "actual_charge_usd": None,
        "charge_status": "UNKNOWN" if has_records else "NO_REQUESTS",
        "balance_status": "UNSYNCED",
        "rate_source": PACKYCODE_CONTRACT["rate_source"],
    }


def balance(db, settings, diagnostics=None):
    tag = (settings.account_tag(),)
    records_query = """SELECT s.shard_no,s.state,s.tokens,s.remaining,s.updated_at,s.run_id,e.status_code FROM shards s
                         JOIN runs r ON r.id=s.run_id LEFT JOIN evidence e ON e.id=s.evidence_id
                         WHERE r.account_tag=? ORDER BY s.updated_at DESC,s.rowid DESC LIMIT 20"""
    total_query = """SELECT COUNT(*) AS n, COUNT(s.tokens) AS metered, SUM(s.tokens) AS tokens
                    FROM shards s JOIN runs r ON r.id=s.run_id WHERE r.account_tag=? AND s.state='received'"""
    records = db.rows(records_query, tag)
    formal = db.one(total_query, tag)
    diagnostic = diagnostics.one(total_query, tag) if diagnostics else {"n": 0, "metered": 0, "tokens": None}
    counts = formal["n"] + diagnostic["n"]
    measured = formal["metered"] + diagnostic["metered"]
    token_account = settings.provider == "jevmodel"
    sync_query = """SELECT MAX(s.updated_at) AS at FROM shards s JOIN runs r ON r.id=s.run_id
           WHERE r.account_tag=? AND s.state='received' AND s.remaining IS NOT NULL
           """
    stores = (db, diagnostics) if diagnostics else (db,)
    synced = max((source.one(sync_query, tag)["at"] or "" for source in stores), default="") if token_account else ""
    probe_records = diagnostics.rows(records_query, tag) if diagnostics else []
    latest = max(records[:1] + probe_records[:1], key=lambda row: row["updated_at"], default=None)
    last_code = latest["status_code"] if latest else None
    remaining = latest["remaining"] if latest and token_account and last_code == 200 else None
    cap = settings.capacity if token_account else None
    percent = 100 * remaining / cap if remaining is not None and cap else None
    warning = {
        401: "密钥异常",
        402: "额度不足",
        403: "权限不足",
        422: "请求字段异常",
        429: "供应商限流",
        502: "上游服务异常",
    }.get(last_code)
    if not warning and latest and latest["state"] in ("uncertain", "sending"):
        warning = "传输结果或计费待核对"
    if not warning and percent is not None and percent < 20:
        warning = "余额告急" if percent < 5 else "低余额预警"
    total_input = (formal["tokens"] or 0) + (diagnostic["tokens"] or 0) if counts and counts == measured else None
    return {
        "provider": settings.provider,
        "model": MODEL,
        "key_configured": bool(settings.keys.get(settings.provider)),
        "remaining": remaining,
        "capacity": cap,
        "percent": percent,
        "sync_method": "header" if remaining is not None else None,
        "last_synced_at": synced or None,
        "input_tokens": total_input,
        "diagnostic_input_tokens": diagnostic["tokens"] if diagnostic["n"] == diagnostic["metered"] else None,
        "successful_shards": counts,
        "unit": "input tokens" if token_account else "供应商货币账户",
        "warning": warning,
        "records": records,
        "purchase_url": PROVIDERS[settings.provider][2],
        **({"billing": packycode_billing(stores, tag, total_input, bool(latest))}
           if settings.provider == "packycode" else {}),
    }


def connection_diagnostics(db, settings, selected, requirements):
    checks = {r["requirement_id"]: r for r in requirements}
    refs = sorted({i for rid in ("C0-1", "C0-2", "C0-3") for i in checks[rid]["evidence"]})
    observed = db.rows(
        f"""SELECT name, status_code, checked_at, response_json FROM evidence
            WHERE mode='live_http' AND id IN ({','.join('?' for _ in refs)}) ORDER BY id""",
        refs,
    ) if refs else []
    verified_sources = set()
    for row in observed:
        if row["name"] == "forum_post" and row["status_code"] == 200:
            proof = json.loads(row["response_json"])
            if proof.get("verified"):
                verified_sources.add(proof.get("search"))
    schema_gap = checks["C0-2"].get("blocker") or ""
    approved = settings.review_status()["approved"]
    connections = []
    for name, env_var in CONNECTOR_KEYS.items():
        label, signup = CONNECTOR_ACCOUNTS[name]
        is_jev = name in PROVIDERS
        active = is_jev and name == settings.provider
        if is_jev:
            evidence_name = "jev_shard" if selected and name == selected["provider"] else None
        else:
            evidence_name = name
        latest = next((r for r in reversed(observed) if r["name"] == evidence_name), None)
        code = latest["status_code"] if latest else None
        connection = "NOT_TESTED" if latest is None else "CONNECTED" if code == 200 else "ERROR"
        capability = "NOT_TESTED"
        if code == 200 and is_jev:
            reply = json.loads(latest["response_json"]).get("body")
            if not isinstance(reply, dict) or reply.get("model") != MODEL or schema_gap.startswith("schema_gap"):
                capability = "MISMATCH"
            elif all(checks[rid]["status"] == "PASS" for rid in ("C0-1", "C0-2")):
                capability = "VERIFIED"
        if code == 200 and name in verified_sources and checks["C0-3"]["status"] == "PASS":
            capability = "VERIFIED"
        connections.append({
            "id": name,
            "label": label,
            "signup": signup,
            "env_var": env_var,
            "configured": bool(settings.keys.get(name)),
            "selected_for_jev": active,
            "review": ("APPROVED" if approved else "PENDING") if active else None,
            "connection": connection,
            "capability": capability,
            "http_status": code,
            "checked_at": latest["checked_at"] if latest else None,
        })
    return {
        "provider": settings.provider,
        "review": approved,
        "key_names": {r["env_var"]: r["configured"] for r in connections},
        "connections": connections,
        "acceptance": checks["G-1"]["status"],
    }


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID


def business_gate(state):
    base = state.settings
    if not legacy_execution_allowed(base):
        return "BLOCKED"
    try:
        cfg = base.with_local(state.vault.read())
        if not cfg.keys.get(cfg.provider) or cfg.provider == "packycode":
            return "BLOCKED"
        review = cfg.review_status()
        if not review["approved"]:
            return "BLOCKED"
        with state.store.db() as db:
            db.execute("BEGIN")
            latest = db.execute(
                """SELECT id, state FROM runs WHERE provider=? AND account_tag=? ORDER BY rowid DESC LIMIT 1""",
                (cfg.provider, cfg.account_tag()),
            ).fetchone()
            if latest is None or latest["state"] != "complete":
                return "BLOCKED"
            attempt = db.execute(
                "SELECT id FROM attempts WHERE run_id=? AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 1",
                (latest["id"],),
            ).fetchone()
            if attempt is None:
                return "BLOCKED"
            rows = {row["requirement_id"]: dict(row) for row in db.execute(
                "SELECT * FROM results WHERE attempt_id=?", (attempt["id"],),
            )}
            gate = rows.pop("G-1", {})
            statuses = {code: row["status"] for code, row in rows.items()}
            if gate.get("status") != "PASS" or not test_gate_requires_all_six(statuses, review):
                return "BLOCKED"
            refs = json.loads(gate["evidence_json"])
            if not isinstance(refs, list) or len(refs) != 1 or type(refs[0]) is not int:
                return "BLOCKED"
            proof = db.execute(
                """SELECT response_json FROM evidence WHERE id=? AND attempt_id=?
                   AND name='stage_gate' AND mode='local_gate'""", (refs[0], attempt["id"]),
            ).fetchone()
            if proof:
                record = json.loads(proof["response_json"])
                if isinstance(record, dict) and record.get("statuses") == statuses and record.get("provider_review") == review:
                    return "PASS"
    except (VaultError, sqlite3.Error, ValueError):
        pass
    return "BLOCKED"


def create_app(settings=None, *, relation_grants=None, acquisition_permission=None):
    @asynccontextmanager
    async def lifespan(app):
        from src.raw_store.relations import RelationStore

        base = settings or Settings.load_base()
        app.state.settings = base
        app.state.edition_policy = EditionPolicy(base.edition, base.deployment, base.personal_owner)
        if base.deployment == Deployment.LOCAL:
            app.state.store = Store(base.directory, edition=base.edition)
            app.state.studies = StudyStore(app.state.store)
            app.state.imports = ImportStore(app.state.store)
            app.state.corpus = CorpusStore(app.state.store)
            if base.edition == Edition.BUSINESS:
                app.state.sampling = SamplingTasks(base.directory, app.state.studies, acquisition_permission)
                app.state.relations = RelationStore(app.state.store, grants=relation_grants)
                app.state.relation_cursor_key = token_bytes(32)
                app.state.diagnostics = Store(base.directory, diagnostic=True)
                app.state.vault = CredentialVault(base.directory)
        yield

    app = FastAPI(
        title="VOC 研究工作台", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None,
        dependencies=[Depends(edition_access)],
    )
    app.router.route_class = EditionRoute
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])

    @app.middleware("http")
    async def local_controls(request: Request, call_next):
        path = request.url.path
        relation_api = is_relation_path(path)
        acquisition_api = path.startswith("/api/acquisition/")
        private_api = (relation_api or path == "/api/studies"
                       or acquisition_api
                       or path.startswith(("/api/setup/", "/api/studies/", "/api/imports/", "/api/corpus/")))
        legacy = legacy_execution_allowed(request.app.state.settings)
        local_data = (not legacy and path.startswith("/api/")) or private_api or path in {"/api/workspace", "/api/runs"} or path.startswith("/api/runs/")
        denial_headers = {"Cache-Control": "no-store"} if local_data else None
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host')}"
        if (acquisition_api or not legacy) and origin is not None and origin != expected:
            return JSONResponse({"detail": "请从本机工作台发起操作。"}, status_code=403, headers=denial_headers)
        if local_data:
            try:
                loopback = request.client is not None and ip_address(request.client.host).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                if relation_api:
                    return relation_error(403)
                return JSONResponse({"detail": "请从本机 localhost 打开工作台。"}, status_code=403, headers=denial_headers)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("X-VOC-Action") != "connectivity" or ((origin or private_api or not legacy) and origin != expected):
                if relation_api:
                    return relation_error(403)
                return JSONResponse({"detail": "请从本机工作台发起操作。"}, status_code=403, headers=denial_headers)
        if not legacy and path == "/openapi.json":
            return JSONResponse({"detail": "当前运行模式未开放接口说明。"}, status_code=403, headers=denial_headers)
        reply = await call_next(request)
        reply.headers["Referrer-Policy"] = "no-referrer"
        reply.headers["X-Content-Type-Options"] = "nosniff"
        reply.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        if request.url.path.startswith("/api/"):
            reply.headers["Cache-Control"] = "no-store"
        return reply

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        db = getattr(app.state, "store", None)
        return {"status": "ok", "schema_version": db.one("PRAGMA user_version")["user_version"] if db else None}

    @app.get("/api/workspace")
    def workspace(run_id: UUID | None = None):
        db, base, diagnostics = app.state.store, app.state.settings, app.state.diagnostics
        error = None
        try:
            local = app.state.vault.read()
            cfg = base.with_local(local)
        except VaultError as exc:
            error = str(exc)
            cfg = replace(base, keys={}, review="", local_reviews={})
            local = {"keys": {}, "wizard_seen": True}
        history = db.history()
        selected = (
            next((r for r in history if r["id"] == str(run_id)), None)
            if run_id
            else (history[0] if history else None)
        )
        if run_id and selected is None:
            raise HTTPException(404, "批次不存在")
        matrix = requirements(db, selected["id"] if selected else None)
        return {
            "stage": "P0-0",
            "selected": selected,
            "history": history,
            "requirements": matrix,
            "token": balance(db, cfg, diagnostics),
            "config": connection_diagnostics(db, cfg, selected, matrix),
            "setup": setup_view(base, cfg, local, diagnostics, lambda s: balance(db, s, diagnostics), error),
        }

    @app.get("/api/runs/{run_id}/evidence")
    def evidence(run_id: UUID):
        try:
            return app.state.store.audit(str(run_id))
        except KeyError:
            raise HTTPException(404, "批次不存在")

    def execute(key, run=None):
        def current_settings():
            return app.state.settings.with_local(app.state.vault.read())

        try:
            rid = run_checks(current_settings, app.state.store, key, run)
            return {"run_id": rid}
        except Busy as exc:
            raise HTTPException(409, str(exc))
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except KeyError:
            raise HTTPException(404, "批次不存在")
        except VaultError as exc:
            raise HTTPException(503, str(exc)) from None

    @app.post("/api/runs", status_code=201)
    def create_run(body: Batch):
        return execute(str(body.request_key))

    @app.post("/api/runs/{run_id}/resume")
    def resume(run_id: UUID):
        return execute(None, str(run_id))

    register_edition(app, business_gate)
    register_personal_governance(app)
    register_setup(app)
    register_studies(app)
    register_imports(app)
    register_acquisition(app)
    register_corpus(app)
    register_relations(app)
    register_registry(app)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
