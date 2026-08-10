from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class _StorageLike(Protocol):
    def download(self, path: str) -> bytes: ...


# A dedicated sync engine for background tasks. We use psycopg (sync)
# so the task does not have to share a loop with the main app. In a
# production setup this would be replaced with a real worker (Celery,
# RQ, Arq, etc.).
_sync_engine: Engine | None = None
_SyncSessionLocal = None


def _get_sync_engine():
    global _sync_engine, _SyncSessionLocal
    if _sync_engine is None:
        url = settings.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg://", 1
        )
        _sync_engine = create_engine(url, pool_pre_ping=True, future=True)
        _SyncSessionLocal = sessionmaker(
            bind=_sync_engine, expire_on_commit=False, class_=Session
        )
    return _SyncSessionLocal


def set_sync_engine(engine: Engine, session_factory) -> None:
    global _sync_engine, _SyncSessionLocal
    _sync_engine = engine
    _SyncSessionLocal = session_factory


# Allow tests to swap storage/embeddings/transcriber without booting
# the real ones.
_storage_override: _StorageLike | None = None
_embeddings_override = None  # duck-typed: embed_texts(Sequence[str]) -> list[list[float]]
_transcriber_override = None  # duck-typed: transcribe(bytes, str) -> list[TimeSegment]


def set_storage_for_tasks(backend: _StorageLike) -> None:
    global _storage_override
    _storage_override = backend


def set_embeddings_for_tasks(backend) -> None:  # noqa: ANN001
    global _embeddings_override
    _embeddings_override = backend


def set_transcriber_for_tasks(backend) -> None:  # noqa: ANN001
    global _transcriber_override
    _transcriber_override = backend


def index_document(document_id: UUID) -> None:
    """Index a document: detect kind, extract, chunk, embed, persist.

    Supports PDFs (extracted with pypdf) and audio/video (transcribed
    with the configured transcriber). PDF chunks are anchored to pages;
    audio/video chunks are anchored to time ranges in seconds. Both
    share the same embeddings + retrieval pipeline.
    """
    from app.models.chunk import Chunk
    from app.models.document import Document, DocumentStatus
    from app.services.chunking import (
        DEFAULT_CHUNK_OVERLAP,
        DEFAULT_CHUNK_SIZE,
        chunk_segments,
    )
    from app.services.embeddings import get_embeddings
    from app.services.ingestion import (
        AudioExtractionError,
        PdfExtractionError,
        extract,
    )
    from app.services.storage import get_storage
    from app.services.transcription import get_transcriber
    from app.services.validation import FileKind, detect_kind

    logger.info("index_document: starting for %s", document_id)
    SessionLocal = _get_sync_engine()
    session: Session = SessionLocal()
    try:
        doc = session.execute(
            select(Document).where(Document.id == document_id)
        ).scalar_one_or_none()
        if doc is None:
            logger.warning("index_document: document %s not found", document_id)
            return
        if doc.status not in (DocumentStatus.uploaded,):
            logger.info(
                "index_document: document %s already in status %s, skipping",
                document_id,
                doc.status,
            )
            return

        doc.status = DocumentStatus.processing
        session.commit()

        # Download
        storage = _storage_override or get_storage()
        data = storage.download(doc.storage_path)
        if not data:
            raise PdfExtractionError("Downloaded file is empty")

        # Detect kind (use the mime we already stored, but also re-detect
        # from bytes to be safe).
        detected = detect_kind(data, doc.mime_type)
        if detected is None or detected.kind == FileKind.unknown:
            raise PdfExtractionError(
                f"Could not detect file kind from bytes (mime={doc.mime_type!r})"
            )

        # Extract
        segments = extract(data, detected)
        if not segments:
            raise PdfExtractionError("No content extracted from document")

        # Update document-level metadata
        from app.services.ingestion import PageSegment, TimeSegment
        pages = [s for s in segments if isinstance(s, PageSegment)]
        time_segs = [s for s in segments if isinstance(s, TimeSegment)]
        if pages:
            doc.page_count = len(pages)
        if time_segs:
            last = time_segs[-1]
            doc.duration_seconds = last.end_seconds

        # Chunk
        chunks = chunk_segments(
            segments,
            chunk_size=DEFAULT_CHUNK_SIZE,
            chunk_overlap=DEFAULT_CHUNK_OVERLAP,
        )
        if not chunks:
            raise PdfExtractionError("No chunks produced from document")

        # Embed
        embeddings_backend = _embeddings_override or get_embeddings()
        vectors = embeddings_backend.embed_texts([c.text for c in chunks])
        if len(vectors) != len(chunks):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(vectors)}, expected {len(chunks)}"
            )

        # Persist
        for chunk, vec in zip(chunks, vectors):
            row = Chunk(
                document_id=doc.id,
                text=chunk.text,
                token_count=chunk.token_count,
                embedding_model=embeddings_backend.model,
                embedding=vec,
            )
            if chunk.page_start is not None:
                row.page_start = chunk.page_start
                row.page_end = chunk.page_end
            if chunk.start_seconds is not None:
                row.start_seconds = chunk.start_seconds
                row.end_seconds = chunk.end_seconds
            session.add(row)
        doc.status = DocumentStatus.ready
        session.commit()
        logger.info(
            "index_document: %s ready (%d chunks)",
            document_id,
            len(chunks),
        )
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("index_document failed for %s", document_id)
        try:
            doc = session.execute(
                select(Document).where(Document.id == document_id)
            ).scalar_one_or_none()
            if doc is not None:
                doc.status = DocumentStatus.failed
                doc.error_message = str(exc)[:2048]
                session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
    finally:
        session.close()
