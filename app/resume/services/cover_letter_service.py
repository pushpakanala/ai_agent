"""
cover_letter_service.py
------------------------
Generates a tailored cover letter from resume plain text + job description.

Updated for v3:
  - Uses OpenAI (gpt-4.1-mini) instead of Claude — consistent with
    the rest of the simplified module
  - Takes resume_text (str) directly — no JSON, no render_resume_text()
  - No dependencies on any deleted services
"""

from openai import AsyncOpenAI
from app.common.config import OPENAI_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

_SYSTEM = """You are an expert cover letter writer and career coach.

Write a compelling, tailored cover letter:
1. Open with a strong hook — name the role and one standout achievement.
2. Connect 2-3 of the candidate's skills/projects directly to the JD.
3. Show genuine enthusiasm for this specific company.
4. Close with a clear call-to-action (no generic 'I look forward to hearing').
5. Never invent experience not in the resume.
6. Use the candidate's real name from the resume.
Return ONLY the cover letter text — no subject line, no markdown, no preamble."""

_TONE_GUIDE = {
    "professional":  "Formal, confident, results-focused.",
    "enthusiastic":  "Warm, energetic, shows genuine passion for the role.",
    "concise":       "Direct and brief — under 180 words total.",
}


async def generate_cover_letter(
    resume_text: str,
    job_description: str,
    company_name: str = "",
    tone: str = "professional",
) -> str:
    tone_note = _TONE_GUIDE.get(tone, _TONE_GUIDE["professional"])

    response = await client.chat.completions.create(
        model="gpt-4.1-mini",
        max_tokens=500,
        temperature=0.4,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"TONE: {tone_note}\n"
                f"COMPANY: {company_name or 'the company'}\n\n"
                f"RESUME:\n{resume_text}\n\n"
                f"JOB DESCRIPTION:\n{job_description}"
            )},
        ],
    )

    return response.choices[0].message.content.strip()