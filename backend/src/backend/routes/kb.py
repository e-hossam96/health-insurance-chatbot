from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from backend.deps import Db, RequireAdmin, SettingsDep
from backend.kb_jobs import KbJobRunner
from backend.models import Account, KbDocument, KbDocumentStatus, KbFileType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/kb-documents", tags=["kb"])

CHUNK_BYTES = 64 * 1024
ALLOWED_TYPES = {"pdf": KbFileType.pdf, "txt": KbFileType.txt, "docx": KbFileType.docx}


class KbDocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    error_message: str | None
    uploaded_by: str
    created_at: str


class KbDocumentList(BaseModel):
    items: list[KbDocumentOut]
    total: int
    max_upload_bytes: int


def _error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def _out(document: KbDocument, username: str) -> KbDocumentOut:
    return KbDocumentOut(
        id=document.id,
        filename=document.filename,
        file_type=document.file_type.value,
        file_size_bytes=document.file_size_bytes,
        status=document.status.value,
        error_message=document.error_message,
        uploaded_by=username,
        created_at=document.created_at.isoformat(),
    )


def _runner(request: Request) -> KbJobRunner:
    runner: KbJobRunner = request.app.state.kb_runner
    return runner


def _size_label(limit: int) -> str:
    if limit >= 1024 * 1024:
        return f"{limit / (1024 * 1024):g} MB"
    return f"{limit / 1024:g} KB"


async def _document_out(db: Db, document_id: int) -> KbDocumentOut:
    row = (
        await db.execute(
            select(KbDocument, Account.username).join(Account, Account.id == KbDocument.uploaded_by).where(KbDocument.id == document_id)
        )
    ).one_or_none()
    if row is None:
        raise _error("not_found", "Document not found.", 404)
    return _out(row[0], row[1])


@router.get("")
async def list_documents(
    db: Db,
    admin: RequireAdmin,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KbDocumentList:
    total = (await db.execute(select(func.count()).select_from(KbDocument))).scalar_one()
    rows = await db.execute(
        select(KbDocument, Account.username)
        .join(Account, Account.id == KbDocument.uploaded_by)
        .order_by(KbDocument.created_at.desc(), KbDocument.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return KbDocumentList(
        items=[_out(document, username) for document, username in rows.all()],
        total=total,
        max_upload_bytes=settings.kb_max_upload_bytes,
    )


@router.post("", status_code=201)
async def upload_document(
    request: Request,
    db: Db,
    admin: RequireAdmin,
    settings: SettingsDep,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
) -> KbDocumentOut:
    clean_name = Path(filename).name
    extension = clean_name.rsplit(".", 1)[-1].lower() if "." in clean_name else ""
    file_type = ALLOWED_TYPES.get(extension)
    if file_type is None:
        raise _error("unsupported_type", "Only pdf, txt and docx files are supported.", 415)

    limit = settings.kb_max_upload_bytes
    too_large = _error("file_too_large", f"The file is larger than {_size_label(limit)}.", 413)
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise too_large

    storage = Path(settings.kb_storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    final_path = storage / f"{uuid.uuid4().hex}.{extension}"
    partial_path = final_path.with_suffix(final_path.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with partial_path.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise too_large
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        partial_path.unlink(missing_ok=True)
        raise
    if size == 0:
        partial_path.unlink(missing_ok=True)
        raise _error("validation_error", "The file is empty.", 422)

    content_hash = digest.hexdigest()
    duplicate = (await db.execute(select(KbDocument.id).where(KbDocument.content_hash == content_hash))).scalar_one_or_none()
    if duplicate is not None:
        partial_path.unlink(missing_ok=True)
        raise _error("duplicate_document", "This file was already uploaded.", 409)

    partial_path.replace(final_path)
    document = KbDocument(
        filename=clean_name,
        file_type=file_type,
        file_size_bytes=size,
        storage_path=str(final_path),
        content_hash=content_hash,
        status=KbDocumentStatus.uploaded,
        uploaded_by=admin.id,
    )
    db.add(document)
    try:
        await db.commit()
    except Exception:
        final_path.unlink(missing_ok=True)
        raise
    _runner(request).enqueue(document.id)
    return await _document_out(db, document.id)


@router.post("/{document_id}/reindex")
async def reindex_document(document_id: int, request: Request, db: Db, admin: RequireAdmin) -> KbDocumentOut:
    document = await db.get(KbDocument, document_id)
    if document is None:
        raise _error("not_found", "Document not found.", 404)
    if document.status in (KbDocumentStatus.ready, KbDocumentStatus.failed):
        document.status = KbDocumentStatus.uploaded
        document.error_message = None
        await db.commit()
        _runner(request).enqueue(document_id)
    return await _document_out(db, document_id)


@router.delete("/{document_id}", status_code=204)
async def delete_kb_document(document_id: int, request: Request, db: Db, admin: RequireAdmin) -> Response:
    document = await db.get(KbDocument, document_id)
    if document is None:
        raise _error("not_found", "Document not found.", 404)
    runner = _runner(request)
    if runner.ai_settings is not None:
        try:
            await runner.delete_points(document_id, runner.ai_settings)
        except Exception as error:
            logger.warning("deleting the points of document %s failed", document_id, exc_info=True)
            raise _error("kb_index_unavailable", "The search index is unavailable. The document was kept.", 503) from error
    Path(document.storage_path).unlink(missing_ok=True)
    await db.delete(document)
    await db.commit()
    return Response(status_code=204)
