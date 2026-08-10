from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence

from groq import Groq
from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


SYSTEM_PROMPT = (
    "You are a precise assistant that answers questions strictly from the "
    "provided context. If the answer is not in the context, say you don't "
    "know — do not make anything up. Reply in the user's language. Cite "
    "the sources you used by their bracketed numbers, e.g. [1], [2]. "
    "Keep the answer concise."
)


class LLMBackend:
    model: str

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        raise NotImplementedError

    async def stream(
        self, system: str, user: str, max_tokens: int = 800
    ) -> AsyncIterator[str]:
        # Default: block-then-yield. Subclasses can override with native SSE.
        yield self.complete(system, user, max_tokens=max_tokens)


class GroqLLM(LLMBackend):
    """Groq-hosted models (llama, mixtral)."""

    def __init__(self, model: str | None = None) -> None:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. "
                "Get one at https://console.groq.com/keys"
            )
        self._client = Groq(api_key=settings.groq_api_key)
        self.model = model or settings.groq_model

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()

    async def stream(
        self, system: str, user: str, max_tokens: int = 800
    ) -> AsyncIterator[str]:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta


class OpenAILLM(LLMBackend):
    """OpenAI-compatible chat completion endpoint."""

    def __init__(self, model: str | None = None) -> None:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. "
                "Get one at https://platform.openai.com/api-keys"
            )
        self._client = OpenAI(api_key=settings.openai_api_key)
        self.model = model or settings.groq_model

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()

    async def stream(
        self, system: str, user: str, max_tokens: int = 800
    ) -> AsyncIterator[str]:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta


_backend: LLMBackend | None = None


def set_llm(backend: LLMBackend) -> None:
    global _backend
    _backend = backend


def get_llm() -> LLMBackend:
    if _backend is not None:
        return _backend
    provider = settings.llm_provider
    if provider == "groq":
        backend: LLMBackend = GroqLLM()
    elif provider == "openai":
        backend = OpenAILLM()
    else:
        raise RuntimeError(f"Unknown LLM provider: {provider}")
    set_llm(backend)
    return backend


def _location(chunk) -> str:
    if chunk.page_start is not None and chunk.page_end is not None:
        if chunk.page_start == chunk.page_end:
            return f"page {chunk.page_start}"
        return f"pages {chunk.page_start}-{chunk.page_end}"
    if chunk.start_seconds is not None and chunk.end_seconds is not None:
        return f"{chunk.start_seconds:.1f}s-{chunk.end_seconds:.1f}s"
    return "no-location"


def build_user_prompt(question: str, chunks: Sequence) -> str:
    """Render the user prompt with numbered context blocks.

    Each chunk becomes ``[i] filename (location)\\n<text>``. The indices
    correspond to the sources list returned by /api/v1/query.
    """
    blocks: list[str] = []
    for i, c in enumerate(chunks, start=1):
        blocks.append(f"[{i}] {c.filename} ({_location(c)})\n{c.text.strip()}")
    context = "\n\n".join(blocks) if blocks else "(no context)"
    return f"Question:\n{question}\n\nContext:\n{context}"
