"""Video database model."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Enum, Float, Integer, String, Text

from app.database.session import Base


class VideoStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EmbeddingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(str, enum.Enum):
    UPLOAD = "upload"
    YOUTUBE = "youtube"


class IngestionMethod(str, enum.Enum):
    CAPTION = "caption"
    WHISPER = "whisper"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True, default=_uuid)
    # Supabase user id ("sub" claim), or "local" in single-user mode.
    user_id = Column(String, nullable=True, index=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False, unique=True)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    duration = Column(Float, nullable=True)
    status = Column(Enum(VideoStatus), nullable=False, default=VideoStatus.UPLOADED)
    transcript = Column(Text, nullable=True)
    tldr = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True)
    chapters = Column(JSON, nullable=True)
    embedding_status = Column(
        Enum(EmbeddingStatus), nullable=False, default=EmbeddingStatus.PENDING
    )
    embedding_error = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    processing_progress = Column(Integer, nullable=False, default=0)
    # How many times a worker has claimed this job (guards against a video
    # that crashes the worker being retried forever).
    job_attempts = Column(Integer, nullable=True, default=0)
    transcript_path = Column(String, nullable=True)
    language = Column(String, nullable=True)
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at = Column(DateTime(timezone=True), nullable=True)
    source_type = Column(Enum(SourceType), nullable=False, default=SourceType.UPLOAD)
    source_url = Column(String, nullable=True)
    youtube_video_id = Column(String, nullable=True)
    source_title = Column(String, nullable=True)
    source_thumbnail = Column(String, nullable=True)
    ingestion_method = Column(Enum(IngestionMethod), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
