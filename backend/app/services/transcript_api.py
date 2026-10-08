"""TranscriptAPI.com client: YouTube transcripts without touching YouTube directly.

Servers in data centres get YouTube's "confirm you're not a bot" check far
more often than home connections, so the deployed app fetches transcripts
through this paid API instead of yt-dlp. Enabled when TRANSCRIPT_API_KEY is
set; youtube_service falls back to yt-dlp when it isn't, or when the API
can't serve a video.

Docs: https://transcriptapi.com/docs/llms-full.txt
Billing: 1 credit per successful (HTTP 200) request; errors cost nothing.
"""
import html
import json
import logging
import threading
import time
from typing import Optional, TypedDict

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 429, 503}
_MAX_ATTEMPTS = 3
_CACHE_TTL_SECONDS = 600

# get_metadata() (in the API request) and fetch_captions() (in the background
# job, possibly a separate worker process) both need this video's transcript.
# Caching it in memory and on the shared disk means one credit per video.
_cache: dict[str, tuple[float, "TranscriptResult"]] = {}
_cache_lock = threading.Lock()


def _disk_cache_path(video_id: str):
    return settings.CACHE_DIR / "transcripts" / f"{video_id}.json"


def _read_disk_cache(video_id: str) -> Optional["TranscriptResult"]:
    path = _disk_cache_path(video_id)
    try:
        if time.time() - path.stat().st_mtime > _CACHE_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_disk_cache(video_id: str, result: "TranscriptResult") -> None:
    path = _disk_cache_path(video_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("Couldn't write transcript cache for %s: %s", video_id, exc)


class TranscriptAPIError(Exception):
    """Raised when TranscriptAPI can't return a transcript.

    `status` is the HTTP status (None for network errors); `code` is the API's
    error code when it sent one (e.g. "insufficient_credits").
    """

    def __init__(self, message: str, status: Optional[int] = None, code: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.code = code


class TranscriptResult(TypedDict):
    video_id: str
    language: Optional[str]
    segments: list[dict]
    duration: Optional[float]
    title: Optional[str]
    thumbnail: Optional[str]


def is_enabled() -> bool:
    return bool(settings.TRANSCRIPT_API_KEY)


def _to_result(video_id: str, data: dict) -> TranscriptResult:
    segments: list[dict] = []
    for item in data.get("transcript") or []:
        text = " ".join(html.unescape(str(item.get("text") or "")).split())
        if not text:
            continue
        start = float(item.get("start") or 0.0)
        end = start + float(item.get("duration") or 0.0)
        segments.append({"start": round(start, 2), "end": round(end, 2), "text": text})

    # Caption lines overlap while the next one appears; keep timestamps monotonic.
    for current, nxt in zip(segments, segments[1:]):
        if current["end"] > nxt["start"]:
            current["end"] = nxt["start"]

    metadata = data.get("metadata") or {}
    length = data.get("length_seconds")
    return {
        "video_id": data.get("video_id") or video_id,
        "language": (data.get("language") or "").split("-")[0] or None,
        "segments": segments,
        "duration": float(length) if length else None,
        "title": metadata.get("title"),
        "thumbnail": metadata.get("thumbnail_url"),
    }


def fetch_transcript(video_id: str) -> TranscriptResult:
    """Return the transcript and metadata for a video, retrying temporary failures."""
    with _cache_lock:
        cached = _cache.get(video_id)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
    from_disk = _read_disk_cache(video_id)
    if from_disk:
        return from_disk

    params = {"video_url": video_id, "format": "json", "include_timestamp": "true", "send_metadata": "true"}
    headers = {"Authorization": f"Bearer {settings.TRANSCRIPT_API_KEY}"}
    url = f"{settings.TRANSCRIPT_API_URL}/youtube/transcript"

    last_error: Optional[TranscriptAPIError] = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            # Short connect timeout: a stalled connection is retried quickly
            # instead of holding the user's request for a minute.
            resp = httpx.get(url, params=params, headers=headers, timeout=httpx.Timeout(60.0, connect=8.0))
        except httpx.HTTPError as exc:
            last_error = TranscriptAPIError(f"Couldn't reach TranscriptAPI: {exc}")
            logger.warning("TranscriptAPI attempt %d for %s failed: %r", attempt + 1, video_id, exc)
            time.sleep(0.5 * (attempt + 1))
            continue

        if resp.status_code == 200:
            result = _to_result(video_id, resp.json())
            with _cache_lock:
                _cache[video_id] = (time.monotonic(), result)
            _write_disk_cache(video_id, result)
            logger.info(
                "TranscriptAPI: %s → %d segments (cache %s)",
                video_id,
                len(result["segments"]),
                resp.headers.get("X-Cache-Status", "?"),
            )
            return result

        try:
            body = resp.json()
        except ValueError:
            body = {}
        detail = body.get("detail") if isinstance(body, dict) else None
        code = body.get("code") if isinstance(body, dict) else None
        last_error = TranscriptAPIError(
            f"TranscriptAPI returned {resp.status_code}: {detail or resp.text[:200]}",
            status=resp.status_code,
            code=code,
        )
        if resp.status_code not in _RETRYABLE_STATUS:
            break
        retry_after = resp.headers.get("Retry-After")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else 1.5 * (attempt + 1)
        time.sleep(min(delay, 10.0))

    if last_error and last_error.status in (401, 402):
        # Account problems: the operator has to fix these, not the user.
        logger.error("TranscriptAPI account problem: %s", last_error)
    raise last_error or TranscriptAPIError("TranscriptAPI request failed")
