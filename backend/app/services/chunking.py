from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from app.services.ingestion import PageText

# text-embedding-3-* models use the cl100k_base encoding.
_DEFAULT_ENCODING = "cl100k_base"

# Defaults sized for embedding-friendly chunks.
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 80


@dataclass(frozen=True)
class Chunk:
    page_start: int
    page_end: int
    text: str
    token_count: int


def _get_encoder(encoding_name: str = _DEFAULT_ENCODING):
    return tiktoken.get_encoding(encoding_name)


def split_text_by_tokens(
    text: str,
    encoder,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Token-aware splitter that keeps the order and respects boundaries."""
    if not text.strip():
        return []
    tokens = encoder.encode(text)
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be in [0, chunk_size)")

    step = chunk_size - chunk_overlap
    pieces: list[str] = []
    for start in range(0, len(tokens), step):
        end = min(start + chunk_size, len(tokens))
        piece_tokens = tokens[start:end]
        if not piece_tokens:
            break
        pieces.append(encoder.decode(piece_tokens))
        if end >= len(tokens):
            break
    return pieces


def chunk_pages(
    pages: list[PageText],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    encoding_name: str = _DEFAULT_ENCODING,
) -> list[Chunk]:
    """Split each page into chunks, never crossing page boundaries.

    Each chunk's page_start == page_end, so the citation is always exact.
    """
    encoder = _get_encoder(encoding_name)
    out: list[Chunk] = []
    for page in pages:
        for piece in split_text_by_tokens(
            page.text, encoder, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        ):
            if not piece.strip():
                continue
            tokens = encoder.encode(piece)
            out.append(
                Chunk(
                    page_start=page.page_number,
                    page_end=page.page_number,
                    text=piece,
                    token_count=len(tokens),
                )
            )
    return out
