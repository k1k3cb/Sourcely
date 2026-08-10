from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    page_count: int | None
    duration_seconds: float | None
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentWithUrl(DocumentOut):
    signed_url: str | None = None
