"""Pydantic schemas for video API request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.video import EmbeddingStatus, IngestionMethod, SourceType, VideoStatus


class VideoUploadResponse(BaseModel):
    id: str
    filename: str
    status: VideoStatus


class RetryResponse(BaseModel):
    id: str
    status: VideoStatus


class YouTubeIngestRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class YouTubeIngestResponse(BaseModel):
    id: str
    source_type: SourceType
    status: VideoStatus
    message: str


class Chapter(BaseModel):
    title: str
    start: float
    end: float
    summary: Optional[str] = None


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    file_size: int
    duration: Optional[float] = None
    status: VideoStatus
    processing_progress: int = 0
    language: Optional[str] = None
    transcript: Optional[str] = None
    tldr: Optional[str] = None
    summary: Optional[str] = None
    key_points: Optional[list[str]] = None
    chapters: Optional[list[Chapter]] = None
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
    error_message: Optional[str] = None
    source_type: SourceType = SourceType.UPLOAD
    source_url: Optional[str] = None
    youtube_video_id: Optional[str] = None
    source_title: Optional[str] = None
    source_thumbnail: Optional[str] = None
    ingestion_method: Optional[IngestionMethod] = None
    created_at: datetime
    updated_at: datetime


class VideoListResponse(BaseModel):
    videos: list[VideoResponse]
    total: int


class VideoStatusResponse(BaseModel):
    id: str
    status: VideoStatus
    progress: int
    error: Optional[str] = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    video_id: str
    language: Optional[str] = None
    segments: list[TranscriptSegment]


class SummaryResponse(BaseModel):
    video_id: str
    tldr: Optional[str] = None
    summary: str
    key_points: list[str]
    chapters: list[Chapter]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResultItem(BaseModel):
    text: str
    start: float
    end: float
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SearchResultItem]


class HealthResponse(BaseModel):
    status: str
    service: str


class ErrorResponse(BaseModel):
    detail: str


class AccountResponse(BaseModel):
    user_id: str
    email: Optional[str] = None
    auth_enabled: bool
    uploads_enabled: bool
    daily_limit: Optional[int] = None
    used_today: int
    max_video_minutes: Optional[int] = None
