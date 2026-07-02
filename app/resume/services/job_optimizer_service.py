"""
job_optimizer_service.py
-------------------------
Optimizes a resume against a job description using Claude's forced tool-use
(emit_resume), so the output is always schema-valid ResumeData.

Now wired into routes.py /optimize-for-job endpoint. This replaces the
previous approach of hand-building an instruction string and calling
chat_service.modify_resume(), which was less targeted.

Flow:
  1. routes.py calls calculate_match() to find missing keywords.
  2. routes.py calls optimize_for_job() here with the resume JSON + JD + gaps.
  3. We call generate_resume_json() (forced tool use) with a specialist prompt.
  4. Return updated_json; routes.py renders text, scores ATS, saves version.
"""

import json
from app.resume.services.claude_client import generate_resume_json
from app.resume.services.resume_renderer import render_resume_text


SYSTEM_PROMPT = """You are an ATS optimization expert and career coach.

You will receive:
  - The candidate's CURRENT structured resume
  - The target JOB DESCRIPTION
  - A list of MISSING KEYWORDS not yet present in the resume

Your job: rewrite the resume to maximise ATS match for this specific role,
then emit the ENTIRE updated resume via the emit_resume tool.

Rules:
1. Preserve ALL facts — never invent companies, roles, dates, or metrics.
2. Incorporate missing keywords ONLY where they are genuinely supported by
   the candidate's actual background — do not keyword-stuff.
3. Rewrite bullet points to mirror the JD's language and priorities.
4. Reorder skills categories to lead with the most relevant ones for this JD.
5. Rewrite the professional summary to directly target this role and company.
6. Quantify impact wherever the existing bullets allow it.
7. Keep ATS-friendly plain text — no tables, no graphics, no columns.
8. Return the ENTIRE resume, not just changed sections.
"""


async def optimize_for_job(
    resume_json: dict,
    job_description: str,
    missing_keywords: list[str],
) -> tuple[dict, str]:
    """
    Returns (updated_json, updated_text).
    Raises ValueError if Claude can't produce a schema-valid result.
    """
    user_content = (
        f"CURRENT RESUME:\n{json.dumps(resume_json, indent=2)}\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"MISSING KEYWORDS TO INCORPORATE (only where genuinely supported):\n"
        f"{', '.join(missing_keywords) if missing_keywords else 'None identified'}"
    )

    updated_json = await generate_resume_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
    )

    updated_text = render_resume_text(updated_json)
    return updated_json, updated_text