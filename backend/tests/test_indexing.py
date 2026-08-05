"""End-to-end test of the index_document pipeline with mocks.

Uses SQLite in-memory (no pgvector) and overrides storage + embeddings.
The Chunk.embedding column is mapped to TEXT in SQLite via a compiler
override so we don't need a real Postgres+pgvector for the pipeline test.
"""
from __future__ import annotations

import io
import json

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from pgvector.sqlalchemy import Vector

from app.models.document import Document, DocumentStatus
from app.services.embeddings import set_embeddings
from app.services.storage import InMemoryStorage, set_storage
from app.tasks.indexing import (
    index_document,
    set_embeddings_for_tasks,
    set_storage_for_tasks,
    set_sync_engine,
)


@compiles(Vector, "sqlite")
def _compile_vector_sqlite(_type, _compiler, **_kw):
    return "TEXT"


class FakeEmbeddings:
    """Deterministic 768-dim embeddings so the test is hermetic."""

    model = "fake-embed-v1"
    dim = 768

    def embed_texts(self, texts):
        vecs = []
        for t in texts:
            v = [0.0] * self.dim
            for i, ch in enumerate(t):
                v[i % self.dim] += (ord(ch) % 100) / 100.0
            norm = sum(x * x for x in v) ** 0.5 or 1.0
            v = [x / norm for x in v]
            vecs.append(v)
        return vecs


def make_pdf(pages_text: list[str]) -> bytes:
    """Create a real PDF in memory with the given page texts."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for text in pages_text:
        c.setFont("Helvetica", 12)
        y = 750
        for line in (text.splitlines() or [text]):
            c.drawString(50, y, line)
            y -= 16
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 12)
                y = 750
        c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture
def fake_dependencies():
    storage = InMemoryStorage()
    set_storage(storage)
    set_embeddings(FakeEmbeddings())
    set_storage_for_tasks(storage)
    set_embeddings_for_tasks(FakeEmbeddings())
    yield


@pytest.fixture
def sqlite_sync_db():
    """Set up a SQLite sync engine and point the indexing task at it."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    set_sync_engine(engine, SessionLocal)

    # Seed a user so the FK on documents.user_id is satisfied.
    from app.models.user import User

    with SessionLocal() as session:
        user = User(
            email="indexing-test@example.com",
            hashed_password="x",
        )
        session.add(user)
        session.commit()
        user_id = user.id

    yield engine, SessionLocal, user_id


def test_index_document_happy_path(fake_dependencies, sqlite_sync_db):
    _, SessionLocal, user_id = sqlite_sync_db
    pdf_bytes = make_pdf([
        "The quick brown fox jumps over the lazy dog. " * 30,
        "Second page about embeddings and RAG pipelines. " * 30,
    ])

    with SessionLocal() as session:
        doc = Document(
            user_id=user_id,
            filename="test.pdf",
            storage_path="user-x/test.pdf",
            mime_type="application/pdf",
            size_bytes=len(pdf_bytes),
            status=DocumentStatus.uploaded,
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id

    from app.services.storage import get_storage

    get_storage().upload("user-x/test.pdf", pdf_bytes, "application/pdf")

    index_document(doc_id)

    with SessionLocal() as session:
        doc = session.execute(
            select(Document).where(Document.id == doc_id)
        ).scalar_one()
        assert doc.status == DocumentStatus.ready
        assert doc.page_count == 2
        assert doc.error_message is None

        from app.models.chunk import Chunk

        chunks = (
            session.execute(select(Chunk).where(Chunk.document_id == doc_id))
        ).scalars().all()
        assert len(chunks) > 0
        for c in chunks:
            assert c.page_start == c.page_end
            assert c.page_start in (1, 2)
            assert c.embedding_model == "fake-embed-v1"
            vec = json.loads(c.embedding) if isinstance(c.embedding, str) else c.embedding
            assert len(vec) == 768
            assert c.token_count > 0


def test_index_document_no_text_marks_failed(fake_dependencies, sqlite_sync_db):
    _, SessionLocal, user_id = sqlite_sync_db
    pdf_bytes = make_pdf(["", ""])

    with SessionLocal() as session:
        doc = Document(
            user_id=user_id,
            filename="blank.pdf",
            storage_path="user-x/blank.pdf",
            mime_type="application/pdf",
            size_bytes=len(pdf_bytes),
            status=DocumentStatus.uploaded,
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id

    from app.services.storage import get_storage

    get_storage().upload("user-x/blank.pdf", pdf_bytes, "application/pdf")

    index_document(doc_id)

    with SessionLocal() as session:
        doc = session.execute(
            select(Document).where(Document.id == doc_id)
        ).scalar_one()
        assert doc.status == DocumentStatus.failed
        assert "No extractable text" in (doc.error_message or "")


def test_index_document_already_ready_skips(fake_dependencies, sqlite_sync_db):
    _, SessionLocal, user_id = sqlite_sync_db

    with SessionLocal() as session:
        doc = Document(
            user_id=user_id,
            filename="ready.pdf",
            storage_path="user-x/ready.pdf",
            mime_type="application/pdf",
            size_bytes=0,
            status=DocumentStatus.ready,
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id

    index_document(doc_id)

    with SessionLocal() as session:
        doc = session.execute(
            select(Document).where(Document.id == doc_id)
        ).scalar_one()
        assert doc.status == DocumentStatus.ready
