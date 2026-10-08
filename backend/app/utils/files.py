"""File-safety helpers: extension checks and path-traversal prevention."""
import uuid
from pathlib import Path

from app.core.config import settings


def is_allowed_extension(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in settings.ALLOWED_VIDEO_EXTENSIONS


def generate_stored_filename(original_filename: str) -> str:
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


def safe_upload_path(stored_filename: str) -> Path:
    """Resolve stored_filename under UPLOAD_DIR, rejecting any path traversal."""
    candidate = (settings.UPLOAD_DIR / stored_filename).resolve()
    upload_root = settings.UPLOAD_DIR.resolve()
    if upload_root not in candidate.parents and candidate != upload_root:
        raise ValueError("Invalid stored filename")
    return candidate
