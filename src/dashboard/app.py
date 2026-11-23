from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.config import MODEL, PROVIDERS, ROOT, SEARCH_KEYS, Settings
from src.execution.checks import run_checks
from src.raw_store.store import Busy, Conflict, Store

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


def balance(db, settings):
    tag = (settings.account_tag(),)
    records = db.rows(
        """SELECT s.shard_no,s.state,s.tokens,s.remaining,s.updated_at,s.run_id,e.status_code FROM shards s
                         JOIN runs r ON r.id=s.run_id LEFT JOIN evidence e ON e.id=s.evidence_id
                         WHERE r.account_tag=? ORDER BY s.updated_at DESC,s.rowid DESC LIMIT 20""",
        tag,
    )
    total = db.one(
        """SELECT COUNT(*) AS n, COUNT(s.tokens) AS metered, SUM(s.tokens) AS tokens
                      FROM shards s JOIN runs r ON r.id=s.run_id WHERE r.account_tag=? AND s.state='received'""",
        tag,
    )
    latest = db.one(
        """SELECT s.remaining,s.updated_at FROM shards s JOIN runs r ON r.id=s.run_id
                       WHERE r.account_tag=? AND s.remaining IS NOT NULL AND s.state='received' ORDER BY s.updated_at DESC,s.rowid DESC LIMIT 1""",
        tag,
    )
    token_account = settings.provider == "jevmodel"
    remaining = latest["remaining"] if latest and token_account else None
    cap = settings.capacity if token_account else None
    percent = 100 * remaining / cap if remaining is not None and cap else None
    last_code = records[0]["status_code"] if records else None
    warning = {
        401: "密钥异常",
        402: "额度不足",
        403: "权限不足",
        422: "请求字段异常",
        429: "供应商限流",
        502: "上游服务异常",
    }.get(last_code)
    if not warning and percent is not None and percent < 20:
        warning = "余额告急" if percent < 5 else "低余额预警"
    return {
        "provider": settings.provider,
        "model": MODEL,
        "remaining": remaining,
        "capacity": cap,
        "percent": percent,
        "sync_method": "header" if remaining is not None else None,
        "last_synced_at": latest["updated_at"] if latest and token_account else None,
        "input_tokens": total["tokens"] if total["n"] and total["n"] == total["metered"] else None,
        "successful_shards": total["n"],
        "unit": "input tokens" if token_account else "供应商货币账户",
        "warning": warning,
        "records": records,
        "purchase_url": PROVIDERS[settings.provider][2],
    }


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID


def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings.load()
        app.state.store = Store(app.state.settings.directory)
        yield

    app = FastAPI(
        title="VOC 研究工作台", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])

    @app.middleware("http")
    async def local_controls(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if request.headers.get("X-VOC-Action") != "connectivity" or (
                origin
                and (
                    urlsplit(origin).netloc != request.headers.get("host")
                    or urlsplit(origin).scheme != request.url.scheme
                )
            ):
                return JSONResponse({"detail": "请从本机工作台发起操作。"}, status_code=403)
        reply = await call_next(request)
        reply.headers["Referrer-Policy"] = "no-referrer"
        reply.headers["X-Content-Type-Options"] = "nosniff"
        reply.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.url.path.startswith("/api/"):
            reply.headers["Cache-Control"] = "no-store"
        return reply

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "schema_version": app.state.store.one("PRAGMA user_version")["user_version"],
        }

    @app.get("/api/workspace")
    def workspace(run_id: UUID | None = None):
        db, cfg = app.state.store, app.state.settings
        history = db.history()
        selected = (
            next((r for r in history if r["id"] == str(run_id)), None)
            if run_id
            else (history[0] if history else None)
        )
        if run_id and selected is None:
            raise HTTPException(404, "批次不存在")
        return {
            "stage": "P0-0",
            "selected": selected,
            "history": history,
            "requirements": requirements(db, selected["id"] if selected else None),
            "token": balance(db, cfg),
            "config": {
                "provider": cfg.provider,
                "review": cfg.review_status()["approved"],
                "key_names": {
                    name: bool(cfg.keys.get(k))
                    for k, name in {cfg.provider: PROVIDERS[cfg.provider][1], **SEARCH_KEYS}.items()
                },
            },
        }

    @app.get("/api/runs/{run_id}/evidence")
    def evidence(run_id: UUID):
        try:
            return app.state.store.audit(str(run_id))
        except KeyError:
            raise HTTPException(404, "批次不存在")

    def execute(key, run=None):
        try:
            rid = run_checks(app.state.settings, app.state.store, key, run)
            return {"run_id": rid}
        except Busy as exc:
            raise HTTPException(409, str(exc))
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except KeyError:
            raise HTTPException(404, "批次不存在")

    @app.post("/api/runs", status_code=201)
    def create_run(body: Batch):
        return execute(str(body.request_key))

    @app.post("/api/runs/{run_id}/resume")
    def resume(run_id: UUID):
        return execute(None, str(run_id))

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
