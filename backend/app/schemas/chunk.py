from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    page_start: int
    page_end: int
    text: str
    token_count: int
    embedding_model: str
    created_at: datetime


class ChunkWithScore(ChunkOut):
    score: float
