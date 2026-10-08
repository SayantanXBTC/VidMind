"""Speech-to-text for uploaded video files.

FFmpeg pulls a 16 kHz mono WAV out of the upload, and faster-whisper (a CPU
build of Whisper) transcribes it on this server — no extra service or
per-minute fees. The model loads once, on first use. Transcriptions run one
or two at a time (TRANSCRIBE_CONCURRENCY) because each one keeps several
CPU cores busy.
"""
import json
import logging
import subprocess
import threading
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT_SECONDS = 600


class TranscriptionError(Exception):
    """Raised with a message that's safe to show to the visitor."""


class _Whisper:
    def __init__(self) -> None:
        self._model = None
        self._load_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max(1, settings.TRANSCRIBE_CONCURRENCY))

    def _get_model(self):
        with self._load_lock:
            if self._model is None:
                from faster_whisper import WhisperModel  # heavy import, only when uploads are used

                logger.info("Loading Whisper model %s", settings.WHISPER_MODEL)
                self._model = WhisperModel(
                    settings.WHISPER_MODEL,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=settings.WHISPER_THREADS,
                )
            return self._model

    def transcribe(self, wav_path: Path, duration: float, on_progress: Optional[Callable[[float], None]] = None):
        """Return (segments, language). on_progress(fraction) as audio is processed."""
        audio = _read_wav(wav_path)
        with self._slots:
            model = self._get_model()
            try:
                segments_iter, info = model.transcribe(
                    audio,
                    beam_size=1,  # greedy: several times faster, nearly as accurate
                    vad_filter=True,  # skip silence and music
                    condition_on_previous_text=False,
                )
                segments = []
                for seg in segments_iter:
                    text = seg.text.strip()
                    if text:
                        segments.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": text})
                    if on_progress and duration:
                        on_progress(min(seg.end / duration, 1.0))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Whisper failed on %s", wav_path.name)
                raise TranscriptionError("The audio couldn't be transcribed. Try a different file.") from exc
        return segments, info.language


whisper = _Whisper()


def probe(path: Path) -> dict:
    """Duration and whether the file has an audio track, via ffprobe.

    Raises TranscriptionError when the file isn't a readable video/audio file.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        data = json.loads(out.stdout)
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        raise TranscriptionError("This file isn't a playable video.") from exc

    streams = {s.get("codec_type") for s in data.get("streams", [])}
    try:
        duration = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        duration = 0.0
    if not duration:
        raise TranscriptionError("This file isn't a playable video.")
    if "audio" not in streams:
        raise TranscriptionError("This video has no sound, so there's nothing to summarize.")
    return {"duration": duration}


def extract_audio(video_path: Path) -> Path:
    """16 kHz mono 16-bit WAV next to the upload. Caller deletes it."""
    wav_path = video_path.with_suffix(".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video_path),
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path)],
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        wav_path.unlink(missing_ok=True)
        raise TranscriptionError("The audio couldn't be read from this file.") from exc
    return wav_path


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
