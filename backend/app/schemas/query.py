from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=20)


class Source(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    snippet: str
    score: float
    index: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]  
