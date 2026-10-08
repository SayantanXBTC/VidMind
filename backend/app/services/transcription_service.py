"""Whisper-based transcription service.

Loads faster-whisper lazily and caches the model instance for the process
lifetime so repeated transcriptions don't reload weights from disk.
"""
import json
import logging
import uuid
import wave
from pathlib import Path
from typing import Optional, TypedDict

import numpy as np
from faster_whisper import WhisperModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when the Whisper model fails to load or transcribe."""


class Segment(TypedDict):
    start: float
    end: float
    text: str


class TranscriptionResult(TypedDict):
    language: str
    duration: float
    segments: list[Segment]


class WhisperTranscriptionService:
    def __init__(self) -> None:
        self._model: Optional[WhisperModel] = None

    def _load_model(self) -> WhisperModel:
        if self._model is not None:
            return self._model
        try:
            logger.info(
                "Loading Whisper model=%s device=%s compute_type=%s cpu_threads=%d",
                settings.WHISPER_MODEL,
                settings.WHISPER_DEVICE,
                settings.WHISPER_COMPUTE_TYPE,
                settings.WHISPER_CPU_THREADS,
            )
            self._model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
                cpu_threads=settings.WHISPER_CPU_THREADS,
            )
            return self._model
        except Exception as exc:  # noqa: BLE001 - surface as a clean domain error
            raise TranscriptionError(f"Failed to load Whisper model: {exc}") from exc

    def _load_wav_as_float32(self, audio_path: Path) -> np.ndarray:
        """Read a 16-bit PCM mono WAV into a float32 array in [-1, 1].

        video_service.extract_audio() always produces mono 16-bit PCM WAV, so
        we decode it ourselves here instead of routing through faster-whisper's
        PyAV-based decode_audio(), which is incompatible with the PyAV build
        available for this Python version.
        """
        try:
            with wave.open(str(audio_path), "rb") as wav_file:
                if wav_file.getsampwidth() != 2:
                    raise TranscriptionError("Expected 16-bit PCM audio from ffmpeg extraction")
                frames = wav_file.readframes(wav_file.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                if wav_file.getnchannels() > 1:
                    audio = audio.reshape(-1, wav_file.getnchannels()).mean(axis=1)
                return audio
        except wave.Error as exc:
            raise TranscriptionError(f"Unsupported or corrupt audio file: {exc}") from exc

    def transcribe(
        self, audio_path: Path, on_segment: Optional[callable] = None
    ) -> TranscriptionResult:
        """Transcribe audio_path, optionally calling on_segment(index, segment) as segments arrive."""
        model = self._load_model()
        audio = self._load_wav_as_float32(audio_path)
        try:
            # Greedy decoding (beam_size=1) is several times faster than beam
            # search with little accuracy loss; VAD skips silence and music.
            segments_iter, info = model.transcribe(
                audio,
                beam_size=settings.WHISPER_BEAM_SIZE,
                vad_filter=True,
                condition_on_previous_text=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"Whisper transcription failed: {exc}") from exc

        segments: list[Segment] = []
        try:
            for index, segment in enumerate(segments_iter):
                item: Segment = {
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": segment.text.strip(),
                }
                segments.append(item)
                if on_segment:
                    on_segment(index, item)
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"Whisper transcription failed: {exc}") from exc

        return {
            "language": info.language,
            "duration": round(info.duration, 2),
            "segments": segments,
        }

    def save_transcript(self, video_id: str, result: TranscriptionResult) -> Path:
        transcript_path = settings.PROCESSED_DIR / f"{video_id}_{uuid.uuid4().hex[:8]}.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return transcript_path

    def load_transcript(self, transcript_path: Path) -> TranscriptionResult:
        with open(transcript_path, "r", encoding="utf-8") as f:
            return json.load(f)


transcription_service = WhisperTranscriptionService()
