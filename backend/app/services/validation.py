from __future__ import annotations

PDF_MAGIC = b"%PDF-"


def is_pdf(data: bytes) -> bool:
    """Check the PDF magic bytes at the start of the file."""
    if not data or len(data) < 5:
        return False
    return data[:5] == PDF_MAGIC
