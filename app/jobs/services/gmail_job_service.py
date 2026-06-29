from datetime import datetime

from app.email.services.mcp_client import (
    search_emails_via_mcp,
)


async def fetch_recent_job_emails(
    access_token: str,
    refresh_token: str,
):

    query = """
    newer_than:30d
    (
        application
        OR interview
        OR recruiter
        OR hiring
        OR career
        OR jobs
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
                "gmail_id": item.get("id", ""),
                "subject": item.get("subject", ""),
                "body": item.get("body", ""),
                "from_email": item.get("from", ""),
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