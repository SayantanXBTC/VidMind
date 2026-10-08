"""Application configuration loaded from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Real environment variables win over backend/.env.
load_dotenv(BASE_DIR / ".env")


def _parse_origins(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _parse_extensions(raw: str) -> set[str]:
    return {ext.strip().lower() for ext in raw.split(",") if ext.strip()}


# A deployment counts as "public" when sign-in is configured.
_PUBLIC = bool(os.getenv("SUPABASE_URL", "").strip())


def _int_env(name: str, *, public: int, local: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else (public if _PUBLIC else local)


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return raw in ("1", "true", "yes") if raw else default


class Settings:
    APP_NAME: str = "vidmind-backend"

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'vidmind.db'}"
    )

    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
    PROCESSED_DIR: Path = Path(os.getenv("PROCESSED_DIR", str(BASE_DIR / "processed")))

    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))
    MAX_UPLOAD_SIZE_BYTES: int = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    ALLOWED_VIDEO_EXTENSIONS: set[str] = _parse_extensions(
        os.getenv("ALLOWED_VIDEO_EXTENSIONS", ".mp4,.mov,.avi,.mkv,.webm")
    )

    ALLOWED_VIDEO_MIME_TYPES: set[str] = {
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/x-matroska",
        "video/webm",
    }

    ALLOWED_ORIGINS: list[str] = _parse_origins(
        os.getenv(
            "ALLOWED_ORIGINS",
            # 5173 = npm run dev, 4173 = npm run preview
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
        )
    )

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    # ctranslate2 keeps its own thread pool, so it can use several cores even
    # though OMP_NUM_THREADS is pinned to 1 in main.py for torch/faiss.
    WHISPER_CPU_THREADS: int = int(
        os.getenv("WHISPER_CPU_THREADS", str(max(1, min(8, (os.cpu_count() or 2) - 2))))
    )
    WHISPER_BEAM_SIZE: int = int(os.getenv("WHISPER_BEAM_SIZE", "1"))

    # LLM for summaries, chapters and Ask the Video: "anthropic" (Claude API),
    # "ollama" (local), "none" (small Hugging Face models only), or "auto"
    # (Claude when ANTHROPIC_API_KEY is set, otherwise Ollama).
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto").lower()
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
    # low | medium | high | xhigh | max. Summaries don't need deep reasoning,
    # and lower effort is faster and cheaper.
    ANTHROPIC_EFFORT: str = os.getenv("ANTHROPIC_EFFORT", "low")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "600"))
    # Transcripts up to this many words go to the LLM in one call; longer ones
    # are summarized in parts and then merged.
    LLM_SINGLE_PASS_MAX_WORDS: int = int(os.getenv("LLM_SINGLE_PASS_MAX_WORDS", "7500"))

    SUMMARY_MODEL: str = os.getenv("SUMMARY_MODEL", "sshleifer/distilbart-cnn-12-6")
    SUMMARY_DEVICE: str = os.getenv("SUMMARY_DEVICE", "cpu")

    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    QA_MODEL: str = os.getenv("QA_MODEL", "distilbert-base-cased-distilled-squad")
    SEARCH_SIMILARITY_THRESHOLD: float = float(os.getenv("SEARCH_SIMILARITY_THRESHOLD", "0.3"))
    # Stricter than SEARCH_SIMILARITY_THRESHOLD on purpose: a weak search match
    # is fine to show for browsing, but the extractive QA model (SQuAD-1.1
    # trained, so it always extracts *some* span with no real "unanswerable"
    # detection) will confidently answer from irrelevant context if given the
    # chance. Gating on a higher retrieval score is what actually keeps
    # off-topic questions from getting a fabricated-sounding answer.
    QA_SIMILARITY_THRESHOLD: float = float(os.getenv("QA_SIMILARITY_THRESHOLD", "0.45"))
    # The LLM can decide for itself that retrieved context doesn't answer the
    # question, so it gets a wider retrieval net than the extractive fallback.
    QA_LLM_SIMILARITY_THRESHOLD: float = float(os.getenv("QA_LLM_SIMILARITY_THRESHOLD", "0.2"))
    EMBEDDINGS_DIR: Path = Path(
        os.getenv("EMBEDDINGS_DIR", str(PROCESSED_DIR / "embeddings"))
    )

    YOUTUBE_TEMP_DIR: Path = Path(
        os.getenv("YOUTUBE_TEMP_DIR", str(PROCESSED_DIR / "youtube_tmp"))
    )
    # e.g. "chrome" or "firefox"; empty disables. Only needed when YouTube
    # starts answering with "Sign in to confirm you're not a bot".
    YTDLP_COOKIES_FROM_BROWSER: str = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    # Alternative to the above: a Netscape-format cookies.txt exported from a
    # browser signed in to YouTube. Takes precedence when the file exists.
    YTDLP_COOKIES_FILE: str = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    # TranscriptAPI.com key: fetches YouTube transcripts without hitting
    # YouTube from this server (needed when deployed). Empty = use yt-dlp.
    TRANSCRIPT_API_KEY: str = os.getenv("TRANSCRIPT_API_KEY", "").strip()
    TRANSCRIPT_API_URL: str = os.getenv(
        "TRANSCRIPT_API_URL", "https://transcriptapi.com/api/v2"
    ).rstrip("/")
    MAX_CONCURRENT_YOUTUBE_JOBS: int = int(os.getenv("MAX_CONCURRENT_YOUTUBE_JOBS", "2"))

    # --- Accounts (Supabase Auth) ---
    # Set SUPABASE_URL to require sign-in; leave it empty for single-user
    # local mode, where every request acts as the "local" user.
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    # Only needed for projects still on the legacy HS256 JWT secret; newer
    # projects sign with asymmetric keys verified via the project's JWKS.
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "").strip()

    # --- Limits (0 = unlimited) ---
    # With sign-in on (a public deployment) these default to safe values;
    # in single-user local mode they default to unlimited.
    DAILY_VIDEO_LIMIT: int = _int_env("DAILY_VIDEO_LIMIT", public=5, local=0)
    MAX_ACTIVE_JOBS_PER_USER: int = _int_env("MAX_ACTIVE_JOBS_PER_USER", public=2, local=2)
    MAX_VIDEO_MINUTES: int = _int_env("MAX_VIDEO_MINUTES", public=180, local=0)
    ASK_LIMIT_PER_HOUR: int = _int_env("ASK_LIMIT_PER_HOUR", public=60, local=0)
    SEARCH_LIMIT_PER_HOUR: int = _int_env("SEARCH_LIMIT_PER_HOUR", public=120, local=0)
    # Requests per minute from one IP address, across the whole API.
    RATE_LIMIT_PER_MINUTE: int = _int_env("RATE_LIMIT_PER_MINUTE", public=240, local=0)
    # Largest accepted JSON request body; uploads have their own limit.
    MAX_JSON_BODY_BYTES: int = int(os.getenv("MAX_JSON_BODY_BYTES", str(64 * 1024)))
    ENABLE_UPLOADS: bool = os.getenv("ENABLE_UPLOADS", "true").lower() in ("1", "true", "yes")

    # --- Transport security ---
    # Redirect plain-HTTP requests (as reported by the platform's proxy) to
    # HTTPS and send HSTS. On by default when sign-in is on.
    FORCE_HTTPS: bool = _bool_env("FORCE_HTTPS", default=_PUBLIC)
    # Interactive API docs at /docs; off by default for public deployments.
    ENABLE_DOCS: bool = _bool_env("ENABLE_DOCS", default=not _PUBLIC)

    # --- Background jobs ---
    # "inline": run in the API process (simple local dev).
    # "queue": the API only records jobs; `python -m app.worker` runs them,
    # so jobs survive API restarts and deploys.
    JOB_MODE: str = os.getenv("JOB_MODE", "inline").lower()
    WORKER_CONCURRENCY: int = int(os.getenv("WORKER_CONCURRENCY", "2"))

    @property
    def AUTH_ENABLED(self) -> bool:
        return bool(self.SUPABASE_URL)


settings = Settings()

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
settings.EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
settings.YOUTUBE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
