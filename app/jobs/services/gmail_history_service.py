from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.common.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
)


async def get_new_message_ids(
    access_token: str,
    refresh_token: str,
    start_history_id: str,
):

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
        .history()
        .list(
            userId="me",
            startHistoryId=start_history_id,
        )
        .execute()
    )

    history = response.get(
        "history",
        []
    )

    message_ids = set()

    for item in history:

        for msg in item.get(
            "messagesAdded",
            []
        ):

            message_ids.add(
                msg["message"]["id"]
            )

    return (
        list(message_ids),
        response.get("historyId"),
    )