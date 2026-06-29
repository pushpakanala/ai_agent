from datetime import datetime

from app.common.db import db


async def save_user(
    email: str,
    name: str,
    access_token: str,
    refresh_token: str | None = None,
):
    users = db.db["users"]   # Use your actual DB attribute

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


async def get_user(email: str):
    users = db.db["users"]

    return users.find_one({"email": email})

async def initialize_job_tracking(
    email: str,
):

    users = db.db["users"]

    user = users.find_one(
        {"email": email}
    )

    if not user:
        return None

    if not user.get(
        "job_tracking_started_at"
    ):

        users.update_one(
            {"email": email},
            {
                "$set": {
                    "job_tracking_started_at":
                        datetime.utcnow()
                }
            },
        )

        user = users.find_one(
            {"email": email}
        )

    return user