import base64
import json
from email.mime.text import MIMEText

from fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.common.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
)


mcp = FastMCP("gmail-server")


# ==================================================
# Gmail Service
# ==================================================
def get_gmail_service(
    access_token: str,
    refresh_token: str,
):

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=[
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
        ],
    )

    return build(
        "gmail",
        "v1",
        credentials=creds,
    )


# ==================================================
# Send Email Tool
# ==================================================
@mcp.tool()
def send_email(
    access_token: str,
    refresh_token: str,
    to_email: str,
    subject: str,
    body: str,
):

    try:

        service = get_gmail_service(
            access_token,
            refresh_token,
        )

        message = MIMEText(body)

        message["to"] = to_email
        message["subject"] = subject

        raw_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode()

        sent_message = (
            service.users()
            .messages()
            .send(
                userId="me",
                body={"raw": raw_message},
            )
            .execute()
        )

        return json.dumps(
            {
                "status": "success",
                "message": f"Email sent to {to_email}",
                "id": sent_message.get("id"),
            }
        )

    except Exception as e:

        return json.dumps(
            {
                "status": "error",
                "message": str(e),
            }
        )


# ==================================================
# List Sent Emails Tool
# ==================================================
@mcp.tool()
def list_sent_emails(
    access_token: str,
    refresh_token: str,
    limit: int = 5,
):

    try:

        service = get_gmail_service(
            access_token,
            refresh_token,
        )

        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=["SENT"],
                maxResults=limit,
            )
            .execute()
        )

        messages = results.get("messages", [])

        emails = []

        for msg in messages:

            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                )
                .execute()
            )

            headers = message["payload"]["headers"]

            subject = ""

            for h in headers:
                if h["name"] == "Subject":
                    subject = h["value"]
                    break

            emails.append(
                {
                    "id": msg["id"],
                    "subject": subject,
                }
            )

        return json.dumps(emails)

    except Exception as e:

        return json.dumps(
            [
                {
                    "status": "error",
                    "message": str(e),
                }
            ]
        )


# ==================================================
# Search Emails Tool
# ==================================================
@mcp.tool()
def search_emails(
    access_token: str,
    refresh_token: str,
    query: str,
):

    try:

        service = get_gmail_service(
            access_token,
            refresh_token,
        )

        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=10,
            )
            .execute()
        )

        messages = results.get(
            "messages",
            []
        )

        emails = []

        for msg in messages:

            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="full",   # IMPORTANT
                )
                .execute()
            )

            payload = message.get(
                "payload",
                {}
            )

            headers = payload.get(
                "headers",
                []
            )

            subject = ""
            sender = ""
            date = ""

            for h in headers:

                if h["name"] == "Subject":
                    subject = h["value"]

                elif h["name"] == "From":
                    sender = h["value"]

                elif h["name"] == "Date":
                    date = h["value"]

            # =====================================
            # Extract body
            # =====================================
            body = ""

            try:

                # Simple emails
                if payload.get("body", {}).get("data"):

                    body = base64.urlsafe_b64decode(
                        payload["body"]["data"]
                    ).decode(
                        "utf-8",
                        errors="ignore",
                    )

                # Multipart emails
                elif payload.get("parts"):

                    html_body = ""

                    for part in payload["parts"]:

                        mime = part.get("mimeType", "")
                        data = part.get("body", {}).get("data")

                        if mime == "text/plain" and data:
                            body = (
                                base64.urlsafe_b64decode(data)
                                .decode("utf-8", errors="ignore")
                            )
                            break

                        elif mime == "text/html" and data and not html_body:
                            import re as _re
                            raw_html = (
                                base64.urlsafe_b64decode(data)
                                .decode("utf-8", errors="ignore")
                            )
                            html_body = _re.sub(r"<[^>]+>", " ", raw_html)
                            html_body = _re.sub(r"\s+", " ", html_body).strip()

                        elif mime.startswith("multipart/"):
                            for subpart in part.get("parts", []):
                                submime = subpart.get("mimeType", "")
                                subdata = subpart.get("body", {}).get("data")
                                if submime == "text/plain" and subdata:
                                    body = (
                                        base64.urlsafe_b64decode(subdata)
                                        .decode("utf-8", errors="ignore")
                                    )
                                    break
                                elif submime == "text/html" and subdata and not html_body:
                                    import re as _re
                                    raw_html = (
                                        base64.urlsafe_b64decode(subdata)
                                        .decode("utf-8", errors="ignore")
                                    )
                                    html_body = _re.sub(r"<[^>]+>", " ", raw_html)
                                    html_body = _re.sub(r"\s+", " ", html_body).strip()

                    # Use HTML body as fallback if no plain text found
                    if not body and html_body:
                        body = html_body

            except Exception as e:

                print(
                    "Body extraction failed:",
                    e,
                )

                body = ""

            emails.append(
                {
                    "id": msg["id"],
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "body": body,   # NEW
                }
            )

        return json.dumps(emails)

    except Exception as e:

        return json.dumps(
            {
                "status": "error",
                "message": str(e),
            }
        )

# ==================================================
# Get Single Email Tool
# ==================================================
@mcp.tool()
def get_email(
    access_token: str,
    refresh_token: str,
    message_id: str,
):

    try:

        service = get_gmail_service(
            access_token,
            refresh_token,
        )

        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
            )
            .execute()
        )

        return json.dumps(message)

    except Exception as e:

        return json.dumps(
            {
                "status": "error",
                "message": str(e),
            }
        )


# ==================================================
# Run MCP Server
# ==================================================
if __name__ == "__main__":

    mcp.run()