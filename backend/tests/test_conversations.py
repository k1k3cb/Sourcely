"""Tests for the conversation history feature."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_create_conversation(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "supersecret"},
    )
    r = await client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "supersecret"})
    assert r.status_code == 200
    r = await client.post("/api/v1/conversations", json={"title": "My chat"})
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "My chat"
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_conversation_default_title(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "bob@example.com", "password": "supersecret"})
    r = await client.post("/api/v1/conversations", json={})
    assert r.status_code == 201
    assert r.json()["title"] == "New conversation"


@pytest.mark.asyncio
async def test_list_conversations_empty(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "carol@example.com", "password": "supersecret"})
    r = await client.get("/api/v1/conversations")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_conversations_scoped_to_user(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dan@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "dan@example.com", "password": "supersecret"})
    await client.post("/api/v1/conversations", json={"title": "A"})
    await client.post("/api/v1/conversations", json={"title": "B"})

    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/register",
        json={"email": "eve@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "eve@example.com", "password": "supersecret"})
    r = await client.get("/api/v1/conversations")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_conversation_other_user_returns_404(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "frank@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "frank@example.com", "password": "supersecret"})
    r = await client.post("/api/v1/conversations", json={"title": "private"})
    conv_id = r.json()["id"]

    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/register",
        json={"email": "grace@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "grace@example.com", "password": "supersecret"})
    r = await client.get(f"/api/v1/conversations/{conv_id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "henry@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "henry@example.com", "password": "supersecret"})
    r = await client.post("/api/v1/conversations", json={"title": "x"})
    cid = r.json()["id"]
    r = await client.delete(f"/api/v1/conversations/{cid}")
    assert r.status_code == 204
    r = await client.get(f"/api/v1/conversations/{cid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_send_message_persists_user_and_assistant(client):
    """End-to-end: send a message, mock the LLM, verify both turns persist."""
    from uuid import uuid4
    from app.services import retrieval
    from app.api import conversations as conv_module
    from app.services import llm

    fake_chunk = retrieval.RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="a.pdf",
        page_start=1,
        page_end=1,
        text="context",
        score=0.9,
    )

    async def fake_retrieve(session, user_id, question, k=5):
        return [fake_chunk]

    async def fake_stream(system, user, **kwargs) -> AsyncIterator[str]:
        for tok in ("The ", "answer."):
            yield tok

    await client.post(
        "/api/v1/auth/register",
        json={"email": "isaac@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "isaac@example.com", "password": "supersecret"})
    r = await client.post("/api/v1/conversations", json={})
    cid = r.json()["id"]

    with (
        patch.object(conv_module, "retrieve", side_effect=fake_retrieve),
        patch.object(conv_module, "get_llm") as mock_get_llm,
    ):
        mock_llm = mock_get_llm.return_value
        mock_llm.stream.side_effect = fake_stream

        async with client.stream(
            "POST",
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "What is X?"},
        ) as resp:
            assert resp.status_code == 200
            body = b"".join([c async for c in resp.aiter_bytes()]).decode()

    # Both turns persisted
    r = await client.get(f"/api/v1/conversations/{cid}")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "What is X?"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "The answer."
    assert msgs[1]["sources"] is not None
    assert len(msgs[1]["sources"]) == 1
    assert msgs[1]["sources"][0]["filename"] == "a.pdf"
    assert msgs[1]["sources"][0]["chunk_id"] == str(fake_chunk.chunk_id)
    # The conversation title was auto-updated from the first message
    assert r.json()["title"] == "What is X?"


@pytest.mark.asyncio
async def test_send_message_validates_content(client):
    # Register (may already exist; ignore 409)
    await client.post(
        "/api/v1/auth/register",
        json={"email": "jane@example.com", "password": "supersecret"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "supersecret"},
    )
    assert r.status_code == 200
    r = await client.post("/api/v1/conversations", json={})
    assert r.status_code == 201
    cid = r.json()["id"]
    r = await client.post(
        f"/api/v1/conversations/{cid}/messages", json={"content": ""}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_send_message_other_users_conversation_returns_404(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "kate@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "kate@example.com", "password": "supersecret"})
    r = await client.post("/api/v1/conversations", json={})
    cid = r.json()["id"]

    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/register",
        json={"email": "liam@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "liam@example.com", "password": "supersecret"})
    r = await client.post(
        f"/api/v1/conversations/{cid}/messages", json={"content": "hi"}
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_send_message_emits_sse_events(client):
    """The endpoint emits meta, token, sources, done in order."""
    from uuid import uuid4
    from app.services import retrieval
    from app.api import conversations as conv_module

    fake_chunk = retrieval.RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="a.pdf",
        page_start=1,
        page_end=1,
        text="ctx",
        score=0.9,
    )

    async def fake_retrieve(session, user_id, question, k=5):
        return [fake_chunk]

    async def fake_stream(system, user, **kwargs):
        for tok in ("A", "B", "C"):
            yield tok

    await client.post(
        "/api/v1/auth/register",
        json={"email": "mia@example.com", "password": "supersecret"},
    )
    await client.post("/api/v1/auth/login", json={"email": "mia@example.com", "password": "supersecret"})
    r = await client.post("/api/v1/conversations", json={})
    cid = r.json()["id"]

    with (
        patch.object(conv_module, "retrieve", side_effect=fake_retrieve),
        patch.object(conv_module, "get_llm") as mock_get_llm,
    ):
        mock_llm = mock_get_llm.return_value
        mock_llm.stream.side_effect = fake_stream

        async with client.stream(
            "POST",
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "hi"},
        ) as resp:
            assert resp.status_code == 200
            body = b"".join([c async for c in resp.aiter_bytes()]).decode()

    # Parse SSE events and concatenate tokens
    full_answer = ""
    events = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        ev = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if ev and data:
            events.append((ev, data))

    token_events = [e for e in events if e[0] == "token"]
    full_answer = "".join(json.loads(d)["t"] for _, d in token_events)
    assert full_answer == "ABC"
    assert any(e[0] == "meta" for e in events)
    assert any(e[0] == "sources" for e in events)
    assert any(e[0] == "done" for e in events)
