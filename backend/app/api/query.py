from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.security import get_current_user
from app.db.base import get_session
from app.models.user import User
from app.schemas.query import QueryRequest, QueryResponse, Source
from app.services.llm import SYSTEM_PROMPT, build_user_prompt, get_llm
from app.services.retrieval import RetrievedChunk, retrieve

router = APIRouter(prefix="/query", tags=["query"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _snippet(text: str, max_chars: int = 240) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "\u2026"


def _format_source(chunk: RetrievedChunk) -> Source:
    return Source(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        filename=chunk.filename,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        start_seconds=chunk.start_seconds,
        end_seconds=chunk.end_seconds,
        snippet=_snippet(chunk.text),
        score=chunk.score,
    )


@router.post("", response_model=QueryResponse)
async def query(
    payload: QueryRequest, user: CurrentUserDep, session: SessionDep
) -> QueryResponse:
    chunks = await retrieve(
        session=session, user_id=user.id, question=payload.question, k=payload.k
    )
    sources = [_format_source(c) for c in chunks]
    if not sources:
        answer = (
            "No relevant documents found. Upload some PDFs first, or "
            "rephrase the question."
        )
    else:
        answer = (
            f"Found {len(sources)} relevant chunk(s) across your documents."
        )
    return QueryResponse(answer=answer, sources=sources)


def _sse(event: str, data: dict) -> bytes:
    """Format a Server-Sent Event."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


async def _answer_stream(
    question: str, chunks: list[RetrievedChunk]
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
    sources = [_format_source(c) for c in chunks]
    yield _sse("sources", {"sources": [s.model_dump(mode="json") for s in sources]})
    yield _sse("done", {})


@router.post("/stream")
async def query_stream(
    payload: QueryRequest, user: CurrentUserDep, session: SessionDep
) -> StreamingResponse:
    chunks = await retrieve(
        session=session, user_id=user.id, question=payload.question, k=payload.k
    )
    return StreamingResponse(
        _answer_stream(payload.question, chunks),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
