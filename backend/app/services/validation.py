from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


PDF_MAGIC = b"%PDF-"


class FileKind(str, Enum):
    pdf = "pdf"
    audio = "audio"
    video = "video"
    unknown = "unknown"


@dataclass(frozen=True)
class DetectedFile:
    kind: FileKind
    # The MIME type the API should store on the document. For audio/video
    # we keep the container MIME; the extraction step derives a normalized
    # internal representation.
    mime_type: str
    # File extension hint for the extraction backend (e.g. "mp3", "mp4",
    # "wav", "m4a"). Empty when not applicable.
    extension: str


# Magic bytes for common audio/video containers. We only need enough to
# confidently reject obvious garbage, not to fully validate the file.
_MAGIC_RULES: list[tuple[bytes, FileKind, str, str]] = [
    (b"%PDF-", FileKind.pdf, "application/pdf", "pdf"),
    (b"ID3", FileKind.audio, "audio/mpeg", "mp3"),
    (b"\xff\xfb", FileKind.audio, "audio/mpeg", "mp3"),
    (b"\xff\xf3", FileKind.audio, "audio/mpeg", "mp3"),
    (b"\xff\xf2", FileKind.audio, "audio/mpeg", "mp3"),
    (b"RIFF", FileKind.audio, "audio/wav", "wav"),  # also WebM; we check "WAVE"
    (b"fLaC", FileKind.audio, "audio/flac", "flac"),
    (b"OggS", FileKind.audio, "audio/ogg", "ogg"),
    (b"\x1a\x45\xdf\xa3", FileKind.video, "video/webm", "webm"),
    (b"\x00\x00\x00", FileKind.video, "video/mp4", "mp4"),  # ftyp box; needs deeper check
    (b"ftyp", FileKind.video, "video/mp4", "mp4"),
]


def _starts_with(data: bytes, prefix: bytes) -> bool:
    return len(data) >= len(prefix) and data[: len(prefix)] == prefix


def _looks_like_mp4(data: bytes) -> bool:
    # MP4 files have an "ftyp" box at offset 4. The first 4 bytes are the
    # box size. Some encoders write 'ftyp' immediately at offset 0, but
    # the standard is at offset 4.
    if len(data) < 12:
        return False
    if data[4:8] == b"ftyp":
        return True
    return False


def detect_kind(data: bytes, declared_mime: str | None = None) -> DetectedFile | None:
    """Return the detected file kind, or None if it can't be classified.

    Trust magic bytes first; the declared MIME is only a hint used when
    magic bytes alone are ambiguous (e.g. RIFF for WAV vs WebM).
    """
    if not data:
        return None

    if _starts_with(data, PDF_MAGIC):
        return DetectedFile(FileKind.pdf, "application/pdf", "pdf")

    # MP3: ID3v2 tag, or MPEG frame sync (0xFFFB / 0xFFF3 / 0xFFF2)
    if _starts_with(data, b"ID3") or (
        len(data) >= 2 and data[0] == 0xFF and data[1] in (0xFB, 0xF3, 0xF2)
    ):
        return DetectedFile(FileKind.audio, "audio/mpeg", "mp3")

    # FLAC
    if _starts_with(data, b"fLaC"):
        return DetectedFile(FileKind.audio, "audio/flac", "flac")

    # OGG
    if _starts_with(data, b"OggS"):
        return DetectedFile(FileKind.audio, "audio/ogg", "ogg")

    # MP4 / MOV: ftyp box at offset 4
    if _looks_like_mp4(data):
        # Differentiate audio-only (m4a) from video (mp4) by the major
        # brand. Audio-only m4a files have brands like M4A, mp42, isom.
        # Video mp4 also uses isom/mp42 but we can store the mime as
        # audio/mp4 vs video/mp4.
        brand = data[8:12].decode("ascii", errors="ignore").lower()
        if brand in ("m4a ", "m4a"):
            return DetectedFile(FileKind.audio, "audio/mp4", "m4a")
        return DetectedFile(FileKind.video, "video/mp4", "mp4")

    # WAV: RIFF....WAVE
    if _starts_with(data, b"RIFF") and len(data) >= 12 and data[8:12] == b"WAVE":
        return DetectedFile(FileKind.audio, "audio/wav", "wav")

    # WebM (also starts with EBML header 0x1A 0x45 0xDF 0xA3)
    if _starts_with(data, b"\x1a\x45\xdf\xa3"):
        # Check DocType. For WebM: "webm". For Matroska audio: "matroska".
        if len(data) >= 80:
            # Crude scan: look for "webm" in the first KB
            if b"webm" in data[:1024].lower():
                return DetectedFile(FileKind.video, "video/webm", "webm")
            if b"matroska" in data[:1024].lower():
                return DetectedFile(FileKind.audio, "audio/x-matroska", "mka")
        return DetectedFile(FileKind.video, "video/webm", "webm")

    return None


# MIME types the API endpoint accepts. The validation runs after the
# client-declared content_type is checked, and after magic bytes are
# checked, so the two layers must agree.
ACCEPTED_MIMES: dict[str, FileKind] = {
    # PDF
    "application/pdf": FileKind.pdf,
    "application/x-pdf": FileKind.pdf,
    # Audio
    "audio/mpeg": FileKind.audio,  # .mp3
    "audio/mp3": FileKind.audio,
    "audio/wav": FileKind.audio,
    "audio/x-wav": FileKind.audio,
    "audio/wave": FileKind.audio,
    "audio/x-m4a": FileKind.audio,
    "audio/m4a": FileKind.audio,
    "audio/mp4": FileKind.audio,  # m4a
    "audio/ogg": FileKind.audio,
    "audio/flac": FileKind.audio,
    "audio/x-flac": FileKind.audio,
    "audio/webm": FileKind.audio,
    # Video
    "video/mp4": FileKind.video,
    "video/webm": FileKind.video,
    "video/quicktime": FileKind.video,  # .mov
}


def normalize_mime(declared: str | None, detected: DetectedFile) -> str:
    """Pick the canonical MIME for storage.

    We prefer the detected MIME because it's based on the actual bytes;
    the declared one may be wrong (browsers sometimes send
    application/octet-stream when they don't know).
    """
    return detected.mime_type
