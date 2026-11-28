"""Authorized local HTTP entry points for isolated M09 analysis."""

from dataclasses import asdict
from typing import Annotated, Literal, NamedTuple
from uuid import UUID
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StringConstraints

from src.dashboard.api_setup import body
from src.dashboard.edition_access import DISCOVERY, EditionRoute, request_proof, scoped_decision
from src.discovery.embedding_backend import EmbeddingBackendError
from src.discovery.embedding_inputs import MentionEvidence, OfflineEvidence, SamplingEvidence
from src.discovery.topic_candidates import TopicCandidates
from src.discovery.topic_runs import TopicRuns
from src.discovery.topics import TopicConfig
from src.edition_policy import Edition, Permission
from src.ingestion.m08_tasks import AuthorizationBlocked
from src.raw_store.mentions import MentionStore
from src.raw_store.registry_versions import RegistryVersions
from src.raw_store.relations import RelationStore
from src.raw_store.store import Busy, Conflict


class DiscoveryRoute(EditionRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def route(request):
            try:
                return await handle(request)
            except (KeyError, PermissionError):
                raise HTTPException(404, "找不到获准的主题运行、范围或证据。") from None
            except (Conflict, AuthorizationBlocked):
                raise HTTPException(409, "当前资格、版本或运行条件已变化，请重新核对。") from None
            except (RequestValidationError, ValueError):
                raise HTTPException(422, "主题发现请求无效，请检查参数。") from None
            except (Busy, sqlite3.Error, EmbeddingBackendError, ImportError):
                raise HTTPException(503, "本机主题发现暂不可用，请核对模型与运行环境。") from None

        return route


Language = Annotated[str, StringConstraints(min_length=2, max_length=35)]
DocumentId = Annotated[str, StringConstraints(pattern=r"^m09-[0-9a-f]{64}$")]
ScopeVersion = Annotated[str, Path(pattern=r"^v[1-9][0-9]{0,12}$")]
RevisionQuery = Annotated[int | None, Query(ge=0)]


class ConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    random_seed: StrictInt = Field(default=42, ge=0, le=2**32 - 1)
    n_neighbors: StrictInt = Field(default=10, ge=2, le=1000)
    n_components: StrictInt = Field(default=2, ge=1, le=100)
    min_dist: StrictFloat = Field(default=0.05, ge=0, le=1)
    min_cluster_size: StrictInt = Field(default=5, ge=2, le=1000)
    min_samples: StrictInt = Field(default=3, ge=1, le=1000)
    top_n_words: StrictInt = Field(default=10, ge=1, le=100)

    def config(self):
        return TopicConfig(**self.model_dump())


class Calculate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    config: ConfigInput | None = None


class Create(Calculate):
    analysis_language: Language
    output_language: Language
    evidence_ids: list[DocumentId] = Field(max_length=1000)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    decision: Literal["retained", "rejected"]
    expected_revision: StrictInt = Field(ge=0)


class DiscoveryContext(NamedTuple):
    runs: TopicRuns
    registry_version: str
    references: tuple[MentionEvidence | SamplingEvidence, ...]
    scope: tuple[str, str, str]


def authorized_actor(request, scope):
    state = request.app.state
    if state.edition_policy.edition == Edition.PERSONAL:
        decision = scoped_decision(request, Permission.READ_CORPUS, request_proof(request), scope[0])
        if decision.allowed and (decision.scope.study_id, decision.scope.scope_id, decision.scope.scope_version) == scope:
            return decision.actor_ref
        return None
    access = state.relations._access()
    if all(access.permits(operation, scope[0], entire_project=True) for operation in ("read", "evidence")):
        return access.actor
    return None


def reviewer(request, scope):
    actor = authorized_actor(request, scope)
    if actor is None:
        return None
    state = request.app.state
    if state.edition_policy.edition == Edition.PERSONAL:
        decision = scoped_decision(request, Permission.REVIEW_CORPUS, request_proof(request), scope[0])
        return actor if decision.allowed and decision.actor_ref == actor else None
    access = state.relations._access()
    return actor if access.actor == actor and access.permits("validate", scope[0], entire_project=True) else None


def context(request: Request, study_id: UUID, scope_id: UUID, scope_version: ScopeVersion):
    state = request.app.state
    key = (str(study_id), str(scope_id), scope_version)

    def actor(study, operation=None):
        return authorized_actor(request, key) if study == key[0] else None

    if actor(key[0]) is None:
        raise KeyError(key)
    if state.discovery_catalog is None:
        raise HTTPException(503, "请核对本机合成证据清单。")
    if key not in state.discovery_catalog:
        raise KeyError(key)
    registry, refs = state.discovery_catalog[key]
    evidence = OfflineEvidence(
        study_id=key[0], scope_id=key[1], scope_version=key[2],
        mentions=MentionStore(state.store, authorize=actor),
        registry=RegistryVersions(RelationStore(state.store)),
        sampling=getattr(state, "sampling", None),
        fixture_records=(ref.record for ref in refs if isinstance(ref, MentionEvidence)),
    )
    runs = TopicRuns(state.store, evidence, authorize_project=lambda study: actor(study) is not None)
    return DiscoveryContext(runs, registry, refs, key)


def available_inputs(runs, refs):
    eligible = {}
    for ref in refs:
        try:
            document = runs.evidence.read(ref)
        except (Conflict, AuthorizationBlocked, KeyError, PermissionError):
            continue
        eligible[document.lineage.document_id] = (ref, document)
    return eligible


def backend(request):
    model = request.app.state.discovery_backend
    if model is None:
        raise HTTPException(503, "请先在本机配置已核验的离线模型。")
    return model


def register_discovery(app):
    router = APIRouter(prefix=DISCOVERY, route_class=DiscoveryRoute)
    selected = Depends(context)
    calculate_body = Depends(body(Calculate, 4096))
    create_body = Depends(body(Create, 80000))
    review_body = Depends(body(Review, 4096))

    @router.get("/inputs")
    def inputs(ctx=selected):
        eligible = available_inputs(ctx.runs, ctx.references)
        return {"registry_version": ctx.runs.evidence.registry_version(ctx.registry_version), "inputs": [
            {"document_id": doc.lineage.document_id, "record_id": doc.lineage.record_id,
             "mention_id": doc.lineage.mention_id, "evidence_id": doc.lineage.evidence_id,
             "original_language": doc.original_language}
            for _, doc in eligible.values()
        ]}

    @router.get("/runs")
    def list_runs(request: Request, ctx=selected):
        return {"runs": ctx.runs.list_runs(), "model_available": request.app.state.discovery_backend is not None,
                "review_available": reviewer(request, ctx.scope) is not None}

    @router.post("/runs", status_code=201)
    def create_run(request: Request, form=create_body, ctx=selected):
        eligible = available_inputs(ctx.runs, ctx.references)
        if any(document_id not in eligible for document_id in form.evidence_ids):
            raise Conflict("m09_input_ineligible")
        config = form.config.config() if form.config else TopicConfig()
        run = ctx.runs.create(
            backend(request), (eligible[document_id][0] for document_id in form.evidence_ids),
            request_id=str(form.request_id), registry_version=ctx.registry_version, analysis_language=form.analysis_language,
            output_language=form.output_language, config=config,
        )
        return TopicCandidates(ctx.runs).get(run["run_id"])

    @router.get("/runs/{run_id}")
    def get_run(run_id: UUID, revision: RevisionQuery = None, ctx=selected):
        return TopicCandidates(ctx.runs).get(str(run_id), revision=revision)

    @router.get("/runs/{run_id}/evidence/{document_id}")
    def evidence(run_id: UUID, document_id: DocumentId, ctx=selected):
        return asdict(ctx.runs.evidence_for(str(run_id), document_id))

    @router.get("/runs/{run_id}/compare/{other_run_id}")
    def compare(run_id: UUID, other_run_id: UUID, left_revision: RevisionQuery = None,
                right_revision: RevisionQuery = None, ctx=selected):
        return TopicCandidates(ctx.runs).compare(str(run_id), str(other_run_id),
                                                left_revision=left_revision, right_revision=right_revision)

    @router.post("/runs/{run_id}/recalculate", status_code=201)
    def recalculate(request: Request, run_id: UUID, form=calculate_body, ctx=selected):
        config = form.config.config() if form.config else None
        run = ctx.runs.recalculate(str(run_id), backend(request), request_id=str(form.request_id), config=config)
        return TopicCandidates(ctx.runs).get(run["run_id"])

    @router.post("/runs/{run_id}/candidates/{topic_id}/review")
    def review(request: Request, run_id: UUID, topic_id: Annotated[int, Path(ge=0)], form=review_body, ctx=selected):
        actor = reviewer(request, ctx.scope)
        if actor is None:
            raise HTTPException(403, "当前本机授权未包含候选审核。")
        return TopicCandidates(ctx.runs).review(
            str(run_id), topic_id, decision=form.decision, expected_revision=form.expected_revision,
            request_id=str(form.request_id), actor_ref=actor,
        )

    app.include_router(router)
