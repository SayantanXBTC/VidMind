"""Public API: analyze a YouTube video, poll its job, ask questions about it.

No accounts: a video's ID is its YouTube video ID, and results are shared
through the cache, so anyone opening the same video gets the same brief.
"""
import logging
import re

from fastapi import APIRouter, HTTPException, Path, Request, status

from app.core import limits
from app.core.security import client_ip
from app.schemas import AnalyzeRequest, AskRequest, AskResponse, JobResponse, UsageResponse
from app.services import qa_service, youtube_service
from app.services.jobs import COMPLETED, FAILED, job_manager
from app.services.youtube_service import YouTubeError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["videos"])

VIDEO_ID = Path(..., pattern=r"^[A-Za-z0-9_-]{11}$", description="YouTube video ID")


def _ip(request: Request) -> str:
    return client_ip(request.scope)


@router.post("/analyze", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def analyze(body: AnalyzeRequest, request: Request) -> dict:
    """Start (or reuse) the analysis of a YouTube video."""
    try:
        video_id = youtube_service.extract_video_id(body.url)
    except YouTubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = job_manager.get(video_id)
    if existing and existing.status != FAILED:
        # Already analyzed or in progress: free, doesn't count toward limits.
        return existing.public(include_result=existing.status == COMPLETED)

    ip = _ip(request)
    limits.check_can_analyze(ip, job_manager.active_jobs_for_ip(ip))

    try:
        meta = youtube_service.get_metadata(body.url)
    except YouTubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    limits.check_duration(meta.get("duration"))

    limits.record_analysis(ip)
    job = job_manager.start(
        {
            "id": video_id,
            "url": meta["canonical_url"],
            "title": meta.get("title"),
            "duration": meta.get("duration"),
            "thumbnail": meta.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        },
        owner_ip=ip,
    )
    return job.public(include_result=False)


@router.get("/videos/{video_id}", response_model=JobResponse)
def get_video(video_id: str = VIDEO_ID, include_result: bool = True) -> dict:
    """Status of an analysis, with the full result once it's ready."""
    job = job_manager.get(video_id)
    if not job:
        raise HTTPException(status_code=404, detail="This video hasn't been analyzed yet.")
    return job.public(include_result=include_result and job.status == COMPLETED)


@router.post("/videos/{video_id}/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, video_id: str = VIDEO_ID) -> dict:
    job = job_manager.get(video_id)
    if not job or job.status != COMPLETED:
        raise HTTPException(
            status_code=409, detail="This video needs to be analyzed again before you can ask about it."
        )
    limits.check_and_record_question(_ip(request))
    try:
        return qa_service.ask(job.result["segments"], body.question, summary=job.result.get("summary"))
    except qa_service.QAError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/usage", response_model=UsageResponse)
def usage(request: Request) -> dict:
    """How many new videos this visitor has left today."""
    return limits.usage_for(_ip(request))
