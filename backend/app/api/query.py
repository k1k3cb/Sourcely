from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.security import get_current_user
from app.db.base import get_session
from app.models.document import Document
from app.models.user import User
from app.schemas.query import QueryRequest, QueryResponse, Source
from app.services.llm import SYSTEM_PROMPT, build_user_prompt, get_llm
from app.services.retrieval import RetrievedChunk, retrieve
from app.services.storage import StorageBackend, get_storage

router = APIRouter(prefix="/query", tags=["query"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
StorageDep = Annotated[StorageBackend, Depends(get_storage)]


def _snippet(text: str, max_chars: int = 240) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "\u2026"


async def _resolve_documents(
    session: AsyncSession,
    storage: StorageBackend,
    chunks: list[RetrievedChunk],
) -> dict:
    """Batch-fetch the parent documents for the retrieved chunks.

    Returns a mapping chunk_id -> {mime_type, document_url}.
    """
    out: dict = {}
    if not chunks:
        return out
    doc_ids = {c.document_id for c in chunks}
    result = await session.execute(
        select(Document).where(Document.id.in_(doc_ids))
    )
    docs = {d.id: d for d in result.scalars().all()}
    for c in chunks:
        d = docs.get(c.document_id)
        if d is None:
            continue
        out[c.chunk_id] = {
            "mime_type": d.mime_type,
            "document_url": storage.signed_url(d.storage_path),
        }
    return out


def _format_source(
    chunk: RetrievedChunk,
    index: int,
    doc_meta: dict | None = None,
) -> Source:
    meta = doc_meta or {}
    return Source(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        filename=chunk.filename,
        mime_type=meta.get("mime_type", "application/octet-stream"),
        document_url=meta.get("document_url"),
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        start_seconds=chunk.start_seconds,
        end_seconds=chunk.end_seconds,
        snippet=_snippet(chunk.text),
        score=chunk.score,
        index=index,
    )


@router.post("", response_model=QueryResponse)
async def query(
    payload: QueryRequest,
    user: CurrentUserDep,
    session: SessionDep,
    storage: StorageDep,
) -> QueryResponse:
    chunks = await retrieve(
        session=session, user_id=user.id, question=payload.question, k=payload.k
    )
    doc_meta = await _resolve_documents(session, storage, chunks)
    sources = [
        _format_source(c, i, doc_meta.get(c.chunk_id))
        for i, c in enumerate(chunks, start=1)
    ]
    if not chunks:
        return QueryResponse(
            answer=(
                "No relevant documents found. Upload some PDFs first, or "
                "rephrase the question."
            ),
            sources=sources,
        )

    user_prompt = build_user_prompt(payload.question, chunks)
    try:
        answer = get_llm().complete(SYSTEM_PROMPT, user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM completion failed: %s", exc)
        answer = ""
    if not answer:
        answer = (
            f"Found {len(chunks)} relevant passage(s) in your documents, "
            "but I couldn't synthesize an answer right now. See the snippets below."
        )
    return QueryResponse(answer=answer, sources=sources)


def _sse(event: str, data: dict) -> bytes:
    """Format a Server-Sent Event."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


async def _answer_stream(
    session: AsyncSession,
    storage: StorageBackend,
    question: str,
    chunks: list[RetrievedChunk],
) -> AsyncIterator[bytes]:
    """Stream a token-by-token answer followed by a 'sources' event."""
    llm = get_llm()
    user_prompt = build_user_prompt(question, chunks)
    try:
        async for token in llm.stream(SYSTEM_PROMPT, user_prompt):
            yield _sse("token", {"t": token})
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM streaming failed: %s", exc)
        yield _sse("error", {"detail": str(exc)})
        return
    doc_meta = await _resolve_documents(session, storage, chunks)
    sources = [
        _format_source(c, i, doc_meta.get(c.chunk_id))
        for i, c in enumerate(chunks, start=1)
    ]
    yield _sse("sources", {"sources": [s.model_dump(mode="json") for s in sources]})
    yield _sse("done", {})


@router.post("/stream")
async def query_stream(
    payload: QueryRequest,
    user: CurrentUserDep,
    session: SessionDep,
    storage: StorageDep,
) -> StreamingResponse:
    chunks = await retrieve(
        session=session, user_id=user.id, question=payload.question, k=payload.k
    )
    return StreamingResponse(
        _answer_stream(session, storage, payload.question, chunks),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
