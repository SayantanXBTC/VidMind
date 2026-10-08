"""Analysis jobs and the results cache — no database.

Each YouTube video is one job, keyed by its video ID. Jobs run on a small
thread pool inside the API process. Finished results stay in memory (LRU)
and are mirrored as JSON files under CACHE_DIR, so a video anyone has
already analyzed is served again instantly and for free. If the files are
lost (e.g. a redeploy without a persistent disk), the next request simply
analyzes the video again.
"""
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Optional

from app.core.config import settings
from app.services import transcription, youtube_service
from app.services.llm_service import LLMError, llm_service
from app.services.llm_summarizer import summarize_with_llm
from app.services.transcription import TranscriptionError
from app.services.youtube_service import YouTubeError

logger = logging.getLogger(__name__)

QUEUED, PROCESSING, COMPLETED, FAILED = "queued", "processing", "completed", "failed"

GENERIC_FAILURE = "Something went wrong while analyzing this video. Try again in a moment."
NO_CAPTIONS = "This video has no captions or subtitles, so VidMind can't read it."
NO_SPEECH = "No speech was found in this video, so there's nothing to summarize."
AI_UNAVAILABLE = "VidMind's AI is busy right now. Try again in a minute."

_RESULTS_DIR = settings.CACHE_DIR / "results"


@dataclass
class Job:
    id: str
    video: dict
    status: str = QUEUED
    progress: int = 0
    stage: str = "Queued"
    error: Optional[str] = None
    result: Optional[dict] = None
    created_at: float = field(default_factory=time.time)
    owner_ip: Optional[str] = None  # who started it, for per-IP concurrency limits
    upload_path: Optional[Path] = None  # uploaded file, deleted once transcribed

    def public(self, include_result: bool = True) -> dict:
        data = {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "error": self.error,
            "video": self.video,
        }
        if include_result:
            data["result"] = self.result
        return data


class JobManager:
    def __init__(self) -> None:
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=settings.WORKER_THREADS, thread_name_prefix="analyze")
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ cache

    def _remember(self, job: Job) -> None:
        self._jobs[job.id] = job
        self._jobs.move_to_end(job.id)
        while len(self._jobs) > settings.CACHE_MAX_ITEMS:
            oldest_id, oldest = next(iter(self._jobs.items()))
            if oldest.status in (QUEUED, PROCESSING):
                break  # never evict running jobs
            self._jobs.popitem(last=False)

    def _load_from_disk(self, video_id: str) -> Optional[Job]:
        path = _RESULTS_DIR / f"{video_id}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return Job(
            id=video_id, video=data["video"], status=COMPLETED, progress=100, stage="Ready", result=data["result"]
        )

    def _save_to_disk(self, job: Job) -> None:
        path = _RESULTS_DIR / f"{job.id}.json"
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"video": job.video, "result": job.result}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            self._prune_disk()
        except OSError as exc:
            logger.warning("Couldn't cache result for %s: %s", job.id, exc)

    def _prune_disk(self) -> None:
        files = sorted(_RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for path in files[: max(0, len(files) - settings.CACHE_MAX_ITEMS)]:
            path.unlink(missing_ok=True)

    def get(self, video_id: str) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(video_id)
            if job:
                self._jobs.move_to_end(video_id)
                return job
        job = self._load_from_disk(video_id)
        if job:
            with self._lock:
                self._remember(job)
        return job

    def active_jobs_for_ip(self, ip: str) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.owner_ip == ip and j.status in (QUEUED, PROCESSING))

    # ------------------------------------------------------------------- jobs

    def start(self, video: dict, owner_ip: str, upload_path: Optional[Path] = None) -> Job:
        """Queue a new analysis. The caller has already checked limits and that
        no usable job exists for this video."""
        job = Job(id=video["id"], video=video, owner_ip=owner_ip, stage="Queued", progress=5, upload_path=upload_path)
        with self._lock:
            self._remember(job)
        self._pool.submit(self._run, job)
        return job

    def _set(self, job: Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)

    def _transcribe_upload(self, job: Job):
        """Uploaded file → (segments, language). Progress 10–60%."""
        wav = None
        try:
            self._set(job, status=PROCESSING, progress=8, stage="Extracting audio")
            wav = transcription.extract_audio(job.upload_path)
            job.upload_path.unlink(missing_ok=True)  # the video itself is no longer needed
            self._set(job, progress=12, stage="Transcribing speech")

            def on_progress(fraction: float) -> None:
                self._set(job, progress=12 + int(fraction * 48))

            return transcription.whisper.transcribe(wav, job.video.get("duration") or 0, on_progress)
        finally:
            if wav:
                wav.unlink(missing_ok=True)

    def _run(self, job: Job) -> None:
        try:
            if job.upload_path:
                segments, language = self._transcribe_upload(job)
                if not segments:
                    self._set(job, status=FAILED, error=NO_SPEECH, stage="Failed")
                    return
                notes_from = 60
            else:
                self._set(job, status=PROCESSING, progress=15, stage="Reading the transcript")
                captions = youtube_service.fetch_captions(job.video["url"])
                if not captions:
                    self._set(job, status=FAILED, error=NO_CAPTIONS, stage="Failed")
                    return
                segments, language = captions
                notes_from = 30
            if not llm_service.is_available():
                self._set(job, status=FAILED, error=AI_UNAVAILABLE, stage="Failed")
                return

            self._set(job, progress=notes_from, stage="Writing summary & chapters")

            def on_progress(fraction: float) -> None:
                self._set(job, progress=notes_from + int(fraction * (95 - notes_from)))

            notes = summarize_with_llm(
                segments,
                title=job.video.get("title"),
                duration=job.video.get("duration"),
                on_progress=on_progress,
            )
            result = {**notes, "language": language, "segments": segments}
            self._set(job, status=COMPLETED, progress=100, stage="Ready", result=result)
            self._save_to_disk(job)
            logger.info("Analyzed %s (%d segments)", job.id, len(segments))
        except (YouTubeError, TranscriptionError) as exc:
            self._set(job, status=FAILED, error=str(exc), stage="Failed")
        except LLMError as exc:
            logger.error("LLM failed for %s: %s", job.id, exc)
            self._set(job, status=FAILED, error=AI_UNAVAILABLE, stage="Failed")
        except Exception:  # noqa: BLE001 - never leave a job stuck in "processing"
            logger.exception("Unexpected error analyzing %s", job.id)
            self._set(job, status=FAILED, error=GENERIC_FAILURE, stage="Failed")
        finally:
            if job.upload_path:
                job.upload_path.unlink(missing_ok=True)
                job.upload_path = None


job_manager = JobManager()
