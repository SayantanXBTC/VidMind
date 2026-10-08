"""YouTube: URL validation, video metadata and caption transcripts.

Uses TranscriptAPI.com when TRANSCRIPT_API_KEY is set (needed on servers,
which YouTube often blocks), and yt-dlp otherwise or as a fallback.
"""
import json
import logging
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional, TypedDict

import yt_dlp

from app.core.config import settings
from app.services import transcript_api
from app.services.transcript_api import TranscriptAPIError

logger = logging.getLogger(__name__)

# youtube.com/watch?v=ID, youtu.be/ID, youtube.com/shorts/ID (+ optional query/fragment)
_YOUTUBE_URL_RE = re.compile(
    r"^https?://(www\.|m\.)?"
    r"(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)"
    r"(?P<id>[A-Za-z0-9_-]{11})"
)

_PREFERRED_CAPTION_LANGS = ["en", "en-US", "en-GB", "en-orig"]

# get_metadata() runs in the request and fetch_captions() in the background
# job right after it; caching the yt-dlp info dict saves a second full
# extraction (several seconds) per video.
_INFO_CACHE_TTL_SECONDS = 600
_info_cache: dict[str, tuple[float, dict]] = {}
_info_cache_lock = threading.Lock()


class YouTubeError(Exception):
    """Raised for any YouTube ingestion failure. Message is always safe to show a user."""


class VideoMetadata(TypedDict):
    video_id: str
    canonical_url: str
    title: Optional[str]
    duration: Optional[float]
    thumbnail: Optional[str]


class TranscriptSegment(TypedDict):
    start: float
    end: float
    text: str


def extract_video_id(url: str) -> str:
    match = _YOUTUBE_URL_RE.match((url or "").strip())
    if not match:
        raise YouTubeError(
            "That doesn't look like a supported YouTube URL. "
            "Use a youtube.com/watch, youtu.be, or youtube.com/shorts link."
        )
    return match.group("id")


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


# Tried in order when YouTube answers the default web client with a bot
# check; these clients are often still served when the web client isn't.
_FALLBACK_PLAYER_CLIENTS = (["web_creator"], ["web_safari"], ["mweb"], ["android_vr"])

# Set when reading browser cookies fails (e.g. Keychain access denied), so
# later requests stop retrying it and go straight to cookie-less requests.
_cookies_unavailable = False


def _ydl_opts(use_cookies: bool = True, **overrides) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    cookie_file = Path(settings.YTDLP_COOKIES_FILE).expanduser() if settings.YTDLP_COOKIES_FILE else None
    if use_cookies and cookie_file and cookie_file.is_file():
        opts["cookiefile"] = str(cookie_file)
    elif use_cookies and settings.YTDLP_COOKIES_FROM_BROWSER and not _cookies_unavailable:
        # Reuse the local browser's YouTube session so YouTube doesn't demand
        # a "confirm you're not a bot" sign-in. Cookies never leave this machine.
        opts["cookiesfrombrowser"] = (settings.YTDLP_COOKIES_FROM_BROWSER,)
    opts.update(overrides)
    return opts


def _is_bot_check(exc: Exception) -> bool:
    text = str(exc).lower()
    return "not a bot" in text or "sign in to confirm" in text


def _is_retryable(exc: Exception) -> bool:
    """Errors that another YouTube client type may not hit."""
    text = str(exc).lower()
    return _is_bot_check(exc) or "page needs to be reloaded" in text or "format is not available" in text


def _is_cookie_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(k in text for k in ("cookie", "keyring", "keychain", "safe storage", "decrypt"))


def _run_ydl(url: str, download: bool, **overrides) -> tuple[dict, "yt_dlp.YoutubeDL"]:
    """extract_info with browser cookies, falling back to no cookies if the
    browser's cookie store can't be read."""
    global _cookies_unavailable
    try:
        ydl = yt_dlp.YoutubeDL(_ydl_opts(**overrides))
        return ydl.extract_info(url, download=download), ydl
    except Exception as exc:  # noqa: BLE001
        if not (settings.YTDLP_COOKIES_FROM_BROWSER and _is_cookie_error(exc)) or _cookies_unavailable:
            raise
        _cookies_unavailable = True
        logger.warning(
            "Couldn't read %s cookies (%s); continuing without them",
            settings.YTDLP_COOKIES_FROM_BROWSER,
            exc,
        )
        ydl = yt_dlp.YoutubeDL(_ydl_opts(use_cookies=False, **overrides))
        return ydl.extract_info(url, download=download), ydl


def _friendly_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "private" in text:
        return "This video is private and can't be analyzed."
    if "age" in text and "restrict" in text:
        return "This video is age-restricted and can't be accessed without sign-in."
    if "unavailable" in text or "removed" in text:
        return "This video is unavailable or has been removed."
    if "region" in text or "not available in your country" in text:
        return "This video isn't available in this region."
    if "not a bot" in text or "sign in to confirm" in text:
        if settings.YTDLP_COOKIES_FILE or (settings.YTDLP_COOKIES_FROM_BROWSER and not _cookies_unavailable):
            return (
                "YouTube is blocking requests from this network. Make sure you're signed in to "
                f"YouTube in {settings.YTDLP_COOKIES_FROM_BROWSER.title()}, then try again."
            )
        return (
            "YouTube is asking VidMind to confirm it's not a bot. Add a YouTube cookies.txt "
            "(YTDLP_COOKIES_FILE in backend/.env), or try again later."
        )
    if "copyright" in text:
        return "This video is blocked due to a copyright claim."
    return "VidMind couldn't access this YouTube video. Try a publicly accessible video."


def _extract_info(video_id: str) -> dict:
    with _info_cache_lock:
        cached = _info_cache.get(video_id)
        if cached and time.monotonic() - cached[0] < _INFO_CACHE_TTL_SECONDS:
            return cached[1]
    url = canonical_url(video_id)
    # Metadata and captions don't need media formats, and YouTube often
    # withholds formats (PO token / JS challenge) while still serving both.
    attempts = [None, *_FALLBACK_PLAYER_CLIENTS]
    info = None
    first_error: Exception | None = None
    for clients in attempts:
        overrides = {"ignore_no_formats_error": True}
        if clients:
            overrides["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            candidate, _ = _run_ydl(url, download=False, **overrides)
        except yt_dlp.utils.DownloadError as exc:
            first_error = first_error or exc
            if not _is_retryable(exc):
                raise
            logger.info("YouTube client %s failed for %s: %s", clients or "default", video_id, exc)
            continue
        if info is None:
            info = candidate
        if candidate.get("subtitles") or candidate.get("automatic_captions"):
            info = candidate
            if clients:
                logger.info("Using %s client for %s", clients[0], video_id)
            break
    if info is None:
        raise first_error
    with _info_cache_lock:
        _info_cache[video_id] = (time.monotonic(), info)
    return info


def get_metadata(url: str) -> VideoMetadata:
    video_id = extract_video_id(url)

    if transcript_api.is_enabled():
        try:
            result = transcript_api.fetch_transcript(video_id)
            if result["segments"]:
                return {
                    "video_id": video_id,
                    "canonical_url": canonical_url(video_id),
                    "title": result["title"],
                    "duration": result["duration"],
                    "thumbnail": result["thumbnail"]
                    or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                }
        except TranscriptAPIError as exc:
            if exc.status == 422:
                raise YouTubeError(
                    "That doesn't look like a valid YouTube video link."
                ) from exc
            # 404 (no transcript), account or temporary problems: try yt-dlp,
            # which also reports "private" / "removed" etc. precisely.
            logger.warning("TranscriptAPI failed for %s, falling back to yt-dlp: %s", video_id, exc)

    try:
        info = _extract_info(video_id)
    except yt_dlp.utils.DownloadError as exc:
        raise YouTubeError(_friendly_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error fetching YouTube metadata for %s", video_id)
        raise YouTubeError("VidMind couldn't access this YouTube video.") from exc

    return {
        "video_id": video_id,
        "canonical_url": canonical_url(video_id),
        "title": info.get("title"),
        "duration": float(info["duration"]) if info.get("duration") else None,
        "thumbnail": info.get("thumbnail"),
    }


def _parse_json3(raw: str) -> list[TranscriptSegment]:
    """Parse YouTube's json3 caption format.

    Unlike VTT, json3 lists each caption line once, so auto-generated
    captions don't come back with every line repeated two or three times.
    """
    data = json.loads(raw)
    segments: list[TranscriptSegment] = []
    for event in data.get("events") or []:
        segs = event.get("segs")
        if not segs or "tStartMs" not in event:
            continue
        text = " ".join("".join(seg.get("utf8", "") for seg in segs).split())
        if not text:
            continue
        start = event["tStartMs"] / 1000.0
        end = start + event.get("dDurationMs", 0) / 1000.0
        segments.append({"start": round(start, 2), "end": round(end, 2), "text": text})

    # Auto captions overlap in time (a line stays on screen while the next one
    # appears); clip each end to the next start so timestamps are monotonic.
    for current, nxt in zip(segments, segments[1:]):
        if current["end"] > nxt["start"]:
            current["end"] = nxt["start"]
    return segments


def _parse_vtt(vtt_text: str) -> list[TranscriptSegment]:
    """WebVTT parser that removes the rolling repeats of auto-generated captions.

    Auto captions show each line twice: first as the new bottom line, then as
    the top line of the next cue. Only lines that differ from the previously
    emitted line are kept.
    """
    timestamp_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->\s*"
        r"(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})"
    )
    tag_re = re.compile(r"<[^>]+>")

    def to_seconds(ts: str) -> float:
        parts = ts.split(":")
        if len(parts) == 3:
            h, m, s = parts
        else:
            h, m, s = "0", parts[0], parts[1]
        return int(h) * 3600 + int(m) * 60 + float(s)

    segments: list[TranscriptSegment] = []
    recent_lines: list[str] = []
    lines = vtt_text.splitlines()
    i = 0
    while i < len(lines):
        match = timestamp_re.search(lines[i])
        if match:
            start = to_seconds(match.group(1))
            end = to_seconds(match.group(2))
            i += 1
            new_lines = []
            while i < len(lines) and lines[i].strip():
                line = " ".join(tag_re.sub("", lines[i]).split())
                if line and line not in recent_lines:
                    new_lines.append(line)
                    recent_lines = (recent_lines + [line])[-3:]
                i += 1
            text = " ".join(new_lines)
            if text:
                segments.append({"start": start, "end": end, "text": text})
        i += 1

    for current, nxt in zip(segments, segments[1:]):
        if current["end"] > nxt["start"]:
            current["end"] = nxt["start"]
    return segments


def _pick_caption_track(caption_map: dict) -> Optional[tuple[str, list[dict]]]:
    if not caption_map:
        return None
    for lang in _PREFERRED_CAPTION_LANGS:
        if caption_map.get(lang):
            return lang, caption_map[lang]
    # Prefer any English variant, then whatever's available, rather than
    # forcing a slow Whisper run.
    for lang, track in caption_map.items():
        if lang.startswith("en") and track:
            return lang, track
    for lang, track in caption_map.items():
        if track and lang != "live_chat":
            return lang, track
    return None


def _download_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_captions(url: str) -> Optional[tuple[list[TranscriptSegment], str]]:
    """Return (segments, language) from YouTube's own captions, or None if unavailable."""
    video_id = extract_video_id(url)

    if transcript_api.is_enabled():
        try:
            result = transcript_api.fetch_transcript(video_id)
            if result["segments"]:
                logger.info("Using TranscriptAPI transcript for %s", video_id)
                return result["segments"], result["language"] or "en"
        except TranscriptAPIError as exc:
            logger.warning("TranscriptAPI transcript failed for %s: %s", video_id, exc)

    try:
        info = _extract_info(video_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Caption lookup failed for %s: %s", video_id, exc)
        return None

    picked = _pick_caption_track(info.get("subtitles") or {})
    is_manual = picked is not None
    if not picked:
        picked = _pick_caption_track(info.get("automatic_captions") or {})
    if not picked:
        return None
    language, track = picked

    segments: list[TranscriptSegment] = []
    for ext, parser in (("json3", _parse_json3), ("vtt", _parse_vtt)):
        entry = next((t for t in track if t.get("ext") == ext and t.get("url")), None)
        if not entry:
            continue
        try:
            segments = parser(_download_text(entry["url"]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load %s captions for %s: %s", ext, video_id, exc)
            continue
        if segments:
            break

    if not segments:
        return None

    logger.info(
        "Using %s %s captions for %s (%d segments)",
        "manual" if is_manual else "auto-generated",
        language,
        video_id,
        len(segments),
    )
    return segments, language.split("-")[0]
