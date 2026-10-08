"""Test setup: temp cache dir, small limits, no external services.

YouTube, TranscriptAPI and the LLM are mocked per test. Settings are read
at import time, so the environment is set before any `app` import.
"""
import os
import tempfile
import time

import pytest

_TMP = tempfile.mkdtemp(prefix="vidmind-tests-")
os.environ.update(
    {
        "CACHE_DIR": _TMP,
        "LLM_PROVIDER": "none",
        "ANTHROPIC_API_KEY": "",
        "TRANSCRIPT_API_KEY": "",
        "ANALYSES_PER_IP_PER_DAY": "3",
        "ANALYSES_PER_DAY_TOTAL": "6",
        "QUESTIONS_PER_IP_PER_HOUR": "4",
        "MAX_VIDEO_MINUTES": "60",
        "RATE_LIMIT_PER_MINUTE": "0",  # enabled only in the rate-limit tests
        "ALLOWED_ORIGINS": "https://app.example.com",
        "FORCE_HTTPS": "true",
        "ENABLE_DOCS": "false",
        "UPLOAD_TMP_DIR": _TMP + "/uploads",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.core import limits  # noqa: E402
from app.main import app  # noqa: E402
from app.services import jobs as jobs_module  # noqa: E402

SEGMENTS = [
    {"start": i * 5.0, "end": i * 5.0 + 5, "text": f"Sentence {i} about rockets, engines and launch pads."}
    for i in range(40)
]

NOTES = {
    "tldr": "A video about rockets.",
    "summary": "Rockets are explained.",
    "key_points": ["Rockets need engines."],
    "chapters": [{"title": "Intro", "start": 0.0, "end": 200.0, "summary": None}],
}


def metadata(video_id="dQw4w9WgXcQ", duration=600.0):
    return {
        "video_id": video_id,
        "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": "Test video",
        "duration": duration,
        "thumbnail": None,
    }


def yt(video_id="dQw4w9WgXcQ") -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def ip(addr: str) -> dict:
    """Pretend the request came from `addr` via the hosting proxy."""
    return {"X-Forwarded-For": addr}


def wait_for(client, video_id, timeout=5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/videos/{video_id}").json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.02)
    raise AssertionError(f"job {video_id} didn't finish")


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fresh_state():
    """Each test starts with an empty cache and fresh limit counters."""
    jobs_module.job_manager._jobs.clear()
    for path in (jobs_module._RESULTS_DIR).glob("*.json"):
        path.unlink()
    limits._analyses = limits._Window()
    limits._questions = limits._Window()
    yield
