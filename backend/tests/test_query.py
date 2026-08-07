"""Tests for the /query endpoint.

The /query endpoint delegates to services.retrieval.retrieve(). The
critical isolation guarantee (a user's query only sees their own chunks)
lives in the SQL of retrieve(), which uses JOIN chunks -> documents
WHERE d.user_id = current_user.id.

We test that contract two ways:
  1. By inspecting the SQL produced by retrieve() to confirm the JOIN +
     filter are present.
  2. By mocking retrieve() and verifying the endpoint passes the right
     user_id from the JWT.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_retrieve_sql_has_user_filter():
    """The retrieve() function must include JOIN + WHERE user_id."""
    import inspect

    from app.services import retrieval

    src = inspect.getsource(retrieval.retrieve)
    assert "join documents d" in src
    assert "d.user_id" in src
    assert "where d.user_id = :user_id" in src
    # The filter must reference the bind parameter, not be hardcoded
    assert ":user_id" in src


@pytest.mark.asyncio
async def test_retrieve_calls_embeddings_with_query_text(client):
    """The endpoint must pass the user_id from the JWT to retrieve."""
    from app.api import query as query_module

    captured = {}

    async def fake_retrieve(session, user_id, question, k=5):
        captured["user_id"] = user_id
        captured["question"] = question
        captured["k"] = k
        return []

    with patch.object(query_module, "retrieve", side_effect=fake_retrieve):
        # 201 first time, 409 if already registered from a prior test
        await client.post(
            "/api/v1/auth/register",
            json={"email": "iso@example.com", "password": "supersecret"},
        )
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": "iso@example.com", "password": "supersecret"},
        )
        assert r.status_code == 200
        me = await client.get("/api/v1/auth/me")
        my_id = me.json()["id"]
        r = await client.post(
            "/api/v1/query",
            json={"question": "What is pgvector?", "k": 3},
        )
        assert r.status_code == 200

    assert str(captured["user_id"]) == my_id
    assert captured["question"] == "What is pgvector?"
    assert captured["k"] == 3


@pytest.mark.asyncio
async def test_query_returns_empty_when_no_documents(client):
    from app.api import query as query_module

    async def empty_retrieve(session, user_id, question, k=5):
        return []

    with patch.object(query_module, "retrieve", side_effect=empty_retrieve):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "alice@example.com", "password": "supersecret"},
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "supersecret"},
        )
        r = await client.post(
            "/api/v1/query", json={"question": "anything", "k": 3}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["sources"] == []
        assert "No relevant" in body["answer"]


@pytest.mark.asyncio
async def test_query_with_mocked_retrieve_returns_sources(client):
    """When retrieve() returns chunks, the endpoint exposes them as sources."""
    from uuid import uuid4

    from app.services import retrieval
    from app.api import query as query_module

    fake_chunk = retrieval.RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="guide.pdf",
        page_start=2,
        page_end=2,
        text="pgvector uses HNSW indexes for fast similarity search.",
        score=0.91,
    )

    async def fake_retrieve(session, user_id, question, k=5):
        return [fake_chunk]

    # Patch the symbol the router imported (not just the source module).
    with patch.object(query_module, "retrieve", side_effect=fake_retrieve):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "bob@example.com", "password": "supersecret"},
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "bob@example.com", "password": "supersecret"},
        )
        r = await client.post(
            "/api/v1/query", json={"question": "pgvector?", "k": 3}
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["sources"]) == 1
        src = body["sources"][0]
        assert src["filename"] == "guide.pdf"
        assert src["page_start"] == 2
        assert src["page_end"] == 2
        assert src["score"] == 0.91
        assert "HNSW" in src["snippet"]


@pytest.mark.asyncio
async def test_query_validates_input(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "supersecret"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "supersecret"},
    )
    # Empty question
    r = await client.post("/api/v1/query", json={"question": "", "k": 5})
    assert r.status_code == 422
    # k out of range
    r = await client.post("/api/v1/query", json={"question": "hi", "k": 0})
    assert r.status_code == 422
    r = await client.post("/api/v1/query", json={"question": "hi", "k": 100})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_query_requires_auth(client):
    r = await client.post("/api/v1/query", json={"question": "hi", "k": 5})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_query_snippet_truncation(client):
    """A long chunk text is truncated to the snippet helper's max length."""
    from uuid import uuid4

    from app.services import retrieval
    from app.api import query as query_module

    long_text = "lorem ipsum " * 100
    fake_chunk = retrieval.RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="big.pdf",
        page_start=1,
        page_end=1,
        text=long_text,
        score=0.5,
    )

    async def fake_retrieve(session, user_id, question, k=5):
        return [fake_chunk]

    with patch.object(query_module, "retrieve", side_effect=fake_retrieve):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "dan@example.com", "password": "supersecret"},
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "dan@example.com", "password": "supersecret"},
        )
        r = await client.post(
            "/api/v1/query", json={"question": "anything", "k": 1}
        )
        assert r.status_code == 200
        snippet = r.json()["sources"][0]["snippet"]
        assert len(snippet) <= 240
        assert snippet.endswith("\u2026")
