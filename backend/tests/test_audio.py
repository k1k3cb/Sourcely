"""Tests for audio/video ingestion and chunking."""
from __future__ import annotations

import io
import wave
import struct

import pytest


def make_wav(duration_seconds: float = 1.0, sample_rate: int = 8000) -> bytes:
    """Generate a minimal valid WAV file with silence."""
    n_samples = int(duration_seconds * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Silence
        wf.writeframes(b"\x00\x00" * n_samples)
    return buf.getvalue()


def test_wav_magic_bytes_recognized():
    from app.services.validation import detect_kind, FileKind

    data = make_wav()
    detected = detect_kind(data, "audio/wav")
    assert detected is not None
    assert detected.kind == FileKind.audio
    assert detected.mime_type == "audio/wav"
    assert detected.extension == "wav"


def test_mp3_id3_recognized():
    from app.services.validation import detect_kind, FileKind

    data = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff" * 100
    detected = detect_kind(data, "audio/mpeg")
    assert detected is not None
    assert detected.kind == FileKind.audio
    assert detected.mime_type == "audio/mpeg"
    assert detected.extension == "mp3"


def test_mp3_mpeg_frame_sync():
    from app.services.validation import detect_kind, FileKind

    data = b"\xff\xfb\x90\x00" + b"\x00" * 100
    detected = detect_kind(data, "audio/mpeg")
    assert detected is not None
    assert detected.kind == FileKind.audio
    assert detected.extension == "mp3"


def test_mp4_ftyp_recognized():
    from app.services.validation import detect_kind, FileKind

    # Minimal ftyp box: 4-byte size + 'ftyp' + 4-byte major brand
    data = b"\x00\x00\x00\x20" + b"ftyp" + b"isom" + b"\x00\x00\x02\x00" + b"isom"
    detected = detect_kind(data, "video/mp4")
    assert detected is not None
    assert detected.kind == FileKind.video
    assert detected.extension == "mp4"


def test_m4a_audio_only():
    from app.services.validation import detect_kind, FileKind

    # Same as mp4 but with 'M4A ' brand
    data = b"\x00\x00\x00\x20" + b"ftyp" + b"M4A " + b"\x00\x00\x02\x00" + b"M4A "
    detected = detect_kind(data, "audio/mp4")
    assert detected is not None
    assert detected.kind == FileKind.audio
    assert detected.extension == "m4a"


def test_unknown_returns_none():
    from app.services.validation import detect_kind

    assert detect_kind(b"") is None
    assert detect_kind(b"random garbage bytes here") is None


def test_pdf_still_recognized():
    from app.services.validation import detect_kind, FileKind

    data = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"a" * 100
    detected = detect_kind(data, "application/pdf")
    assert detected is not None
    assert detected.kind == FileKind.pdf


def test_chunk_time_segments_groups_short_segments():
    """Verify that consecutive TimeSegments are grouped into ~30s blocks."""
    from app.services.chunking import _group_time_segments
    from app.services.transcription import TimeSegment

    # 6 segments of 5s each, total 30s
    segs = [
        TimeSegment(start_seconds=i * 5.0, end_seconds=(i + 1) * 5.0, text=f"seg {i}")
        for i in range(6)
    ]
    groups = _group_time_segments(segs, max_group_seconds=15.0, max_group_chars=1000)
    # We expect the first ~3 segments to be one group (15s), the next 3 another
    assert len(groups) >= 2
    # All segments covered
    all_indices = [i for g in groups for i in g[0]]
    assert sorted(all_indices) == list(range(6))


def test_chunk_time_segments_preserves_timestamps():
    from app.services.chunking import chunk_segments
    from app.services.transcription import TimeSegment

    segs = [
        TimeSegment(start_seconds=0.0, end_seconds=10.0, text="alpha beta gamma " * 30),
        TimeSegment(start_seconds=10.0, end_seconds=20.0, text="delta epsilon zeta " * 30),
    ]
    chunks = chunk_segments(segs, chunk_size=50, chunk_overlap=10)
    assert len(chunks) > 0
    for c in chunks:
        # Audio chunks should have timestamps, not page numbers
        assert c.start_seconds is not None
        assert c.end_seconds is not None
        assert c.page_start is None
        assert c.page_end is None
        # start <= end and within source range
        assert 0.0 <= c.start_seconds < c.end_seconds <= 20.0


def test_chunk_pages_still_works():
    """Backwards compat: PDF chunking path unchanged."""
    from app.services.chunking import chunk_pages
    from app.services.ingestion import PageSegment

    pages = [
        PageSegment(page_number=1, text="lorem ipsum " * 50),
        PageSegment(page_number=2, text="dolor sit amet " * 50),
    ]
    chunks = chunk_pages(pages, chunk_size=20, chunk_overlap=5)
    for c in chunks:
        assert c.page_start is not None
        assert c.start_seconds is None
