from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings import get_embeddings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_start: int
    page_end: int
    text: str
    score: float


async def retrieve(
    session: AsyncSession,
    user_id: UUID,
    question: str,
    k: int = 5,
) -> list[RetrievedChunk]:
    """Return the k chunks most similar to `question`, scoped to the user.

    The query ALWAYS joins chunks to documents and filters by
    documents.user_id. There is no code path that searches chunks without
    this filter, so user A can never see user B's chunks.
    """
    if k <= 0:
        return []
    embeddings = get_embeddings()
    # Embed the question with the retrieval_query task type (Gemini) so
    # the score is calibrated against document embeddings.
    query_vec = await _embed_query(embeddings, question)

    # pgvector cosine distance: <=>. Similarity = 1 - distance.
    # The HNSW index (ix_chunks_embedding_hnsw) is used because we filter
    # by user_id first via the JOIN; pgvector picks the index when the
    # result set is small relative to total.
    # NOTE: for the query vector we pass it as a string formatted for
    # pgvector: '[v1,v2,...]'. SQLAlchemy doesn't auto-bind list[float>
    # to the vector type, so we format it ourselves.
    q_vec_str = "[" + ",".join(f"{x:.8f}" for x in query_vec) + "]"
    sql = text(
        """
        select
            c.id as chunk_id,
            c.document_id,
            d.filename,
            c.page_start,
            c.page_end,
            c.text,
            1 - (c.embedding <=> CAST(:q_vec AS vector)) as score
        from chunks c
        join documents d on d.id = c.document_id
        where d.user_id = :user_id
          and c.embedding_model = :model
        order by c.embedding <=> CAST(:q_vec AS vector)
        limit :k
        """
    )

    result = await session.execute(
        sql,
        {
            "q_vec": q_vec_str,
            "user_id": str(user_id),
            "model": embeddings.model,
            "k": k,
        },
    )

    rows = result.mappings().all()
    return [
        RetrievedChunk(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            filename=r["filename"],
            page_start=r["page_start"],
            page_end=r["page_end"],
            text=r["text"],
            score=float(r["score"]),
        )
        for r in rows
    ]


async def _embed_query(embeddings, question: str) -> list[float]:
    """Embed a query string. Uses RETRIEVAL_QUERY when supported."""
    # The Gemini SDK exposes task_type per request; for OpenAI/Ollama we
    # fall back to the default embed_texts.
    if hasattr(embeddings, "_client") and embeddings.__class__.__name__ == "GeminiEmbeddings":
        from google import genai

        from app.core.config import get_settings

        # Build a fresh client call with task_type=RETRIEVAL_QUERY.
        # We re-use the existing client to keep the API key.
        response = embeddings._client.models.embed_content(
            model=embeddings.model,
            contents=[question],
            config=genai.types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=embeddings.dim,
            ),
        )
        vec = list(response.embeddings[0].values or [])
        if len(vec) != embeddings.dim:
            raise RuntimeError(
                f"Query embedding dim mismatch: got {len(vec)}, expected {embeddings.dim}"
            )
        return vec
    # Generic fallback
    vecs = embeddings.embed_texts([question])
    return vecs[0]
