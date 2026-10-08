"""Per-user usage limits that keep a public deployment's costs bounded."""
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.video import Video, VideoStatus


def videos_created_today(db: Session, user_id: str) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.query(Video).filter(Video.user_id == user_id, Video.created_at >= since).count()


def check_can_start_video(db: Session, user_id: str) -> None:
    """Raise 429 when the user hit the daily quota or has too many jobs running."""
    if settings.DAILY_VIDEO_LIMIT and videos_created_today(db, user_id) >= settings.DAILY_VIDEO_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've reached today's limit of {settings.DAILY_VIDEO_LIMIT} videos. Try again tomorrow.",
        )
    if settings.MAX_ACTIVE_JOBS_PER_USER:
        active = (
            db.query(Video)
            .filter(
                Video.user_id == user_id,
                Video.status.in_([VideoStatus.UPLOADED, VideoStatus.PROCESSING]),
            )
            .count()
        )
        if active >= settings.MAX_ACTIVE_JOBS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You already have videos being analyzed. Wait for one to finish, then try again.",
            )


def check_duration(duration_seconds: float | None) -> None:
    if settings.MAX_VIDEO_MINUTES and duration_seconds and duration_seconds > settings.MAX_VIDEO_MINUTES * 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Videos can be at most {settings.MAX_VIDEO_MINUTES} minutes long.",
        )


class _SlidingWindowLimiter:
    """In-memory per-user limiter. Per-process, which is fine for one API instance."""

    def __init__(self) -> None:
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > window_seconds:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True


_ask_limiter = _SlidingWindowLimiter()
_search_limiter = _SlidingWindowLimiter()


def check_search_rate(user_id: str) -> None:
    if settings.SEARCH_LIMIT_PER_HOUR and not _search_limiter.hit(user_id, settings.SEARCH_LIMIT_PER_HOUR, 3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You're searching very quickly. Wait a few minutes and try again.",
        )


def check_ask_rate(user_id: str) -> None:
    if settings.ASK_LIMIT_PER_HOUR and not _ask_limiter.hit(user_id, settings.ASK_LIMIT_PER_HOUR, 3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You're asking questions very quickly. Wait a few minutes and try again.",
        )
