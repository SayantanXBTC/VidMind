"""The processing pipeline must always end in "completed" or "failed" with a
readable message — never stuck in "processing", never a raw stack trace."""
from unittest.mock import patch

from app.database.session import SessionLocal
from app.models.video import SourceType, Video, VideoStatus
from app.services import processing_service as ps
from app.services import summarization_service as ss
from app.services import youtube_service
from app.services.llm_service import LLMError
from app.services.youtube_service import YouTubeError


def make_youtube_video(user_id="pipeline-user") -> str:
    db = SessionLocal()
    v = Video(
        user_id=user_id,
        original_filename="Test",
        stored_filename=f"yt-{id(object())}",
        file_path="",
        file_size=0,
        duration=120.0,
        status=VideoStatus.PROCESSING,
        source_type=SourceType.YOUTUBE,
        source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        youtube_video_id="dQw4w9WgXcQ",
    )
    db.add(v)
    db.commit()
    vid = v.id
    db.close()
    return vid


def load(vid) -> Video:
    db = SessionLocal()
    v = db.get(Video, vid)
    db.close()
    return v


SEGMENTS = [
    {"start": i * 5.0, "end": i * 5.0 + 5, "text": f"Sentence number {i} about rockets and engines."}
    for i in range(30)
]


def test_no_captions_and_no_audio_fails_with_clear_message():
    vid = make_youtube_video()
    with patch.object(youtube_service, "fetch_captions", return_value=None), patch.object(
        youtube_service, "download_audio", side_effect=YouTubeError("VidMind couldn't retrieve audio for this video.")
    ):
        ps.processing_service.process_youtube_video(vid)
    v = load(vid)
    assert v.status == VideoStatus.FAILED
    assert v.error_message == "VidMind couldn't retrieve audio for this video."


def test_unexpected_crash_marks_failed_with_generic_message():
    vid = make_youtube_video()
    with patch.object(youtube_service, "fetch_captions", side_effect=MemoryError("/opt/secret/path")):
        ps.processing_service.process_youtube_video(vid)
    v = load(vid)
    assert v.status == VideoStatus.FAILED
    assert "/opt/secret" not in v.error_message
    assert v.error_message == ps.GENERIC_FAILURE


def test_llm_outage_falls_back_to_local_summary():
    vid = make_youtube_video()
    local = {"summary": "Local fallback summary.", "key_points": ["A point."], "chapters": []}
    fake_llm = type("FakeLLM", (), {"is_available": lambda self: True})()
    with patch.object(youtube_service, "fetch_captions", return_value=(SEGMENTS, "en")), patch.object(
        ss, "llm_service", fake_llm
    ), patch.object(ss, "summarize_with_llm", side_effect=LLMError("Anthropic API error 529: overloaded")), patch.object(
        ss.SummarizationService, "_summarize_local", return_value=local
    ):
        ps.processing_service.process_youtube_video(vid)
    v = load(vid)
    assert v.status == VideoStatus.COMPLETED
    assert v.summary == "Local fallback summary."


def test_silent_video_completes_without_crashing():
    vid = make_youtube_video()
    with patch.object(youtube_service, "fetch_captions", return_value=([{"start": 0, "end": 1, "text": "   "}], "en")):
        ps.processing_service.process_youtube_video(vid)
    v = load(vid)
    assert v.status == VideoStatus.COMPLETED
    assert "No speech" in v.summary


def test_video_deleted_mid_processing_does_not_crash():
    vid = make_youtube_video()

    def delete_then_return(*_args, **_kwargs):
        db = SessionLocal()
        db.delete(db.get(Video, vid))
        db.commit()
        db.close()
        return SEGMENTS, "en"

    with patch.object(youtube_service, "fetch_captions", side_effect=delete_then_return):
        ps.processing_service.process_youtube_video(vid)  # must not raise
    assert load(vid) is None


def test_llm_output_is_cleaned_and_bounded():
    """Whatever the model returns, chapters stay ordered, inside the video and
    reasonably spaced, and lists are capped."""
    from app.services import llm_summarizer as ls

    raw = {
        "tldr": "  A   test. ",
        "summary": "One.\n\nTwo.",
        "key_points": ["- first point here", "first point here", "x", *[f"Point {i} is long enough" for i in range(20)]],
        "chapters": [
            {"start": "99:99:99", "title": "Way past the end", "summary": "x"},
            {"start": "00:30", "title": "Second", "summary": "x"},
            {"start": "00:00", "title": "First", "summary": "x"},
            {"start": "00:35", "title": "Too close", "summary": "x"},
            {"start": "garbage", "title": "No time", "summary": "x"},
            {"start": "01:00", "title": "", "summary": "x"},
        ],
    }
    with patch.object(ls, "llm_service") as fake, patch.object(ls, "_complete_chapters", side_effect=lambda c, *a: c):
        fake.single_pass_max_words = 10_000
        fake.chat_json.return_value = raw
        out = ls.summarize_with_llm(SEGMENTS, title="T", duration=150)
    assert out["tldr"] == "A test."
    assert [c["title"] for c in out["chapters"]] == ["First", "Second"]
    assert all(0 <= c["start"] <= 150 for c in out["chapters"])
    assert out["chapters"][-1]["end"] == 150
    assert len(out["key_points"]) <= 10
    assert out["key_points"][0] == "First point here"
