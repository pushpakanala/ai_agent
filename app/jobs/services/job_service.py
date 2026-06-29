from datetime import datetime
from email.utils import parsedate_to_datetime

from app.auth.repositories.user_repository import (
    get_user,
)

from app.jobs.repositories.job_repository import (
    create_job,
    update_job_status,
    get_job_by_job_id,
    get_job_by_company_and_role,
)

from app.jobs.services.gmail_job_service import (
    fetch_recent_job_emails,
)

from app.jobs.services.job_classifier_service import (
    classify_job_email,
)


# ==========================================
# Process Single Job Email
# ==========================================
async def process_job_email(
    user_email: str,
    job_data: dict,
    email_date: datetime,
):

    job_id = (job_data.get("job_id") or "").strip()
    company_name = (job_data.get("company_name") or "").strip()
    role = (job_data.get("role") or "").strip()
    status = job_data.get("status", "applied")

    if not company_name or not role:
        return "ignored"

    # ----------------------------
    # Generate unique key
    # ----------------------------
    if job_id:
        unique_key = f"{user_email}:{job_id}"
    else:
        unique_key = (
            f"{user_email}:"
            f"{company_name.lower()}:"
            f"{role.lower()}"
        )

    existing_job = None

    # ----------------------------
    # First: job id
    # ----------------------------
    if job_id:
        existing_job = await get_job_by_job_id(
            user_email=user_email,
            job_id=job_id,
        )

    # ----------------------------
    # Fallback: company + role
    # ----------------------------
    if not existing_job:
        existing_job = await get_job_by_company_and_role(
            user_email=user_email,
            company_name=company_name,
            role=role,
        )

    # ----------------------------
    # Update existing
    # ----------------------------
    if existing_job:

        if existing_job["status"] != status:

            await update_job_status(
                user_email=user_email,
                job_id=existing_job["job_id"],
                status=status,
            )

            return "updated"

        return "skipped"

    # ----------------------------
    # Create new job
    # ----------------------------
    await create_job(
        user_email=user_email,
        job_id=job_id,
        company_name=company_name,
        role=role,
        status=status,
        date_applied=email_date,
        unique_key=unique_key,   # <-- FIX
    )

    return "created"


# ==========================================
# Main Sync Service
# ==========================================
async def sync_jobs(
    user_email: str,
):

    user = await get_user(user_email)

    if not user:
        return {
            "message": "User not found",
        }

    started_at = user.get(
        "job_tracking_started_at"
    )

    if not started_at:
        return {
            "message": "Initialize tracking first",
        }

    emails = await fetch_recent_job_emails(
        access_token=user["access_token"],
        refresh_token=user["refresh_token"],
    )

    print(f"\nFound {len(emails)} emails")

    created = 0
    updated = 0
    skipped = 0
    ignored = 0
    processed = 0

    for email_item in emails:

        try:

            # ----------------------------------
            # Parse email date
            # ----------------------------------
            raw_date = email_item.get("date", "")

            # Gmail sometimes returns:
            # Thu, 25 Jun 2026 13:48:05 +0000 (UTC)

            raw_date = raw_date.replace("(UTC)", "").strip()

            try:
                email_date = parsedate_to_datetime(raw_date)

            except Exception as e:
                print("DATE PARSE ERROR:", e)
                email_date = datetime.utcnow()

            if email_date.tzinfo:
                email_date = email_date.astimezone().replace(tzinfo=None)

            if not email_date:
                email_date = datetime.utcnow()

            elif isinstance(email_date, str):

                email_date = (
                    email_date
                    .replace("(UTC)", "")
                    .strip()
                )

                try:

                    email_date = (
                        parsedate_to_datetime(
                            email_date
                        )
                    )

                except Exception as e:

                    print(
                        f"Failed to parse date: {email_date}"
                    )

                    print(e)

                    email_date = datetime.utcnow()

            if email_date.tzinfo:

                email_date = (
                    email_date.replace(
                        tzinfo=None
                    )
                )

            # ----------------------------------
            # Ignore old emails
            # ----------------------------------
            # if email_date < started_at:
            #     continue

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

            # ----------------------------------
            # Ignore non-job emails
            # ----------------------------------
            if not classification.get(
                "is_job_email"
            ):

                ignored += 1
                continue

            processed += 1

            result = await process_job_email(
                user_email=user_email,
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

        except Exception as e:

            print(
                "Job sync error:",
                str(e),
            )

    return {
        "processed": processed,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "ignored": ignored,
    }