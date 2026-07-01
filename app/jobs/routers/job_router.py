from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from app.auth.dependencies import (
    get_current_user,
)

from app.auth.repositories.user_repository import (
    initialize_job_tracking,
)

from app.jobs.repositories.job_repository import (
    get_jobs,
    get_job_stats,
)

from app.jobs.services.job_service import (
    sync_jobs,
)
from app.jobs.services.watch_renewal_service import (
    renew_expiring_watches,
)


router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)


# ==========================================
# Initialize Job Tracking
# ==========================================
@router.post("/init")
async def init_jobs(
    email: str = Depends(get_current_user),
):

    user = await initialize_job_tracking(
        email
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return {
        "tracking_started_at":
            user["job_tracking_started_at"]
    }


# ==========================================
# Dashboard Stats
# ==========================================
@router.get("/stats")
async def job_stats(
    email: str = Depends(get_current_user),
):

    stats = await get_job_stats(
        email
    )

    return stats


# ==========================================
# List All Jobs
# ==========================================
@router.get("/")
async def list_jobs(
    email: str = Depends(get_current_user),
):

    jobs = await get_jobs(
        email
    )

    return {
        "jobs": jobs
    }


# ==========================================
# Sync Jobs From Gmail
# ==========================================
@router.post("/sync")
async def sync_job_emails(
    email: str = Depends(get_current_user),
):

    result = await sync_jobs(
        email
    )

    return result

@router.post("/renew-watches")
async def renew_watches():

    await renew_expiring_watches()

    return {
        "message":
        "Watch renewal completed"
    }