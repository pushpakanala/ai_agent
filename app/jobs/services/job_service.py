from datetime import datetime
from email.utils import parsedate_to_datetime

from app.auth.repositories.user_repository import get_user

from app.jobs.repositories.job_repository import (
    create_job,
    update_job_status,
    get_job_by_job_id,
    get_job_by_company_and_role,
    is_gmail_message_processed,      # NEW
    save_processed_gmail_message,    # NEW
    get_job_by_gmail_id
)

from app.jobs.services.gmail_job_service import (
    fetch_recent_job_emails,
)

from app.jobs.services.job_classifier_service import (
    classify_job_email,
)

from app.auth.repositories.user_repository import (
    update_last_job_sync_time,       # NEW
)


# ==================================================
# Process Single Job Email
# ==================================================
async def process_job_email(
    user_email: str,
    gmail_id: str,
    job_data: dict,
    email_date: datetime,
):

    job_id = (job_data.get("job_id") or "").strip()
    company_name = (job_data.get("company_name") or "").strip()
    role = (job_data.get("role") or "").strip()
    status = job_data.get("status", "applied")

    # Only skip if role is also missing — if we have a role but no company
    # use "Unknown Company" as fallback so the email is not silently dropped.
    # The classifier prompt fix handles company extraction going forward.
    if not role:
        return "ignored"

    if not company_name:
        company_name = "Unknown Company"

    # --------------------------------------
    # Unique key
    # --------------------------------------
    if job_id:

        unique_key = f"{user_email}:{job_id}"

    else:

        unique_key = (
            f"{user_email}:"
            f"{company_name.lower()}:"
            f"{role.lower()}"
        )

    existing_job = None

    # --------------------------------------
    # First preference: Job ID
    # --------------------------------------
    if job_id:

        existing_job = await get_job_by_job_id(
            user_email=user_email,
            job_id=job_id,
        )

    # --------------------------------------
    # Fallback: company + role
    # --------------------------------------
    if not existing_job:

        existing_job = await get_job_by_company_and_role(
            user_email=user_email,
            company_name=company_name,
            role=role,
        )

    # --------------------------------------
    # Update existing job
    # --------------------------------------
    if existing_job:

        if existing_job["status"] != status:

            await update_job_status(
                user_email=user_email,
                job_id=existing_job["job_id"],
                status=status,
            )

            return "updated"

        return "skipped"

    # --------------------------------------
    # Create new job
    # --------------------------------------
    await create_job(
        user_email=user_email,
        gmail_id=gmail_id,
        job_id=job_id,
        company_name=company_name,
        role=role,
        status=status,
        date_applied=email_date,
        unique_key=unique_key,
    )

    return "created"


# ==================================================
# Sync Jobs
# ==================================================
async def sync_jobs(user_email: str):

    user = await get_user(user_email)

    if not user:
        return {
            "message": "User not found"
        }

    emails = await fetch_recent_job_emails(
        access_token=user["access_token"],
        refresh_token=user["refresh_token"],
        last_synced_at=user.get("last_job_sync_at"),
    )

    # --------------------------------------
    # Process oldest → newest
    # --------------------------------------
    emails = sorted(
        emails,
        key=lambda x: parsedate_to_datetime(
            x["date"]
            .replace("(UTC)", "")
            .strip()
        )
    )

    print(f"\nFound {len(emails)} emails")

    created = 0
    updated = 0
    skipped = 0
    ignored = 0
    processed = 0

    for email_item in emails:

        try:

            gmail_id = email_item.get("gmail_id")

            # --------------------------------------
            # Skip already processed Gmail messages
            # --------------------------------------
            if gmail_id:

                already_processed = (
                    await is_gmail_message_processed(
                        user_email=user_email,
                        gmail_id=gmail_id,
                    )
                )

                if already_processed:

                    print(
                        f"Skipping Gmail ID: {gmail_id}"
                    )

                    skipped += 1
                    continue

            # --------------------------------------
            # Parse email date
            # --------------------------------------
            raw_date = (
                email_item.get("date", "")
                .replace("(UTC)", "")
                .strip()
            )

            try:

                email_date = parsedate_to_datetime(
                    raw_date
                )

            except Exception:

                email_date = datetime.utcnow()

            if email_date.tzinfo:

                email_date = (
                    email_date
                    .astimezone()
                    .replace(tzinfo=None)
                )

            # --------------------------------------
            # Classification
            # --------------------------------------
            subject = email_item.get(
                "subject",
                "",
            )

            body = email_item.get(
                "body",
                "",
            )

            classification = classify_job_email(
                subject,
                body,
            )

            print(
                f"\nSubject: {subject}"
            )

            print(
                f"Classification: {classification}"
            )

            # --------------------------------------
            # Ignore non-job emails
            # --------------------------------------
            if not classification.get(
                "is_job_email"
            ):

                ignored += 1

                if gmail_id:

                    await save_processed_gmail_message(
                        user_email=user_email,
                        gmail_id=gmail_id,
                    )

                continue

            processed += 1

            # --------------------------------------
            # Create / Update Job
            # --------------------------------------
            result = await process_job_email(
                user_email=user_email,
                gmail_id=gmail_id,      # NEW
                job_data=classification,
                email_date=email_date,
            )

            if result == "created":

                created += 1

            elif result == "updated":

                updated += 1

            elif result == "skipped":

                skipped += 1

            else:

                ignored += 1

            # --------------------------------------
            # Mark Gmail message as processed
            # --------------------------------------
            if gmail_id:

                await save_processed_gmail_message(
                    user_email=user_email,
                    gmail_id=gmail_id,
                )

        except Exception as e:

            print(
                "Job sync error:",
                str(e),
            )

    # --------------------------------------
    # Update last sync time
    # --------------------------------------
    await update_last_job_sync_time(
        user_email,
        datetime.utcnow(),
    )

    return {
        "processed": processed,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "ignored": ignored,
    }