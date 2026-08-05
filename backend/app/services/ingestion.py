from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-indexed
    text: str


class PdfExtractionError(Exception):
    pass


def extract_pages(data: bytes) -> list[PageText]:
    """Extract text from a PDF, one entry per page.

    Pages with no extractable text (scanned, image-only) return an empty
    string and a warning is logged. They are still included so chunk
    counts match the source document.
    """
    try:
        reader = PdfReader(BytesIO(data), strict=False)
    except Exception as exc:  # noqa: BLE001
        raise PdfExtractionError(f"Could not read PDF: {exc}") from exc

    pages: list[PageText] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("page %d extraction failed: %s", idx, exc)
            text = ""
        pages.append(PageText(page_number=idx, text=text))
    return pages
