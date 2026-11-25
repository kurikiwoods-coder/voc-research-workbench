"""Same-origin workbook upload, previews, confirmation, batch history and error reports."""

from contextlib import contextmanager
import csv
import hashlib
from io import StringIO
import sqlite3
from threading import BoundedSemaphore
from typing import Annotated, Literal
from unicodedata import normalize
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints
from starlette.concurrency import run_in_threadpool

from src.config import ROOT
from src.dashboard.api_setup import body
from src.ingestion.import_files import ImportProblem, MAX_UPLOAD, file_kind, list_sheets, read_sheet
from src.ingestion.import_mapping import evaluate, field_catalog, suggestions
from src.raw_store.store import Conflict, dump


MAX_PARSE_JOBS = 2
CHECK_VERSION = 1
Privacy = Literal["unknown", "public", "private", "internal"]
RowFilter = Literal["all", "staged", "pending_review", "duplicate", "rejected"]
SheetIndex = Annotated[int, Field(strict=True, ge=0, lt=40)]
Offset = Annotated[int, Query(ge=0, le=5000)]


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet_index: SheetIndex
    mapping: dict[str, StrictInt] = Field(max_length=64)
    privacy: Privacy = "unknown"


class Preview(Plan):
    offset: int = Field(default=0, ge=0, le=5000)


class Confirm(Plan):
    preview_token: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


def form(model):
    return body(model, 8192, label="导入配置", explain=lambda _: "导入配置无效，请检查工作表和字段映射。")


@contextmanager
def errors():
    try:
        yield
    except KeyError:
        raise HTTPException(404, "此项目下找不到所选范围、文件或导入批次。") from None
    except ImportProblem as exc:
        raise HTTPException(422, str(exc)) from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(503, "无法读取或保存本机导入。请检查数据库权限和剩余空间后重试。") from None


def preview_signature(file, plan):
    # File digest and frozen context anchor retries. Server recomputes all row outcomes.
    content = [CHECK_VERSION, file["study_id"], file["scope_id"], file["sha256"],
               plan.sheet_index, plan.mapping, plan.privacy]
    return hashlib.sha256(dump(content).encode()).hexdigest()


def sheet_preview(sheet):
    return {
        "sheet_name": sheet.name, "header_line": sheet.header_line,
        "columns": sheet.columns, "total": len(sheet.rows),
        "encoding": sheet.encoding, "delimiter": sheet.delimiter,
        "samples": [{"line_number": row.line, "populated": [bool(cell.strip()) for cell in row.values],
                     "content_restricted": True} for row in sheet.rows[:5]],
        "standard_fields": field_catalog(), "suggested_mapping": suggestions(sheet.columns),
        "blank_headers": [index for index, name in enumerate(sheet.columns) if not name.strip()],
    }


def safe_csv_cell(value):
    text = str(value) if value is not None else ""
    normalized = normalize("NFKC", text)
    if normalized.startswith(("\t", "\r", "\n")) or normalized.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def issue_csv(batch, rows):
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["批次 ID", "工作表", "文件行号", "状态", "级别", "问题编号", "问题说明", "重复原行号"])
    for row in rows:
        for issue in row["issues"]:
            writer.writerow(map(safe_csv_cell, [
                batch["batch_id"], batch["sheet_name"], row["line_number"], row["status"],
                issue["severity"], issue["code"], issue["message"], row["duplicate_of_line"],
            ]))
    return buffer.getvalue().encode("utf-8-sig")


def register_imports(app):
    router = APIRouter(prefix="/api/imports", tags=["数据导入"])
    slots = BoundedSemaphore(MAX_PARSE_JOBS)

    @contextmanager
    def parse_slot():
        if not slots.acquire(blocking=False):
            raise HTTPException(429, "已有文件正在解析，稍后可重试。")
        try:
            yield
        finally:
            slots.release()

    def store(request: Request):
        return request.app.state.imports

    @router.get("/templates/{kind}")
    def template(kind: Literal["csv", "xlsx"]):
        return FileResponse(ROOT / "examples" / f"import-template.{kind}", filename=f"voc-import-template.{kind}")

    @router.get("/{study_id}/batches")
    def history(study_id: UUID, db=Depends(store), offset: Offset = 0):
        with errors():
            return db.history(str(study_id), offset)

    @router.post("/{study_id}/scopes/{scope_id}/uploads", status_code=201)
    async def upload(request: Request, study_id: UUID, scope_id: UUID, db=Depends(store)):
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/octet-stream":
            raise HTTPException(415, "请以文件方式上传 CSV 或 XLSX。")
        try:
            filename = unquote(request.headers.get("x-voc-filename", ""), errors="strict")
        except UnicodeDecodeError:
            raise HTTPException(422, "文件名编码不合法。") from None
        study, scope = str(study_id), str(scope_id)

        def save(data, kind):
            return db.upload(study, scope, filename, kind, data, list_sheets(data, kind))

        with errors(), parse_slot():
            kind = file_kind(filename)
            await run_in_threadpool(db.check_target, study, scope)
            buffer = bytearray()
            async for chunk in request.stream():
                if len(buffer) + len(chunk) > MAX_UPLOAD:
                    raise HTTPException(413, "文件超过 8 MiB，请拆分后上传。")
                buffer.extend(chunk)
            if not buffer:
                raise ImportProblem("文件为空。")
            return await run_in_threadpool(save, bytes(buffer), kind)

    @router.get("/{study_id}/uploads/{file_id}")
    def inspect(study_id: UUID, file_id: UUID, db=Depends(store),
                sheet_index: Annotated[int, Query(ge=0, lt=40)] = 0):
        with errors(), parse_slot():
            file, scope = db.get_file(str(study_id), str(file_id), sheet_index)
            sheet = read_sheet(file.pop("source_bytes"), file["kind"], sheet_index)
            db.check_preview_sources(str(study_id), sheet)
            return {"file": file, "scope_version": scope["scope_version"], **sheet_preview(sheet)}

    @router.delete("/{study_id}/uploads/{file_id}")
    def discard(study_id: UUID, file_id: UUID, db=Depends(store)):
        with errors():
            db.discard(str(study_id), str(file_id))
            return {"discarded": True}

    @router.post("/{study_id}/uploads/{file_id}/preview")
    def preview(study_id: UUID, file_id: UUID, plan=Depends(form(Preview)), db=Depends(store)):
        with errors(), parse_slot():
            try:
                file, scope = db.get_file(str(study_id), str(file_id), plan.sheet_index)
            except Conflict:
                receipt = db.revoked_preview_receipt(str(study_id), str(file_id), plan.sheet_index,
                                                    plan.mapping, plan.privacy)
                if receipt is None:
                    raise
                return receipt
            sheet = read_sheet(file.pop("source_bytes"), file["kind"], plan.sheet_index)
            db.check_preview_sources(str(study_id), sheet)
            rows, summary = evaluate(sheet, plan.mapping, scope, plan.privacy)
            flagged = [row for row in rows if row["issues"]]
            return {
                "preview_token": preview_signature(file, plan), "summary": {**summary, "source_types": {}},
                "sample_rows": [{"line_number": row["line_number"], "status": row["status"],
                                 "content_restricted": True, "privacy": row["privacy"]} for row in rows[:5]],
                "issue_rows": [{key: row[key] for key in ("line_number", "status", "issues", "duplicate_of_line")}
                               for row in flagged[plan.offset:plan.offset + 20]],
                "more_issues": len(flagged) > plan.offset + 20,
            }

    @router.post("/{study_id}/uploads/{file_id}/confirm", status_code=201)
    def confirm(study_id: UUID, file_id: UUID, plan=Depends(form(Confirm)), db=Depends(store)):
        study, upload_id = str(study_id), str(file_id)
        with errors():
            receipt = db.confirmation_receipt(
                study, upload_id, plan.sheet_index, plan.mapping, plan.privacy, plan.preview_token,
            )
            if receipt is not None:
                return receipt
        with errors(), parse_slot():
            file, scope = db.get_file(study, upload_id, plan.sheet_index)
            signature = preview_signature(file, plan)
            if plan.preview_token != signature:
                raise Conflict("导入配置已变化，请重新运行质量检查。")
            sheet = read_sheet(file.pop("source_bytes"), file["kind"], plan.sheet_index)
            rows, summary = evaluate(sheet, plan.mapping, scope, plan.privacy)
            if not (summary["staged"] or summary["pending_review"]):
                raise ImportProblem("没有可暂存的记录。请修正文件中的错误后重新上传。")
            return db.commit(file, sheet, plan.sheet_index, plan.mapping, plan.privacy, signature, rows, summary)

    @router.get("/{study_id}/batches/{batch_id}")
    def detail(study_id: UUID, batch_id: UUID, db=Depends(store), status: RowFilter = "all", offset: Offset = 0):
        with errors():
            return db.get_batch(str(study_id), str(batch_id), status, offset)

    @router.get("/{study_id}/batches/{batch_id}/errors.csv")
    def report(study_id: UUID, batch_id: UUID, db=Depends(store)):
        with errors():
            batch, rows = db.report(str(study_id), str(batch_id))
            return Response(issue_csv(batch, rows), media_type="text/csv",
                            headers={"Content-Disposition": f'attachment; filename="import-errors-{batch_id}.csv"'})

    @router.post("/{study_id}/batches/{batch_id}/revoke")
    def revoke(study_id: UUID, batch_id: UUID, db=Depends(store)):
        with errors():
            return db.revoke(str(study_id), str(batch_id))

    app.include_router(router)
