from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.services.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()


SYSTEM_PROMPT = (
    "You are a precise assistant that answers questions about a user's "
    "uploaded documents.\n\n"
    "Rules:\n"
    "1. Use ONLY the context provided below. If the answer is not in the "
    "context, say so explicitly.\n"
    "2. Cite the source for every fact using the format "
    "[doc:filename page=<n>]. The page number must match the page the "
    "fact came from.\n"
    "3. Be concise. Prefer short, direct answers.\n"
    "4. Do not invent filenames, page numbers, or facts."
)


class LLMBackend(Protocol):
    model: str

    async def stream(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> AsyncIterator[str]: ...


class GroqLLM:
    """Groq chat completions via the HTTP API, streamed.

    The official `groq` SDK is sync-only. We hit the same endpoint with
    httpx (streaming) so we can yield tokens from a FastAPI handler
    without blocking the event loop.
    """

    model: str

    def __init__(self, model: str | None = None) -> None:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. "
                "Get one at https://console.groq.com/keys"
            )
        self.model = model or settings.groq_model
        self._client = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def stream(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with self._client.stream(
            "POST", "/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                token = delta.get("content")
                if token:
                    yield token

    async def aclose(self) -> None:
        await self._client.aclose()


_backend: LLMBackend | None = None


def set_llm(backend: LLMBackend) -> None:
    global _backend
    _backend = backend


def get_llm() -> LLMBackend:
    if _backend is not None:
        return _backend
    backend = GroqLLM()
    set_llm(backend)
    return backend


def build_user_prompt(question: str, chunks: Sequence[RetrievedChunk]) -> str:
    """Build the user message: the question + a numbered context block."""
    if not chunks:
        return (
            f"Question: {question}\n\n"
            "Context: (no relevant documents found)"
        )
    parts = [f"Question: {question}\n", "Context:"]
    for i, c in enumerate(chunks, start=1):
        parts.append(
            f"\n[{i}] filename={c.filename} page={c.page_start} "
            f"score={c.score:.3f}\n{c.text}"
        )
    parts.append(
        "\nAnswer the question using only the context above. "
        "Cite sources inline as [doc:<filename> page=<n>]."
    )
    return "\n".join(parts)
