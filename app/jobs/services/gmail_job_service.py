from datetime import datetime

from app.email.services.mcp_client import search_emails_via_mcp
from app.common.logger import get_logger

logger = get_logger(__name__)


# ==================================================
# Fetch Recent Job Emails
# ==================================================
async def fetch_recent_job_emails(
    access_token: str,
    refresh_token: str,
    last_synced_at: datetime | None = None,
):

    query = """
    newer_than:7d
    (
        application
        OR interview
        OR recruiter
        OR hiring
        OR offer
        OR rejection
        OR applying
        OR position
        OR candidacy
        OR "thank you for your interest"
        OR "thank you for applying"
        OR "no longer available"
        OR "position has been filled"
        OR "we will not be moving forward"
        OR "not selected"
        OR "pursuing other candidates"
        OR "decided to move forward with other"
        OR "appreciate your interest"
        OR "has been received"
        OR "your application"
        OR "forwarded to our"
        OR "HR Department"
    )
    """

    logger.info("Fetching recent job emails from MCP...")

    results = await search_emails_via_mcp(
        access_token=access_token,
        refresh_token=refresh_token,
        query=query,
    )

    logger.info(f"MCP returned {len(results)} raw items")

    normalized = []

    for index, item in enumerate(results):

        # FIX: MCP sometimes returns raw strings instead of dicts
        # when JSON parsing fails or an error occurs on the MCP side.
        # Skip any non-dict items to prevent AttributeError crash.
        if not isinstance(item, dict):
            logger.warning(
                f"Skipping non-dict item at index {index} "
                f"(type={type(item).__name__}): {str(item)[:100]}"
            )
            continue

        gmail_id  = item.get("id", "")
        subject   = item.get("subject", "")
        body      = item.get("body", "")
        from_email = item.get("from", "")
        date      = item.get("date", datetime.utcnow())

        # Log each email being processed for debugging
        logger.info(
            f"Email [{index}] gmail_id={gmail_id} "
            f"subject={subject[:60]!r} "
            f"body_len={len(body)} "
            f"from={from_email}"
        )

        normalized.append({
            "gmail_id":   gmail_id,
            "subject":    subject,
            "body":       body,
            "from_email": from_email,
            "date":       date,
        })

    logger.info(f"Found {len(normalized)} valid emails after filtering")

    return normalized