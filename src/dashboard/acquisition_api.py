"""Local-only routes for M08 frozen-scope previews and synthetic acquisition."""

from contextlib import contextmanager
from datetime import date
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from src.dashboard.api_setup import body, recent_tests, search_quota
from src.config import SEARCH_KEYS
from src.execution.transport import Denied
from src.ingestion.m08_acquisition import FORMAL_COLLECTION, PlanError, demo, preview, source_catalog
from src.ingestion.m08_platforms import platform_catalog
from src.ingestion.m08_sampling import ACTOR, sampling_config, should_dispatch
from src.ingestion.m08_tasks import AuthorizationBlocked, TaskError
from src.raw_store.credentials import VaultError
from src.raw_store.store import Conflict


Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")]
Object = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Goal = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
IsoDate = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]


class AcquisitionScopeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_id: UUID
    scope_version: Annotated[str, StringConstraints(pattern=r"^v[1-9][0-9]{0,9}$")]
    product_category_id: Term | None = None
    allowed_domains: list[Term] = Field(min_length=1, max_length=8)
    language: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$")] | None = None
    country: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z]{2}$")] | None = None
    date_from: IsoDate | None = None
    date_to: IsoDate | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 5
    mode: Literal["independent", "merge", "fallback"]
    providers: list[Literal["tavily", "brave"]] = Field(min_length=1, max_length=2)
    data_class: Literal["synthetic"]

    @field_validator("date_from", "date_to")
    @classmethod
    def calendar_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def providers_and_domains(self):
        count = 1 if self.mode == "independent" else 2
        if len(self.providers) != count or len(set(self.providers)) != count:
            raise ValueError("搜索源与搜索策略不符。")
        self.allowed_domains = sorted(set(domain.lower() for domain in self.allowed_domains))
        return self


class AcquisitionInput(AcquisitionScopeInput):
    research_object: Object
    research_goal: Goal
    keywords: list[Term] = Field(min_length=1, max_length=12)
    include_terms: list[Term] = Field(default_factory=list, max_length=12)
    exclude_terms: list[Term] = Field(default_factory=list, max_length=12)


Unit = Literal["tavily_credit", "brave_request", "stackexchange_request", "youtube_quota_unit"]
Number = Annotated[int, Field(strict=True, ge=0, le=2000)]


class SamplingInput(AcquisitionScopeInput):
    request_key: UUID
    source_ids: list[Literal["m08-stackexchange", "m08-youtube", "m08-reddit"]] = Field(min_length=1, max_length=2)
    sample_target: Annotated[int, Field(strict=True, ge=1, le=400)]
    per_source_limit: Annotated[int, Field(strict=True, ge=1, le=400)]
    query_limit: Number
    page_limit: Number
    batch_count: Annotated[int, Field(strict=True, ge=1, le=10)]
    budgets: dict[Unit, Number] = Field(default_factory=dict, max_length=4)
    fixture_scenario: Literal["normal", "primary_unavailable", "source_unavailable"] = "normal"
    fallback_format: Literal["none", "csv", "xlsx"] = "none"

    @field_validator("source_ids")
    @classmethod
    def distinct_sources(cls, sources):
        if len(set(sources)) != len(sources):
            raise ValueError("采样来源不能重复。")
        return sources


class StepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID


@contextmanager
def task_errors():
    try:
        yield
    except (KeyError, IndexError):
        raise HTTPException(404, "找不到该项目下的任务或证据。") from None
    except AuthorizationBlocked as exc:
        raise HTTPException(403, exc.code) from None
    except TaskError as exc:
        raise HTTPException(404 if exc.code == "task_not_found" else 409, exc.code) from None
    except PlanError as exc:
        raise HTTPException(422, str(exc)) from None
    except Conflict:
        raise HTTPException(409, "本机任务或来源资格已变化。") from None
    except (sqlite3.Error, OSError):
        raise HTTPException(503, "本机采样任务账本暂不可用。") from None


def register_acquisition(app):
    parse_preview = body(AcquisitionInput, 12 * 1024, label="查询计划")
    parse_demo = body(AcquisitionScopeInput, 4 * 1024, label="离线演示配置")
    parse_task = body(SamplingInput, 8 * 1024, label="合成采样任务")
    parse_step = body(StepInput, 1024, label="检查点请求")

    @app.get("/api/acquisition/sources")
    def sources(request: Request):
        state = request.app.state
        try:
            settings = state.settings.with_local(state.vault.read())
        except VaultError:
            catalogue = source_catalog({})
            for source in catalogue["sources"]:
                if source["provider"] in SEARCH_KEYS:
                    source["credential_configured"] = None
                    source["credential_status"] = "unavailable"
            return {**catalogue, "platforms": platform_catalog()}
        catalogue = source_catalog(settings.keys)
        for source in catalogue["sources"]:
            provider = source["provider"]
            if provider in SEARCH_KEYS and source["credential_configured"]:
                tests = recent_tests(state.diagnostics, settings, provider)
                source["connection_diagnostic"] = search_quota(
                    state.diagnostics, settings, provider, tests[0] if tests else {},
                )
        return {**catalogue, "platforms": platform_catalog()}

    def execute(request, study_id, form, runner):
        state = request.app.state
        try:
            return runner(state.studies, str(study_id), form.model_dump(mode="json"))
        except KeyError:
            raise HTTPException(404, "项目或范围不存在。") from None
        except (PlanError, Denied) as exc:
            raise HTTPException(422, str(exc)) from None
        except (OSError, sqlite3.DatabaseError):
            raise HTTPException(503, "本机离线回执账本不可用。") from None

    @app.post("/api/acquisition/{study_id}/preview")
    def create_preview(request: Request, study_id: UUID, form: AcquisitionInput = Depends(parse_preview)):
        return execute(request, study_id, form, preview)

    @app.post("/api/acquisition/{study_id}/demo")
    def run_demo(request: Request, study_id: UUID, form: AcquisitionScopeInput = Depends(parse_demo)):
        def run(studies, project, data):
            return demo(studies, project, data, request.app.state.settings.directory)

        return execute(request, study_id, form, run)

    @app.get("/api/acquisition/{study_id}/tasks")
    def list_tasks(request: Request, study_id: UUID, offset: Annotated[int, Query(ge=0, le=10000)] = 0):
        sampling = request.app.state.sampling
        project = str(study_id)
        with task_errors():
            sampling.authorize_project(project)
            rows = sampling.ledger.list(project, offset=offset)
            visible = []
            for row in rows:
                try:
                    detail = sampling.project_view(sampling.ledger.get(project, row["acquisition_task_id"]))
                except AuthorizationBlocked:
                    continue
                visible.append({key: value for key, value in detail.items() if key not in (
                    "config", "attempts", "history",
                )})
            return {"tasks": visible, "next_offset": offset + len(rows) if len(rows) == 50 else None}

    @app.post("/api/acquisition/{study_id}/tasks", status_code=201)
    def create_task(request: Request, study_id: UUID, form: SamplingInput = Depends(parse_task)):
        sampling = request.app.state.sampling
        project = str(study_id)
        with task_errors():
            sampling.authorize_project(project)
            config = sampling_config(sampling.studies, project, form.model_dump(mode="json"))
            sampling.authorize(config)
            task = sampling.ledger.create(project, config, actor=ACTOR, idempotency_key=str(form.request_key))
            return sampling.project_view(task)

    @app.post("/api/acquisition/{study_id}/tasks/preview")
    def preview_task(request: Request, study_id: UUID, form: SamplingInput = Depends(parse_task)):
        sampling = request.app.state.sampling
        project = str(study_id)
        with task_errors():
            sampling.authorize_project(project)
            config = sampling_config(sampling.studies, project, form.model_dump(mode="json"))
            sampling.authorize(config)
            return {"config": config}

    @app.get("/api/acquisition/{study_id}/tasks/{task_id}")
    def task_detail(request: Request, study_id: UUID, task_id: UUID):
        sampling = request.app.state.sampling
        with task_errors():
            sampling.authorize_project(str(study_id))
            return sampling.project_view(sampling.ledger.get(str(study_id), str(task_id)))

    @app.post("/api/acquisition/{study_id}/tasks/{task_id}/step")
    def task_step(request: Request, study_id: UUID, task_id: UUID, form: StepInput = Depends(parse_step)):
        sampling = request.app.state.sampling
        with task_errors():
            sampling.authorize_project(str(study_id))
            task = sampling.ledger.step(
                str(study_id), str(task_id), actor=ACTOR, authorize=sampling.authorize, worker=sampling.work,
                idempotency_key=str(form.request_key), should_dispatch=should_dispatch, recover=sampling.recover,
            )
            return sampling.project_view(task)

    @app.post("/api/acquisition/{study_id}/tasks/{task_id}/{action}")
    def task_action(request: Request, study_id: UUID, task_id: UUID,
                    action: Literal["queue", "pause", "resume", "cancel"]):
        sampling = request.app.state.sampling
        with task_errors():
            sampling.authorize_project(str(study_id))
            if action in ("pause", "cancel"):
                sampling.authorize(sampling.ledger.get(str(study_id), str(task_id))["config"])
            task = sampling.ledger.action(str(study_id), str(task_id), action, actor=ACTOR,
                                          authorize=sampling.authorize)
            return sampling.project_view(task)

    @app.get("/api/acquisition/{study_id}/tasks/{task_id}/evidence/{index}")
    def read_task_evidence(request: Request, study_id: UUID, task_id: UUID, index: int):
        sampling = request.app.state.sampling
        with task_errors():
            sampling.authorize_project(str(study_id))
            task = sampling.ledger.get(str(study_id), str(task_id))
            config = {**task["config"], "acquisition_task_id": str(task_id)}
            sampling.authorize(config)
            items = [item for attempt in task["attempts"]
                     if attempt["state"] == "reconciled" and attempt["receipt"] is not None
                     for item in attempt["receipt"].get("evidence", ())]
            if not 0 <= index < len(items):
                raise KeyError(index)
            return sampling.evidence(config, items[index])

    @app.post("/api/acquisition/{study_id}/collect")
    def formal_collection(study_id: UUID):
        raise HTTPException(403, FORMAL_COLLECTION["reason"])
