# Must run before any ML import — see app/core/native_threads.py.
import app.core.native_threads  # noqa: F401,I001

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import account, health, videos
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.security import (
    BodySizeLimitMiddleware,
    CatchAllMiddleware,
    HTTPSRedirectMiddleware,
    RateLimitMiddleware,
    RedactTokensFilter,
    SecurityHeadersMiddleware,
)
from app.database.session import SessionLocal, init_db
from app.models.video import Video, VideoStatus

configure_logging()
logging.getLogger("uvicorn.access").addFilter(RedactTokensFilter())
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VidMind API",
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

# Middleware runs outermost-last-added. Order, outside in: HTTPS redirect,
# security headers, CORS (so even 413/429/500 responses carry CORS headers
# and the browser shows their message), rate limit, body size limit, then a
# catch-all that turns unexpected exceptions into a generic 500.
app.add_middleware(CatchAllMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    # Auth uses a bearer token, not cookies, so credentials aren't needed.
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(HTTPSRedirectMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return one readable sentence instead of Pydantic's error list."""
    errors = exc.errors()
    message = "Invalid request."
    if errors:
        first = errors[0]
        field = ".".join(str(part) for part in first.get("loc", ())[1:]) or "request"
        message = f"Invalid {field}: {first.get('msg', 'invalid value')}"
    return JSONResponse(status_code=422, content={"detail": message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _fail_interrupted_jobs() -> None:
    """Background jobs live in this process, so any video still marked
    processing at startup was interrupted by a restart. Mark it failed so the
    UI offers Retry instead of polling forever."""
    db = SessionLocal()
    try:
        stuck = db.query(Video).filter(Video.status.in_([VideoStatus.PROCESSING, VideoStatus.UPLOADED])).all()
        for video in stuck:
            video.status = VideoStatus.FAILED
            video.error_message = "Processing was interrupted by a server restart. Retry to run it again."
        if stuck:
            db.commit()
            logger.warning("Marked %d interrupted video(s) as failed", len(stuck))
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    if settings.JOB_MODE == "inline":
        # Queue mode leaves recovery to the worker (app/worker.py).
        _fail_interrupted_jobs()
    logger.info(
        "VidMind backend started. auth=%s jobs=%s uploads=%s",
        "supabase" if settings.AUTH_ENABLED else "off (local)",
        settings.JOB_MODE,
        settings.ENABLE_UPLOADS,
    )


app.include_router(health.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(account.router, prefix="/api")
