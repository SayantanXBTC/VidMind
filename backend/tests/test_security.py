"""Adversarial tests: try to break the API the way a hostile or careless
client would, and check it fails safely with a clear message."""
import time
from unittest.mock import patch

import jwt
import pytest

from app.core.config import settings
from app.services import youtube_service
from conftest import FAKE_METADATA, ISSUER, auth, make_token

YT = "/api/videos/youtube"


def ingest(client, headers, url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", metadata=FAKE_METADATA):
    with patch.object(youtube_service, "get_metadata", return_value=metadata):
        return client.post(YT, json={"url": url}, headers=headers)


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer " + "A" * 5000},
    ],
)
def test_missing_or_garbage_token_is_rejected(client, headers):
    r = client.get("/api/videos", headers=headers)
    assert r.status_code == 401
    assert "detail" in r.json()


def test_forged_tokens_are_rejected(client):
    base = {"sub": "attacker", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 600}
    forged = [
        jwt.encode(base, "wrong-secret-wrong-secret-wrong-secret", algorithm="HS256"),
        jwt.encode(base, None, algorithm="none") if hasattr(jwt, "encode") else "",
        make_token(exp=int(time.time()) - 10),  # expired
        make_token(aud="anon"),  # wrong audience
        make_token(iss="https://evil.supabase.co/auth/v1"),  # other project
        make_token(sub=""),  # no user id
    ]
    for token in forged:
        r = client.get("/api/videos", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, token


def test_valid_token_works(client):
    r = client.get("/api/me", headers=auth("user-a"))
    assert r.status_code == 200
    assert r.json()["user_id"] == "user-a"


# --------------------------------------------------------------------------
# Users can't reach each other's data
# --------------------------------------------------------------------------

def test_users_are_isolated(client):
    vid = ingest(client, auth("user-a")).json()["id"]
    other = auth("user-b")
    assert client.get("/api/videos", headers=other).json()["total"] == 0
    for method, path, body in [
        ("get", f"/api/videos/{vid}", None),
        ("get", f"/api/videos/{vid}/status", None),
        ("get", f"/api/videos/{vid}/transcript", None),
        ("get", f"/api/videos/{vid}/summary", None),
        ("get", f"/api/videos/{vid}/file", None),
        ("post", f"/api/videos/{vid}/retry", None),
        ("post", f"/api/videos/{vid}/ask", {"question": "hi"}),
        ("post", f"/api/videos/{vid}/search", {"query": "hi"}),
        ("delete", f"/api/videos/{vid}", None),
    ]:
        r = getattr(client, method)(path, headers=other, **({"json": body} if body else {}))
        assert r.status_code == 404, (method, path, r.status_code)
    # Still there for its owner.
    assert client.get(f"/api/videos/{vid}", headers=auth("user-a")).status_code == 200


@pytest.mark.parametrize("video_id", ["does-not-exist", "../../etc/passwd", "' OR '1'='1", "%00", "x" * 2000])
def test_unknown_or_malicious_ids_are_404(client, video_id):
    r = client.get(f"/api/videos/{video_id}", headers=auth())
    assert r.status_code == 404


# --------------------------------------------------------------------------
# YouTube links
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "javascript:alert(1)",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
        "https://evil.com/?u=https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/playlist?list=PL123",
        "https://vimeo.com/123456",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ" + "a" * 3000,
        "' OR 1=1; DROP TABLE videos; --",
        "https://www.youtube.com/watch?v=\u0000\u0000",
    ],
)
def test_bad_youtube_urls_fail_cleanly(client, url):
    r = client.post(YT, json={"url": url}, headers=auth())
    assert r.status_code in (400, 422), (url, r.status_code)
    assert isinstance(r.json()["detail"], str)
    # Nothing was created.
    assert client.get("/api/videos", headers=auth()).json()["total"] == 0


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "  https://www.youtube.com/watch?v=dQw4w9WgXcQ  ",
    ],
)
def test_valid_youtube_url_forms_are_accepted(url):
    assert youtube_service.extract_video_id(url) == "dQw4w9WgXcQ"


def test_video_over_length_limit_is_refused(client):
    too_long = {**FAKE_METADATA, "duration": (settings.MAX_VIDEO_MINUTES + 1) * 60.0}
    r = ingest(client, auth(), metadata=too_long)
    assert r.status_code == 400
    assert "minutes" in r.json()["detail"]


# --------------------------------------------------------------------------
# Quotas and rate limits
# --------------------------------------------------------------------------

def test_daily_quota(client):
    headers = auth("quota-user")
    for _ in range(settings.DAILY_VIDEO_LIMIT):
        assert ingest(client, headers).status_code == 201
    r = ingest(client, headers)
    assert r.status_code == 429
    assert "limit" in r.json()["detail"]
    # Another user is unaffected.
    assert ingest(client, auth("someone-else")).status_code == 201


def test_ip_rate_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 20)
    headers = {**auth("flooder"), "X-Forwarded-For": "203.0.113.7"}
    codes = [client.get("/api/me", headers=headers).status_code for _ in range(30)]
    assert codes[:20] == [200] * 20
    assert set(codes[20:]) == {429}
    r = client.get("/api/me", headers=headers)
    assert r.headers.get("retry-after")
    # A different client IP isn't blocked; health checks never are.
    assert client.get("/api/me", headers={**auth("x"), "X-Forwarded-For": "203.0.113.8"}).status_code == 200
    assert client.get("/api/health", headers=headers).status_code == 200


def test_spoofed_forwarded_for_prefix_does_not_bypass_limit(client, monkeypatch):
    """Clients can prepend fake X-Forwarded-For entries; only the last
    (proxy-added) one counts."""
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 5)
    codes = [
        client.get(
            "/api/me",
            headers={**auth("spoofer"), "X-Forwarded-For": f"10.0.0.{i}, 198.51.100.9"},
        ).status_code
        for i in range(8)
    ]
    assert codes.count(429) == 3


# --------------------------------------------------------------------------
# Request bodies
# --------------------------------------------------------------------------

def test_oversized_json_body_is_rejected(client):
    r = client.post(
        f"/api/videos/x/ask",
        content=b'{"question": "' + b"a" * (settings.MAX_JSON_BODY_BYTES + 10) + b'"}',
        headers={**auth(), "Content-Type": "application/json"},
    )
    assert r.status_code == 413


@pytest.mark.parametrize(
    "body",
    [b"not json", b"{", b"[]", b'{"question": 123}', b'{"question": ""}', b'{"question": "' + b"q" * 501 + b'"}'],
)
def test_malformed_ask_bodies_get_readable_422(client, body):
    vid = ingest(client, auth()).json()["id"]
    r = client.post(
        f"/api/videos/{vid}/ask", content=body, headers={**auth(), "Content-Type": "application/json"}
    )
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


@pytest.mark.parametrize("top_k", [0, -1, 21, "abc", None])
def test_bad_search_params(client, top_k):
    vid = ingest(client, auth()).json()["id"]
    r = client.post(f"/api/videos/{vid}/search", json={"query": "x", "top_k": top_k}, headers=auth())
    assert r.status_code == 422


def test_ask_before_ready_is_409_not_500(client):
    vid = ingest(client, auth()).json()["id"]
    r = client.post(f"/api/videos/{vid}/ask", json={"question": "What happens?"}, headers=auth())
    assert r.status_code == 409


def test_transcript_and_summary_before_ready(client):
    vid = ingest(client, auth()).json()["id"]
    assert client.get(f"/api/videos/{vid}/transcript", headers=auth()).status_code == 409
    assert client.get(f"/api/videos/{vid}/summary", headers=auth()).status_code == 409


# --------------------------------------------------------------------------
# Uploads
# --------------------------------------------------------------------------

def upload(client, name, content, content_type="video/mp4"):
    return client.post(
        "/api/videos/upload", files={"file": (name, content, content_type)}, headers=auth()
    )


def test_text_file_disguised_as_video_is_rejected(client):
    r = upload(client, "movie.mp4", b"this is not a video at all")
    assert r.status_code == 400
    assert "playable video" in r.json()["detail"]


@pytest.mark.parametrize(
    "name,ctype",
    [("virus.exe", "application/octet-stream"), ("page.html", "text/html"), ("clip.mp4", "text/html"), ("noext", "video/mp4")],
)
def test_wrong_file_types_are_rejected(client, name, ctype):
    assert upload(client, name, b"data", ctype).status_code == 400


def test_path_traversal_filename_is_harmless(client, tmp_path):
    r = upload(client, "../../../../etc/passwd.mp4", b"not a video")
    assert r.status_code == 400  # rejected as unplayable, and nothing escaped UPLOAD_DIR
    assert not any(p.name == "passwd.mp4" for p in settings.UPLOAD_DIR.parent.rglob("passwd.mp4"))


def test_uploads_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_UPLOADS", False)
    r = upload(client, "clip.mp4", b"x")
    assert r.status_code == 403


# --------------------------------------------------------------------------
# State transitions
# --------------------------------------------------------------------------

def test_retry_only_failed_videos(client):
    vid = ingest(client, auth()).json()["id"]
    assert client.post(f"/api/videos/{vid}/retry", headers=auth()).status_code == 400


def test_double_delete(client):
    vid = ingest(client, auth()).json()["id"]
    assert client.delete(f"/api/videos/{vid}", headers=auth()).status_code == 204
    assert client.delete(f"/api/videos/{vid}", headers=auth()).status_code == 404


def test_wrong_http_methods(client):
    assert client.put("/api/videos", headers=auth()).status_code == 405
    assert client.patch(f"/api/videos/x", headers=auth()).status_code == 405


# --------------------------------------------------------------------------
# Errors don't leak internals
# --------------------------------------------------------------------------

def test_unexpected_errors_return_generic_500(client):
    from app.api.routes import videos as routes
    from app.models.video import EmbeddingStatus, Video, VideoStatus
    from app.database.session import SessionLocal

    vid = ingest(client, auth()).json()["id"]
    db = SessionLocal()
    v = db.get(Video, vid)
    v.status, v.embedding_status = VideoStatus.COMPLETED, EmbeddingStatus.COMPLETED
    db.commit()
    db.close()

    with patch.object(routes, "search_video", side_effect=RuntimeError("secret path /etc/db password=hunter2")):
        r = client.post(f"/api/videos/{vid}/search", json={"query": "x"}, headers=auth())
    assert r.status_code == 500
    assert "hunter2" not in r.text and "/etc" not in r.text
    assert r.json()["detail"].startswith("Something went wrong")


def test_processing_failure_message_is_friendly():
    from app.services.processing_service import GENERIC_FAILURE, _user_message
    from app.services.transcription_service import TranscriptionError
    from app.services.youtube_service import YouTubeError

    assert _user_message(TranscriptionError("ctranslate2 /opt/x.so segfault")) != "ctranslate2 /opt/x.so segfault"
    assert _user_message(RuntimeError("boom /secret")) == GENERIC_FAILURE
    assert _user_message(YouTubeError("This video is private and can't be analyzed.")).startswith("This video is private")


# --------------------------------------------------------------------------
# HTTPS, headers, CORS, docs
# --------------------------------------------------------------------------

def test_http_is_redirected_to_https(client):
    r = client.get(
        "/api/health",
        headers={"X-Forwarded-Proto": "http", "Host": "api.example.com"},
        follow_redirects=False,
    )
    assert r.status_code == 308
    assert r.headers["location"] == "https://api.example.com/api/health"


def test_security_headers(client):
    r = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    h = r.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "default-src 'none'" in h["content-security-policy"]
    assert h["cache-control"] == "no-store"
    assert "max-age" in h["strict-transport-security"]


def test_no_hsts_over_plain_local_http(client):
    assert "strict-transport-security" not in client.get("/api/health").headers


def test_cors_allows_only_configured_origin(client):
    ok = client.options(
        "/api/videos",
        headers={"Origin": "https://app.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "https://app.example.com"
    bad = client.options(
        "/api/videos",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_rate_limited_response_still_has_cors(client, monkeypatch):
    """Otherwise the browser hides the 429 message behind a CORS error."""
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    headers = {**auth(), "Origin": "https://app.example.com", "X-Forwarded-For": "192.0.2.50"}
    client.get("/api/me", headers=headers)
    r = client.get("/api/me", headers=headers)
    assert r.status_code == 429
    assert r.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_api_docs_hidden_in_public_mode(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_token_is_redacted_from_access_logs():
    import logging

    from app.core.security import RedactTokensFilter

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s"', ("1.2.3.4", "GET", "/api/videos/x/file?access_token=eyJsecret.part"), None
    )
    RedactTokensFilter().filter(record)
    assert "eyJsecret" not in record.getMessage()
