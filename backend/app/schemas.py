from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

BrandContext = Literal["NONE", "MRQ"]
AIStatus = Literal["PROCESSING", "READY", "FAILED"]


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp_ms: int = Field(strict=True, ge=0)
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    video_id: UUID
    timestamp_ms: int
    text: str
    author: Literal["HUMAN", "AI"]
    created_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    video_id: UUID
    role: Literal["USER", "ASSISTANT"]
    text: str
    created_at: datetime


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value):
        return value.strip() if isinstance(value, str) else value


class ChatResponse(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead
    comments: list[CommentRead]
    updated_comments: list[CommentRead] = Field(default_factory=list)
    deleted_comment_ids: list[UUID] = Field(default_factory=list)


class VideoRead(BaseModel):
    id: UUID
    original_filename: str
    mime_type: str
    byte_size: int
    duration_ms: int
    brand_context: BrandContext
    ai_status: AIStatus
    ai_error: str | None
    created_at: datetime
    media_url: str
    comments: list[CommentRead]
    messages: list[MessageRead]
