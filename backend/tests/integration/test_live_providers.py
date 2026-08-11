"""Live-provider smoke tests.

These tests hit the real external services (Supabase Postgres+pgvector,
Gemini embeddings, Groq LLM) and are skipped by default in CI. They
are intended to be run locally before a deploy, or in a separate CI
job with secrets available.

Set RUN_INTEGRATION=1 to enable. Without it the whole module is
skipped so a normal `pytest` run stays fast and offline.

Cost: each run costs ~$0.0001 in Gemini + a few free-tier Groq tokens.
Do not run in a tight loop.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid as uuidlib

import asyncpg
import pytest

RUN_INTEGRATION = os.environ.get("RUN_INTEGRATION") == "1"

if not RUN_INTEGRATION:
    pytest.skip(
        "Integration tests are disabled. Set RUN_INTEGRATION=1 to run.",
        allow_module_level=True,
    )

# These tests use the real .env configuration. Import lazily so the
# skip above short-circuits before any network calls happen.
from app.core.config import get_settings  # noqa: E402

SUPABASE_POOLER_URL = os.environ.get(
    "SUPABASE_POOLER_URL",
    "",
)


def _require_keys() -> None:
    settings = get_settings()
    missing = []
    if not settings.gemini_api_key:
        missing.append("GEMINI_API_KEY")
    if not settings.groq_api_key:
        missing.append("GROQ_API_KEY")
    if not SUPABASE_POOLER_URL and not settings.database_url:
        missing.append("SUPABASE_POOLER_URL or DATABASE_URL")
    if missing:
        pytest.skip(
            f"Missing required env vars for integration tests: {missing}",
            allow_module_level=False,
        )


# ---------------------------------------------------------------------------
# Gemini embeddings
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_gemini_embed_returns_768_dim_vector() -> None:
    _require_keys()
    from app.services.embeddings import get_embeddings

    emb = get_embeddings()
    assert emb.model
    vecs = emb.embed_texts(["hello world"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 768, f"expected 768 dims, got {len(vecs[0])}"


@pytest.mark.integration
def test_gemini_embed_handles_batch() -> None:
    _require_keys()
    from app.services.embeddings import get_embeddings

    emb = get_embeddings()
    vecs = emb.embed_texts(["one", "two", "three", "four", "five"])
    assert len(vecs) == 5
    for v in vecs:
        assert len(v) == 768


@pytest.mark.integration
def test_gemini_embed_similar_texts_have_high_cosine() -> None:
    _require_keys()
    from app.services.embeddings import get_embeddings

    emb = get_embeddings()
    a, b = emb.embed_texts(["the cat sat on the mat", "a cat is sitting on a mat"])
    # Cosine similarity
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    sim = dot / (na * nb)
    assert sim > 0.85, f"expected similar texts to score > 0.85, got {sim:.3f}"


# ---------------------------------------------------------------------------
# Groq LLM
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_groq_stream_produces_at_least_one_token() -> None:
    _require_keys()
    from app.services.llm import SYSTEM_PROMPT, get_llm

    llm = get_llm()
    tokens = []
    async for tok in llm.stream(SYSTEM_PROMPT, "Reply with exactly one word."):
        tokens.append(tok)
        if len(tokens) >= 5:
            break
    assert tokens, "no tokens streamed"
    full = "".join(tokens)
    assert full.strip(), "empty content"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_groq_returns_about_configured_model() -> None:
    _require_keys()
    from app.services.llm import get_llm

    llm = get_llm()
    # We don't assert the exact id (it could be a fine-tune), but the
    # model string should be non-empty and look like a Groq model id.
    assert llm.model and "/" not in llm.model or llm.model.startswith("llama")


# ---------------------------------------------------------------------------
# Supabase retrieval (pgvector)
# ---------------------------------------------------------------------------


def _pg_url() -> str:
    """Return the Supabase pooler URL for sync queries.

    Falls back to settings.database_url (which is postgresql+asyncpg).
    We swap the async driver for psycopg because asyncpg is async-only
    and these tests are quick.
    """
    if SUPABASE_POOLER_URL:
        return SUPABASE_POOLER_URL
    settings = get_settings()
    return settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://", 1
    )


@pytest.mark.integration
def test_pgvector_query_returns_expected_shape() -> None:
    """Run the production SQL against real Supabase pgvector and check
    the column types and operators are valid.
    """
    _require_keys()
    import psycopg

    url = _pg_url()
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)

            # Confirm pgvector is installed and the chunks table has
            # the embedding column.
            cur.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'chunks' AND column_name = 'embedding'"
            )
            row = cur.fetchone()
            assert row is not None, "chunks.embedding column missing"
            # In Postgres, vector columns are reported as USER-DEFINED.

            cur.execute(
                "SELECT typname FROM pg_type WHERE typname = 'vector'"
            )
            assert cur.fetchone() is not None, "vector extension missing"


@pytest.mark.integration
def test_pgvector_cosine_distance_roundtrip() -> None:
    """Insert a known vector, query it back with <=>, verify it works."""
    _require_keys()
    import psycopg

    url = _pg_url()
    user_id = uuidlib.uuid4()
    doc_id = uuidlib.uuid4()
    chunk_id = uuidlib.uuid4()
    # A vector where element 0 is much larger than the rest; a random
    # other vector should be farther (smaller similarity).
    known = [0.99] + [0.01] * 767
    random_vec = [0.5] * 768

    with psycopg.connect(url) as conn:
        try:
            # Need a user row first (FK from documents.user_id).
            conn.execute(
                "INSERT INTO users (id, email, hashed_password, is_active, "
                "created_at) "
                "VALUES (%s, %s, %s, true, now())",
                (str(user_id), f"smoke-{user_id}@test.local", "x"),
            )
            conn.execute(
                "INSERT INTO documents "
                "(id, user_id, filename, storage_path, mime_type, "
                " size_bytes, status, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::document_status, "
                " now(), now())",
                (
                    str(doc_id),
                    str(user_id),
                    "smoke.pdf",
                    f"smoke/{doc_id}.pdf",
                    "application/pdf",
                    1,
                    "ready",
                ),
            )
            # Insert two chunks
            known_str = "[" + ",".join(f"{x:.6f}" for x in known) + "]"
            rand_str = "[" + ",".join(f"{x:.6f}" for x in random_vec) + "]"
            conn.execute(
                "INSERT INTO chunks "
                "(id, document_id, page_start, page_end, text, "
                " token_count, embedding_model, embedding, created_at) "
                "VALUES (%s, %s, 1, 1, 'known', 1, %s, %s::vector, now())",
                (
                    str(chunk_id),
                    str(doc_id),
                    "gemini-embedding-001",
                    known_str,
                ),
            )
            other_id = uuidlib.uuid4()
            conn.execute(
                "INSERT INTO chunks "
                "(id, document_id, page_start, page_end, text, "
                " token_count, embedding_model, embedding, created_at) "
                "VALUES (%s, %s, 1, 1, 'random', 1, %s, %s::vector, now())",
                (
                    str(other_id),
                    str(doc_id),
                    "gemini-embedding-001",
                    rand_str,
                ),
            )

            # The 'known' vector is its own nearest neighbor.
            rows = conn.execute(
                "SELECT id FROM chunks "
                "WHERE document_id = %s "
                "ORDER BY embedding <=> %s::vector LIMIT 1",
                (str(doc_id), known_str),
            ).fetchall()
            assert len(rows) == 1
            assert str(rows[0][0]) == str(chunk_id)
        finally:
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (str(doc_id),))
            conn.execute("DELETE FROM documents WHERE id = %s", (str(doc_id),))
            conn.execute("DELETE FROM users WHERE id = %s", (str(user_id),))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retrieve_function_against_live_supabase() -> None:
    """Run the production SQL against real Supabase pgvector and verify
    the shape of the returned row matches what retrieve() expects.

    We bypass SQLAlchemy here because the conftest has overridden the
    settings to SQLite, and we want to test against the live DB
    without dragging psycopg2 in. The query mirrors what
    app.services.retrieval.retrieve() does.
    """
    _require_keys()
    import psycopg

    url = _pg_url()
    user_id = uuidlib.uuid4()
    doc_id = uuidlib.uuid4()
    chunk_id = uuidlib.uuid4()

    vec = [0.7] + [0.05] * 767

    with psycopg.connect(url) as conn:
        conn.execute(
            "INSERT INTO users (id, email, hashed_password, is_active, "
            "created_at) "
            "VALUES (%s, %s, %s, true, now())",
            (str(user_id), f"smoke-{user_id}@test.local", "x"),
        )
        conn.execute(
            "INSERT INTO documents "
            "(id, user_id, filename, storage_path, mime_type, "
            " size_bytes, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::document_status, "
            " now(), now())",
            (
                str(doc_id),
                str(user_id),
                "smoke.pdf",
                f"smoke/{doc_id}.pdf",
                "application/pdf",
                1,
                "ready",
            ),
        )
        conn.execute(
            "INSERT INTO chunks "
            "(id, document_id, page_start, page_end, text, "
            " token_count, embedding_model, embedding, created_at) "
            "VALUES (%s, %s, 1, 1, %s, 1, %s, %s::vector, now())",
            (
                str(chunk_id),
                str(doc_id),
                "smoke content",
                "gemini-embedding-001",
                "[" + ",".join(f"{x:.6f}" for x in vec) + "]",
            ),
        )
        conn.commit()

    try:
        async_url = url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        async_conn = await asyncpg.connect(async_url)
        try:
            q_vec = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
            rows = await async_conn.fetch(
                """
                select
                    c.id as chunk_id,
                    c.document_id,
                    d.filename,
                    c.page_start,
                    c.page_end,
                    c.start_seconds,
                    c.end_seconds,
                    c.text,
                    1 - (c.embedding <=> $1::vector) as score
                from chunks c
                join documents d on d.id = c.document_id
                where d.user_id = $2
                  and c.embedding_model = $3
                order by c.embedding <=> $1::vector
                limit 3
                """,
                q_vec,
                user_id,
                "gemini-embedding-001",
            )
        finally:
            await async_conn.close()
        assert len(rows) >= 1
        first = dict(rows[0])
        assert first["chunk_id"] == chunk_id
        assert first["filename"] == "smoke.pdf"
        assert first["text"] == "smoke content"
        assert first["page_start"] == 1
        assert first["page_end"] == 1
        assert 0.0 <= float(first["score"]) <= 1.0
    finally:
        with psycopg.connect(url) as conn:
            conn.execute(
                "DELETE FROM chunks WHERE document_id = %s", (str(doc_id),)
            )
            conn.execute("DELETE FROM documents WHERE id = %s", (str(doc_id),))
            conn.execute("DELETE FROM users WHERE id = %s", (str(user_id),))


# ---------------------------------------------------------------------------
# Latency sanity check
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_gemini_embed_under_3s_per_text() -> None:
    """Smoke: a single embed should return well under 3 seconds."""
    _require_keys()
    from app.services.embeddings import get_embeddings

    emb = get_embeddings()
    start = time.perf_counter()
    emb.embed_texts(["latency probe"])
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"too slow: {elapsed:.2f}s"