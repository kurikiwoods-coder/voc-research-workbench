"""Local project and scope API. Project text stays in the workbench SQLite database."""

from contextlib import contextmanager
from datetime import date
import re
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator, model_validator

from src.dashboard.api_setup import body
from src.raw_store.store import Conflict
from src.raw_store.studies import PROJECT_FIELDS


StudyStatus = Literal["draft", "active"]
StatusFilter = Literal["open", "all", "draft", "active", "archived"]
Sort = Literal["updated", "created", "name"]
Mode = Literal["single_product", "single_category", "multi_product_category", "cross_category", "open"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Topic = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ListItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class StudyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DateWindow(StudyInput):
    start: date | None = None
    end: date | None = None

    @field_validator("start", "end", mode="before")
    @classmethod
    def iso_date(cls, value):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)):
            raise ValueError("请使用年月日（YYYY-MM-DD）格式。")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if self.start and self.end and self.start > self.end:
            raise ValueError("结束日期须等于或晚于开始日期。")
        return self


class ScopeInput(StudyInput):
    mode: Mode
    topic: Topic
    market: ShortText = ""
    language: ShortText = ""
    date_window: DateWindow = Field(default_factory=DateWindow)
    product_ids: list[Reference] = Field(default_factory=list, max_length=24)
    product_category_ids: list[Reference] = Field(default_factory=list, max_length=24)
    user_tasks: list[ListItem] = Field(default_factory=list, max_length=24)
    audience: LongText = ""
    source_preferences: list[ListItem] = Field(default_factory=list, max_length=24)
    inclusion_criteria: list[ListItem] = Field(default_factory=list, max_length=24)
    exclusion_criteria: list[ListItem] = Field(default_factory=list, max_length=24)

    @field_validator("product_ids", "product_category_ids")
    @classmethod
    def unique_references(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("引用 ID 不能重复。")
        return sorted(values)

    @model_validator(mode="after")
    def match_mode(self):
        products, categories = len(self.product_ids), len(self.product_category_ids)
        valid, message = {
            "single_product": (products == 1 and categories <= 1, "单一产品研究需填写一个产品 ID，品类 ID 最多一个。"),
            "single_category": (products == 0 and categories == 1, "单一品类研究需填写一个品类 ID，产品 ID 留空。"),
            "multi_product_category": (products >= 2 or categories >= 2, "多产品、多品类研究至少填写两个产品 ID 或两个品类 ID。"),
            "cross_category": (categories >= 2, "跨品类用户需求研究至少填写两个不同的品类 ID。"),
            "open": (products == 0 and categories == 0, "开放式研究中的产品 ID 和品类 ID 均须留空。"),
        }[self.mode]
        if not valid:
            raise ValueError(message)
        return self


class ProjectInput(StudyInput):
    name: Name
    description: LongText = ""
    background: LongText = ""
    objective: LongText = ""
    subject: LongText = ""
    status: StudyStatus = "draft"
    scope: ScopeInput
    change_note: ShortText = ""

    def metadata(self):
        return self.model_dump(include=set(PROJECT_FIELDS))

    def snapshot(self):
        return self.scope.model_dump(mode="json", exclude_none=True)


class CreateStudy(ProjectInput):
    request_key: UUID


class EditStudy(ProjectInput):
    revision: Annotated[int, Field(strict=True, ge=1)]


class StudyRevision(StudyInput):
    revision: Annotated[int, Field(strict=True, ge=1)]


class StudySearch(StudyInput):
    query: ShortText = ""
    status: StatusFilter = "open"
    sort: Sort = "updated"


FIELD_LABELS = {
    "name": "项目名称", "description": "项目描述", "background": "研究背景",
    "objective": "研究目标", "subject": "研究对象", "status": "项目状态", "revision": "项目修订号",
    "mode": "研究模式", "topic": "核心研究问题", "market": "目标市场", "language": "研究语言",
    "start": "开始日期", "end": "结束日期", "date_window": "研究时间范围",
    "product_ids": "产品引用", "product_category_ids": "品类引用", "user_tasks": "用户任务",
    "audience": "目标用户群体", "source_preferences": "数据来源偏好", "change_note": "变更说明",
    "inclusion_criteria": "纳入标准", "exclusion_criteria": "排除标准", "query": "搜索词",
}


def validation_message(exc):
    if not isinstance(exc, ValidationError):
        return "无法读取项目内容，请检查输入。"
    error = exc.errors(include_input=False, include_context=False, include_url=False)[0]
    if error["type"] == "value_error":
        return error["msg"].removeprefix("Value error, ")
    label = next((FIELD_LABELS[field] for field in reversed(error["loc"]) if field in FIELD_LABELS), "项目内容")
    if error["type"] in ("missing", "string_too_short"):
        return f"请填写{label}。"
    if error["type"] in ("too_long", "string_too_long"):
        return f"{label}超出长度或条数上限。"
    return f"{label}格式无效，请检查输入。"


def study_body(model):
    return body(model, 192 * 1024, label="项目表单内容", explain=validation_message)


@contextmanager
def study_errors():
    try:
        yield
    except KeyError:
        raise HTTPException(404, "找不到此研究项目或范围版本。") from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(503, "无法读取或保存本机项目。请检查数据库文件权限及存储空间后重试。") from None


def register_studies(app):
    router = APIRouter(prefix="/api/studies", tags=["研究项目"])

    def store(request: Request):
        return request.app.state.studies

    @router.get("")
    def list_studies(db=Depends(store)):
        with study_errors():
            return db.listing()

    @router.post("/search")
    def search(data=Depends(study_body(StudySearch)), db=Depends(store)):
        with study_errors():
            return db.listing(data.query, data.status, data.sort)

    @router.post("", status_code=201)
    def create(data=Depends(study_body(CreateStudy)), db=Depends(store)):
        with study_errors():
            return db.create(str(data.request_key), data.metadata(), data.snapshot(), data.change_note)

    @router.get("/{study_id}")
    def detail(study_id: UUID, db=Depends(store)):
        with study_errors():
            return db.get(str(study_id))

    @router.put("/{study_id}")
    def update(study_id: UUID, data=Depends(study_body(EditStudy)), db=Depends(store)):
        with study_errors():
            return db.update(str(study_id), data.revision, data.metadata(), data.snapshot(), data.change_note)

    @router.delete("/{study_id}")
    def archive(study_id: UUID, revision: Annotated[int, Query(ge=1)], db=Depends(store)):
        with study_errors():
            return db.archive(str(study_id), revision)

    @router.post("/{study_id}/restore")
    def restore(study_id: UUID, data=Depends(study_body(StudyRevision)), db=Depends(store)):
        with study_errors():
            return db.restore(str(study_id), data.revision)

    @router.post("/{study_id}/select")
    def select(study_id: UUID, db=Depends(store)):
        with study_errors():
            return db.select(str(study_id))

    @router.get("/{study_id}/scopes")
    def history(study_id: UUID, db=Depends(store)):
        with study_errors():
            return db.history(str(study_id))

    @router.get("/{study_id}/scopes/{scope_id}")
    def scope(study_id: UUID, scope_id: UUID, db=Depends(store)):
        with study_errors():
            return db.get_scope(str(study_id), str(scope_id))

    @router.post("/{study_id}/scopes/{scope_id}/freeze")
    def freeze(study_id: UUID, scope_id: UUID, db=Depends(store)):
        with study_errors():
            return db.freeze(str(study_id), str(scope_id))

    app.include_router(router)
