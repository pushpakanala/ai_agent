"""
chat_service.py
----------------
Token optimization: resume JSON sent as compact (no indent) instead of
indent=2. Saves ~200 tokens per call with zero information loss.
"""

import json
from app.resume.services.claude_client import generate_resume_json
from app.resume.services.resume_renderer import render_resume_text


SYSTEM_PROMPT = """You are an ATS resume writer and career coach.

Given the candidate's CURRENT resume and an INSTRUCTION, apply the change
and emit the ENTIRE updated resume via emit_resume.

Rules:
1. Return the ENTIRE resume — never only the changed section.
2. Preserve ALL existing sections unless told to remove them.
3. Keep edits ATS-friendly: strong action verbs, quantified impact.
4. Never invent companies, roles, skills, or certifications.
5. Never keyword-stuff."""


async def modify_resume(current_resume_json: dict, user_instruction: str):
    # Compact JSON — saves ~200 tokens vs indent=2 with no info loss
    user_content = (
        f"CURRENT RESUME:\n{json.dumps(current_resume_json, separators=(',', ':'))}\n\n"
        f"INSTRUCTION:\n{user_instruction}"
    )

    updated_json = await generate_resume_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
    )

    if not updated_json.get("experience"):
        raise Exception("Experience section missing from updated resume.")
    if not updated_json.get("education"):
        raise Exception("Education section missing from updated resume.")

    return updated_json, render_resume_text(updated_json)