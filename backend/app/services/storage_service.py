"""Database CRUD operations for Video records."""
import shutil
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.video import SourceType, Video, VideoStatus


class StorageService:
    def create_video(
        self,
        db: Session,
        *,
        user_id: str,
        original_filename: str,
        stored_filename: str,
        file_path: str,
        file_size: int,
        duration: Optional[float] = None,
    ) -> Video:
        video = Video(
            user_id=user_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_size=file_size,
            duration=duration,
            status=VideoStatus.UPLOADED,
            source_type=SourceType.UPLOAD,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return video

    def create_youtube_video(
        self,
        db: Session,
        *,
        user_id: str,
        youtube_video_id: str,
        source_url: str,
        title: Optional[str],
        duration: Optional[float],
        thumbnail: Optional[str],
    ) -> Video:
        # No local media file exists for a YouTube video by design (captions
        # path never downloads anything; the Whisper fallback deletes its
        # temp audio once processed) — file_path/stored_filename/file_size
        # stay non-null (schema constraint carried over from uploads) but
        # are sentinel values, never read as a real path.
        video = Video(
            user_id=user_id,
            original_filename=title or source_url,
            stored_filename=f"youtube-{youtube_video_id}-{uuid.uuid4().hex[:8]}",
            file_path="",
            file_size=0,
            duration=duration,
            status=VideoStatus.UPLOADED,
            source_type=SourceType.YOUTUBE,
            source_url=source_url,
            youtube_video_id=youtube_video_id,
            source_title=title,
            source_thumbnail=thumbnail,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return video

    def get_video(self, db: Session, video_id: str, user_id: str) -> Optional[Video]:
        """Return the video only if it belongs to user_id (others' videos look like 404s)."""
        return db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()

    def list_videos(self, db: Session, user_id: str) -> list[Video]:
        return (
            db.query(Video)
            .filter(Video.user_id == user_id)
            .order_by(Video.created_at.desc())
            .all()
        )

    def delete_video(self, db: Session, video: Video) -> None:
        if video.file_path:
            file_path = Path(video.file_path)
            if file_path.is_file():
                file_path.unlink()

        if video.transcript_path:
            Path(video.transcript_path).unlink(missing_ok=True)

        embeddings_dir = settings.EMBEDDINGS_DIR / video.id
        if embeddings_dir.exists():
            shutil.rmtree(embeddings_dir, ignore_errors=True)

        db.delete(video)
        db.commit()

        from app.services.embedding_service import embedding_service

        embedding_service.invalidate_cache(video.id)


storage_service = StorageService()
