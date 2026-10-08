"""HTTP-level protections: HTTPS enforcement, security headers, per-IP rate
limiting and request-body size limits.

Written as pure ASGI middleware so they also cover streaming request bodies
(Starlette's BaseHTTPMiddleware would buffer them).
"""
import json
import logging
import re
import time
from collections import defaultdict, deque
from threading import Lock

from app.core.config import settings

logger = logging.getLogger(__name__)

_UPLOAD_PATH = "/api/videos/upload"
_EXEMPT_FROM_RATE_LIMIT = {"/api/health"}

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cross-origin-resource-policy", b"cross-origin"),
]
_API_CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
_HSTS = (b"strict-transport-security", b"max-age=63072000; includeSubDomains")


def _header(scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return ""


def _is_https(scope) -> bool:
    proto = _header(scope, b"x-forwarded-proto").split(",")[0].strip().lower()
    return proto == "https" or scope.get("scheme") == "https"


def client_ip(scope) -> str:
    """The caller's IP. Behind Railway/Vercel the proxy appends the real
    client address as the last X-Forwarded-For entry; earlier entries can be
    set by the client, so they aren't trusted."""
    forwarded = _header(scope, b"x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _send_json(send, status: int, detail: str, extra_headers=()) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *extra_headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class HTTPSRedirectMiddleware:
    """Redirect requests the proxy reports as plain HTTP to HTTPS.

    Only acts when X-Forwarded-Proto says "http", so local development and
    the platform's internal health checks (no header) are unaffected.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and settings.FORCE_HTTPS:
            proto = _header(scope, b"x-forwarded-proto").split(",")[0].strip().lower()
            host = _header(scope, b"host")
            if proto == "http" and host:
                query = scope.get("query_string", b"").decode("latin-1")
                location = f"https://{host}{scope['path']}" + (f"?{query}" if query else "")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 308,
                        "headers": [(b"location", location.encode("latin-1")), (b"content-length", b"0")],
                    }
                )
                await send({"type": "http.response.body", "body": b""})
                return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_docs = scope["path"] in ("/docs", "/redoc", "/openapi.json") or scope["path"].startswith("/docs/")
        add_hsts = settings.FORCE_HTTPS and _is_https(scope)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}
                extra = list(_SECURITY_HEADERS)
                if not is_docs:
                    extra.append(_API_CSP)
                    # Responses carry private, per-user data.
                    extra.append((b"cache-control", b"no-store"))
                if add_hsts:
                    extra.append(_HSTS)
                headers.extend((k, v) for k, v in extra if k not in existing)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Reject oversized JSON bodies early, including chunked ones without a
    Content-Length. The upload route enforces its own (much larger) limit."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == _UPLOAD_PATH:
            await self.app(scope, receive, send)
            return

        limit = settings.MAX_JSON_BODY_BYTES
        declared = _header(scope, b"content-length")
        if declared.isdigit() and int(declared) > limit:
            await _send_json(send, 413, "Request body is too large.")
            return

        # Non-upload bodies are small JSON, so buffer them (up to the limit)
        # and replay them to the app.
        chunks: list[bytes] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            received += len(body)
            if received > limit:
                await _send_json(send, 413, "Request body is too large.")
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)


class RateLimitMiddleware:
    """Sliding-window limit of RATE_LIMIT_PER_MINUTE requests per client IP.

    In-memory, so it's per process — fine for one API instance. Per-user
    quotas (app/core/limits.py) are the main cost control; this one stops
    floods and scripted abuse before they reach the database.
    """

    def __init__(self, app):
        self.app = app
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()
        self._last_sweep = time.monotonic()

    def _allow(self, key: str, limit: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            if now - self._last_sweep > 300:
                # Drop idle clients so memory doesn't grow without bound.
                for k in [k for k, q in self._hits.items() if not q or now - q[-1] > 60]:
                    del self._hits[k]
                self._last_sweep = now
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= limit:
                return False, int(60 - (now - hits[0])) + 1
            hits.append(now)
            return True, 0

    async def __call__(self, scope, receive, send):
        limit = settings.RATE_LIMIT_PER_MINUTE
        if scope["type"] != "http" or not limit or scope["path"] in _EXEMPT_FROM_RATE_LIMIT or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        allowed, retry_after = self._allow(client_ip(scope), limit)
        if not allowed:
            await _send_json(
                send,
                429,
                "Too many requests. Slow down and try again in a minute.",
                extra_headers=[(b"retry-after", str(retry_after).encode())],
            )
            return
        await self.app(scope, receive, send)


class CatchAllMiddleware:
    """Innermost safety net: turn unexpected exceptions into a generic 500
    *inside* the CORS and security-header layers (Starlette's own handler sits
    outside them, so the browser would only see a CORS error). Details go to
    the log, never to the client."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:  # noqa: BLE001
            logger.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if not started:
                await _send_json(send, 500, "Something went wrong on our side. Try again in a moment.")


_TOKEN_IN_URL = re.compile(r"(access_token=)[^&\s\"]+")


class RedactTokensFilter(logging.Filter):
    """Keep sign-in tokens (passed in the URL for <video src> requests) out of logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(
                _TOKEN_IN_URL.sub(r"\1[redacted]", a) if isinstance(a, str) else a for a in record.args
            )
        if isinstance(record.msg, str):
            record.msg = _TOKEN_IN_URL.sub(r"\1[redacted]", record.msg)
        return True
