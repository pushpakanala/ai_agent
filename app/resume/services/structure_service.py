"""
structure_service.py
---------------------
Parses raw resume text into structured JSON using Claude, constrained to
ResumeData via forced tool use (see claude_client.py) — replaces the old
OpenAI json_object call, which only asked for JSON matching a schema
described in the prompt with nothing actually enforcing it.
"""

from app.resume.services.claude_client import generate_resume_json


SYSTEM_PROMPT = """You are an ATS resume parser.

Convert the candidate's resume text into structured data using the
emit_resume tool.

Rules:
- Preserve ALL information from the source text.
- Keep bullet points as separate items in the relevant bullets list.
- Extract skills into sensible categories (e.g. Languages, AI/ML, Cloud,
  Databases, Tools) based on what's actually present — don't force empty
  categories.
- Do not invent information that isn't present in the resume.
"""


async def structure_resume(text: str) -> dict:
    return await generate_resume_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"Resume:\n\n{text}",
    )
