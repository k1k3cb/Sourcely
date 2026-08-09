from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceRef(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_start: int
    page_end: int
    score: float


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceRef] | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class CreateConversation(BaseModel):
    title: str = Field(default="New conversation", max_length=255)


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
