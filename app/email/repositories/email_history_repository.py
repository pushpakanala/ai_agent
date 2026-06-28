from datetime import datetime

from app.common.db import db


async def save_email_history(
    user_email: str,
    prompt: str,
    to_email: str,
    subject: str,
    body: str,
    gmail_message_id: str,
):
    collection = db.db["email_history"]

    collection.insert_one(
        {
            "user_email": user_email,
            "prompt": prompt,
            "to_email": to_email,
            "subject": subject,
            "body": body,
            "gmail_message_id": gmail_message_id,
            "status": "sent",
            "created_at": datetime.utcnow(),
        }
    )


async def get_email_history(
    user_email: str,
):
    collection = db.db["email_history"]

    emails = list(
        collection.find(
            {"user_email": user_email},
            {"_id": 0},
        ).sort("created_at", -1)
    )

    return emails