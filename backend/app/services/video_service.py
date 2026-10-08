"""Video processing service: validation, duration probing, audio extraction.

ML inference (Whisper transcription, summarization, embeddings) is added in
later work on top of this service, so keep those seams (extract_audio /
get_duration) stable and free of API/route concerns.
"""
import logging
import re
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _last_ffmpeg_error_line(stderr: str) -> str:
    """Return ffmpeg's last non-empty stderr line, stripped of local file paths."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    last_line = lines[-1] if lines else "unknown ffmpeg error"
    return re.sub(r"/[^\s]+", "<file>", last_line)


class VideoProcessingError(Exception):
    """Raised when video validation or processing fails."""


class VideoService:
    def validate_file_exists(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            raise VideoProcessingError(f"Video file not found: {file_path}")

    def get_duration(self, file_path: Path) -> Optional[float]:
        """Return duration in seconds via ffprobe, or None if it can't be read."""
        self.validate_file_exists(file_path)
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            return round(float(result.stdout.strip()), 2)
        except (subprocess.SubprocessError, ValueError, FileNotFoundError) as exc:
            logger.warning("ffprobe failed for %s: %s", file_path, exc)
            return None

    def extract_audio(self, file_path: Path) -> Path:
        """Extract mono 16kHz WAV audio into PROCESSED_DIR for downstream ASR."""
        self.validate_file_exists(file_path)
        output_path = settings.PROCESSED_DIR / f"{uuid.uuid4().hex}.wav"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(file_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=600,
                check=True,
            )
            return output_path
        except subprocess.CalledProcessError as exc:
            logger.error("ffmpeg audio extraction failed for %s: %s", file_path, exc.stderr)
            raise VideoProcessingError(
                f"Audio extraction failed: {_last_ffmpeg_error_line(exc.stderr)}"
            ) from exc
        except subprocess.SubprocessError as exc:
            logger.error("ffmpeg audio extraction failed for %s: %s", file_path, exc)
            raise VideoProcessingError("Audio extraction failed: ffmpeg error") from exc

    def cleanup_file(self, file_path: Path) -> None:
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove temp file %s: %s", file_path, exc)


video_service = VideoService()
