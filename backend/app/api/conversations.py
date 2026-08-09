from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_session
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.conversation import (
    ConversationDetail,
    ConversationOut,
    CreateConversation,
    MessageOut,
    SendMessage,
)
from app.services.llm import SYSTEM_PROMPT, build_user_prompt, get_llm
from app.services.retrieval import RetrievedChunk, retrieve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _sources_to_refs(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {
            "chunk_id": str(c.chunk_id),
            "document_id": str(c.document_id),
            "filename": c.filename,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "score": c.score,
        }
        for c in chunks
    ]


def _snippet(text: str, max_chars: int = 240) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "\u2026"


def _format_sources_for_sse(chunks: list[RetrievedChunk]) -> list[dict]:
    refs = _sources_to_refs(chunks)
    # Add snippet for the UI
    by_id = {str(c.chunk_id): c for c in chunks}
    out = []
    for r in refs:
        c = by_id[r["chunk_id"]]
        out.append({**r, "snippet": _snippet(c.text)})
    return out


async def _load_owned_conversation(
    session: AsyncSession, user_id: UUID, conv_id: UUID
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user_id
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
        )
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: CurrentUserDep, session: SessionDep
) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: CreateConversation, user: CurrentUserDep, session: SessionDep
) -> Conversation:
    conv = Conversation(user_id=user.id, title=payload.title)
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: UUID, user: CurrentUserDep, session: SessionDep
) -> ConversationDetail:
    conv = await _load_owned_conversation(session, user.id, conv_id)
    # Eagerly load messages via the relationship
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=json.loads(m.sources_json) if m.sources_json else None,
                created_at=m.created_at,
            )
            for m in conv.messages
        ],
    )


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conv_id: UUID, user: CurrentUserDep, session: SessionDep
) -> None:
    conv = await _load_owned_conversation(session, user.id, conv_id)
    await session.delete(conv)
    await session.commit()


def _sse(event: str, data: dict) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@router.post("/{conv_id}/messages")
async def send_message(
    conv_id: UUID,
    payload: SendMessage,
    user: CurrentUserDep,
    session: SessionDep,
) -> StreamingResponse:
    """Send a user message to the conversation, stream the assistant reply.

    The stream emits: meta (id of the user + assistant messages), token
    events, sources, done. The user message is persisted at the start;
    the assistant message is persisted at the end.
    """
    conv = await _load_owned_conversation(session, user.id, conv_id)

    # Persist the user message
    user_msg = Message(
        conversation_id=conv.id, role="user", content=payload.content
    )
    session.add(user_msg)
    await session.commit()
    await session.refresh(user_msg)

    # Auto-title from the first message
    if conv.title == "New conversation":
        conv.title = payload.content[:60].strip() or "New conversation"
        await session.commit()

    # Retrieve (read in same session; uses the same engine)
    chunks: list[RetrievedChunk] = await retrieve(
        session=session,
        user_id=user.id,
        question=payload.content,
        k=5,
    )
    sources_payload = _format_sources_for_sse(chunks)
    conv_id_str = str(conv.id)
    user_msg_id = str(user_msg.id)

    async def _stream() -> AsyncIterator[bytes]:
        llm = get_llm()
        user_prompt = build_user_prompt(payload.content, chunks)
        acc = ""
        try:
            yield _sse(
                "meta",
                {
                    "conversation_id": conv_id_str,
                    "user_message_id": user_msg_id,
                },
            )
            async for token in llm.stream(SYSTEM_PROMPT, user_prompt):
                acc += token
                yield _sse("token", {"t": token})
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM streaming failed in conversation: %s", exc)
            yield _sse("error", {"detail": str(exc)})
            return

        # Persist the assistant message. We use a fresh sessionmaker
        # bound to whatever engine `get_engine()` returns so tests
        # using StaticPool still see the same in-memory DB.
        from app.db.base import get_sessionmaker

        AsyncSessionLocal = get_sessionmaker()
        async with AsyncSessionLocal() as persist_session:
            assistant_msg = Message(
                conversation_id=UUID(conv_id_str),
                role="assistant",
                content=acc,
                sources_json=json.dumps(_sources_to_refs(chunks))
                if chunks
                else None,
            )
            persist_session.add(assistant_msg)
            # Touch conversation.updated_at
            from datetime import datetime, timezone

            from app.models.conversation import Conversation as Conv

            result = await persist_session.execute(
                select(Conv).where(Conv.id == UUID(conv_id_str))
            )
            conv_obj = result.scalar_one()
            conv_obj.updated_at = datetime.now(timezone.utc)
            await persist_session.commit()

        yield _sse(
            "sources",
            {"sources": sources_payload},
        )
        yield _sse("done", {})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
