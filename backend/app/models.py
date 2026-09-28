from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint("duration_ms > 0", name="video_positive_duration"),
        CheckConstraint("byte_size > 0", name="video_positive_size"),
        CheckConstraint("brand_context IN ('NONE', 'MRQ')", name="video_context"),
        CheckConstraint("ai_status IN ('PROCESSING', 'READY', 'FAILED')", name="video_ai_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int]
    duration_ms: Mapped[int]
    brand_context: Mapped[str] = mapped_column(String(8))
    ai_status: Mapped[str] = mapped_column(String(12), default="PROCESSING")
    gemini_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gemini_file_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_file_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint("timestamp_ms >= 0", name="comment_nonnegative_time"),
        CheckConstraint("char_length(trim(text)) BETWEEN 1 AND 1000", name="comment_text_length"),
        CheckConstraint("author IN ('HUMAN', 'AI')", name="comment_author"),
        Index("ix_comments_video_time", "video_id", "timestamp_ms"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    video_id: Mapped[UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    timestamp_ms: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(8), default="HUMAN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ASSISTANT')", name="message_role"),
        CheckConstraint("char_length(trim(text)) BETWEEN 1 AND 8000", name="message_text_length"),
        Index("ix_messages_video_id", "video_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    video_id: Mapped[UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(12))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
