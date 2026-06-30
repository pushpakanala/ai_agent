from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.common.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GMAIL_PUBSUB_TOPIC,
)


TOPIC_NAME = GMAIL_PUBSUB_TOPIC


async def start_gmail_watch(
    access_token: str,
    refresh_token: str,
):

    try:

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=[
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
        )

        service = build(
            "gmail",
            "v1",
            credentials=creds,
        )

        response = (
            service.users()
            .watch(
                userId="me",
                body={
                    "topicName": TOPIC_NAME,
                    "labelIds": ["INBOX"],
                    "labelFilterBehavior": "INCLUDE",
                },
            )
            .execute()
        )

        print("\n===== GMAIL WATCH STARTED =====")
        print(response)
        print("===============================\n")

        return response

    except HttpError as e:

        print("\n===== GMAIL WATCH ERROR =====")
        print(e)
        print("=============================\n")

        raise

    except Exception as e:

        print("\n===== UNKNOWN WATCH ERROR =====")
        print(str(e))
        print("================================\n")

        raise