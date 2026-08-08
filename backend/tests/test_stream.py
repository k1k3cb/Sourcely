"""Tests for the LLM service and /query/stream endpoint."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest


def test_build_user_prompt_includes_question():
    from app.services.llm import build_user_prompt
    from app.services.retrieval import RetrievedChunk
    from uuid import uuid4

    chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            filename="guide.pdf",
            page_start=1,
            page_end=1,
            text="Some context here.",
            score=0.9,
        )
    ]
    prompt = build_user_prompt("What is X?", chunks)
    assert "What is X?" in prompt
    assert "guide.pdf" in prompt
    assert "Some context here." in prompt
    assert "page=1" in prompt


def test_build_user_prompt_handles_empty_chunks():
    from app.services.llm import build_user_prompt
    prompt = build_user_prompt("Anything?", [])
    assert "Anything?" in prompt
    assert "no relevant documents" in prompt


def test_sse_format():
    from app.api.query import _sse
    out = _sse("token", {"t": "hello"})
    assert out.startswith(b"event: token\ndata: ")
    body = out.split(b"data: ", 1)[1].rstrip(b"\n\n")
    assert json.loads(body) == {"t": "hello"}


@pytest.mark.asyncio
async def test_query_stream_yields_tokens_and_sources(client):
    """End-to-end: /query/stream yields SSE events in the right order."""
    from uuid import uuid4
    from app.services import retrieval
    from app.api import query as query_module
    from app.services import llm

    fake_chunk = retrieval.RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="guide.pdf",
        page_start=1,
        page_end=1,
        text="relevant context",
        score=0.9,
    )

    async def fake_retrieve(session, user_id, question, k=5):
        return [fake_chunk]

    async def fake_stream(system, user, **kwargs) -> AsyncIterator[str]:
        assert "relevant context" in user
        for tok in ("Hello", " ", "world"):
            yield tok

    with (
        patch.object(query_module, "retrieve", side_effect=fake_retrieve),
        patch.object(query_module, "get_llm") as mock_get_llm,
    ):
        mock_llm = mock_get_llm.return_value
        mock_llm.stream.side_effect = fake_stream

        await client.post(
            "/api/v1/auth/register",
            json={"email": "streamer@example.com", "password": "supersecret"},
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "streamer@example.com", "password": "supersecret"},
        )

        async with client.stream(
            "POST", "/api/v1/query/stream", json={"question": "hi", "k": 3}
        ) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            body = b"".join([chunk async for chunk in r.aiter_bytes()]).decode()

    # Parse SSE events
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        ev = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[len("event: "):]
            elif line.startswith("data: "):
                data = line[len("data: "):]
        if ev and data is not None:
            events.append((ev, json.loads(data)))

    token_events = [e for e in events if e[0] == "token"]
    source_events = [e for e in events if e[0] == "sources"]
    done_events = [e for e in events if e[0] == "done"]

    # Token events concatenated form the LLM answer
    full_answer = "".join(e[1]["t"] for e in token_events)
    assert full_answer == "Hello world"

    # Sources event has the chunk info
    assert len(source_events) == 1
    sources = source_events[0][1]["sources"]
    assert len(sources) == 1
    assert sources[0]["filename"] == "guide.pdf"
    assert sources[0]["page_start"] == 1

    # Done event closes the stream
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_query_stream_emits_sources_even_when_llm_yields_nothing(client):
    """When LLM produces no tokens, we still send the sources event."""
    from uuid import uuid4
    from app.services import retrieval
    from app.api import query as query_module
    from app.services import llm

    fake_chunk = retrieval.RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="guide.pdf",
        page_start=1,
        page_end=1,
        text="x",
        score=0.9,
    )

    async def fake_retrieve(session, user_id, question, k=5):
        return [fake_chunk]

    async def empty_stream(system, user, **kwargs) -> AsyncIterator[str]:
        if False:
            yield ""

    with (
        patch.object(query_module, "retrieve", side_effect=fake_retrieve),
        patch.object(query_module, "get_llm") as mock_get_llm,
    ):
        mock_llm = mock_get_llm.return_value
        mock_llm.stream.side_effect = empty_stream

        await client.post(
            "/api/v1/auth/register",
            json={"email": "streamer2@example.com", "password": "supersecret"},
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "streamer2@example.com", "password": "supersecret"},
        )
        async with client.stream(
            "POST", "/api/v1/query/stream", json={"question": "hi", "k": 3}
        ) as r:
            assert r.status_code == 200
            body = b"".join([chunk async for chunk in r.aiter_bytes()]).decode()

    # sources event is present even with no token events
    assert "event: sources" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_query_stream_sends_error_event_on_llm_failure(client):
    from uuid import uuid4
    from app.services import retrieval
    from app.api import query as query_module
    from app.services import llm

    fake_chunk = retrieval.RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="g.pdf",
        page_start=1,
        page_end=1,
        text="x",
        score=0.9,
    )

    async def fake_retrieve(session, user_id, question, k=5):
        return [fake_chunk]

    async def broken_stream(system, user, **kwargs) -> AsyncIterator[str]:
        raise RuntimeError("provider down")
        yield ""  # pragma: no cover

    with (
        patch.object(query_module, "retrieve", side_effect=fake_retrieve),
        patch.object(query_module, "get_llm") as mock_get_llm,
    ):
        mock_llm = mock_get_llm.return_value
        mock_llm.stream.side_effect = broken_stream

        await client.post(
            "/api/v1/auth/register",
            json={"email": "streamer3@example.com", "password": "supersecret"},
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "streamer3@example.com", "password": "supersecret"},
        )
        async with client.stream(
            "POST", "/api/v1/query/stream", json={"question": "hi", "k": 3}
        ) as r:
            assert r.status_code == 200
            body = b"".join([chunk async for chunk in r.aiter_bytes()]).decode()

    assert "event: error" in body
    assert "provider down" in body


@pytest.mark.asyncio
async def test_query_stream_requires_auth(client):
    r = await client.post(
        "/api/v1/query/stream", json={"question": "hi", "k": 3}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_chunk_other_user_returns_404(client, db_session, db_engine):
    """A user cannot read another user's chunks (404 even if they know
    the chunk and document ids)."""
    from app.core.security import hash_password
    from app.models.chunk import Chunk
    from app.models.document import Document, DocumentStatus
    from app.models.user import User

    # Owner: seeds a user, a doc, and a chunk.
    owner = User(
        email="chunk-owner@example.com",
        hashed_password=hash_password("supersecret"),
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)
    d = Document(
        user_id=owner.id,
        filename="d.pdf",
        storage_path=f"{owner.id}/d.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        page_count=1,
        status=DocumentStatus.ready,
    )
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    c = Chunk(
        document_id=d.id,
        page_start=1,
        page_end=1,
        text="private",
        token_count=1,
        embedding_model="fake",
        embedding=[0.0],
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)

    # Outsider: register, login, and try to read the owner's chunk.
    await client.post(
        "/api/v1/auth/register",
        json={"email": "chunk-outsider@example.com", "password": "supersecret"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "chunk-outsider@example.com", "password": "supersecret"},
    )
    r = await client.get(f"/api/v1/documents/{d.id}/chunks/{c.id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_chunk_endpoint_shape(client):
    """The endpoint returns the expected JSON shape (404 if not found)."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "shape-tester@example.com", "password": "supersecret"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "shape-tester@example.com", "password": "supersecret"},
    )
    # Random UUIDs that won't exist
    r = await client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000/chunks/00000000-0000-0000-0000-000000000000"
    )
    assert r.status_code == 404
    assert r.json() == {"detail": "Not found"}
