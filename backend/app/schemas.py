"""Request and response models."""
from typing import Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class VideoInfo(BaseModel):
    id: str
    url: str
    title: Optional[str] = None
    duration: Optional[float] = None
    thumbnail: Optional[str] = None


class Chapter(BaseModel):
    title: str
    start: float
    end: float
    summary: Optional[str] = None


class Segment(BaseModel):
    start: float
    end: float
    text: str


class AnalysisResult(BaseModel):
    tldr: Optional[str] = None
    summary: str
    key_points: list[str]
    chapters: list[Chapter]
    language: Optional[str] = None
    segments: list[Segment]


class JobResponse(BaseModel):
    id: str
    status: str
    progress: int
    stage: str
    error: Optional[str] = None
    video: VideoInfo
    result: Optional[AnalysisResult] = None


class Source(BaseModel):
    start: float
    end: float
    text: str


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[Source]


class UsageResponse(BaseModel):
    analyses_today: int
    analyses_per_day: Optional[int] = None
    max_video_minutes: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    service: str
