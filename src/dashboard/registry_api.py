"""Loopback HTTP interface for registry definitions and private proposals."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from src.dashboard.api_setup import body
from src.dashboard.relations_api import Id, IntentStatus, PathId, RelationRoute, Revision
from src.raw_store.registry_drafts import RegistryDrafts
from src.raw_store.registry_versions import RegistryVersions


class RegistryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(RegistryInput):
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100_000)


class VersionQuery(RegistryInput):
    registry_version: Id | None = None


class CatalogQuery(Page, VersionQuery):
    q: str | None = Field(default=None, max_length=120)
    lifecycle_status: IntentStatus | None = None
    primary_category_id: Id | None = None
    survey_validation_status: Literal["unvalidated", "validating", "validated", "failed"] | None = None


class CompareQuery(Page):
    from_version: Id
    to_version: Id


class DraftQuery(RegistryInput):
    revision: Revision
    expected_segment_revision: Revision | None = None


class Definition(RegistryInput):
    name: str = Field(default="", max_length=4000)
    definition: str = Field(default="", max_length=4000)
    inclusion_criteria: str = Field(default="", max_length=4000)
    exclusion_criteria: str = Field(default="", max_length=4000)
    primary_category_id: Id | None = None
    secondary_category_ids: list[Id] = Field(default_factory=list, max_length=100)
    source_intent_ids: list[Id] = Field(default_factory=list, max_length=100)


class EvidenceRef(RegistryInput):
    mention_id: Id
    evidence_id: Id
    segment_revision: Revision


class CommandBody(RegistryInput):
    request_key: Id
    expected_registry_version: Id | None
    reason: str = Field(min_length=1, max_length=2000)


class ReviewBody(CommandBody):
    expected_revision: Revision


class DraftBody(CommandBody):
    definition: Definition | None = None
    source_refs: list[EvidenceRef] | None = Field(default=None, max_length=100)
    target_ids: list[Id] | None = Field(default=None, max_length=100)


class CreateBody(DraftBody):
    kind: Literal["candidate", "amend", "merge", "split", "retire", "restore"]
    intent_id: Id | None = None
    origin_registry_version: Id | None = None


class EditBody(DraftBody, ReviewBody):
    pass


def _origin(request: Request):
    origin = request.headers.get("origin")
    if origin is not None and origin != f"{request.url.scheme}://{request.headers.get('host')}":
        raise HTTPException(403)


def _drafts(request: Request):
    return RegistryDrafts(request.app.state.relations)


def _versions(request: Request):
    return RegistryVersions(request.app.state.relations)


def register_registry(app):
    router = APIRouter(prefix="/api", route_class=RelationRoute, tags=["意图注册表"],
                       dependencies=[Depends(_origin)])
    drafts = Depends(_drafts)
    registry = Depends(_versions)
    create_body = Depends(body(CreateBody, 64 * 1024, label="意图草稿"))
    edit_body = Depends(body(EditBody, 64 * 1024, label="意图草稿"))
    review_body = Depends(body(ReviewBody, 16 * 1024, label="意图审核提案"))
    project_drafts = "/studies/{study_id}/registry/drafts"

    @router.get("/registry/versions")
    def versions(query: Annotated[Page, Query()], service=registry):
        return service.versions(**query.model_dump())

    @router.get("/registry/intents")
    def intents(query: Annotated[CatalogQuery, Query()], service=registry):
        return service.catalog(query.registry_version, **query.model_dump(exclude={"registry_version"}))

    @router.get("/registry/intents/{intent_id}")
    def intent(intent_id: PathId, query: Annotated[VersionQuery, Query()], service=registry):
        return service.detail(query.registry_version, intent_id)

    @router.get("/registry/diff")
    def diff(query: Annotated[CompareQuery, Query()], service=registry):
        return service.compare(**query.model_dump())

    @router.get("/registry/projects")
    def projects(service=drafts):
        return {"items": service.projects()}

    @router.get(project_drafts)
    def list_drafts(study_id: UUID, query: Annotated[Page, Query()], service=drafts):
        return service.list(str(study_id), **query.model_dump())

    @router.get(project_drafts + "/{draft_id}")
    def detail(study_id: UUID, draft_id: UUID, service=drafts):
        return service.detail(str(study_id), str(draft_id))

    @router.get(project_drafts + "/{draft_id}/history")
    def history(study_id: UUID, draft_id: UUID, query: Annotated[Page, Query()], service=drafts):
        return service.history(str(study_id), str(draft_id), **query.model_dump())

    @router.get(project_drafts + "/{draft_id}/preflight")
    def preflight(study_id: UUID, draft_id: UUID, query: Annotated[DraftQuery, Query()], service=drafts):
        return service.preflight(str(study_id), str(draft_id), **query.model_dump())

    @router.post(project_drafts, status_code=201)
    def create(study_id: UUID, form=create_body, service=drafts):
        return service.command(str(study_id), "create", **form.model_dump())

    @router.patch(project_drafts + "/{draft_id}")
    def edit(study_id: UUID, draft_id: UUID, form=edit_body, service=drafts):
        return service.command(str(study_id), "edit", draft_id=str(draft_id), **form.model_dump())

    @router.post(project_drafts + "/{draft_id}/submit")
    def submit(study_id: UUID, draft_id: UUID, form=review_body, service=drafts):
        return service.command(str(study_id), "submit", draft_id=str(draft_id), **form.model_dump())

    @router.post(project_drafts + "/{draft_id}/withdraw")
    def withdraw(study_id: UUID, draft_id: UUID, form=review_body, service=drafts):
        return service.command(str(study_id), "withdraw", draft_id=str(draft_id), **form.model_dump())

    app.include_router(router)
