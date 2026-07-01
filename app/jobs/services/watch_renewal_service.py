from datetime import datetime
from datetime import timedelta

from app.common.db import db
from app.jobs.services.gmail_watch_service import (
    start_gmail_watch,
)


async def renew_expiring_watches():

    users = db.db["users"]

    now_ms = int(
        datetime.utcnow().timestamp() * 1000
    )

    next_24_hours_ms = int(
        (
            datetime.utcnow()
            + timedelta(days=1)
        ).timestamp() * 1000
    )

    expiring_users = users.find(
        {
            "gmail_watch_expiration": {
                "$lte": next_24_hours_ms,
            },
            "job_tracking_started_at": {
                "$exists": True,
            },
        }
    )

    renewed = 0

    for user in expiring_users:

        try:

            print(
                f"Renewing Gmail watch for {user['email']}"
            )

            watch_response = await start_gmail_watch(
                access_token=user[
                    "access_token"
                ],
                refresh_token=user[
                    "refresh_token"
                ],
            )

            users.update_one(
                {"email": user["email"]},
                {
                    "$set": {
                        "gmail_history_id": str(
                            watch_response[
                                "historyId"
                            ]
                        ),
                        "gmail_watch_expiration": int(
                            watch_response[
                                "expiration"
                            ]
                        ),
                    }
                },
            )

            renewed += 1

            print(
                f"Successfully renewed {user['email']}"
            )

        except Exception as e:

            print(
                f"Failed renewing {user['email']}: {e}"
            )

    print(
        f"Total watches renewed: {renewed}"
    )