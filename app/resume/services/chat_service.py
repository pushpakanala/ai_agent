"""
chat_service.py
----------------
Applies a natural-language edit instruction to a resume, using Claude
constrained to ResumeData via forced tool use (see claude_client.py) —
replaces the old OpenAI json_object call.
"""

import json

from app.resume.services.claude_client import generate_resume_json
from app.resume.services.resume_renderer import render_resume_text


SYSTEM_PROMPT = """You are a world-class ATS resume writer, technical
recruiter, and career coach.

You will be given the candidate's CURRENT resume (as structured data) and
an instruction describing a change to make. Apply the instruction and emit
the ENTIRE updated resume via the emit_resume tool.

Critical rules:
1. ALWAYS return the ENTIRE updated resume — never only the changed section.
2. Preserve ALL existing sections unless explicitly asked to remove them.
3. Make every modification ATS-friendly; use strong action verbs and
   quantify impact where appropriate.
4. Do NOT invent companies, experience, certifications, or skills that
   aren't already present or explicitly provided in the instruction.
5. Improve keyword density naturally — never keyword-stuff.
"""


async def modify_resume(
    current_resume_json: dict,
    user_instruction: str,
):
    user_content = (
        f"CURRENT RESUME:\n{json.dumps(current_resume_json, indent=2)}\n\n"
        f"INSTRUCTION:\n{user_instruction}"
    )

    updated_json = await generate_resume_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
    )

    # ------------------------------------
    # Safety checks
    # ------------------------------------
    # NOTE: the old "missing required key" loop is no longer needed here —
    # generate_resume_json() already guarantees the shape is valid (every
    # ResumeData field is present, since Pydantic validated it). What's
    # still worth guarding against is a *business-logic* regression: the
    # shape being valid doesn't mean the model didn't wipe out real content.

    if len(updated_json.get("experience", [])) == 0:
        raise Exception("Experience section vanished.")

    if len(updated_json.get("education", [])) == 0:
        raise Exception("Education section vanished.")

    updated_text = render_resume_text(updated_json)

    return updated_json, updated_text
