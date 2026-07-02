"""
analyze_service.py  (NEW)
--------------------------
Handles all analysis/critique prompts — requests where the user wants
feedback ON their resume rather than an edit TO it.

Uses generate_text() (plain text, no tool use) so:
  - No schema enforcement needed
  - No version created
  - Response is structured markdown feedback, not a JSON resume

Six analysis modes, each with a specialist system prompt:

  1. recruiter_scan     — 10-second first-impression test
  2. deep_critique      — find every weakness
  3. bullet_audit       — score each bullet point
  4. positioning        — industry alignment check
  5. final_polish       — executive-level language refinement
  6. quick_wins         — top 3 highest-impact changes
  7. free               — any custom analysis question the user types
"""

import json
from app.resume.services.claude_client import generate_text
from app.resume.services.resume_renderer import render_resume_text


# ── System prompt shared by all analysis modes ────────────────────────────────

_BASE_SYSTEM = """You are a senior recruiter and career coach with 15+ years
of experience hiring for top-tier technology companies. You give direct,
honest, actionable feedback — no filler, no flattery.

When you identify problems, be specific: quote the exact phrase or section
that is weak and explain precisely why. When you suggest improvements,
show a concrete before/after example wherever possible.

Format your response with clear section headings using markdown (##).
Keep the total response under 600 words unless the user's question
specifically requires more depth."""


# ── Per-mode specialist prompts ───────────────────────────────────────────────

_MODE_PROMPTS = {

    "recruiter_scan": """You are doing a 10-second recruiter scan.
Look at the resume the way a recruiter does when they are processing
100+ applications and deciding in seconds whether to read further.

Structure your response as:
## What immediately stands out (good)
## What feels forgettable or unclear
## First impression verdict
## One thing to fix right now

Be blunt. The user needs to know if this resume gets them to the next round
or gets skipped.""",

    "deep_critique": """You are a highly competitive hiring manager reviewing
candidates for a role that gets 500+ applications.

Analyse every section systematically. For each weakness found:
- Quote the specific text
- Explain why it hurts the candidate
- Give a concrete fix

Structure your response as:
## Critical issues (will get this resume skipped)
## Moderate issues (weaken the application)
## Minor issues (polish items)
## What is actually working well
## Priority fix order (numbered list, most important first)""",

    "bullet_audit": """You are auditing every bullet point in the
experience and projects sections for impact and specificity.

For each bullet, classify it as:
  STRONG — specific, quantified, action-led
  WEAK   — vague, responsibility-focused, or generic
  FIXABLE — has potential but needs a rewrite

Then provide:
## Bullet audit results (STRONG / WEAK / FIXABLE for each)
## Rewrites for every WEAK and FIXABLE bullet
## Overall bullet quality score (X/10) with reasoning

When rewriting, use the format: [Action verb] + [what you did] +
[measurable result]. If a metric is missing, suggest what the candidate
should try to quantify.""",

    "positioning": """You are a market positioning consultant specialising
in professional profiles.

Analyse whether this resume clearly communicates:
- What type of role this person is targeting
- What makes them different from other candidates at the same level
- Whether the summary and skills section use the right industry language

Structure your response as:
## Current positioning (what the resume says about this person)
## Positioning gaps (what is unclear or generic)
## Language and terminology audit (industry-specific terms missing)
## Rewritten summary (show a stronger version)
## Skills section recommendations""",

    "final_polish": """You are an executive resume writer doing a final
polish pass before submission to a top-tier company.

Hunt for:
- Inconsistent tense or formatting
- Repetitive sentence openers
- Vague or overused corporate phrases ("responsible for", "helped with",
  "worked on", "collaborated with", "assisted in")
- Anything that sounds junior, generic, or low-confidence
- Weak verbs that should be stronger

Structure your response as:
## Language issues found (quote each one, explain why it's weak)
## Stronger alternatives for each flagged phrase
## Formatting and consistency issues
## Overall polish score (X/10)
## Final verdict: ready to send or needs more work?""",

    "quick_wins": """You are a career coach who has 5 minutes with this
candidate before they submit their application.

Identify the 3 highest-impact changes they can make RIGHT NOW —
changes that will meaningfully improve their chances without requiring
a full rewrite.

Structure your response as:
## Quick win #1 — [title]
What to change, exactly where, and why it matters.

## Quick win #2 — [title]
What to change, exactly where, and why it matters.

## Quick win #3 — [title]
What to change, exactly where, and why it matters.

## Why these 3 matter most
One short paragraph on the cumulative effect of these changes.""",

    "free": """The user has a specific question about their resume.
Answer it directly, specifically, and with actionable advice.
Reference specific parts of their resume in your answer.
Use markdown headings to structure your response if it covers
multiple points.""",
}


# ── Entry point ───────────────────────────────────────────────────────────────

async def analyze_resume(
    resume_json: dict,
    mode: str,
    custom_message: str = "",
) -> str:
    """
    Run an analysis on the resume and return plain-text markdown feedback.
    No version is created. No schema is enforced.

    Args:
        resume_json:    The current optimized_resume_json from MongoDB.
        mode:           One of the keys in _MODE_PROMPTS, or "free".
        custom_message: Required when mode == "free". Optional additional
                        context for any other mode.

    Returns:
        A markdown-formatted string ready to display in the UI.
    """
    mode_prompt = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["free"])
    system_prompt = f"{_BASE_SYSTEM}\n\n{mode_prompt}"

    # Render the resume as clean plain text — easier for the model to
    # read than raw JSON, and avoids leaking schema internals into the prompt.
    resume_text = render_resume_text(resume_json)

    if mode == "free" and not custom_message:
        raise ValueError("custom_message is required for free-form analysis.")

    if custom_message:
        user_content = (
            f"RESUME:\n{resume_text}\n\n"
            f"MY QUESTION / REQUEST:\n{custom_message}"
        )
    else:
        user_content = f"RESUME:\n{resume_text}"

    return await generate_text(
        system_prompt=system_prompt,
        user_content=user_content,
        max_tokens=1200,   # analysis needs more room than cover letters
        temperature=0.3,   # low temp = consistent, structured critique
    )