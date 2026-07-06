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
        },
        "$setOnInsert": {
            "created_at": datetime.utcnow(),
        },
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
from datetime import datetime

from app.jobs.services.gmail_watch_service import (
    start_gmail_watch,
)


async def initialize_job_tracking(
    email: str,
):

    users = db.db["users"]

    user = users.find_one(
        {"email": email}
    )

    if not user:
        return None

    # --------------------------------------
    # Already initialized
    # --------------------------------------
    if user.get(
        "job_tracking_started_at"
    ):

        return user

    now = datetime.utcnow()

    # --------------------------------------
    # Start Gmail watch
    # --------------------------------------
    try:

        watch_response = await start_gmail_watch(
            access_token=user[
                "access_token"
            ],
            refresh_token=user[
                "refresh_token"
            ],
        )

        print(
            "\nWATCH RESPONSE:"
        )

        print(watch_response)

    except Exception as e:

        print(
            f"Failed to start Gmail watch: {e}"
        )

        raise Exception(
            f"Gmail watch failed: {e}"
        )

    # --------------------------------------
    # Validate response
    # --------------------------------------
    history_id = watch_response.get(
        "historyId"
    )

    expiration = watch_response.get(
        "expiration"
    )

    if not history_id:

        raise Exception(
            f"Invalid watch response: {watch_response}"
        )

    # --------------------------------------
    # Prepare updates
    # --------------------------------------
    updates = {
        "job_tracking_started_at": now,
        "last_job_sync_at": now,
        "gmail_history_id": str(
            history_id
        ),
    }

    if expiration:

        updates[
            "gmail_watch_expiration"
        ] = int(expiration)

    print(
        "\nMONGO UPDATES:"
    )

    print(updates)

    # --------------------------------------
    # Save to MongoDB
    # --------------------------------------
    users.update_one(
        {"email": email},
        {
            "$set": updates
        },
    )

    return users.find_one(
        {"email": email}
    )

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