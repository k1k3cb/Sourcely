"""Tests for the chunking service."""
from __future__ import annotations

import pytest

from app.services.chunking import chunk_pages, split_text_by_tokens
from app.services.ingestion import PageSegment


@pytest.fixture
def encoder():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


def test_split_short_text_returns_single_chunk(encoder):
    out = split_text_by_tokens("hello world", encoder, chunk_size=10, chunk_overlap=2)
    assert out == ["hello world"]


def test_split_empty_text_returns_empty(encoder):
    assert split_text_by_tokens("", encoder) == []
    assert split_text_by_tokens("   \n\t  ", encoder) == []


def test_split_long_text_with_overlap(encoder):
    text = "lorem ipsum " * 200
    out = split_text_by_tokens(text, encoder, chunk_size=20, chunk_overlap=5)
    assert all(isinstance(s, str) and s for s in out)
    assert len(out) > 1


def test_split_invalid_overlap_raises(encoder):
    with pytest.raises(ValueError):
        split_text_by_tokens("hello", encoder, chunk_size=10, chunk_overlap=10)
    with pytest.raises(ValueError):
        split_text_by_tokens("hello", encoder, chunk_size=0, chunk_overlap=0)


def test_chunk_pages_respects_page_boundaries(encoder):
    pages = [
        PageSegment(page_number=1, text="Page one content " * 50),
        PageSegment(page_number=2, text="Page two content " * 50),
    ]
    chunks = chunk_pages(pages, chunk_size=20, chunk_overlap=5)
    assert all(c.page_start == c.page_end for c in chunks)
    assert {c.page_start for c in chunks} == {1, 2}


def test_chunk_pages_skips_empty_pages(encoder):
    pages = [
        PageSegment(page_number=1, text=""),
        PageSegment(page_number=2, text="real content " * 30),
    ]
    chunks = chunk_pages(pages, chunk_size=20, chunk_overlap=5)
    assert all(c.page_start == 2 for c in chunks)


def test_chunk_pages_empty_input(encoder):
    assert chunk_pages([]) == []


def test_chunk_pages_token_count_matches(encoder):
    text = "Some text for the chunking test " * 30
    pages = [PageSegment(page_number=1, text=text)]
    chunks = chunk_pages(pages, chunk_size=20, chunk_overlap=5)
    for c in chunks:
        assert c.token_count == len(encoder.encode(c.text))
