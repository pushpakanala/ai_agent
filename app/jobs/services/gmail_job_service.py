from datetime import datetime

from app.email.services.mcp_client import (
    search_emails_via_mcp,
)


# ==================================================
# Fetch Recent Job Emails
# ==================================================
async def fetch_recent_job_emails(
    access_token: str,
    refresh_token: str,
    last_synced_at: datetime | None = None,
):

    # Fetch the last 7 days.
    # Duplicate prevention happens via gmail_id storage.
    query = """
    newer_than:7d
    (
        application
        OR interview
        OR recruiter
        OR hiring
        OR offer
        OR rejection
    )
    """

    results = await search_emails_via_mcp(
        access_token=access_token,
        refresh_token=refresh_token,
        query=query,
    )

    normalized = []

    for item in results:

        normalized.append(
            {
                "gmail_id": item.get(
                    "id",
                    "",
                ),

                "subject": item.get(
                    "subject",
                    "",
                ),

                "body": item.get(
                    "body",
                    "",
                ),

                "from_email": item.get(
                    "from",
                    "",
                ),

                "date": item.get(
                    "date",
                    datetime.utcnow(),
                ),
            }
        )

    print(
        f"\nFound {len(normalized)} emails"
    )

    return normalized