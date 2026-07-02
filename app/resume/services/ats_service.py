"""
ats_service.py
--------------
Two distinct scoring functions — because ATS score means different things
depending on whether a job description is available.

PROBLEM WITH THE OLD APPROACH:
  1. calculate_ats_score(text) with no JD used a hardcoded AI/ML keyword list
     as fallback — completely meaningless for non-AI resumes. A marketing resume
     would score ~0 on keywords for no reason.

  2. calculate_ats_score(text, jd) after optimize-for-job inflated to ~100
     because Claude rewrote the resume to mirror the JD verbatim — the extracted
     keyword pool and the resume text matched almost perfectly. Not a real signal.

  3. Two different scoring systems (ats_service and job_match_service) used
     different algorithms and different scales — the numbers disagreed and
     confused users.

THE FIX — two separate functions with honest, distinct purposes:

  calculate_quality_score(resume_text)
    → Always available, no JD needed.
    → Measures structural quality only: sections, action verbs, metrics,
      formatting. Nothing JD-dependent.
    → Score label in the UI: "Resume Quality Score"
    → Range: 0–100, honest and stable across sessions.

  calculate_ats_match(resume_text, job_description)
    → Only called when a JD is available (job-match, optimize-for-job).
    → Uses the SAME algorithm as job_match_service.calculate_match() so
      the numbers are consistent — no more "100 after optimize, 60 after re-match".
    → Score label in the UI: "ATS Match Score"
    → Range: 0–100.

Routes updated:
  /upload          → calculate_quality_score only (no JD available)
  /chat            → calculate_quality_score only (general edit, no JD)
  /job-match       → calculate_match from job_match_service (unchanged)
  /optimize-for-job → calculate_ats_match (same algorithm as job-match)
  /ats-score       → calculate_quality_score (standalone quality check)
"""

import re
from collections import Counter


# ── Shared constants ──────────────────────────────────────────────────────────

ACTION_VERBS = [
    "built", "developed", "designed", "implemented", "optimized",
    "engineered", "led", "created", "improved", "launched", "scaled",
    "architected", "delivered", "automated", "reduced", "increased",
    "deployed", "migrated", "refactored", "integrated", "managed",
    "mentored", "collaborated", "drove", "streamlined", "established",
    "spearheaded", "transformed", "accelerated", "generated", "secured",
]

SECTION_VARIANTS = {
    "education":  ["education"],
    "skills":     ["technical skills", "skills", "core competencies"],
    "experience": ["work experience", "experience", "employment"],
    "projects":   ["projects", "personal projects", "key projects"],
}

METRIC_PATTERNS = [
    r"\d+\s*%",                # 40%
    r"\$[\d,.]+[KkMmBb]?",    # $1.2M, $500K
    r"\d+[Xx×]",              # 3x, 2X
    r"\d+\+",                 # 50+
    r"\d[\d,]*\s+(?:users|requests|engineers|countries|clients|languages|"
    r"teams|systems|services|applications|products)",
]

STOP_WORDS = {
    "the", "and", "with", "for", "this", "that", "have", "will", "your",
    "from", "using", "into", "their", "they", "our", "you", "are", "not",
    "but", "all", "can", "its", "any", "has", "was", "were", "been",
    "being", "about", "more", "who", "also", "what", "when", "where",
    "able", "work", "team", "strong", "good", "great", "ability", "must",
    "should", "would", "could", "look", "looking", "join", "help",
    "experience", "skills", "role", "position", "job", "company",
    "candidate", "responsibilities", "requirements", "preferred",
    "opportunity", "environment", "culture", "growth", "learning",
}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _extract_terms(text: str) -> tuple[set[str], set[str]]:
    """
    Returns (bigrams, single_words) — the same algorithm used by
    job_match_service so scores are consistent across both.
    """
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+\-#./]{1,}\b", text.lower())
    clean = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    bigrams = {
        clean[i] + " " + clean[i + 1]
        for i in range(len(clean) - 1)
    }
    singles = set(clean)
    return bigrams, singles


def _count_metrics(resume_text: str) -> int:
    return sum(
        len(re.findall(p, resume_text, re.IGNORECASE))
        for p in METRIC_PATTERNS
    )


def _count_action_verbs(text_lower: str) -> int:
    return sum(text_lower.count(v) for v in ACTION_VERBS)


# ── Function 1: Resume Quality Score (no JD needed) ──────────────────────────

def calculate_quality_score(resume_text: str) -> dict:
    """
    Measures intrinsic resume quality — structure, language strength, and
    quantification. No job description needed or used.

    Scoring breakdown (total 100):
      Sections   — 40 pts (4 sections × 10 each)
      Action verbs — 30 pts
      Metrics    — 30 pts

    Label in UI: "Resume Quality Score"
    Show on: upload, after chat edits, standalone /ats-score endpoint.
    """
    text = resume_text.lower()
    recommendations: list[str] = []

    # ── Sections (40 pts) ────────────────────────────────────────────────
    section_score = 0
    for section_name, variants in SECTION_VARIANTS.items():
        if any(v in text for v in variants):
            section_score += 10
        else:
            readable = section_name.replace("_", " ").title()
            recommendations.append(f"Add a clear '{readable}' section heading.")

    # ── Action verbs (30 pts) ────────────────────────────────────────────
    action_count = _count_action_verbs(text)
    action_score = min(30, action_count * 2)

    if action_score < 12:
        recommendations.append(
            "Use stronger action verbs: built, engineered, launched, optimized, scaled."
        )

    # ── Quantified metrics (30 pts) ──────────────────────────────────────
    metrics_found = _count_metrics(resume_text)
    metric_score  = min(30, metrics_found * 3)

    if metric_score < 12:
        recommendations.append(
            "Quantify your impact — add percentages, dollar values, or scale numbers "
            "(e.g. 'reduced load time by 40%', 'managed team of 6')."
        )

    overall_score = section_score + action_score + metric_score

    return {
        "score_type":       "quality",
        "overall_score":    overall_score,
        # Sub-scores — same field names as calculate_ats_match so
        # the frontend uses identical rendering logic for both.
        "keyword_score":    None,   # no JD available — frontend shows "–" not NaN
        "section_score":    section_score,
        "action_score":     action_score,
        "metric_score":     metric_score,
        "matched_phrases":  [],
        "matched_keywords": [],
        "missing_keywords": [],
        "recommendations":  recommendations,
    }


# ── Function 2: ATS Match Score (requires JD) ─────────────────────────────────

def calculate_ats_match(resume_text: str, job_description: str) -> dict:
    """
    Measures how well this resume matches a specific job description.
    Uses the same keyword-overlap algorithm as job_match_service.calculate_match()
    so scores are consistent — no more "100 after optimize, 60 after re-match".

    Also runs the structural breakdown (sections, verbs, metrics) so the
    frontend always receives all four sub-score fields and never shows NaN.

    overall_score = weighted blend:
      60% keyword match (JD relevance — the most important signal)
      40% structural quality (sections, verbs, metrics)

    Label in UI: "ATS Match Score"
    """
    # ── Keyword match (60% weight) ────────────────────────────────────────
    resume_bigrams, resume_words = _extract_terms(resume_text)
    jd_bigrams,    jd_words      = _extract_terms(job_description)

    matched_phrases = resume_bigrams & jd_bigrams
    missing_phrases = jd_bigrams    - resume_bigrams
    matched_words   = resume_words  & jd_words
    missing_words   = jd_words      - resume_words

    total_jd_terms  = len(jd_bigrams) * 2 + len(jd_words)
    matched_weight  = len(matched_phrases) * 2 + len(matched_words)
    keyword_score   = min(100, int(matched_weight / max(total_jd_terms, 1) * 100))

    top_missing = sorted(missing_phrases)[:10] + sorted(missing_words)[:10]

    # ── Structural quality (40% weight) — same as calculate_quality_score ─
    text = resume_text.lower()

    section_score = sum(
        10 for variants in SECTION_VARIANTS.values()
        if any(v in text for v in variants)
    )

    action_count  = _count_action_verbs(text)
    action_score  = min(30, action_count * 2)

    metrics_found = _count_metrics(resume_text)
    metric_score  = min(30, metrics_found * 3)

    quality_score = section_score + action_score + metric_score   # 0–100

    # ── Blended overall score ─────────────────────────────────────────────
    overall_score = min(100, int(keyword_score * 0.6 + quality_score * 0.4))

    # ── Recommendations ───────────────────────────────────────────────────
    recommendations: list[str] = []
    if keyword_score < 50:
        recommendations.append(
            "Keyword match is low — incorporate more terms from the job description naturally."
        )
    if keyword_score < 75:
        recommendations.append(
            "Focus on matching the specific tools and technologies mentioned in the JD."
        )
    if action_score < 12:
        recommendations.append(
            "Use stronger action verbs: built, engineered, launched, optimized, scaled."
        )
    if metric_score < 12:
        recommendations.append(
            "Quantify your impact — add percentages, dollar values, or scale numbers."
        )

    return {
        "score_type":       "ats_match",
        "overall_score":    overall_score,
        # Sub-scores the frontend displays in the four breakdown bars
        "keyword_score":    keyword_score,
        "section_score":    section_score,
        "action_score":     action_score,
        "metric_score":     metric_score,
        # Keyword details
        "matched_phrases":  sorted(matched_phrases)[:20],
        "matched_keywords": sorted(matched_words)[:30],
        "missing_keywords": top_missing[:20],
        "recommendations":  recommendations,
    }


# ── Backwards-compat shim ─────────────────────────────────────────────────────
# Old call sites that pass job_description still work. New code should call
# calculate_quality_score() or calculate_ats_match() directly.

def calculate_ats_score(
    resume_text: str,
    job_description: str | None = None,
) -> dict:
    """
    Backwards-compatible wrapper.
    Prefer calling calculate_quality_score() or calculate_ats_match() directly.
    """
    if job_description:
        return calculate_ats_match(resume_text, job_description)
    return calculate_quality_score(resume_text)