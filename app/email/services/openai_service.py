import json

from openai import OpenAI

from app.common.config import OPENAI_API_KEY


client = OpenAI(api_key=OPENAI_API_KEY)


SYSTEM_PROMPT = """
You are an email assistant.

The user will give instructions like:

"Send an email to john@gmail.com thanking him for helping with the project."

Your task:
1. Extract recipient email.
2. Generate a professional subject.
3. Generate a professional email body.

Return ONLY valid JSON:

{
    "to_email": "...",
    "subject": "...",
    "body": "..."
}
"""


def generate_email(prompt: str):

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={"type": "json_object"}
    )

    return json.loads(
        response.choices[0].message.content
    )

def generate_gmail_query(user_query: str):

    prompt = f"""
You are a Gmail search assistant.

Convert the user's request into a valid Gmail search query.

Examples:

Show emails from Amazon last week
-> amazon newer_than:7d

Show unread emails from Google
-> is:unread Google

Emails with attachments
-> has:attachment

Show emails from Quantra Classroom
-> Quantra

Return ONLY the Gmail query.

User request:
{user_query}
"""

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return response.choices[0].message.content.strip()