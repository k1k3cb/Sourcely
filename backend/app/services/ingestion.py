from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Union

from app.services.transcription import TimeSegment, get_transcriber
from app.services.validation import DetectedFile, FileKind

logger = logging.getLogger(__name__)


# A normalized unit of source content used by chunking. For PDFs, each
# page is a PageSegment with (page_number, text). For audio/video, each
# transcribed TimeSegment is a TimeSegment. The chunker is responsible
# for breaking each into smaller chunks while preserving the source unit
# boundaries (chunk.page_start == chunk.page_end, or chunk.start_seconds
# is a contiguous slice of one TimeSegment).


@dataclass(frozen=True)
class PageSegment:
    page_number: int
    text: str


SourceSegment = Union[PageSegment, TimeSegment]


class PdfExtractionError(Exception):
    pass


class AudioExtractionError(Exception):
    pass


def extract_pdf(data: bytes) -> list[PageSegment]:
    """Extract text from a PDF, one entry per page.

    Pages with no extractable text (scanned, image-only) return an
    empty string. They are still included so chunk counts match the
    source document.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise PdfExtractionError("pypdf is not installed") from exc

    try:
        reader = PdfReader(BytesIO(data), strict=False)
    except Exception as exc:  # noqa: BLE001
        raise PdfExtractionError(f"Could not read PDF: {exc}") from exc

    pages: list[PageSegment] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("page %d extraction failed: %s", idx, exc)
            text = ""
        pages.append(PageSegment(page_number=idx, text=text))
    return pages


def extract_audio_or_video(data: bytes, detected: DetectedFile) -> list[TimeSegment]:
    """Transcribe an audio/video file with the configured transcriber.

    Returns a list of TimeSegment with the original timestamps from the
    transcriber. Chunking downstream preserves each segment's range.
    """
    if detected.kind not in (FileKind.audio, FileKind.video):
        raise AudioExtractionError(
            f"Cannot transcribe a {detected.kind.value} file"
        )
    try:
        return get_transcriber().transcribe(data, detected.extension)
    except Exception as exc:  # noqa: BLE001
        raise AudioExtractionError(str(exc)) from exc


def extract(data: bytes, detected: DetectedFile) -> list[SourceSegment]:
    """Dispatch extraction by file kind and return normalized segments.

    Returns PageSegment for PDFs, TimeSegment for audio/video.
    """
    if detected.kind == FileKind.pdf:
        return extract_pdf(data)
    if detected.kind in (FileKind.audio, FileKind.video):
        return extract_audio_or_video(data, detected)
    raise ValueError(f"Unsupported file kind: {detected.kind}")
