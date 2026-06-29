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

    # --------------------------------------
    # Build Gmail query
    # --------------------------------------
    if last_synced_at:

        diff_seconds = (
            datetime.utcnow() - last_synced_at
        ).total_seconds()

        hours = max(
            int(diff_seconds / 3600),
            1,
        )

        query = f"""
        newer_than:{hours}h
        (
            application
            OR interview
            OR recruiter
            OR hiring
            OR offer
            OR rejection
        )
        """

        print(
            f"\nIncremental sync ({hours}h)"
        )

    else:

        # ----------------------------------
        # First-time users:
        # Only start tracking from now.
        # ----------------------------------
        query = """
        newer_than:1h
        (
            application
            OR interview
            OR recruiter
            OR hiring
            OR offer
            OR rejection
        )
        """

        print(
            "\nFirst sync (1 hour window)"
        )

    print("\nGMAIL QUERY:")
    print(query)

    # --------------------------------------
    # Call MCP
    # --------------------------------------
    results = await search_emails_via_mcp(
        access_token=access_token,
        refresh_token=refresh_token,
        query=query,
    )

    if not results:

        print("\nNo emails found.")

        return []

    print(
        f"\nRaw MCP results: {len(results)} emails"
    )

    # --------------------------------------
    # Normalize
    # --------------------------------------
    normalized = []

    for item in results:

        if not isinstance(item, dict):

            print(
                "Skipping invalid item:",
                item,
            )

            continue

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
        f"\nNormalized {len(normalized)} emails"
    )

    return normalized