import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Status(str, enum.Enum):
    uploading = "uploading"      # row created, browser is PUTting the file to the bucket
    queued = "queued"            # file is in the bucket, waiting for a worker
    processing = "processing"    # worker is validating / splitting the audio
    transcribing = "transcribing"
    summarizing = "summarizing"
    completed = "completed"
    failed = "failed"


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    language_code: Mapped[str] = mapped_column(String(10))
    duration_s: Mapped[float | None]

    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.uploading)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    stage_message: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)

    transcript: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    summary_error: Mapped[str | None] = mapped_column(Text)

    # The worker sets this when it claims the row; a stale value means the worker died.
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="recording", order_by="Chunk.index", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """One ~30 s slice of a recording. Kept so a retry only redoes the slices that failed."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float]
    end_s: Mapped[float]
    transcript: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    recording: Mapped[Recording] = relationship(back_populates="chunks")
