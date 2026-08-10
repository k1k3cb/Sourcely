from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Source(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    # PDF: page_start/page_end; audio/video: start_seconds/end_seconds.
    # Either page_start or start_seconds will be non-null depending on
    # the source's file kind. Both are returned for rendering flexibility.
    page_start: int | None = None
    page_end: int | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    snippet: str
    score: float


class ChunkWithScore(BaseModel):
    id: UUID
    document_id: UUID
    page_start: int | None = None
    page_end: int | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    text: str
    token_count: int
    embedding_model: str
    created_at: str
    score: float
