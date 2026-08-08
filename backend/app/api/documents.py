from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import get_current_user
from app.db.base import get_session
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.document import DocumentOut, DocumentWithUrl
from app.services.storage import StorageBackend, get_storage
from app.services.validation import is_pdf
from app.tasks.indexing import index_document

router = APIRouter(prefix="/documents", tags=["documents"])

settings = get_settings()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
StorageDep = Annotated[StorageBackend, Depends(get_storage)]


@router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="PDF file to upload")],
    user: CurrentUserDep,
    session: SessionDep,
    storage: StorageDep,
) -> Document:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only application/pdf is accepted",
        )

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_mb} MB",
        )
    if not is_pdf(data):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File is not a valid PDF (magic bytes mismatch)",
        )

    safe_name = file.filename or "document.pdf"
    storage_path = f"{user.id}/{uuid4()}-{safe_name[:200]}"
    storage.upload(storage_path, data, "application/pdf")

    doc = Document(
        user_id=user.id,
        filename=safe_name,
        storage_path=storage_path,
        mime_type="application/pdf",
        size_bytes=len(data),
        status=DocumentStatus.uploaded,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    background_tasks.add_task(index_document, doc.id)
    return doc


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    user: CurrentUserDep, session: SessionDep
) -> list[Document]:
    result = await session.execute(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{doc_id}", response_model=DocumentWithUrl)
async def get_document(
    doc_id: UUID, user: CurrentUserDep, session: SessionDep, storage: StorageDep
) -> DocumentWithUrl:
    doc = await session.execute(
        select(Document).where(
            Document.id == doc_id, Document.user_id == user.id
        )
    )
    doc = doc.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    out = DocumentWithUrl.model_validate(doc)
    out.signed_url = storage.signed_url(doc.storage_path)
    return out


@router.get("/{doc_id}/chunks/{chunk_id}")
async def get_chunk(
    doc_id: UUID,
    chunk_id: UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict:
    """Return a single chunk, scoped to the user via its parent document.

    Used by the chat UI to highlight the cited fragment when the user
    clicks a source. The chunk must belong to a document owned by the
    current user; otherwise 404.
    """
    from app.models.chunk import Chunk

    result = await session.execute(
        select(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Chunk.id == chunk_id,
            Document.id == doc_id,
            Document.user_id == user.id,
        )
    )
    chunk = result.scalar_one_or_none()
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {
        "id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "text": chunk.text,
        "token_count": chunk.token_count,
    }


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: UUID, user: CurrentUserDep, session: SessionDep, storage: StorageDep
) -> None:
    doc = await session.execute(
        select(Document).where(
            Document.id == doc_id, Document.user_id == user.id
        )
    )
    doc = doc.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        storage.delete(doc.storage_path)
    except Exception:  # noqa: BLE001
        # If the file is already gone in storage, still delete the row.
        pass
    await session.delete(doc)
    await session.commit()
