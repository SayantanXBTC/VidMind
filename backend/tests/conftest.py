"""Test setup: an isolated SQLite database and temp dirs, sign-in enabled with
a test HS256 secret, and no external services (TranscriptAPI, Claude,
YouTube) — those are mocked per test.

Settings are read at import time, so the environment is set before any
`app` import.
"""
import os
import tempfile
import time

import pytest

_TMP = tempfile.mkdtemp(prefix="vidmind-tests-")
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{_TMP}/test.db",
        "UPLOAD_DIR": f"{_TMP}/uploads",
        "PROCESSED_DIR": f"{_TMP}/processed",
        "SUPABASE_URL": "https://test-project.supabase.co",
        "SUPABASE_JWT_SECRET": "test-secret-that-is-long-enough-for-hs256-signing",
        "LLM_PROVIDER": "none",
        "TRANSCRIPT_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "JOB_MODE": "queue",  # nothing runs in the background during tests
        "DAILY_VIDEO_LIMIT": "3",
        "MAX_ACTIVE_JOBS_PER_USER": "10",
        "MAX_VIDEO_MINUTES": "60",
        "RATE_LIMIT_PER_MINUTE": "0",  # enabled only in the rate-limit test
        "ALLOWED_ORIGINS": "https://app.example.com",
    }
)

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

ISSUER = f"{settings.SUPABASE_URL}/auth/v1"


def make_token(sub="user-a", email="a@example.com", **overrides) -> str:
    claims = {
        "sub": sub,
        "email": email,
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 600,
        **overrides,
    }
    return jwt.encode(claims, settings.SUPABASE_JWT_SECRET, algorithm="HS256")


def auth(sub="user-a") -> dict:
    return {"Authorization": f"Bearer {make_token(sub=sub, email=f'{sub}@example.com')}"}


FAKE_METADATA = {
    "video_id": "dQw4w9WgXcQ",
    "canonical_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "title": "Test video",
    "duration": 600.0,
    "thumbnail": None,
}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    from app.database.session import SessionLocal, init_db
    from app.models.video import Video

    init_db()  # tables may not exist yet if no test has started the app
    db = SessionLocal()
    db.query(Video).delete()
    db.commit()
    db.close()
    yield
