from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Union

import tiktoken

from app.services.ingestion import PageSegment, SourceSegment, TimeSegment

# text-embedding-3-* and gemini-embedding-001 use the cl100k_base
# encoding.
_DEFAULT_ENCODING = "cl100k_base"

# Defaults sized for embedding-friendly chunks.
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 80


@dataclass(frozen=True)
class Chunk:
    """A chunk ready to be embedded and stored.

    For PDFs: page_start == page_end (the page the chunk came from).
    For audio/video: start_seconds <= end_seconds, the time range in
    the source media the chunk covers.
    """

    page_start: int | None = None
    page_end: int | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    text: str = ""
    token_count: int = 0
    # Optional metadata. For audio, the segment indices that the chunk
    # covers (e.g. [3, 4, 5] means it spans Whisper segments 3..5). This
    # is useful for the frontend to map "minute 12:34" back to a
    # specific transcript snippet.
    segment_indices: list[int] = field(default_factory=list)


def _get_encoder(encoding_name: str = _DEFAULT_ENCODING):
    return tiktoken.get_encoding(encoding_name)


def _is_page_segment(seg: SourceSegment) -> bool:
    return isinstance(seg, PageSegment)


def _is_time_segment(seg: SourceSegment) -> bool:
    return isinstance(seg, TimeSegment)


def split_text_by_tokens(
    text: str,
    encoder,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
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


def _chunk_pages(
    pages: list[PageSegment],
    encoder,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
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


def _group_time_segments(
    segments: list[TimeSegment],
    max_group_seconds: float = 30.0,
    max_group_chars: int = 3000,
) -> list[tuple[list[int], float, float, str]]:
    """Group consecutive TimeSegments into longer text blocks.

    Whisper segments are short (a few seconds each). For chunking we
    want larger blocks so embeddings capture topic context. We group
    while the cumulative duration stays under `max_group_seconds` and
    the cumulative character count stays under `max_group_chars`.

    Returns a list of (indices, start_s, end_s, joined_text) tuples.
    """
    if not segments:
        return []

    groups: list[tuple[list[int], float, float, str]] = []
    cur_indices: list[int] = []
    cur_start = segments[0].start_seconds
    cur_end = segments[0].end_seconds
    cur_text: list[str] = []

    for i, seg in enumerate(segments):
        seg_text = seg.text.strip()
        if not seg_text:
            continue
        new_indices = cur_indices + [i]
        new_text = " ".join(cur_text + [seg_text])
        if cur_indices and (
            (seg.end_seconds - cur_start) > max_group_seconds
            or len(new_text) > max_group_chars
        ):
            groups.append(
                (cur_indices, cur_start, cur_end, " ".join(cur_text))
            )
            cur_indices = [i]
            cur_start = seg.start_seconds
            cur_end = seg.end_seconds
            cur_text = [seg_text]
        else:
            cur_indices = new_indices
            cur_end = seg.end_seconds
            cur_text.append(seg_text)
    if cur_indices:
        groups.append((cur_indices, cur_start, cur_end, " ".join(cur_text)))
    return groups


def _chunk_time_segments(
    segments: list[TimeSegment],
    encoder,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    out: list[Chunk] = []
    if not segments:
        return []
    # First group short Whisper segments into ~30s blocks.
    groups = _group_time_segments(segments)
    for indices, start_s, end_s, text in groups:
        for piece in split_text_by_tokens(
            text, encoder, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        ):
            if not piece.strip():
                continue
            tokens = encoder.encode(piece)
            out.append(
                Chunk(
                    start_seconds=start_s,
                    end_seconds=end_s,
                    text=piece,
                    token_count=len(tokens),
                    segment_indices=indices,
                )
            )
    return out


def chunk_segments(
    segments: list[SourceSegment],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    encoding_name: str = _DEFAULT_ENCODING,
) -> list[Chunk]:
    """Split a list of source segments into chunks.

    The function auto-detects whether segments are PageSegment (PDF) or
    TimeSegment (audio/video) and dispatches accordingly. Mixed inputs
    are not supported; chunk_pages / chunk_time_segments is called
    based on the first segment's type.
    """
    if not segments:
        return []
    encoder = _get_encoder(encoding_name)
    if _is_page_segment(segments[0]):
        return _chunk_pages(
            [s for s in segments if _is_page_segment(s)],
            encoder,
            chunk_size,
            chunk_overlap,
        )
    if _is_time_segment(segments[0]):
        return _chunk_time_segments(
            [s for s in segments if _is_time_segment(s)],
            encoder,
            chunk_size,
            chunk_overlap,
        )
    return []


# Backwards-compatible aliases used by the existing tests / indexer.
def chunk_pages(
    pages: list[PageSegment],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    encoding_name: str = _DEFAULT_ENCODING,
) -> list[Chunk]:
    encoder = _get_encoder(encoding_name)
    return _chunk_pages(pages, encoder, chunk_size, chunk_overlap)
