"""Semantic search over a video's transcript using its saved FAISS index.

Only the query gets embedded per request — the index and chunk embeddings
are built once (embedding_service.build_index) during processing and reused
here via embedding_service's in-memory index cache.
"""
from typing import TypedDict

from app.core.config import settings
from app.services.embedding_service import EmbeddingError, embedding_service


class SearchResult(TypedDict):
    text: str
    start: float
    end: float
    score: float


def search_video(
    video_id: str, query: str, top_k: int = 5, threshold: float | None = None
) -> list[SearchResult]:
    """Return up to top_k transcript chunks relevant to query, above threshold."""
    if not query or not query.strip():
        return []

    min_score = settings.SEARCH_SIMILARITY_THRESHOLD if threshold is None else threshold

    index, chunks = embedding_service.load_index(video_id)
    query_vector = embedding_service.embed_query(query.strip())

    k = min(top_k, len(chunks))
    if k <= 0:
        return []

    scores, indices = index.search(query_vector, k)

    results: list[SearchResult] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        score = float(score)
        if score < min_score:
            continue
        chunk = chunks[idx]
        results.append(
            {"text": chunk["text"], "start": chunk["start"], "end": chunk["end"], "score": score}
        )

    return results


__all__ = ["search_video", "SearchResult", "EmbeddingError"]
