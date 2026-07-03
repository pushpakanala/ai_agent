"""
analyze_service.py
------------------
Token optimizations:
  - Uses render_resume_text() (plain text) instead of JSON — saves ~400
    tokens per analyze call since analysis is read-only (no schema needed)
  - Uses Haiku via generate_text() — ~20x cheaper than Sonnet for prose
  - System prompts trimmed of redundant instructions
  - max_tokens capped per mode (critique needs more than quick_wins)
"""

from app.resume.services.claude_client import generate_text
from app.resume.services.resume_renderer import render_resume_text


_BASE_SYSTEM = """You are a senior recruiter and career coach with 15+ years
hiring for top technology companies. Give direct, honest, actionable feedback.
Quote specific weak phrases. Show concrete before/after examples.
Format with ## markdown headings. Be concise — under 500 words unless the
task genuinely requires more."""


_MODE_PROMPTS = {

    "recruiter_scan": (
        "Do a 10-second recruiter scan. Respond with:\n"
        "## What immediately stands out (good)\n"
        "## What feels forgettable or unclear\n"
        "## First impression verdict\n"
        "## One thing to fix right now\n"
        "Be blunt."
    ),

    "deep_critique": (
        "Systematically find every weakness. For each issue: quote the text, "
        "explain why it hurts, give a fix. Respond with:\n"
        "## Critical issues (will get resume skipped)\n"
        "## Moderate issues (weaken the application)\n"
        "## What is working well\n"
        "## Priority fix order (numbered)"
    ),

    "bullet_audit": (
        "Audit every bullet in experience and projects. Classify each as "
        "STRONG, WEAK, or FIXABLE. Rewrite every WEAK and FIXABLE bullet "
        "using: [Action verb] + [what you did] + [measurable result].\n"
        "End with: ## Overall bullet quality (X/10)"
    ),

    "positioning": (
        "Analyse whether this resume has clear positioning. Respond with:\n"
        "## Current positioning (what the resume says about this person)\n"
        "## Positioning gaps\n"
        "## Industry language missing\n"
        "## Rewritten summary\n"
        "## Skills section recommendations"
    ),

    "final_polish": (
        "Final polish pass. Hunt for: inconsistent tense, repetitive openers, "
        "vague phrases ('responsible for', 'helped with', 'worked on'), weak "
        "verbs, overused corporate language. Respond with:\n"
        "## Issues found (quote each, explain why weak, give stronger alternative)\n"
        "## Formatting and consistency issues\n"
        "## Polish score (X/10) and verdict"
    ),

    "quick_wins": (
        "Identify the 3 highest-impact changes the candidate can make right now. "
        "Respond with:\n"
        "## Quick win #1 — [title]\n"
        "## Quick win #2 — [title]\n"
        "## Quick win #3 — [title]\n"
        "## Why these 3 matter most"
    ),

    "free": (
        "Answer the candidate's question directly and specifically. "
        "Reference specific parts of their resume. "
        "Use ## headings if covering multiple points."
    ),
}

# Per-mode output token caps — don't over-allocate for simple modes
_MODE_MAX_TOKENS = {
    "recruiter_scan": 500,
    "deep_critique":  800,
    "bullet_audit":   900,   # needs room for rewrites
    "positioning":    600,
    "final_polish":   700,
    "quick_wins":     400,
    "free":           600,
}


async def analyze_resume(
    resume_json: dict,
    mode: str,
    custom_message: str = "",
) -> str:
    """
    Returns markdown feedback. No version saved. Uses Haiku (cheap + fast).
    Sends plain text resume (not JSON) since analysis is read-only.
    """
    mode_prompt = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["free"])
    system_prompt = f"{_BASE_SYSTEM}\n\n{mode_prompt}"

    # Plain text is ~4x more token-efficient than JSON for read-only calls
    resume_text = render_resume_text(resume_json)

    if mode == "free" and not custom_message:
        raise ValueError("custom_message is required for free-form analysis.")

    user_content = f"RESUME:\n{resume_text}"
    if custom_message:
        user_content += f"\n\nQUESTION / REQUEST:\n{custom_message}"

    return await generate_text(
        system_prompt=system_prompt,
        user_content=user_content,
        max_tokens=_MODE_MAX_TOKENS.get(mode, 600),
        temperature=0.3,
    )