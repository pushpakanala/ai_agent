from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from app.auth.dependencies import (
    get_current_user,
)

from app.auth.repositories.user_repository import (
    get_user,
)

router = APIRouter()


@router.get("/me")
async def get_me(
    current_user=Depends(get_current_user),
):

    # current_user is actually an email string
    user = await get_user(
        current_user
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return {
        "email": user["email"],
        "name": user.get("name"),

        "job_tracking_started_at":
            user.get(
                "job_tracking_started_at"
            ),

        "last_job_sync_at":
            user.get(
                "last_job_sync_at"
            ),

        "gmail_history_id":
            user.get(
                "gmail_history_id"
            ),

        "gmail_watch_expiration":
            user.get(
                "gmail_watch_expiration"
            ),
    }