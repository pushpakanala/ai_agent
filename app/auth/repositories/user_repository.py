from datetime import datetime
from app.jobs.services.gmail_watch_service import (
    start_gmail_watch,
)
from app.common.db import db


# ==================================================
# Save / Update User
# ==================================================
async def save_user(
    email: str,
    name: str,
    access_token: str,
    refresh_token: str | None = None,
):

    users = db.db["users"]

    users.update_one(
        {"email": email},
        {
            "$set": {
                "name": name,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )


# ==================================================
# Get User
# ==================================================
async def get_user(
    email: str,
):

    users = db.db["users"]

    return users.find_one(
        {"email": email}
    )


# ==================================================
# Initialize Job Tracking
# ==================================================
async def initialize_job_tracking(
    email: str,
):

    users = db.db["users"]

    user = users.find_one(
        {"email": email}
    )

    if not user:
        return None

    now = datetime.utcnow()

    updates = {}

    # --------------------------------------
    # First time job tracking
    # --------------------------------------
    if not user.get(
        "job_tracking_started_at"
    ):

        try:

            # Start Gmail Push Notifications
            watch_response = await start_gmail_watch(
                access_token=user[
                    "access_token"
                ],
                refresh_token=user[
                    "refresh_token"
                ],
            )

            print(
                f"Gmail watch started for {email}"
            )

            print(
                f"Watch response: {watch_response}"
            )

            # Store Gmail history ID
            if watch_response.get(
                "historyId"
            ):

                updates[
                    "gmail_history_id"
                ] = str(
                    watch_response[
                        "historyId"
                    ]
                )

        except Exception as e:

            print(
                f"Failed to start Gmail watch: {e}"
            )

        updates[
            "job_tracking_started_at"
        ] = now

    # --------------------------------------
    # First sync timestamp
    # --------------------------------------
    if not user.get(
        "last_job_sync_at"
    ):

        updates[
            "last_job_sync_at"
        ] = now

    # --------------------------------------
    # Save updates
    # --------------------------------------
    if updates:

        users.update_one(
            {"email": email},
            {
                "$set": updates
            },
        )

        user = users.find_one(
            {"email": email}
        )

    return user

# ==================================================
# Update Last Job Sync Time
# ==================================================
async def update_last_job_sync_time(
    email: str,
    sync_time: datetime | None = None,
):

    users = db.db["users"]

    if sync_time is None:
        sync_time = datetime.utcnow()

    users.update_one(
        {"email": email},
        {
            "$set": {
                "last_job_sync_at": sync_time,
                "updated_at": datetime.utcnow(),
            }
        },
    )


# ==================================================
# Reset Job Tracking (Optional Utility)
# ==================================================
async def reset_job_tracking(
    email: str,
):

    users = db.db["users"]

    now = datetime.utcnow()

    users.update_one(
        {"email": email},
        {
            "$set": {
                "job_tracking_started_at": now,
                "last_job_sync_at": now,
                "updated_at": now,
            }
        },
    )

async def update_gmail_history_id(
    email: str,
    history_id: str,
):

    users = db.db["users"]

    users.update_one(
        {"email": email},
        {
            "$set": {
                "gmail_history_id":
                    history_id
            }
        },
    )