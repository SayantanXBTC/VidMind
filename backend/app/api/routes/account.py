from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.core.limits import videos_created_today
from app.database.session import get_db
from app.schemas.video import AccountResponse

router = APIRouter(tags=["account"])


@router.get("/me", response_model=AccountResponse)
def get_account(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> AccountResponse:
    """Who the caller is plus the limits the UI should show."""
    return AccountResponse(
        user_id=user.id,
        email=user.email,
        auth_enabled=settings.AUTH_ENABLED,
        uploads_enabled=settings.ENABLE_UPLOADS,
        daily_limit=settings.DAILY_VIDEO_LIMIT or None,
        used_today=videos_created_today(db, user.id),
        max_video_minutes=settings.MAX_VIDEO_MINUTES or None,
    )
