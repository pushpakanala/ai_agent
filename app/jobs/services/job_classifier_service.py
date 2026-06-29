import json
import os

from openai import OpenAI

from app.jobs.prompts.job_classifier_prompt import (
    JOB_CLASSIFIER_PROMPT,
)


client = OpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)


def classify_job_email(
    subject: str,
    body: str,
):

    prompt = f"""
Subject:
{subject}

Body:
{body}
"""

    try:

        response = (
            client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0,
                response_format={
                    "type": "json_object"
                },
                messages=[
                    {
                        "role": "system",
                        "content": (
                            JOB_CLASSIFIER_PROMPT
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            )
        )

        result = json.loads(
            response.choices[0]
            .message.content
        )

        return {
            "is_job_email": result.get(
                "is_job_email",
                False,
            ),

            "company_name": result.get(
                "company_name",
                "",
            ),

            "role": result.get(
                "role",
                "",
            ),

            "job_id": result.get(
                "job_id",
                "",
            ),

            "status": result.get(
                "status",
                "applied",
            ),

            "confidence": result.get(
                "confidence",
                0,
            ),

            "interview_date": result.get(
                "interview_date",
                None,
            ),
        }

    except Exception as e:

        print(
            "Job classification error:",
            e,
        )

        return {
            "is_job_email": False,
            "company_name": "",
            "role": "",
            "job_id": "",
            "status": "",
            "confidence": 0,
            "interview_date": None,
        }