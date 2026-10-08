"""Application configuration loaded from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Real environment variables win over backend/.env.
load_dotenv(BASE_DIR / ".env")


def _parse_origins(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return raw in ("1", "true", "yes") if raw else default


class Settings:
    ALLOWED_ORIGINS: list[str] = _parse_origins(
        os.getenv(
            "ALLOWED_ORIGINS",
            # 5173 = npm run dev, 4173 = npm run preview
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
        )
    )
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # --- AI ---
    # "anthropic" (Claude API), "ollama" (local model), "none", or "auto"
    # (Claude when ANTHROPIC_API_KEY is set, otherwise Ollama).
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto").lower()
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    # low | medium | high | xhigh | max. Summaries don't need deep reasoning,
    # and lower effort is faster and cheaper.
    ANTHROPIC_EFFORT: str = os.getenv("ANTHROPIC_EFFORT", "low")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "600"))
    # Ollama: transcripts up to this many words go in one call; longer ones are
    # summarized in parts. (Claude's context fits any allowed video.)
    LLM_SINGLE_PASS_MAX_WORDS: int = int(os.getenv("LLM_SINGLE_PASS_MAX_WORDS", "7500"))

    # --- YouTube transcripts ---
    # TranscriptAPI.com key: transcripts without this server contacting
    # YouTube (needed when deployed). Empty = use yt-dlp directly.
    TRANSCRIPT_API_KEY: str = os.getenv("TRANSCRIPT_API_KEY", "").strip()
    TRANSCRIPT_API_URL: str = os.getenv("TRANSCRIPT_API_URL", "https://transcriptapi.com/api/v2").rstrip("/")
    # yt-dlp fallback only: reuse a browser's YouTube sign-in when YouTube
    # demands "confirm you're not a bot". A cookies.txt file wins over a browser.
    YTDLP_COOKIES_FILE: str = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    YTDLP_COOKIES_FROM_BROWSER: str = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()

    # --- Cache ---
    # Finished analyses are kept per YouTube video, so a video anyone already
    # analyzed is served again for free. In memory, mirrored to this folder
    # (survives restarts if it's on a persistent disk; fine if it isn't).
    CACHE_DIR: Path = Path(os.getenv("CACHE_DIR", str(BASE_DIR / "cache")))
    CACHE_MAX_ITEMS: int = int(os.getenv("CACHE_MAX_ITEMS", "2000"))
    WORKER_THREADS: int = int(os.getenv("WORKER_THREADS", "4"))

    # --- Cost and abuse limits (0 = unlimited) ---
    # New analyses per visitor IP per 24 h. Cached videos don't count.
    ANALYSES_PER_IP_PER_DAY: int = int(os.getenv("ANALYSES_PER_IP_PER_DAY", "5"))
    # New analyses for the whole site per 24 h: caps the daily API bill.
    ANALYSES_PER_DAY_TOTAL: int = int(os.getenv("ANALYSES_PER_DAY_TOTAL", "200"))
    QUESTIONS_PER_IP_PER_HOUR: int = int(os.getenv("QUESTIONS_PER_IP_PER_HOUR", "30"))
    MAX_VIDEO_MINUTES: int = int(os.getenv("MAX_VIDEO_MINUTES", "180"))
    # Requests per minute from one IP, across the whole API.
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    MAX_JSON_BODY_BYTES: int = int(os.getenv("MAX_JSON_BODY_BYTES", str(16 * 1024)))

    # --- Transport security ---
    # Redirect plain-HTTP requests (as reported by the hosting proxy) to HTTPS
    # and send HSTS. Has no effect locally, where there's no proxy header.
    FORCE_HTTPS: bool = _bool_env("FORCE_HTTPS", True)
    # Interactive API docs at /docs.
    ENABLE_DOCS: bool = _bool_env("ENABLE_DOCS", False)


settings = Settings()
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
