"""Local-only routes for the M08 frozen-scope preview and offline rehearsal."""

from datetime import date
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from src.dashboard.api_setup import body, recent_tests, search_quota
from src.config import SEARCH_KEYS
from src.execution.transport import Denied
from src.ingestion.m08_acquisition import FORMAL_COLLECTION, PlanError, demo, preview, source_catalog
from src.raw_store.credentials import VaultError


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


def register_acquisition(app):
    parse_preview = body(AcquisitionInput, 12 * 1024, label="查询计划")
    parse_demo = body(AcquisitionScopeInput, 4 * 1024, label="离线演示配置")

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
            return catalogue
        catalogue = source_catalog(settings.keys)
        for source in catalogue["sources"]:
            provider = source["provider"]
            if provider in SEARCH_KEYS and source["credential_configured"]:
                tests = recent_tests(state.diagnostics, settings, provider)
                source["connection_diagnostic"] = search_quota(
                    state.diagnostics, settings, provider, tests[0] if tests else {},
                )
        return catalogue

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

    @app.post("/api/acquisition/{study_id}/collect")
    def formal_collection(study_id: UUID):
        raise HTTPException(403, FORMAL_COLLECTION["reason"])
