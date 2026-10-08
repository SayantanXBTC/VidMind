"""Usage limits for an open website with no accounts.

Visitors are identified by IP address. Only *new* analyses count: videos
already in the cache are free to serve. A site-wide daily cap bounds the
total AI and transcript bill no matter how many IPs show up. All counters
are in memory, so they reset on restart — acceptable for cost control, and
it keeps the app free of a database.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from app.core.config import settings

DAY = 24 * 3600
HOUR = 3600


class _Window:
    """Timestamps of events in a sliding window, per key."""

    def __init__(self) -> None:
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def count(self, key: str, window: int) -> int:
        now = time.time()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > window:
                events.popleft()
            if not events:
                self._events.pop(key, None)
                return 0
            return len(events)

    def add(self, key: str) -> None:
        with self._lock:
            self._events[key].append(time.time())


_analyses = _Window()
_questions = _Window()
_SITE = "__site__"


def _too_many(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


def check_can_analyze(ip: str, active_jobs: int) -> None:
    if settings.ANALYSES_PER_DAY_TOTAL and _analyses.count(_SITE, DAY) >= settings.ANALYSES_PER_DAY_TOTAL:
        raise _too_many(
            "VidMind has reached today's limit for new videos. Videos others have already analyzed still work, "
            "and new ones open up again tomorrow."
        )
    if settings.ANALYSES_PER_IP_PER_DAY and _analyses.count(ip, DAY) >= settings.ANALYSES_PER_IP_PER_DAY:
        raise _too_many(
            f"You've analyzed {settings.ANALYSES_PER_IP_PER_DAY} new videos today, the daily limit. Try again tomorrow."
        )
    if active_jobs >= 2:
        raise _too_many("You already have videos being analyzed. Wait for one to finish, then try again.")


def record_analysis(ip: str) -> None:
    _analyses.add(ip)
    _analyses.add(_SITE)


def check_and_record_question(ip: str) -> None:
    limit = settings.QUESTIONS_PER_IP_PER_HOUR
    if limit and _questions.count(ip, HOUR) >= limit:
        raise _too_many("You're asking questions very quickly. Wait a few minutes and try again.")
    _questions.add(ip)


def check_duration(duration_seconds: float | None) -> None:
    if settings.MAX_VIDEO_MINUTES and duration_seconds and duration_seconds > settings.MAX_VIDEO_MINUTES * 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Videos can be at most {settings.MAX_VIDEO_MINUTES} minutes long.",
        )


def usage_for(ip: str) -> dict:
    return {
        "analyses_today": _analyses.count(ip, DAY),
        "analyses_per_day": settings.ANALYSES_PER_IP_PER_DAY or None,
        "max_video_minutes": settings.MAX_VIDEO_MINUTES or None,
        "uploads_enabled": settings.ENABLE_UPLOADS,
        "max_upload_mb": settings.MAX_UPLOAD_MB or None,
    }
