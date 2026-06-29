from datetime import datetime

from app.common.db import db


# ==================================================
# Create Job
# ==================================================
async def create_job(
    user_email: str,
    job_id: str | None,
    unique_key: str,
    company_name: str,
    role: str,
    status: str,
    date_applied: datetime,
):

    jobs = db.db["job_applications"]

    result = jobs.insert_one(
        {
            "user_email": user_email,
            "job_id": job_id,
            "unique_key": unique_key,
            "company_name": company_name,
            "role": role,
            "status": status,
            "date_applied": date_applied,
            "last_updated": datetime.utcnow(),
            "timeline": [
                {
                    "status": status,
                    "timestamp": datetime.utcnow(),
                }
            ],
        }
    )

    return str(result.inserted_id)


# ==================================================
# Find By Job ID
# ==================================================
async def get_job_by_job_id(
    user_email: str,
    job_id: str,
):

    jobs = db.db["job_applications"]

    result = jobs.find_one(
        {
            "user_email": user_email,
            "job_id": job_id,
        }
    )

    if not result:
        return None

    result["id"] = str(result.pop("_id"))

    return result


# ==================================================
# Find By Unique Key
# ==================================================
async def get_job_by_unique_key(
    user_email: str,
    unique_key: str,
):

    jobs = db.db["job_applications"]

    result = jobs.find_one(
        {
            "user_email": user_email,
            "unique_key": unique_key,
        }
    )

    if not result:
        return None

    result["id"] = str(result.pop("_id"))

    return result


# ==================================================
# Find By Company + Role
# ==================================================
async def get_job_by_company_and_role(
    user_email: str,
    company_name: str,
    role: str,
):

    jobs = db.db["job_applications"]

    result = jobs.find_one(
        {
            "user_email": user_email,
            "company_name": company_name,
            "role": role,
        }
    )

    if not result:
        return None

    result["id"] = str(result.pop("_id"))

    return result


# ==================================================
# Get Single Job
# ==================================================
async def get_job_details(
    user_email: str,
    job_id: str,
):

    jobs = db.db["job_applications"]

    result = jobs.find_one(
        {
            "user_email": user_email,
            "job_id": job_id,
        }
    )

    if not result:
        return None

    result["id"] = str(result.pop("_id"))

    return result


# ==================================================
# Update Job Status
# ==================================================
async def update_job_status(
    user_email: str,
    job_id: str,
    status: str,
):

    jobs = db.db["job_applications"]

    jobs.update_one(
        {
            "user_email": user_email,
            "job_id": job_id,
        },
        {
            "$set": {
                "status": status,
                "last_updated": datetime.utcnow(),
            },
            "$push": {
                "timeline": {
                    "status": status,
                    "timestamp": datetime.utcnow(),
                }
            },
        },
    )


# ==================================================
# Get All Jobs
# ==================================================
async def get_jobs(
    user_email: str,
):

    jobs = db.db["job_applications"]

    result = list(
        jobs.find(
            {"user_email": user_email},
            {"user_email": 0},
        ).sort(
            "last_updated",
            -1,
        )
    )

    for item in result:

        item["id"] = str(item.pop("_id"))

    return result


# ==================================================
# Dashboard Stats
# ==================================================
async def get_job_stats(
    user_email: str,
):

    jobs = db.db["job_applications"]

    applied = jobs.count_documents(
        {
            "user_email": user_email,
            "status": "applied",
        }
    )

    interview = jobs.count_documents(
        {
            "user_email": user_email,
            "status": "interview",
        }
    )

    rejected = jobs.count_documents(
        {
            "user_email": user_email,
            "status": "rejected",
        }
    )

    offer = jobs.count_documents(
        {
            "user_email": user_email,
            "status": "offer",
        }
    )

    total = jobs.count_documents(
        {
            "user_email": user_email,
        }
    )

    return {
        "total": total,
        "applied": applied,
        "interview": interview,
        "rejected": rejected,
        "offer": offer,
    }


# ==================================================
# Gmail Message Tracking
# ==================================================
async def is_gmail_message_processed(
    user_email: str,
    gmail_id: str,
):

    collection = db.db["processed_gmail_messages"]

    result = collection.find_one(
        {
            "user_email": user_email,
            "gmail_id": gmail_id,
        }
    )

    return result is not None


async def save_processed_gmail_message(
    user_email: str,
    gmail_id: str,
):

    collection = db.db["processed_gmail_messages"]

    collection.update_one(
        {
            "user_email": user_email,
            "gmail_id": gmail_id,
        },
        {
            "$set": {
                "processed_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )