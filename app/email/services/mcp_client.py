import json
import sys

from mcp import ClientSession
from mcp.client.stdio import (
    stdio_client,
    StdioServerParameters,
)


SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=[
        "-m",
        "app.email.mcp_server.email_server",
    ],
)


async def send_email_via_mcp(
    access_token: str,
    refresh_token: str,
    to_email: str,
    subject: str,
    body: str,
):

    async with stdio_client(SERVER_PARAMS) as (read, write):

        async with ClientSession(read, write) as session:

            await session.initialize()

            result = await session.call_tool(
                "send_email",
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "to_email": to_email,
                    "subject": subject,
                    "body": body,
                },
            )

            if not result.content:
                return {"status": "unknown"}

            text = result.content[0].text

            try:
                return json.loads(text)

            except json.JSONDecodeError:

                return {
                    "status": "success",
                    "message": text,
                }


async def list_sent_via_mcp(
    access_token: str,
    refresh_token: str,
    limit: int = 5,
):

    async with stdio_client(SERVER_PARAMS) as (read, write):

        async with ClientSession(read, write) as session:

            await session.initialize()

            result = await session.call_tool(
                "list_sent_emails",
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "limit": limit,
                },
            )

            if not result.content:
                return []

            text = result.content[0].text

            try:
                return json.loads(text)

            except json.JSONDecodeError:

                return [text]

async def search_emails_via_mcp(
    access_token: str,
    refresh_token: str,
    query: str,
):

    async with stdio_client(SERVER_PARAMS) as (read, write):

        async with ClientSession(read, write) as session:

            await session.initialize()

            result = await session.call_tool(
                "search_emails",
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "query": query,
                },
            )

            if not result.content:
                return []

            text = result.content[0].text

            try:
                return json.loads(text)

            except json.JSONDecodeError:
                return [text]