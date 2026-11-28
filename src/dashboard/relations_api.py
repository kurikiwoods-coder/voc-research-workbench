"""Local HTTP projections and preflight for the M06 relationship registry."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, date, datetime, time
from hashlib import sha256
from hmac import compare_digest, digest
import json
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from src.dashboard.api_setup import body
from src.dashboard.edition_access import EditionRoute
from src.raw_store.denominators import _empty
from src.raw_store.store import Busy, Conflict, now


PATH_ROOTS = ("/api/product-categories", "/api/categories", "/api/intents", "/api/registry")
PUBLIC_ERRORS = {
    400: ("FILTER_CONFLICT", "筛选条件或分页参数不一致。"),
    403: ("FORBIDDEN", "当前操作需要有效的本机权限。"),
    404: ("NOT_FOUND", "找不到所选关系或证据。"),
    409: ("VIEW_CHANGED", "版本、资格或授权已变更。请重新查询。"),
    413: ("BODY_TOO_LARGE", "预检内容过大。"),
    415: ("INVALID_CONTENT_TYPE", "请从工作台提交 JSON。"),
    422: ("INVALID_REQUEST", "关系查询或预检格式无效。"),
    503: ("TEMPORARILY_UNAVAILABLE", "本机关系数据暂时不可核实，请重试。"),
}


def is_relation_path(path):
    parts = path.strip("/").split("/")
    return (any(path == root or path.startswith(root + "/") for root in PATH_ROOTS)
            or path == "/api/studies/relations/projects"
            or len(parts) > 3 and parts[:2] == ["api", "studies"]
            and parts[3] in {"mentions", "relations", "registry", "product-relations", "denominators"})


def relation_error(status):
    code, message = PUBLIC_ERRORS.get(status, ("REQUEST_FAILED", "当前请求无法完成。"))
    return JSONResponse({"code": code, "message": message, "retryable": status in (409, 503)},
                        status_code=status, headers={"Cache-Control": "no-store"})


class RelationRoute(EditionRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def sanitized(request):
            try:
                return await handle(request)
            except HTTPException as exc:
                return relation_error(exc.status_code)
            except RequestValidationError:
                return relation_error(422)
            except PermissionError:
                return relation_error(403)
            except KeyError:
                return relation_error(404)
            except Conflict:
                return relation_error(409)
            except ValueError:
                return relation_error(422)
            except (Busy, sqlite3.Error):
                return relation_error(503)

        return sanitized


IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
Id = Annotated[str, Field(pattern=IDENTIFIER)]
PathId = Annotated[str, Path(pattern=IDENTIFIER)]
SourceLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[^\p{Cc}]+$")]
Revision = Annotated[int, Field(gt=0, le=2**53 - 1)]
Mode = Literal["engineering", "synthetic", "formal"]
TaskStatus = Literal["candidate", "confirmed", "rejected", "merged", "retired"]
IntentStatus = Literal["candidate", "pending_parent", "confirmed", "rejected", "merged", "retired"]
ProductStatus = Literal["candidate", "confirmed", "merged", "retired"]


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_version: Id | None = None
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=256)


class ProductQuery(PageQuery):
    q: str | None = Field(default=None, max_length=120)
    parent_id: Id | None = None
    status: ProductStatus | None = None


class TaskQuery(PageQuery):
    q: str | None = Field(default=None, max_length=120)
    lifecycle_status: TaskStatus | None = None


class IntentQuery(PageQuery):
    q: str | None = Field(default=None, max_length=120)
    lifecycle_status: IntentStatus | None = None
    category_id: Id | None = None


class TaskEdgeQuery(PageQuery):
    role: Literal["primary", "secondary", "all"] = "all"
    lifecycle_status: IntentStatus | None = None
    category_id: Id | None = None
    intent_id: Id | None = None


class ProjectSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_version: Id | None = None
    segment_revision: Revision | None = None
    scope_id: UUID | None = None
    scope_version: str | None = Field(default=None, pattern=r"^v[1-9][0-9]{0,12}$")
    mapping_revision: Revision | None = None
    catalog_version: Id | None = None
    batch_id: tuple[UUID, ...] = Field(default=(), max_length=20)
    source: tuple[SourceLabel, ...] = Field(default=(), max_length=20)
    time_field: Literal["published_at", "collected_at"] = "published_at"
    from_: AwareDatetime | date | None = Field(default=None, alias="from")
    to: AwareDatetime | date | None = None
    product_category_id: tuple[Id, ...] = Field(default=(), max_length=20)
    category_id: tuple[Id, ...] = Field(default=(), max_length=20)
    intent_id: tuple[Id, ...] = Field(default=(), max_length=20)
    index_version: Id | None = None
    counting_policy_version: Literal["M06-B-F.1"] = "M06-B-F.1"


class ProjectFilters(ProjectSlice):
    mode: Mode = "engineering"
    confidence_band: Id | None = None
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=256)


class DenominatorQuery(ProjectSlice):
    mode: Mode
    confidence_band: tuple[Id, ...] = Field(default=(), max_length=20)


class ProjectEdgeQuery(ProjectFilters):
    study_id: UUID


class EvidenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_revision: Revision


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention_id: Id
    evidence_id: Id
    segment_revision: Revision | None = None


class ValidateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["candidate", "confirm"]
    candidate_intent_id: Id
    candidate_category_id: Id | None = None
    primary_category_id: Id | None = None
    secondary_ids: list[Id] = Field(default_factory=list, max_length=100)
    expected_registry_version: Id | None
    expected_segment_revision: Revision
    representative_refs: list[Reference] = Field(default_factory=list, max_length=100)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _cursor_key(request):
    return request.app.state.relation_cursor_key


def _encode_cursor(secret, offset, view):
    payload = str(offset).encode() + b"." + view
    return urlsafe_b64encode(payload + digest(secret, payload, "sha256")).decode().rstrip("=")


def _offset(cursor, secret, view):
    if not cursor:
        return 0
    try:
        packed = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload, signature = packed[:-32], packed[-32:]
        if not compare_digest(signature, digest(secret, payload, "sha256")):
            raise ValueError
        offset, bound_view = payload.split(b".", 1)
        position = int(offset)
        if position <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(400) from None
    if not compare_digest(bound_view, view):
        raise HTTPException(409)
    return position


def _page(request, query, data, filters, *, mode="engineering"):
    items = data["items"]
    resolved = data["resolved_versions"]
    view = sha256(_json((request.url.path, query.limit, filters, mode, resolved, data))).digest()
    secret = _cursor_key(request)
    start = _offset(query.cursor, secret, view)
    end = start + query.limit
    return {
        **data, "items": items[start:end],
        "next_cursor": _encode_cursor(secret, end, view) if end < len(items) else None,
        "filter_echo": filters, "mode": mode, "as_of_utc": now(),
    }


def _query_filters(query):
    fields = query.model_dump(exclude={"cursor", "limit", "study_id", "mode", "registry_version",
                                       "segment_revision", "counting_policy_version"},
                              exclude_none=True, by_alias=True)
    if ("scope_id" in fields) != ("scope_version" in fields):
        raise HTTPException(400)
    if "mapping_revision" in fields and "scope_id" not in fields:
        raise HTTPException(400)
    for key in ("from", "to"):
        value = fields.get(key)
        if isinstance(value, date) and not isinstance(value, datetime):
            fields[key] = datetime.combine(value, time.min, tzinfo=UTC)
    if "from" in fields and "to" in fields and fields["from"] >= fields["to"]:
        raise HTTPException(400)
    for key, value in fields.items():
        if isinstance(value, (UUID, tuple)):
            fields[key] = str(value) if isinstance(value, UUID) else tuple(sorted({str(part) for part in value}))
        elif isinstance(value, datetime):
            fields[key] = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return {key: value for key, value in fields.items() if value != ()}


def _project_request(request, db, query, study_id, *, product_id=None, intent_id=None, mention_id=None, mentions=False):
    filters = _query_filters(query)
    if product_id and filters.get("product_category_id", (product_id,)) != (product_id,):
        raise HTTPException(400)
    if intent_id and filters.get("intent_id", (intent_id,)) != (intent_id,):
        raise HTTPException(400)
    mode = query.mode
    needs_receipts = bool(query.confidence_band or query.index_version)
    filters.pop("confidence_band", None)
    filters.pop("index_version", None)
    args = {"registry_version": query.registry_version, "segment_revision": query.segment_revision,
            "filters": filters, "mode": "formal" if needs_receipts else mode}
    if mentions:
        data = db.project_mentions(study_id, mention_id=mention_id, **args)
    else:
        data = db.product_intent_edges(study_id, product_id=product_id, intent_id=intent_id, **args)
    if needs_receipts and mode != "formal":
        data = {**data, "items": [], "availability": "unavailable", "counts": None,
                "reasons": ["M12_RECEIPTS_MISSING"]}
    if mention_id and data.get("availability") != "unavailable":
        if not data["items"]:
            raise HTTPException(404)
        return {**data["items"][0], "resolved_versions": data["resolved_versions"], "mode": mode}
    return _page(request, query, data, {
        "study_id": study_id, "registry_version": data["resolved_versions"].get("registry_version"),
        "segment_revision": data["resolved_versions"].get("segment_revision"),
        "counting_policy_version": query.counting_policy_version,
        **filters, **({"product_category_id": product_id} if product_id else {}),
        **({"intent_id": intent_id} if intent_id else {}),
        **({"confidence_band": query.confidence_band} if query.confidence_band else {}),
        **({"index_version": query.index_version} if query.index_version else {}),
    }, mode=mode)


def _definitions(request, store, kind, query, object_id=None):
    filters = query.model_dump(exclude={"registry_version", "limit", "cursor"}, exclude_none=True)
    data = store.definitions(kind, registry_version=query.registry_version, object_id=object_id, **filters)
    if object_id is not None:
        if not data["items"]:
            raise HTTPException(404)
        return data["items"][0]
    return _page(request, query, data, {
        **filters, "registry_version": data["resolved_versions"].get("registry_version"),
    })


def _task_edges(request, db, query, *, task_id=None, intent_id=None):
    if ((task_id and query.category_id not in (None, task_id))
            or (intent_id and query.intent_id not in (None, intent_id))):
        raise HTTPException(400)
    task_id = task_id or query.category_id
    intent_id = intent_id or query.intent_id
    filters = query.model_dump(
        exclude={"registry_version", "limit", "cursor", "category_id", "intent_id"}, exclude_none=True,
    )
    data = db.task_intent_edges(registry_version=query.registry_version, task_id=task_id,
                                intent_id=intent_id, **filters)
    return _page(request, query, data, {
        **filters, "registry_version": data["resolved_versions"].get("registry_version"),
        **({"category_id": task_id} if task_id else {}), **({"intent_id": intent_id} if intent_id else {}),
    })


def register_relations(app):
    router = APIRouter(prefix="/api", route_class=RelationRoute, tags=["三层关系"])

    def store(request: Request):
        return request.app.state.relations

    db_dep = Depends(store)
    validate_form = Depends(body(ValidateBody, 64 * 1024, label="关系预检"))

    @router.get("/product-categories")
    def products(request: Request, query: Annotated[ProductQuery, Query()], db=db_dep):
        return _definitions(request, db, "product", query)

    @router.get("/product-categories/{product_id}")
    def product(request: Request, product_id: PathId, query: Annotated[PageQuery, Query()], db=db_dep):
        return _definitions(request, db, "product", query, product_id)

    @router.get("/categories")
    def tasks(request: Request, query: Annotated[TaskQuery, Query()], db=db_dep):
        return _definitions(request, db, "task", query)

    @router.get("/categories/{task_id}")
    def task(request: Request, task_id: PathId, query: Annotated[PageQuery, Query()], db=db_dep):
        return _definitions(request, db, "task", query, task_id)

    @router.get("/intents")
    def intents(request: Request, query: Annotated[IntentQuery, Query()], db=db_dep):
        return _definitions(request, db, "intent", query)

    @router.get("/intents/{intent_id}")
    def intent(request: Request, intent_id: PathId, query: Annotated[PageQuery, Query()], db=db_dep):
        return _definitions(request, db, "intent", query, intent_id)

    @router.get("/categories/{task_id}/intents")
    def task_intents(request: Request, task_id: PathId, query: Annotated[TaskEdgeQuery, Query()], db=db_dep):
        return _task_edges(request, db, query, task_id=task_id)

    @router.get("/intents/{intent_id}/categories")
    def intent_tasks(request: Request, intent_id: PathId, query: Annotated[TaskEdgeQuery, Query()], db=db_dep):
        return _task_edges(request, db, query, intent_id=intent_id)

    @router.get("/product-categories/{product_id}/intents")
    def product_intents(request: Request, product_id: PathId, query: Annotated[ProjectEdgeQuery, Query()], db=db_dep):
        return _project_request(request, db, query, str(query.study_id), product_id=product_id)

    @router.get("/intents/{intent_id}/product-categories")
    def intent_products(request: Request, intent_id: PathId, query: Annotated[ProjectEdgeQuery, Query()], db=db_dep):
        return _project_request(request, db, query, str(query.study_id), intent_id=intent_id)

    @router.get("/studies/relations/projects")
    def projects(request: Request, db=db_dep):
        rows = request.app.state.store.rows("SELECT study_id, name, status FROM study_projects ORDER BY name, study_id")
        items = [dict(row) for row in rows if db.can_read_project(row["study_id"])]
        current = request.app.state.store.one("SELECT study_id FROM study_workspace WHERE slot=1")
        active = current["study_id"] if current and any(
            row["study_id"] == current["study_id"] for row in items
        ) else None
        return {"items": items, "current_study_id": active}

    @router.get("/studies/{study_id}/mentions")
    def mentions(request: Request, study_id: UUID, query: Annotated[ProjectFilters, Query()], db=db_dep):
        return _project_request(request, db, query, str(study_id), mentions=True)

    @router.get("/studies/{study_id}/denominators")
    def denominators(request: Request, study_id: UUID, query: Annotated[DenominatorQuery, Query()]):
        decision = getattr(request.state, "edition_decision", None)
        if decision is not None:
            scope = decision.scope
            if query.mode != "formal":
                raise HTTPException(403)
            if (query.scope_id is not None and str(query.scope_id) != scope.scope_id
                    or query.scope_version not in (None, scope.scope_version)):
                raise HTTPException(404)
            # No lookup of a claimed segment, registry or model receipt before Personal admission.
            versions = {"study_id": scope.study_id, "scope_id": scope.scope_id, "scope_version": scope.scope_version,
                        "counting_policy_version": query.counting_policy_version, "registry_version": None,
                        "segment_revision": None, "mapping_revision": None, "catalog_version": None,
                        "scope_mappings": [], "index_version": None}
            return {**_empty("formal", {}, versions, now()), "reasons": ["G1_PERSONAL_NOT_EVALUATED",
                                                                        "RESEARCH_NOT_ADMITTED"]}
        return store(request).denominators(
            str(study_id), mode=query.mode, registry_version=query.registry_version,
            segment_revision=query.segment_revision, filters=_query_filters(query),
        )

    @router.get("/studies/{study_id}/mentions/{mention_id}")
    def mention(request: Request, study_id: UUID, mention_id: PathId,
                query: Annotated[ProjectFilters, Query()], db=db_dep):
        return _project_request(request, db, query, str(study_id), mention_id=mention_id, mentions=True)

    @router.get("/studies/{study_id}/mentions/{mention_id}/evidence/{evidence_id}")
    def evidence(study_id: UUID, mention_id: PathId, evidence_id: PathId,
                 query: Annotated[EvidenceQuery, Query()], db=db_dep):
        return db.read_evidence(str(study_id), query.segment_revision, mention_id, evidence_id)

    @router.post("/studies/{study_id}/relations/validate")
    def validate(study_id: UUID, form=validate_form, db=db_dep):
        data = form.model_dump(exclude_none=True)
        return db.validate(str(study_id), **(data | {"expected_registry_version": form.expected_registry_version}))

    app.include_router(router)
