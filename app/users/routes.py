from fastapi import APIRouter
from fastapi import Depends

from app.auth.dependencies import get_current_user

router = APIRouter()


@router.get("/me")
async def get_me(
    current_user=Depends(get_current_user),
):

    return {
        "email": current_user["email"],
        "name": current_user.get("name"),

        "job_tracking_started_at":
            current_user.get(
                "job_tracking_started_at"
            ),

        "last_job_sync_at":
            current_user.get(
                "last_job_sync_at"
            ),

        "gmail_history_id":
            current_user.get(
                "gmail_history_id"
            ),

        "gmail_watch_expiration":
            current_user.get(
                "gmail_watch_expiration"
            ),
    }