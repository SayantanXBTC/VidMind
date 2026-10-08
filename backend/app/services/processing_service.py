"""Orchestrates transcript acquisition -> embeddings -> summary -> DB.

Two entry points feed the same shared tail (_finish_pipeline):
  process_video(video_id)          local upload: audio extract -> Whisper
  process_youtube_video(video_id)  YouTube: captions first, Whisper fallback

Runs inside a FastAPI BackgroundTask, so it owns its own DB session rather
than reusing a request-scoped one.

Progress checkpoints (matches the frontend's stage labels):
  5   uploaded/queued (set by the upload/youtube route)
  20  audio extracted (or YouTube audio fallback downloaded), starting transcription
  45  transcription complete (or captions acquired), starting embedding/indexing
  60  embeddings indexed, starting summarization
  60-85  summary, key points and chapters being written (LLM streaming progress)
  85  summary/key points/chapters generated, saving
  100 completed

Embedding failure is non-fatal: it's recorded on embedding_status/
embedding_error but does not fail the video, since transcript/summary are
still fully usable without semantic search.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.database.session import SessionLocal
from app.models.video import EmbeddingStatus, IngestionMethod, Video, VideoStatus
from app.services.embedding_service import EmbeddingError, embedding_service
from app.services.summarization_service import SummarizationError, summarization_service
from app.services.transcription_service import TranscriptionError, transcription_service
from app.services.video_service import VideoProcessingError, video_service
from app.services import youtube_service
from app.services.youtube_service import YouTubeError

logger = logging.getLogger(__name__)

PROGRESS_AUDIO_EXTRACTED = 20
PROGRESS_TRANSCRIBED = 45
PROGRESS_EMBEDDED = 60
PROGRESS_KEY_POINTS_CHAPTERS = 85
PROGRESS_COMPLETE = 100
PROGRESS_WRITE_THRESHOLD = 10


# Shown to users when something unexpected breaks; details go to the logs only.
GENERIC_FAILURE = "Something went wrong while analyzing this video. Try again in a moment."
FRIENDLY_ERRORS = {
    VideoProcessingError: "This file couldn't be read as a video. Check that it plays, then upload it again.",
    TranscriptionError: "The audio couldn't be transcribed. Try again, or try a different video.",
    SummarizationError: "The summary couldn't be written. Try again in a moment.",
}


def _user_message(exc: Exception) -> str:
    # YouTubeError messages are written for users; others may contain internals.
    if isinstance(exc, YouTubeError):
        return str(exc)
    return FRIENDLY_ERRORS.get(type(exc), GENERIC_FAILURE)


def _now():
    return datetime.now(timezone.utc)


class ProcessingService:
    # ------------------------------------------------------------------
    # Local file upload
    # ------------------------------------------------------------------
    def process_video(self, video_id: str) -> None:
        db = SessionLocal()
        audio_path: Path | None = None
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                logger.warning("Video %s deleted before processing started", video_id)
                return

            video.status = VideoStatus.PROCESSING
            video.processing_started_at = _now()
            video.error_message = None
            db.commit()

            file_path = Path(video.file_path)

            # --- audio extraction ---
            audio_path = video_service.extract_audio(file_path)
            if not self._still_exists(db, video_id):
                return
            self._update_progress(db, video_id, PROGRESS_AUDIO_EXTRACTED)

            # --- transcription ---
            expected_duration = video.duration or 0.0
            last_written_progress = PROGRESS_AUDIO_EXTRACTED

            def on_segment(index: int, segment: dict) -> None:
                nonlocal last_written_progress
                if expected_duration <= 0:
                    return
                fraction = min(segment["end"] / expected_duration, 1.0)
                progress = PROGRESS_AUDIO_EXTRACTED + int(
                    fraction * (PROGRESS_TRANSCRIBED - PROGRESS_AUDIO_EXTRACTED)
                )
                if progress - last_written_progress >= PROGRESS_WRITE_THRESHOLD:
                    last_written_progress = progress
                    self._update_progress(db, video_id, progress)

            transcription = transcription_service.transcribe(audio_path, on_segment=on_segment)

            if not self._still_exists(db, video_id):
                return

            self._persist_transcript(db, video_id, transcription, IngestionMethod.WHISPER)
            if not self._still_exists(db, video_id):
                return

            self._finish_pipeline(db, video_id, transcription["segments"])

        except (VideoProcessingError, TranscriptionError, SummarizationError) as exc:
            logger.error("Processing failed for video %s: %s", video_id, exc)
            self._mark_failed(db, video_id, _user_message(exc))
        except Exception:  # noqa: BLE001 - last-resort guard against a stuck "processing" row
            logger.exception("Unexpected error processing video %s", video_id)
            self._mark_failed(db, video_id, GENERIC_FAILURE)
        finally:
            if audio_path:
                video_service.cleanup_file(audio_path)
            db.close()

    # ------------------------------------------------------------------
    # YouTube ingestion
    # ------------------------------------------------------------------
    def process_youtube_video(self, video_id: str) -> None:
        db = SessionLocal()
        raw_audio_path: Path | None = None
        wav_path: Path | None = None
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                logger.warning("Video %s deleted before processing started", video_id)
                return

            video.status = VideoStatus.PROCESSING
            video.processing_started_at = _now()
            video.error_message = None
            db.commit()

            url = video.source_url

            # --- stage 1: captions first, no download ---
            captions = youtube_service.fetch_captions(url)

            if captions:
                segments, language = captions
                ingestion_method = IngestionMethod.CAPTION
                if not self._still_exists(db, video_id):
                    return
                self._update_progress(db, video_id, PROGRESS_AUDIO_EXTRACTED)
            else:
                # --- stage 2: audio-only fallback + Whisper ---
                ingestion_method = IngestionMethod.WHISPER
                raw_audio_path = youtube_service.download_audio(url)
                if not self._still_exists(db, video_id):
                    return
                self._update_progress(db, video_id, PROGRESS_AUDIO_EXTRACTED)

                wav_path = video_service.extract_audio(raw_audio_path)
                if not self._still_exists(db, video_id):
                    return

                expected_duration = video.duration or 0.0
                last_written_progress = PROGRESS_AUDIO_EXTRACTED

                def on_segment(index: int, segment: dict) -> None:
                    nonlocal last_written_progress
                    if expected_duration <= 0:
                        return
                    fraction = min(segment["end"] / expected_duration, 1.0)
                    progress = PROGRESS_AUDIO_EXTRACTED + int(
                        fraction * (PROGRESS_TRANSCRIBED - PROGRESS_AUDIO_EXTRACTED)
                    )
                    if progress - last_written_progress >= PROGRESS_WRITE_THRESHOLD:
                        last_written_progress = progress
                        self._update_progress(db, video_id, progress)

                transcription = transcription_service.transcribe(wav_path, on_segment=on_segment)
                segments, language = transcription["segments"], transcription["language"]

            if not self._still_exists(db, video_id):
                return

            duration = video.duration or (segments[-1]["end"] if segments else 0.0)
            self._persist_transcript(
                db,
                video_id,
                {"language": language, "duration": duration, "segments": segments},
                ingestion_method,
            )
            if not self._still_exists(db, video_id):
                return

            self._finish_pipeline(db, video_id, segments)

        except (YouTubeError, VideoProcessingError, TranscriptionError, SummarizationError) as exc:
            logger.error("Processing failed for YouTube video %s: %s", video_id, exc)
            self._mark_failed(db, video_id, _user_message(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error processing YouTube video %s", video_id)
            self._mark_failed(db, video_id, GENERIC_FAILURE)
        finally:
            if raw_audio_path:
                video_service.cleanup_file(raw_audio_path)
            if wav_path:
                video_service.cleanup_file(wav_path)
            db.close()

    # ------------------------------------------------------------------
    # Shared tail: transcript already acquired -> embeddings -> summary -> done
    # ------------------------------------------------------------------
    def _persist_transcript(
        self, db, video_id: str, transcription: dict, ingestion_method: IngestionMethod
    ) -> None:
        """Persist the transcript immediately, independent of what happens next,
        so a later summarization/embedding failure never loses it."""
        transcript_path = transcription_service.save_transcript(video_id, transcription)
        full_text = " ".join(seg["text"] for seg in transcription["segments"]).strip()

        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            logger.warning("Video %s deleted during processing, discarding result", video_id)
            return
        video.language = transcription["language"]
        video.transcript = full_text
        video.transcript_path = str(transcript_path)
        video.ingestion_method = ingestion_method
        video.processing_progress = PROGRESS_TRANSCRIBED
        db.commit()

    def _finish_pipeline(self, db, video_id: str, segments: list[dict]) -> None:
        # --- embeddings / FAISS index (non-fatal on failure) ---
        self._build_embeddings(db, video_id, segments)
        if not self._still_exists(db, video_id):
            return
        self._update_progress(db, video_id, PROGRESS_EMBEDDED)

        # --- summary, key points and chapters (one LLM pass) ---
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return
        title = video.source_title or Path(video.original_filename).stem
        duration = video.duration
        last_written_progress = PROGRESS_EMBEDDED

        def on_progress(fraction: float) -> None:
            nonlocal last_written_progress
            progress = PROGRESS_EMBEDDED + int(
                fraction * (PROGRESS_KEY_POINTS_CHAPTERS - PROGRESS_EMBEDDED)
            )
            if progress - last_written_progress >= 5:
                last_written_progress = progress
                self._update_progress(db, video_id, progress)

        summary_result = summarization_service.summarize(
            segments, title=title, duration=duration, on_progress=on_progress
        )

        if not self._still_exists(db, video_id):
            return
        self._update_progress(db, video_id, PROGRESS_KEY_POINTS_CHAPTERS)

        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            logger.warning("Video %s deleted during processing, discarding result", video_id)
            return

        video.status = VideoStatus.COMPLETED
        video.processing_progress = PROGRESS_COMPLETE
        video.tldr = summary_result.get("tldr")
        video.summary = summary_result["summary"]
        video.key_points = summary_result["key_points"]
        video.chapters = summary_result["chapters"]
        video.processing_completed_at = _now()
        db.commit()
        logger.info("Video %s processed successfully", video_id)

    def _build_embeddings(self, db, video_id: str, segments: list[dict]) -> None:
        """Build the FAISS index for this video. Failure is recorded but never
        propagates — transcript/summary must remain usable either way."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return
        video.embedding_status = EmbeddingStatus.PROCESSING
        video.embedding_error = None
        db.commit()

        try:
            embedding_service.build_index(video_id, segments)
        except EmbeddingError as exc:
            logger.error("Embedding generation failed for video %s: %s", video_id, exc)
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                video.embedding_status = EmbeddingStatus.FAILED
                video.embedding_error = str(exc)
                db.commit()
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected embedding error for video %s", video_id)
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                video.embedding_status = EmbeddingStatus.FAILED
                video.embedding_error = f"Unexpected embedding error: {exc}"
                db.commit()
            return

        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.embedding_status = EmbeddingStatus.COMPLETED
            db.commit()

    def _still_exists(self, db, video_id: str) -> bool:
        exists = db.query(Video.id).filter(Video.id == video_id).first() is not None
        if not exists:
            logger.warning("Video %s deleted during processing, aborting", video_id)
        return exists

    def _update_progress(self, db, video_id: str, progress: int) -> None:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return
        video.processing_progress = progress
        db.commit()

    def _mark_failed(self, db, video_id: str, error_message: str) -> None:
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                return
            video.status = VideoStatus.FAILED
            video.error_message = error_message
            video.processing_completed_at = _now()
            db.commit()
            logger.error("Video %s processing failed: %s", video_id, error_message)
        except Exception:
            logger.exception("Failed to record failure state for video %s", video_id)
            db.rollback()


processing_service = ProcessingService()
