"""
cover_letter_service.py
------------------------
Generates a tailored cover letter from a structured resume + job
description, using Claude. Plain text output — no tool use needed here
since there's no schema to enforce.
"""

import json

from app.resume.services.claude_client import generate_text


SYSTEM_PROMPT = "You are a world-class cover letter writer and career coach."


async def generate_cover_letter(
    resume_json: dict,
    job_description: str,
    company_name: str = "",
    tone: str = "professional",   # "professional" | "enthusiastic" | "concise"
) -> str:
    """
    Returns a plain-text cover letter (3-4 paragraphs).
    """

    tone_guide = {
        "professional":  "Formal, confident, results-focused.",
        "enthusiastic":  "Warm, energetic, shows genuine passion for the role.",
        "concise":       "Direct and brief — under 200 words total.",
    }.get(tone, "Professional and confident.")

    user_content = f"""CANDIDATE RESUME:
{json.dumps(resume_json, indent=2)}

JOB DESCRIPTION:
{job_description}

COMPANY: {company_name or "the company"}

TONE GUIDE: {tone_guide}

Write a compelling cover letter following these rules:
1. Open with a strong hook — name the role and one standout achievement.
2. Paragraph 2: Connect 2-3 of the candidate's skills/projects directly to the JD.
3. Paragraph 3: Show cultural fit and enthusiasm for the specific company.
4. Closing: Clear call-to-action. No generic "I look forward to hearing from you."
5. Do NOT invent experience, companies, or dates not in the resume.
6. Use the candidate's real name from the resume.
7. Return ONLY the cover letter text. No subject line, no markdown, no explanations.
"""

    return await generate_text(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
        max_tokens=600,
        temperature=0.4,
    )
