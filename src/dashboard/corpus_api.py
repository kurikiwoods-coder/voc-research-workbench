"""Read and review local corpus evidence for one research project."""

from contextlib import contextmanager
from datetime import date
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from src.dashboard.api_setup import body
from src.raw_store.store import Conflict


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["verified", "excluded"]
    role: Literal["user_quote", "background", "internal", "synthetic"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    basis: Annotated[str, Field(max_length=1000)] = ""
    retention_until: date | None = None
    license_status: Literal["authorized", "pending", "denied", "revoked", "expired", "unknown"] | None = None
    license_evidence_ref: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    license_issued_on: date | None = None
    reauthorize: bool = False


Offset = Annotated[int, Query(ge=0, le=100_000)]
RecordId = Annotated[str, Path(pattern=r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}:[1-9][0-9]{0,6}$")]


@contextmanager
def corpus_errors():
    try:
        yield
    except KeyError:
        raise HTTPException(404, "此项目下找不到所选语料或导入批次。") from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(503, "无法读取或保存本机语料。请检查数据库权限和剩余空间后重试。") from None


def register_corpus(app):
    router = APIRouter(prefix="/api/corpus", tags=["原始语料"])
    review_form = body(Review, 12_288, label="语料审核")

    def store(request: Request):
        return request.app.state.corpus

    @router.get("/{study_id}/batches")
    def batches(study_id: UUID, offset: Offset = 0, db=Depends(store)):
        with corpus_errors():
            return db.batches(str(study_id), offset)

    @router.get("/{study_id}/batches/{batch_id}")
    def candidates(study_id: UUID, batch_id: UUID, offset: Offset = 0, db=Depends(store)):
        with corpus_errors():
            return db.candidates(str(study_id), str(batch_id), offset)

    @router.get("/{study_id}/records/{record_id}")
    def detail(study_id: UUID, record_id: RecordId, db=Depends(store)):
        with corpus_errors():
            return db.detail(str(study_id), str(record_id))

    @router.get("/{study_id}/records/{record_id}/eligible")
    def eligible(study_id: UUID, record_id: RecordId, db=Depends(store)):
        with corpus_errors():
            return db.qualified_record(str(study_id), str(record_id))

    @router.post("/{study_id}/records/{record_id}/review")
    def review(study_id: UUID, record_id: RecordId, form=Depends(review_form), db=Depends(store)):
        with corpus_errors():
            return db.review(str(study_id), str(record_id), **form.model_dump(mode="json"))

    app.include_router(router)
