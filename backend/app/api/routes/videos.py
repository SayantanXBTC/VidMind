"""Public API: analyze a YouTube video or an uploaded file, poll its job,
ask questions about it.

No accounts. A YouTube video's ID is its YouTube video ID; an upload's ID is
"up_" plus a hash of the file. Results are shared through the cache, so the
same video (or the same file) is only analyzed once.
"""
import hashlib
import logging
import uuid
from pathlib import Path as FilePath

from fastapi import APIRouter, File, HTTPException, Path, Request, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.core import limits
from app.core.config import settings
from app.core.security import client_ip
from app.schemas import AnalyzeRequest, AskRequest, AskResponse, JobResponse, UsageResponse
from app.services import qa_service, transcription, youtube_service
from app.services.jobs import COMPLETED, FAILED, job_manager
from app.services.youtube_service import YouTubeError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["videos"])

VIDEO_ID = Path(
    ..., pattern=r"^(?:[A-Za-z0-9_-]{11}|up_[0-9a-f]{24})$", description="YouTube video ID or upload ID"
)
UPLOAD_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"}
_CHUNK = 1024 * 1024


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
            "source": "youtube",
            "url": meta["canonical_url"],
            "title": meta.get("title"),
            "duration": meta.get("duration"),
            "thumbnail": meta.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        },
        owner_ip=ip,
    )
    return job.public(include_result=False)


@router.post("/upload", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload(request: Request, file: UploadFile = File(...)) -> dict:
    """Summarize a video file from the visitor's computer.

    The file is streamed to a temp folder (never kept): FFmpeg extracts the
    audio, Whisper transcribes it, and both files are deleted.
    """
    if not settings.ENABLE_UPLOADS:
        raise HTTPException(status_code=403, detail="File uploads are turned off. Paste a YouTube link instead.")
    name = FilePath(file.filename or "").name
    ext = FilePath(name).suffix.lower()
    if ext not in UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload an MP4, MOV, M4V, WEBM, MKV or AVI video.")

    ip = _ip(request)
    limits.check_can_analyze(ip, job_manager.active_jobs_for_ip(ip))

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    tmp = settings.UPLOAD_TMP_DIR / f"{uuid.uuid4().hex}{ext}"
    digest = hashlib.sha256()
    size = 0
    try:
        with open(tmp, "wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if max_bytes and size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"Videos can be at most {settings.MAX_UPLOAD_MB} MB.")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="That file is empty.")

        video_id = "up_" + digest.hexdigest()[:24]
        existing = job_manager.get(video_id)
        if existing and existing.status != FAILED:
            tmp.unlink(missing_ok=True)  # same file analyzed before: free
            return existing.public(include_result=existing.status == COMPLETED)

        try:
            meta = await run_in_threadpool(transcription.probe, tmp)
        except transcription.TranscriptionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        limits.check_duration(meta["duration"])
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    limits.record_analysis(ip)
    title = FilePath(name).stem.replace("_", " ").strip()[:200] or "Uploaded video"
    job = job_manager.start(
        {"id": video_id, "source": "upload", "url": None, "title": title, "duration": meta["duration"], "thumbnail": None},
        owner_ip=ip,
        upload_path=tmp,
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
