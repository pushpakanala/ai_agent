"""
ats_service.py
--------------
ATS score calculation.

IMPROVEMENTS over original:
  1. Accepts an optional job_description so keyword scoring is dynamic
     (matched against the actual JD) rather than a hardcoded tech list.
  2. Checks for more section variants (e.g. "experience" OR "work experience").
  3. More action verbs, better metric patterns (handles "$1.2M", "2x", "3×").
  4. Keyword score now uses TF-presence, not substring of a fixed list.
  5. Returns richer breakdown: matched_keywords, missing_keywords, category scores.
"""

import re
from collections import Counter


# ─── Generic action verbs (always evaluated) ─────────────────────────────────
ACTION_VERBS = [
    "built", "developed", "designed", "implemented", "optimized",
    "engineered", "led", "created", "improved", "launched", "scaled",
    "architected", "delivered", "automated", "reduced", "increased",
    "deployed", "migrated", "refactored", "integrated", "managed",
    "mentored", "collaborated", "drove", "streamlined",
]

# ─── Fallback keyword list when no JD is provided ────────────────────────────
FALLBACK_KEYWORDS = [
    "python", "fastapi", "machine learning", "deep learning", "llm",
    "generative ai", "rag", "langchain", "langgraph", "faiss",
    "chromadb", "docker", "kubernetes", "aws", "mongodb", "sql",
    "rest api", "microservices", "ci/cd", "react", "typescript",
]

# Section headings to detect (any one variant counts)
SECTION_VARIANTS = {
    "education":   ["education"],
    "skills":      ["technical skills", "skills", "core competencies"],
    "experience":  ["work experience", "experience", "employment"],
    "projects":    ["projects", "personal projects", "key projects"],
}


def _extract_jd_keywords(job_description: str) -> list[str]:
    """Pull meaningful words from a job description for keyword matching."""
    stop = {
        "the", "and", "with", "for", "this", "that", "have", "will", "your",
        "from", "using", "into", "their", "they", "our", "you", "are", "not",
        "but", "all", "can", "its", "any", "has", "was", "were", "been",
        "being", "about", "more", "who", "also", "what", "when", "where",
        "able", "work", "team", "skills", "experience", "role", "position",
    }
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+\-#./]{1,}\b", job_description.lower())
    # Multi-word tech terms
    bigrams = [
        words[i] + " " + words[i + 1]
        for i in range(len(words) - 1)
        if words[i] not in stop and words[i + 1] not in stop
    ]
    singles = [w for w in words if w not in stop and len(w) > 2]
    # Frequency-weighted: keep terms appearing 2+ times, or all bigrams
    freq = Counter(singles)
    important = [w for w, c in freq.items() if c >= 2]
    return list(set(important + bigrams))


def calculate_ats_score(
    resume_text: str,
    job_description: str | None = None,
) -> dict:
    text = resume_text.lower()
    recommendations: list[str] = []

    # ── 1. Section presence (25 pts) ────────────────────────────────────
    section_score = 0
    for section_name, variants in SECTION_VARIANTS.items():
        if any(v in text for v in variants):
            section_score += 25
        else:
            readable = section_name.replace("_", " ").title()
            recommendations.append(f"Add a clear '{readable}' section heading.")

    # ── 2. Keyword score (40 pts) ────────────────────────────────────────
    if job_description:
        keyword_pool = _extract_jd_keywords(job_description)
    else:
        keyword_pool = FALLBACK_KEYWORDS

    matched_keywords = [kw for kw in keyword_pool if kw in text]
    missing_keywords = [kw for kw in keyword_pool if kw not in text]

    keyword_score = min(40, int(len(matched_keywords) / max(len(keyword_pool), 1) * 40))

    if keyword_score < 20:
        if job_description:
            recommendations.append(
                "Keyword match is low — incorporate more terms from the job description."
            )
        else:
            recommendations.append("Add more relevant technical keywords to your resume.")

    # ── 3. Quantified metrics (20 pts) ──────────────────────────────────
    metric_patterns = [
        r"\d+\s*%",            # 40%
        r"\$[\d,.]+[KkMmBb]?", # $1.2M, $500K
        r"\d+[Xx×]",           # 3x, 2X
        r"\d+\+",              # 50+
        r"\d[\d,]*\s+(?:users|requests|engineers|countries|clients|languages)",
    ]
    metrics_found = sum(
        len(re.findall(p, resume_text, re.IGNORECASE))
        for p in metric_patterns
    )
    metric_score = min(20, metrics_found * 2)

    if metric_score < 8:
        recommendations.append(
            "Quantify your impact — add percentages, dollar values, or scale numbers."
        )

    # ── 4. Action verbs (15 pts) ─────────────────────────────────────────
    action_count = sum(text.count(v) for v in ACTION_VERBS)
    action_score = min(15, action_count)

    if action_score < 6:
        recommendations.append(
            "Use stronger action verbs: built, optimized, engineered, launched, scaled, etc."
        )

    # ── Overall ──────────────────────────────────────────────────────────
    overall_score = min(100, section_score + keyword_score + metric_score + action_score)

    return {
        "overall_score":     overall_score,
        "section_score":     section_score,
        "keyword_score":     keyword_score,
        "metric_score":      metric_score,
        "action_score":      action_score,
        "matched_keywords":  matched_keywords[:30],   # cap for response size
        "missing_keywords":  missing_keywords[:30],
        "recommendations":   recommendations,
    }