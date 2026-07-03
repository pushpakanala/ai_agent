"""
job_optimizer_service.py
-------------------------
Token optimizations:
  - Resume sent as compact JSON (saves ~200 tokens)
  - missing_keywords list capped at 15 items (was 20 — JD already covers them)
  - System prompt tightened without losing any instructional value
"""

import json
from app.resume.services.claude_client import generate_resume_json
from app.resume.services.resume_renderer import render_resume_text


SYSTEM_PROMPT = """You are an ATS optimization expert and career coach.

Rewrite the candidate's resume to maximise ATS match for the target role,
then emit the ENTIRE updated resume via emit_resume.

Rules:
1. Never invent companies, roles, dates, or metrics.
2. Incorporate missing keywords ONLY where genuinely supported by the
   candidate's background — no keyword stuffing.
3. Mirror the JD's language and priorities in bullet points.
4. Reorder skills to lead with the most JD-relevant ones.
5. Rewrite the summary to target this specific role.
6. Quantify impact wherever existing bullets allow it.
7. Return the ENTIRE resume, not just changed sections."""


async def optimize_for_job(
    resume_json: dict,
    job_description: str,
    missing_keywords: list[str],
) -> tuple[dict, str]:

    # Cap keywords to avoid inflating the prompt unnecessarily
    top_missing = missing_keywords[:15]

    user_content = (
        f"RESUME:\n{json.dumps(resume_json, separators=(',', ':'))}\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"MISSING KEYWORDS (incorporate only where genuine):\n"
        f"{', '.join(top_missing) if top_missing else 'None identified'}"
    )

    updated_json = await generate_resume_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
    )

    return updated_json, render_resume_text(updated_json)