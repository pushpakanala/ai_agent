from fastapi import HTTPException


ALLOWED_EXTENSIONS = [
    ".pdf",
    ".docx",
]

RESUME_KEYWORDS = [
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "technical skills",
    "professional summary",
]


def validate_resume_file(
    filename: str,
):

    if not any(
        filename.lower().endswith(ext)
        for ext in ALLOWED_EXTENSIONS
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Only PDF and DOCX "
                "files are supported."
            ),
        )


def validate_resume_text(
    text: str,
):

    if len(text) < 300:

        raise HTTPException(
            status_code=400,
            detail=(
                "Document contains "
                "too little text."
            ),
        )

    score = sum(
        keyword in text.lower()
        for keyword in RESUME_KEYWORDS
    )

    if score < 3:

        raise HTTPException(
            status_code=400,
            detail=(
                "Uploaded file does not "
                "appear to be a resume."
            ),
        )