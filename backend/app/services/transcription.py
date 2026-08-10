from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimeSegment:
    """A transcribed segment with start/end timestamps in seconds."""

    start_seconds: float
    end_seconds: float
    text: str


class Transcriber(Protocol):
    def transcribe(self, data: bytes, extension: str) -> list[TimeSegment]: ...


class FasterWhisperTranscriber:
    """Local Whisper transcription via faster-whisper.

    faster-whisper is a CTranslate2-backed reimplementation of Whisper
    that runs comfortably on CPU for the small/base models. The model
    is downloaded on first use (~75 MB for "tiny", ~150 MB for "base",
    ~460 MB for "small", ~1.5 GB for "medium").
    """

    def __init__(self) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        self._model_name = settings.whisper_model
        self._device = settings.whisper_device
        self._compute_type = settings.whisper_compute_type
        self._model = None  # lazy

    def _load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        logger.info(
            "Loading Whisper model %s on %s (%s)",
            self._model_name,
            self._device,
            self._compute_type,
        )
        self._model = WhisperModel(
            self._model_name,
            device=self._device,
            compute_type=self._compute_type,
        )

    def transcribe(self, data: bytes, extension: str) -> list[TimeSegment]:
        self._load()
        assert self._model is not None

        # faster-whisper accepts a file path or a numpy array; we use a
        # BytesIO and let it decode the audio via ffmpeg.
        import tempfile
        import os

        suffix = extension if extension else "audio"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f".{suffix}"
        ) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            segments_iter, info = self._model.transcribe(
                tmp_path,
                beam_size=5,
                vad_filter=True,
            )
            out: list[TimeSegment] = []
            for seg in segments_iter:
                text = (seg.text or "").strip()
                if not text:
                    continue
                out.append(
                    TimeSegment(
                        start_seconds=float(seg.start),
                        end_seconds=float(seg.end),
                        text=text,
                    )
                )
            logger.info(
                "Transcribed %d segments (lang=%s, dur=%.1fs)",
                len(out),
                getattr(info, "language", "?"),
                getattr(info, "duration", 0.0),
            )
            return out
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class StubTranscriber:
    """Test transcriber. Returns one segment per ~10 KB of input.

    Used by the test suite so we don't load Whisper or call ffmpeg.
    """

    def transcribe(self, data: bytes, extension: str) -> list[TimeSegment]:
        out: list[TimeSegment] = []
        chunk_size = 10_000
        offset = 0
        i = 0
        while offset < len(data):
            end = min(offset + chunk_size, len(data))
            seg_text = f"segment {i} from bytes {offset}-{end}"
            out.append(
                TimeSegment(
                    start_seconds=i * 5.0,
                    end_seconds=(i + 1) * 5.0,
                    text=seg_text,
                )
            )
            offset = end
            i += 1
        return out


_transcriber: Transcriber | None = None


def set_transcriber(t: Transcriber) -> None:
    global _transcriber
    _transcriber = t


def get_transcriber() -> Transcriber:
    if _transcriber is not None:
        return _transcriber
    backend = FasterWhisperTranscriber()
    set_transcriber(backend)
    return backend
