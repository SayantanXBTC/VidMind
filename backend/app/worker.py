"""Background worker for JOB_MODE=queue.

The API records each new video as "uploaded" (queued); this process claims
queued videos from the database and runs the analysis pipeline, up to
WORKER_CONCURRENCY at a time. Because the queue lives in the database, jobs
survive API restarts and deploys, and no separate queue service is needed.

Run exactly one worker process: `python -m app.worker`. On startup it
re-queues videos left "processing" by a previous worker that stopped.
"""
# Must run before any ML import — see app/core/native_threads.py.
import app.core.native_threads  # noqa: F401,I001

import logging
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import update

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.database.session import SessionLocal, init_db
from app.models.video import SourceType, Video, VideoStatus
from app.services.processing_service import processing_service

configure_logging()
logger = logging.getLogger("app.worker")

POLL_SECONDS = 2.0
MAX_ATTEMPTS = 3

_stopping = threading.Event()
_running: set[str] = set()
_running_lock = threading.Lock()


def _requeue_orphans() -> None:
    """Videos still "processing" at startup were cut off when the last worker stopped."""
    db = SessionLocal()
    try:
        result = db.execute(
            update(Video)
            .where(Video.status == VideoStatus.PROCESSING)
            .values(status=VideoStatus.UPLOADED)
        )
        db.commit()
        if result.rowcount:
            logger.warning("Re-queued %d interrupted video(s)", result.rowcount)
    finally:
        db.close()


def _claim_next() -> tuple[str, SourceType] | None:
    """Atomically move the oldest queued video to "processing" and return it.

    The conditional UPDATE only succeeds for one claimer, so this stays safe
    even if two workers were ever started by mistake.
    """
    db = SessionLocal()
    try:
        while True:
            candidate = (
                db.query(Video.id, Video.source_type, Video.job_attempts)
                .filter(Video.status == VideoStatus.UPLOADED)
                .order_by(Video.created_at)
                .first()
            )
            if candidate is None:
                return None
            video_id, source_type, attempts = candidate
            attempts = (attempts or 0) + 1

            if attempts > MAX_ATTEMPTS:
                db.execute(
                    update(Video)
                    .where(Video.id == video_id, Video.status == VideoStatus.UPLOADED)
                    .values(
                        status=VideoStatus.FAILED,
                        error_message="Processing kept stopping unexpectedly. Try a different video.",
                        processing_completed_at=datetime.now(timezone.utc),
                    )
                )
                db.commit()
                logger.error("Video %s failed after %d attempts", video_id, MAX_ATTEMPTS)
                continue

            result = db.execute(
                update(Video)
                .where(Video.id == video_id, Video.status == VideoStatus.UPLOADED)
                .values(status=VideoStatus.PROCESSING, job_attempts=attempts)
            )
            db.commit()
            if result.rowcount == 1:
                return video_id, source_type
            # Someone else claimed it first; look again.
    finally:
        db.close()


def _run(video_id: str, source_type: SourceType) -> None:
    logger.info("Processing video %s (%s)", video_id, source_type.value)
    try:
        if source_type == SourceType.YOUTUBE:
            processing_service.process_youtube_video(video_id)
        else:
            processing_service.process_video(video_id)
    finally:
        with _running_lock:
            _running.discard(video_id)


def _release_running_jobs() -> None:
    """On shutdown, hand unfinished videos back to the queue right away."""
    with _running_lock:
        ids = list(_running)
    if not ids:
        return
    db = SessionLocal()
    try:
        db.execute(
            update(Video)
            .where(Video.id.in_(ids), Video.status == VideoStatus.PROCESSING)
            .values(status=VideoStatus.UPLOADED)
        )
        db.commit()
        logger.warning("Released %d unfinished video(s) back to the queue", len(ids))
    finally:
        db.close()


def _handle_signal(signum, _frame) -> None:
    logger.info("Received signal %s, shutting down", signum)
    _stopping.set()
    _release_running_jobs()
    raise SystemExit(0)


def main() -> None:
    init_db()
    _requeue_orphans()
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    concurrency = max(1, settings.WORKER_CONCURRENCY)
    logger.info("Worker started (concurrency=%d)", concurrency)

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="job") as pool:
        while not _stopping.is_set():
            with _running_lock:
                free = concurrency - len(_running)
            claimed = None
            if free > 0:
                try:
                    claimed = _claim_next()
                except Exception:  # noqa: BLE001 - e.g. database briefly unreachable
                    logger.exception("Failed to claim a job")
            if claimed is None:
                time.sleep(POLL_SECONDS)
                continue
            video_id, source_type = claimed
            with _running_lock:
                _running.add(video_id)
            pool.submit(_run, video_id, source_type)


if __name__ == "__main__":
    main()
