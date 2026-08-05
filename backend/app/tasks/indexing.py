from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# A dedicated sync engine for background tasks. We use psycopg/psycopg2
# (sync) here so the task does not have to share a loop with the main app.
# In Etapa 3 this will be replaced with a real worker (Celery / RQ / etc.).
_sync_engine = None
_SyncSessionLocal = None


def _get_sync_engine():
    global _sync_engine, _SyncSessionLocal
    if _sync_engine is None:
        # Convert postgresql+asyncpg:// -> postgresql+psycopg://
        url = settings.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg://", 1
        )
        _sync_engine = create_engine(url, pool_pre_ping=True, future=True)
        _SyncSessionLocal = sessionmaker(
            bind=_sync_engine, expire_on_commit=False, class_=Session
        )
    return _SyncSessionLocal


def index_document(document_id: UUID) -> None:
    """Background task stub.

    Flips the document status uploaded -> processing -> ready. The real
    pipeline (PDF extraction, chunking, embeddings) lands in Etapa 3.
    """
    from app.models.document import Document, DocumentStatus

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
        # Real work goes here in Etapa 3.
        doc.status = DocumentStatus.ready
        session.commit()
        logger.info("index_document: %s ready", document_id)
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
