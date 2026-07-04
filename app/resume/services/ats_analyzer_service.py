"""
ats_analyzer_service.py
------------------------
The only AI service in the new resume module.

Takes resume plain text + job description → returns a genuine, accurate
ATS analysis with:
  - Overall ATS match score (0-100)
  - Section-by-section breakdown
  - Exact missing keywords from the JD
  - Specific actionable gaps (not generic advice)
  - What's already strong

Uses OpenAI gpt-4.1-mini with JSON mode for structured, consistent output.
No Claude tool-use, no schema enforcement overhead — just a focused prompt
that returns a clean JSON analysis.

WHY THIS IS MORE ACCURATE THAN THE OLD APPROACH:
  Old: keyword overlap score (bigram matching) — missed synonyms,
       didn't understand context, gave inflated scores.
  New: LLM reads both documents and reasons about match quality the way
       a real ATS/recruiter would — understands that "led a team" matches
       "team leadership", not just exact string overlap.
"""

import json
from openai import AsyncOpenAI
from app.common.config import OPENAI_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

MODEL = "gpt-4.1-mini"

_SYSTEM = """You are a senior ATS (Applicant Tracking System) expert and technical recruiter
with 15+ years of experience. You have deep knowledge of how real ATS systems score resumes
and what hiring managers actually look for.

Analyse the resume against the job description and return a JSON object with this exact shape:

{
  "overall_score": <integer 0-100>,
  "score_breakdown": {
    "keyword_match": {
      "score": <integer 0-40>,
      "max": 40,
      "comment": "<one sentence explaining the score>"
    },
    "skills_alignment": {
      "score": <integer 0-25>,
      "max": 25,
      "comment": "<one sentence>"
    },
    "experience_relevance": {
      "score": <integer 0-20>,
      "max": 20,
      "comment": "<one sentence>"
    },
    "education_fit": {
      "score": <integer 0-10>,
      "max": 10,
      "comment": "<one sentence>"
    },
    "resume_structure": {
      "score": <integer 0-5>,
      "max": 5,
      "comment": "<one sentence>"
    }
  },
  "matched_keywords": [
    "<keyword or phrase from JD that appears in resume>"
  ],
  "missing_keywords": [
    "<important keyword or phrase from JD missing from resume>"
  ],
  "skill_gaps": [
    {
      "skill": "<specific skill or tool>",
      "importance": "required" | "preferred",
      "reason": "<one sentence: why this matters for the role>"
    }
  ],
  "experience_gaps": [
    "<specific experience or responsibility from JD not demonstrated in resume>"
  ],
  "strengths": [
    "<specific thing in the resume that strongly matches the JD>"
  ],
  "improvements": [
    {
      "section": "<which section of the resume>",
      "issue": "<specific problem>",
      "suggestion": "<concrete fix — what exactly to add or change>"
    }
  ],
  "verdict": "<2-3 sentence honest overall assessment — would a recruiter pass this resume to the next stage?>"
}

SCORING RULES — be honest and accurate:
- overall_score = sum of all breakdown scores
- keyword_match: count important JD keywords/phrases present in resume.
  Use semantic understanding — "managed a team" matches "team leadership".
  Penalise heavily for missing role-critical terms.
- skills_alignment: how well the skills section matches JD requirements.
  Distinguish between required vs preferred skills.
- experience_relevance: does the work history demonstrate the core
  responsibilities of this role? Years of relevant experience matters.
- education_fit: does the degree/field match? Overqualified counts as full score.
- resume_structure: are sections clear, ATS-readable, no tables/graphics issues?
- Do NOT inflate scores. A 90+ score should mean the resume is nearly perfect
  for this specific role. Most resumes score 40-70.
- missing_keywords: list the most important ones first. Include tools, frameworks,
  methodologies, and domain-specific terms from the JD.
- improvements: be specific. "Add X to skills section" not "improve skills".

Return only the JSON object. No markdown, no preamble."""


async def analyze_resume_against_jd(
    resume_text: str,
    job_description: str,
) -> dict:
    """
    Returns a full ATS analysis dict.
    Raises ValueError if parsing fails.
    """
    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        temperature=0.1,   # low temp for consistent, accurate scoring
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"RESUME:\n{resume_text}\n\n"
                f"JOB DESCRIPTION:\n{job_description}"
            )},
        ],
    )

    raw = response.choices[0].message.content
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse ATS analysis response: {e}\nRaw: {raw[:200]}")