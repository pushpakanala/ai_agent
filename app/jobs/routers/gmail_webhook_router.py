import asyncio
import base64
import json

from fastapi import APIRouter
from fastapi import Request

from app.auth.repositories.user_repository import (
    get_user,
)

from app.jobs.services.job_service import (
    sync_jobs,
)


router = APIRouter()


@router.post("/gmail/webhook")
async def gmail_webhook(
    request: Request,
):

    try:

        payload = await request.json()

        print("\n===== PUBSUB EVENT =====")
        print(payload)
        print("========================\n")

        message = payload.get(
            "message",
            {}
        )

        if not message.get("data"):

            return {
                "status": "ignored"
            }

        decoded = base64.b64decode(
            message["data"]
        ).decode()

        gmail_payload = json.loads(
            decoded
        )

        print(
            "\n===== GMAIL EVENT ====="
        )

        print(gmail_payload)

        print(
            "=======================\n"
        )

        email_address = gmail_payload.get(
            "emailAddress"
        )

        history_id = gmail_payload.get(
            "historyId"
        )

        print(
            f"Email: {email_address}"
        )

        print(
            f"History ID: {history_id}"
        )

        user = await get_user(
            email_address
        )

        if not user:

            print(
                f"User not found: {email_address}"
            )

            return {
                "status": "user_not_found"
            }

        asyncio.create_task(
            sync_jobs(email_address)
        )

        return {
            "status": "success"
        }

    except Exception as e:

        print(
            f"Webhook error: {e}"
        )

        return {
            "status": "error",
            "message": str(e),
        }