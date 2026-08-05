from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from google import genai
from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingBackend(Protocol):
    model: str
    dim: int

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbeddings:
    """OpenAI text-embedding-3-* with a fixed dim via the `dimensions` arg."""

    model: str
    dim: int

    def __init__(self, model: str | None = None, dim: int | None = None) -> None:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. "
                "Get one at https://platform.openai.com/api-keys"
            )
        self._client = OpenAI(api_key=settings.openai_api_key)
        self.model = model or settings.embedding_model
        self.dim = dim or settings.embedding_dim

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        batch_size = 96
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])
            response = self._client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dim,
            )
            for item in response.data:
                vec = item.embedding
                if len(vec) != self.dim:
                    raise RuntimeError(
                        f"Embedding dim mismatch: got {len(vec)}, expected {self.dim}"
                    )
                all_vectors.append(vec)
        return all_vectors


class GeminiEmbeddings:
    """Google Gemini text-embedding-004.

    The model produces 768-dim vectors natively, which matches our
    vector(768) column. The free tier allows up to 1500 requests/day
    (1500 documents per day if 1 chunk per doc; plenty for a portfolio).
    """

    model: str
    dim: int

    def __init__(self, model: str | None = None, dim: int | None = None) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. "
                "Get one at https://aistudio.google.com/apikey"
            )
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self.model = model or settings.embedding_model
        self.dim = dim or settings.embedding_dim

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        # The SDK accepts a list of strings directly; one request per batch.
        # The response has .embeddings[].values which is the vector.
        # task_type='RETRIEVAL_DOCUMENT' for chunks, 'RETRIEVAL_QUERY' for queries.
        response = self._client.models.embed_content(
            model=self.model,
            contents=list(texts),
            config=genai.types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.dim,
            ),
        )
        vectors: list[list[float]] = []
        for emb in response.embeddings:
            vec = list(emb.values or [])
            if len(vec) != self.dim:
                raise RuntimeError(
                    f"Embedding dim mismatch: got {len(vec)}, expected {self.dim}"
                )
            vectors.append(vec)
        return vectors


class OllamaEmbeddings:
    """Ollama local embeddings (e.g. nomic-embed-text, mxbai-embed-large)."""

    model: str
    dim: int

    def __init__(self, model: str | None = None, dim: int | None = None) -> None:
        import httpx

        self._client = httpx.Client(base_url=settings.ollama_base_url, timeout=60.0)
        self.model = model or settings.embedding_model
        self.dim = dim or settings.embedding_dim

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            r = self._client.post(
                "/api/embeddings",
                json={"model": self.model, "prompt": t},
            )
            r.raise_for_status()
            vec = r.json()["embedding"]
            if len(vec) != self.dim:
                raise RuntimeError(
                    f"Embedding dim mismatch: got {len(vec)}, expected {self.dim}"
                )
            out.append(vec)
        return out


_backend: EmbeddingBackend | None = None


def set_embeddings(backend: EmbeddingBackend) -> None:
    global _backend
    _backend = backend


def get_embeddings() -> EmbeddingBackend:
    if _backend is not None:
        return _backend
    provider = settings.embeddings_provider
    if provider == "openai":
        backend: EmbeddingBackend = OpenAIEmbeddings()
    elif provider == "gemini":
        backend = GeminiEmbeddings()
    elif provider == "ollama":
        backend = OllamaEmbeddings()
    else:
        raise RuntimeError(f"Unknown embeddings provider: {provider}")
    set_embeddings(backend)
    return backend
