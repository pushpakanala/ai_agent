import re


async def extract_resume_metadata(
    text: str,
):

    email_match = re.search(
        r"[\w\.-]+@[\w\.-]+",
        text,
    )

    email = (
        email_match.group(0)
        if email_match
        else None
    )

    lines = text.split("\n")

    candidate_name = (
        lines[0].strip()
        if lines
        else "Unknown"
    )

    return {
        "candidate_name":
            candidate_name,

        "email":
            email,

        "skills": [],
    }