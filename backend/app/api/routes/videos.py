import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.core.limits import check_ask_rate, check_can_start_video, check_duration, check_search_rate
from app.database.session import get_db
from app.models.video import EmbeddingStatus, SourceType, Video, VideoStatus
from app.schemas.video import (
    AskRequest,
    AskResponse,
    RetryResponse,
    SearchRequest,
    SearchResponse,
    SummaryResponse,
    TranscriptResponse,
    TranscriptSegment,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
    VideoUploadResponse,
    YouTubeIngestRequest,
    YouTubeIngestResponse,
)
from app.services import youtube_service
from app.services.embedding_service import EmbeddingError
from app.services.processing_service import processing_service
from app.services.qa_service import QAError, qa_service
from app.services.search_service import search_video
from app.services.storage_service import storage_service
from app.services.transcription_service import transcription_service
from app.services.video_service import video_service
from app.services.youtube_service import YouTubeError
from app.utils.files import generate_stored_filename, is_allowed_extension, safe_upload_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/videos", tags=["videos"])


def _start_processing(db: Session, video: Video, background_tasks: BackgroundTasks) -> None:
    """Queue the video for analysis.

    JOB_MODE=queue leaves it in "uploaded" (queued) state for the worker
    process to claim; inline mode runs it in this process right away.
    """
    video.processing_progress = 5
    if settings.JOB_MODE == "queue":
        video.status = VideoStatus.UPLOADED
        db.commit()
        db.refresh(video)
        return

    video.status = VideoStatus.PROCESSING
    db.commit()
    db.refresh(video)
    if video.source_type == SourceType.YOUTUBE:
        background_tasks.add_task(processing_service.process_youtube_video, video.id)
    else:
        background_tasks.add_task(processing_service.process_video, video.id)


@router.post("/upload", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks, file: UploadFile, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> VideoUploadResponse:
    if not settings.ENABLE_UPLOADS:
        raise HTTPException(status_code=403, detail="File uploads are turned off. Paste a YouTube link instead.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    check_can_start_video(db, user.id)

    if not is_allowed_extension(file.filename):
        allowed = ", ".join(sorted(settings.ALLOWED_VIDEO_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed}")

    if file.content_type and file.content_type not in settings.ALLOWED_VIDEO_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported MIME type: {file.content_type}")

    stored_filename = generate_stored_filename(file.filename)
    dest_path = safe_upload_path(stored_filename)

    size = 0
    try:
        with open(dest_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                    )
                out_file.write(chunk)
    except HTTPException:
        dest_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        dest_path.unlink(missing_ok=True)
        logger.exception("Failed to save uploaded file")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from exc

    duration = video_service.get_duration(dest_path)
    if duration is None:
        # ffprobe couldn't read it: wrong content behind a video extension.
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="This file isn't a playable video.")
    try:
        check_duration(duration)
    except HTTPException:
        dest_path.unlink(missing_ok=True)
        raise

    video = storage_service.create_video(
        db,
        user_id=user.id,
        original_filename=Path(file.filename).name[:255],
        stored_filename=stored_filename,
        file_path=str(dest_path),
        file_size=size,
        duration=duration,
    )

    _start_processing(db, video, background_tasks)

    return VideoUploadResponse(id=video.id, filename=video.original_filename, status=video.status)


@router.get("", response_model=VideoListResponse)
def list_videos(db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),) -> VideoListResponse:
    videos = storage_service.list_videos(db, user.id)
    return VideoListResponse(videos=videos, total=len(videos))


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: str, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),) -> VideoResponse:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: str, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),) -> None:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    storage_service.delete_video(db, video)


@router.post("/{video_id}/retry", response_model=RetryResponse)
def retry_video(
    video_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RetryResponse:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status != VideoStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed videos can be retried")

    video.error_message = None
    video.embedding_status = EmbeddingStatus.PENDING
    video.embedding_error = None
    video.processing_completed_at = None
    _start_processing(db, video, background_tasks)

    return RetryResponse(id=video.id, status=video.status)


@router.post(
    "/youtube", response_model=YouTubeIngestResponse, status_code=status.HTTP_201_CREATED
)
def ingest_youtube_video(
    body: YouTubeIngestRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> YouTubeIngestResponse:
    check_can_start_video(db, user.id)

    try:
        metadata = youtube_service.get_metadata(body.url)
    except YouTubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    check_duration(metadata["duration"])

    if settings.JOB_MODE == "inline":
        # In-process jobs share this machine's CPU, so cap them globally too.
        in_flight = (
            db.query(Video)
            .filter(Video.source_type == SourceType.YOUTUBE, Video.status == VideoStatus.PROCESSING)
            .count()
        )
        if in_flight >= settings.MAX_CONCURRENT_YOUTUBE_JOBS:
            raise HTTPException(
                status_code=429,
                detail="VidMind is already processing the maximum number of YouTube videos. Try again shortly.",
            )

    video = storage_service.create_youtube_video(
        db,
        user_id=user.id,
        youtube_video_id=metadata["video_id"],
        source_url=metadata["canonical_url"],
        title=metadata["title"],
        duration=metadata["duration"],
        thumbnail=metadata["thumbnail"],
    )

    _start_processing(db, video, background_tasks)

    return YouTubeIngestResponse(
        id=video.id,
        source_type=video.source_type,
        status=video.status,
        message="YouTube video queued for analysis",
    )


@router.get("/{video_id}/file")
def get_video_file(video_id: str, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),) -> FileResponse:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.source_type == SourceType.YOUTUBE:
        raise HTTPException(
            status_code=404, detail="This video is sourced from YouTube and has no local file"
        )

    file_path = Path(video.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video file is missing")

    media_type = mimetypes.guess_type(video.original_filename)[0] or "video/mp4"
    return FileResponse(file_path, media_type=media_type, filename=video.original_filename)


@router.get("/{video_id}/status", response_model=VideoStatusResponse)
def get_video_status(video_id: str, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),) -> VideoStatusResponse:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return VideoStatusResponse(
        id=video.id,
        status=video.status,
        progress=video.processing_progress,
        error=video.error_message,
    )


@router.get("/{video_id}/transcript", response_model=TranscriptResponse)
def get_video_transcript(video_id: str, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),) -> TranscriptResponse:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status == VideoStatus.FAILED:
        raise HTTPException(status_code=422, detail=video.error_message or "Processing failed")

    if video.status != VideoStatus.COMPLETED or not video.transcript_path:
        raise HTTPException(status_code=409, detail="Transcript is not ready yet")

    transcript_path = Path(video.transcript_path)
    if not transcript_path.exists():
        raise HTTPException(status_code=500, detail="Transcript file is missing")

    data = transcription_service.load_transcript(transcript_path)
    segments = [TranscriptSegment(**seg) for seg in data["segments"]]

    return TranscriptResponse(video_id=video.id, language=data.get("language"), segments=segments)


@router.get("/{video_id}/summary", response_model=SummaryResponse)
def get_video_summary(video_id: str, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),) -> SummaryResponse:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status == VideoStatus.FAILED:
        raise HTTPException(status_code=422, detail=video.error_message or "Processing failed")

    if video.status != VideoStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Summary is not ready yet")

    return SummaryResponse(
        video_id=video.id,
        tldr=video.tldr,
        summary=video.summary or "",
        key_points=video.key_points or [],
        chapters=video.chapters or [],
    )


def _require_embeddings_ready(video) -> None:
    if video.embedding_status == EmbeddingStatus.FAILED:
        raise HTTPException(
            status_code=422,
            detail=video.embedding_error or "Semantic search could not be prepared for this video",
        )
    if video.embedding_status != EmbeddingStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Semantic search is still being prepared")


@router.post("/{video_id}/search", response_model=SearchResponse)
def search_video_transcript(
    video_id: str, body: SearchRequest, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> SearchResponse:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    _require_embeddings_ready(video)
    check_search_rate(user.id)

    try:
        results = search_video(video_id, body.query, top_k=body.top_k)
    except EmbeddingError as exc:
        logger.error("Search failed for video %s: %s", video_id, exc)
        raise HTTPException(status_code=500, detail="Semantic search is temporarily unavailable") from exc

    return SearchResponse(query=body.query, results=results)


@router.post("/{video_id}/ask", response_model=AskResponse)
def ask_video(video_id: str, body: AskRequest, db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),) -> AskResponse:
    video = storage_service.get_video(db, video_id, user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    _require_embeddings_ready(video)
    check_ask_rate(user.id)

    try:
        result = qa_service.ask(video_id, body.question, video_summary=video.summary)
    except (EmbeddingError, QAError) as exc:
        logger.error("Ask failed for video %s: %s", video_id, exc)
        raise HTTPException(status_code=500, detail="Ask the Video is temporarily unavailable") from exc

    return AskResponse(**result)
