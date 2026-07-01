import asyncio

from app.common.db import db

from app.jobs.services.watch_renewal_service import (
    renew_expiring_watches,
)


async def main():

    db.connect_to_mongo()

    await renew_expiring_watches()

    print(
        "Finished renewing watches"
    )


asyncio.run(main())