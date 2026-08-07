from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_session
from app.models.user import User
from app.schemas.query import QueryRequest, QueryResponse, Source
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
    # The LLM-backed answer comes in Etapa 5. For now we surface the
    # retrieved sources and a deterministic placeholder so the UI can
    # be wired up against the same contract.
    if not sources:
        answer = (
            "No relevant documents found. Upload some PDFs first, or "
            "rephrase the question."
        )
    else:
        answer = (
            f"Found {len(sources)} relevant chunk(s) across your documents. "
            "Answer generation lands in Etapa 5."
        )
    return QueryResponse(answer=answer, sources=sources)
