"""Video summary, key points and chapters.

summarize() uses the local LLM (see llm_summarizer.py) when Ollama is
available. Otherwise it falls back to the Hugging Face distilbart path below.

The fallback loads the summarization pipeline lazily and caches it for the process
lifetime, matching transcription_service's approach. Chunking is by token
budget (using the model's own tokenizer), not by a hardcoded sentence
count, so it scales to both very short and long transcripts.
"""
import logging
import re
from typing import Optional, TypedDict

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app.core.config import settings
from app.services.llm_service import LLMError, llm_service
from app.services.llm_summarizer import summarize_with_llm

logger = logging.getLogger(__name__)

MAX_CHUNK_TOKENS = 900  # leaves headroom under the model's 1024-token limit

# distilbart-cnn is tuned on news articles (hundreds of words). Below this
# many words it doesn't have enough content to abstract from and a forced
# min_length pushes it into hallucinating text that isn't in the transcript
# (e.g. inventing a sentence like "VidMind.com is happy to..."). Below the
# threshold we return the transcript text itself instead of a model
# summary: it's extractive, so it cannot contain anything the speaker
# didn't actually say.
MIN_WORDS_FOR_MODEL_SUMMARY = 50
MIN_WORDS_FOR_ANY_CONTENT = 1  # below this (i.e. empty), skip the model entirely


class Chapter(TypedDict):
    title: str
    start: float
    end: float


class SummaryResult(TypedDict):
    tldr: Optional[str]
    summary: str
    key_points: list[str]
    chapters: list[Chapter]


class SummarizationError(Exception):
    """Raised when the summarization model fails to load or run."""


class TextChunk(TypedDict):
    text: str
    start: float
    end: float


class SummarizationService:
    def __init__(self) -> None:
        self._tokenizer = None
        self._model = None
        self._device = None

    def _load_model(self):
        """Load tokenizer + seq2seq model directly.

        Uses AutoModelForSeq2SeqLM/AutoTokenizer + model.generate() rather
        than the high-level pipeline("summarization", ...) helper: the
        transformers build in this environment doesn't register a
        "summarization" (or "text2text-generation") pipeline task, so the
        high-level wrapper raises "Unknown task summarization". The
        low-level generate() API is stable across versions and drives the
        exact same model/weights.
        """
        if self._model is not None:
            return self._model
        try:
            logger.info(
                "Loading summarization model=%s device=%s",
                settings.SUMMARY_MODEL,
                settings.SUMMARY_DEVICE,
            )
            self._device = "cuda" if settings.SUMMARY_DEVICE == "cuda" else "cpu"
            self._tokenizer = AutoTokenizer.from_pretrained(settings.SUMMARY_MODEL)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(settings.SUMMARY_MODEL)
            self._model.to(self._device)
            self._model.eval()
            return self._model
        except Exception as exc:  # noqa: BLE001
            raise SummarizationError(f"Failed to load summarization model: {exc}") from exc

    def _token_count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False))

    def _chunk_segments(self, segments: list[dict]) -> list[TextChunk]:
        """Group timestamped segments into chunks within MAX_CHUNK_TOKENS."""
        chunks: list[TextChunk] = []
        current_texts: list[str] = []
        current_tokens = 0
        chunk_start: Optional[float] = None
        chunk_end: Optional[float] = None

        for seg in segments:
            text = seg["text"].strip()
            if not text:
                continue
            seg_tokens = self._token_count(text)

            if current_texts and current_tokens + seg_tokens > MAX_CHUNK_TOKENS:
                chunks.append(
                    {"text": " ".join(current_texts), "start": chunk_start, "end": chunk_end}
                )
                current_texts = []
                current_tokens = 0
                chunk_start = None

            if chunk_start is None:
                chunk_start = seg["start"]
            current_texts.append(text)
            current_tokens += seg_tokens
            chunk_end = seg["end"]

        if current_texts:
            chunks.append({"text": " ".join(current_texts), "start": chunk_start, "end": chunk_end})

        return chunks

    def _summarize_text(
        self, text: str, max_length: int = 120, min_length: int = 25
    ) -> str:
        word_count = len(text.split())
        if word_count < MIN_WORDS_FOR_MODEL_SUMMARY:
            return text.strip()

        token_count = self._token_count(text)
        # Scale the output budget off the input length so we never force the
        # model to keep generating past what the source material supports.
        clamped_max = max(10, min(max_length, int(token_count * 0.6)))
        clamped_min = max(3, min(min_length, int(token_count * 0.2), clamped_max - 1))

        try:
            inputs = self._tokenizer(
                text, return_tensors="pt", truncation=True, max_length=1024
            ).to(self._device)
            with torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    max_length=clamped_max,
                    min_length=clamped_min,
                    num_beams=4,
                    do_sample=False,
                    early_stopping=True,
                    no_repeat_ngram_size=3,
                    length_penalty=2.0,
                )
            return self._tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
        except Exception as exc:  # noqa: BLE001
            raise SummarizationError(f"Summarization failed: {exc}") from exc

    def _make_chapter_title(self, chunk_text: str, chunk_summary: str) -> str:
        """Derive a short title from the chunk's own summary sentence.

        Reuses the summary already generated for this chunk rather than
        making a second model call with a tiny max_length budget: forcing
        the model to stop after ~12 tokens tends to cut a sentence off
        mid-clause instead of producing a clean phrase.
        """
        source = chunk_summary.strip() if chunk_summary and chunk_summary.strip() else chunk_text
        first_sentence = re.split(r"(?<=[.!?])\s+", source.strip())[0]
        words = first_sentence.split()
        title = " ".join(words[:8]) + ("…" if len(words) > 8 else "")
        title = title.strip().rstrip(".")
        return title[:1].upper() + title[1:] if title else "Untitled segment"

    def _extract_key_points(self, chunk_summaries: list[str], final_summary: str) -> list[str]:
        source_texts = chunk_summaries if chunk_summaries else [final_summary]
        candidates: list[str] = []
        for text in source_texts:
            for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
                sentence = sentence.strip()
                if len(sentence) >= 15 and sentence not in candidates:
                    candidates.append(sentence)
        return candidates[:10]

    def summarize(
        self,
        segments: list[dict],
        *,
        title: Optional[str] = None,
        duration: Optional[float] = None,
        on_progress: Optional[callable] = None,
    ) -> SummaryResult:
        """Summarize with the local LLM, falling back to distilbart if it's unavailable."""
        has_text = any(seg["text"].strip() for seg in segments)
        if has_text and llm_service.is_available():
            try:
                return summarize_with_llm(
                    segments, title=title, duration=duration, on_progress=on_progress
                )
            except LLMError as exc:
                logger.warning("LLM summarization failed, falling back to %s: %s", settings.SUMMARY_MODEL, exc)

        def on_chunk(index: int, total: int) -> None:
            if on_progress:
                on_progress((index + 1) / total)

        result = self._summarize_local(segments, on_chunk=on_chunk)
        return {"tldr": None, **result}

    def _summarize_local(
        self, segments: list[dict], on_chunk: Optional[callable] = None
    ) -> dict:
        full_text = " ".join(seg["text"].strip() for seg in segments if seg["text"].strip())

        if len(full_text.split()) < MIN_WORDS_FOR_ANY_CONTENT:
            return {"summary": "No speech content detected in this video.", "key_points": [], "chapters": []}

        self._load_model()
        chunks = self._chunk_segments(segments)

        if not chunks:
            return {"summary": "No speech content detected in this video.", "key_points": [], "chapters": []}

        # Very short transcript: summarize directly, skip chapters (section 11).
        if len(chunks) == 1 and len(chunks[0]["text"].split()) < MIN_WORDS_FOR_MODEL_SUMMARY:
            summary = self._summarize_text(chunks[0]["text"])
            key_points = self._extract_key_points([summary], summary)
            return {"summary": summary, "key_points": key_points, "chapters": []}

        chunk_summaries = []
        for index, chunk in enumerate(chunks):
            chunk_summaries.append(self._summarize_text(chunk["text"]))
            if on_chunk:
                on_chunk(index, len(chunks))

        if len(chunk_summaries) == 1:
            final_summary = chunk_summaries[0]
        else:
            combined = " ".join(chunk_summaries)
            final_summary = self._summarize_text(combined, max_length=180, min_length=40)

        key_points = self._extract_key_points(chunk_summaries, final_summary)

        chapters: list[Chapter] = [
            {
                "title": self._make_chapter_title(chunk["text"], summary_text),
                "start": chunk["start"],
                "end": chunk["end"],
            }
            for chunk, summary_text in zip(chunks, chunk_summaries)
        ]

        return {"summary": final_summary, "key_points": key_points, "chapters": chapters}


summarization_service = SummarizationService()
