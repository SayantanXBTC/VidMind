import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, videos
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.security import (
    BodySizeLimitMiddleware,
    CatchAllMiddleware,
    HTTPSRedirectMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.services.llm_service import llm_service

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "VidMind backend started. ai=%s transcripts=%s limits: %s new videos/IP/day, %s/day total",
        llm_service.name,
        "transcriptapi" if settings.TRANSCRIPT_API_KEY else "yt-dlp",
        settings.ANALYSES_PER_IP_PER_DAY or "unlimited",
        settings.ANALYSES_PER_DAY_TOTAL or "unlimited",
    )
    yield


app = FastAPI(
    title="VidMind API",
    lifespan=lifespan,
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
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(HTTPSRedirectMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


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


app.include_router(health.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
