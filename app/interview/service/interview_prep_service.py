"""
interview_prep_service.py
--------------------------
Generates interview prep content for a given job application.

Uses OpenAI (gpt-4.1-mini) — same pattern as embedding_service.py.
Three sections generated in parallel via asyncio.gather():
  1. questions        — behavioral + technical, JD-aware if provided
  2. company_brief    — interview culture, what they look for, red flags
  3. answer_frameworks — STAR starters, personalised if resume provided

All three use JSON mode (response_format=json_object) so the output is
always valid JSON — no markdown fence stripping needed.
"""

import asyncio
import json

from openai import AsyncOpenAI
from app.common.config import OPENAI_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

MODEL      = "gpt-4.1-mini"   # cheap, fast, handles structured JSON well
MAX_TOKENS = 1200


# ── System prompts ────────────────────────────────────────────────────────────

_QUESTIONS_SYSTEM = """You are a senior technical recruiter and interview coach.
Generate interview questions for the given role and company.

Return a JSON object with this exact shape:
{
  "behavioral": [
    {"question": "...", "why_asked": "one sentence, max 12 words"}
  ],
  "technical": [
    {"question": "...", "why_asked": "one sentence, max 12 words"}
  ]
}

Rules:
- Exactly 5 behavioral and 5 technical questions
- Behavioral: use STAR-triggering language ("Tell me about a time...")
- Technical: specific to the role and company's known domain/stack
- If a job description is provided, pull questions from its actual
  requirements — do not invent requirements not in the JD
- Return only valid JSON, no markdown"""


_COMPANY_SYSTEM = """You are an interview coach with deep knowledge of how
top companies hire.

Return a JSON object with this exact shape:
{
  "interview_style": "2-3 sentences on how this company typically interviews",
  "what_they_value": ["trait 1", "trait 2", "trait 3", "trait 4"],
  "red_flags_to_avoid": ["thing to avoid 1", "thing to avoid 2", "thing to avoid 3"],
  "tips": ["specific tip 1", "specific tip 2", "specific tip 3"],
  "typical_process": "1-2 sentences on their typical hiring stages"
}

Base this on the company's known culture and publicly known interview
practices. Be honest — if they're known for hard leetcode, say so.
Return only valid JSON, no markdown."""


_ANSWERS_SYSTEM = """You are an expert career coach who writes STAR-format
interview answer frameworks.

Return a JSON object with this exact shape:
{
  "frameworks": [
    {
      "question": "the behavioral question",
      "situation": "1-2 sentences setting up a realistic situation",
      "task": "1 sentence on what the candidate was responsible for",
      "action": "2-3 sentences on specific actions taken",
      "result": "1 sentence with a measurable outcome",
      "tip": "one coaching tip for delivering this answer well"
    }
  ]
}

Rules:
- 3 frameworks for the top 3 behavioral questions for this role
- If candidate experience is provided, use REAL companies, projects,
  and metrics — do not invent experience not in their background
- If no resume provided, write realistic placeholders using [metric]
  or [company] as fill-in markers the candidate can adapt
- Return only valid JSON, no markdown"""


# ── Individual generators ─────────────────────────────────────────────────────

async def _generate_questions(
    company: str,
    role: str,
    job_description: str | None,
) -> dict:
    jd_section = (
        f"\nJOB DESCRIPTION:\n{job_description[:2000]}"
        if job_description else ""
    )
    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _QUESTIONS_SYSTEM},
            {"role": "user",   "content": (
                f"COMPANY: {company}\n"
                f"ROLE: {role}"
                f"{jd_section}"
            )},
        ],
    )
    return json.loads(response.choices[0].message.content)


async def _generate_company_brief(company: str, role: str) -> dict:
    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=600,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _COMPANY_SYSTEM},
            {"role": "user",   "content": f"COMPANY: {company}\nROLE: {role}"},
        ],
    )
    return json.loads(response.choices[0].message.content)


async def _generate_answer_frameworks(
    company: str,
    role: str,
    resume_text: str | None,
) -> dict:
    resume_section = (
        f"\nCANDIDATE EXPERIENCE (personalise answers using this):\n{resume_text[:1500]}"
        if resume_text
        else "\n(No resume provided — use [metric] and [company] placeholders)"
    )
    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _ANSWERS_SYSTEM},
            {"role": "user",   "content": (
                f"COMPANY: {company}\n"
                f"ROLE: {role}"
                f"{resume_section}"
            )},
        ],
    )
    return json.loads(response.choices[0].message.content)


# ── Entry point ───────────────────────────────────────────────────────────────

async def generate_interview_prep(
    company_name: str,
    role: str,
    job_description: str | None = None,
    resume_text: str | None = None,
) -> dict:
    """
    Runs all three OpenAI calls in parallel.
    Total time = slowest of the three (~4-6s), not their sum.

    Returns:
    {
        "questions": {
            "behavioral": [{"question": "...", "why_asked": "..."}],
            "technical":  [{"question": "...", "why_asked": "..."}]
        },
        "company_brief": {
            "interview_style": "...",
            "what_they_value": [...],
            "red_flags_to_avoid": [...],
            "tips": [...],
            "typical_process": "..."
        },
        "answer_frameworks": {
            "frameworks": [{
                "question": "...",
                "situation": "...",
                "task": "...",
                "action": "...",
                "result": "...",
                "tip": "..."
            }]
        },
        "is_personalised": bool,
        "has_jd": bool
    }
    """
    questions, company_brief, answer_frameworks = await asyncio.gather(
        _generate_questions(company_name, role, job_description),
        _generate_company_brief(company_name, role),
        _generate_answer_frameworks(company_name, role, resume_text),
    )

    return {
        "questions":         questions,
        "company_brief":     company_brief,
        "answer_frameworks": answer_frameworks,
        "is_personalised":   resume_text is not None,
        "has_jd":            job_description is not None,
    }