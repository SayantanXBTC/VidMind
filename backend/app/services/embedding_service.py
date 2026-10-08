"""Sentence embeddings + FAISS indexing for semantic search / Ask the Video.

Loads the sentence-transformer lazily and caches it for the process
lifetime. One FAISS index + metadata.json per video, persisted under
processed/embeddings/<video_id>/, so search/QA requests never re-embed the
transcript — only the query gets embedded per request.
"""
import json
import logging
import uuid
from pathlib import Path
from typing import Optional, TypedDict

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings

logger = logging.getLogger(__name__)

# Embedding chunks are smaller/more granular than summarization chunks: fine
# enough for precise retrieval, coarse enough to avoid hundreds of near-
# duplicate vectors for a short video.
CHUNK_TARGET_WORDS = 70
CHUNK_MAX_DURATION = 45.0


class TranscriptChunk(TypedDict):
    id: str
    start: float
    end: float
    text: str


class EmbeddingError(Exception):
    """Raised when embedding generation, index build, or index load fails."""


class EmbeddingService:
    def __init__(self) -> None:
        self._model: Optional[SentenceTransformer] = None
        self._index_cache: dict[str, tuple["faiss.Index", list[TranscriptChunk]]] = {}

    def _load_model(self) -> SentenceTransformer:
        if self._model is not None:
            return self._model
        try:
            logger.info("Loading embedding model=%s", settings.EMBEDDING_MODEL)
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            return self._model
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"Failed to load embedding model: {exc}") from exc

    def chunk_segments(self, segments: list[dict]) -> list[TranscriptChunk]:
        """Group nearby Whisper segments into retrieval-sized chunks."""
        chunks: list[TranscriptChunk] = []
        current_texts: list[str] = []
        current_words = 0
        chunk_start: Optional[float] = None
        chunk_end: Optional[float] = None

        for seg in segments:
            text = seg["text"].strip()
            if not text:
                continue
            seg_words = len(text.split())
            duration_if_added = (seg["end"] - chunk_start) if chunk_start is not None else 0

            if current_texts and (
                current_words + seg_words > CHUNK_TARGET_WORDS
                or duration_if_added > CHUNK_MAX_DURATION
            ):
                chunks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "start": chunk_start,
                        "end": chunk_end,
                        "text": " ".join(current_texts),
                    }
                )
                current_texts = []
                current_words = 0
                chunk_start = None

            if chunk_start is None:
                chunk_start = seg["start"]
            current_texts.append(text)
            current_words += seg_words
            chunk_end = seg["end"]

        if current_texts:
            chunks.append(
                {
                    "id": str(uuid.uuid4()),
                    "start": chunk_start,
                    "end": chunk_end,
                    "text": " ".join(current_texts),
                }
            )

        return chunks

    def _embed(self, texts: list[str]) -> np.ndarray:
        model = self._load_model()
        try:
            vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return vectors.astype(np.float32)
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"Failed to generate embeddings: {exc}") from exc

    def _index_dir(self, video_id: str) -> Path:
        return settings.EMBEDDINGS_DIR / video_id

    def build_index(self, video_id: str, segments: list[dict]) -> int:
        """Chunk, embed, and persist a FAISS index for one video. Returns chunk count."""
        chunks = self.chunk_segments(segments)
        if not chunks:
            raise EmbeddingError("No transcript content available to index")

        vectors = self._embed([c["text"] for c in chunks])

        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)

        index_dir = self._index_dir(video_id)
        index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(index_dir / "index.faiss"))

        with open(index_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump({"chunks": chunks}, f, ensure_ascii=False, indent=2)

        self.invalidate_cache(video_id)
        return len(chunks)

    def load_index(self, video_id: str) -> tuple["faiss.Index", list[TranscriptChunk]]:
        if video_id in self._index_cache:
            return self._index_cache[video_id]

        index_dir = self._index_dir(video_id)
        index_path = index_dir / "index.faiss"
        metadata_path = index_dir / "metadata.json"

        if not index_path.exists() or not metadata_path.exists():
            raise EmbeddingError("Embedding index not found for this video")

        try:
            index = faiss.read_index(str(index_path))
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            chunks = metadata["chunks"]
            self._index_cache[video_id] = (index, chunks)
            return index, chunks
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"Embedding index is corrupted: {exc}") from exc

    def invalidate_cache(self, video_id: str) -> None:
        self._index_cache.pop(video_id, None)

    def embed_query(self, query: str) -> np.ndarray:
        return self._embed([query])


embedding_service = EmbeddingService()
