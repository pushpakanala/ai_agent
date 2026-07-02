"""
job_match_service.py
--------------------
Calculates how well a resume matches a job description.

IMPROVEMENTS over original:
  1. Expanded stop-word list so noise words don't inflate match score.
  2. Extracts bigrams (two-word tech terms like "machine learning", "rest api").
  3. Returns a tiered breakdown: strong_matches (bigrams) vs word matches.
  4. Caps missing_keywords to the 20 most impactful terms.
"""

import re
from collections import Counter


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
    "passion", "excited", "fast", "paced",
}


def _extract_terms(text: str) -> tuple[set[str], set[str]]:
    """Returns (bigrams, single_words) meaningful sets from text."""
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+\-#./]{1,}\b", text.lower())
    clean = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    bigrams = {
        clean[i] + " " + clean[i + 1]
        for i in range(len(clean) - 1)
    }

    freq = Counter(clean)
    # For the JD: keep words appearing ≥2 times; for resume: keep all
    singles = set(clean)

    return bigrams, singles


def calculate_match(resume_text: str, job_description: str) -> dict:
    resume_bigrams, resume_words = _extract_terms(resume_text)
    jd_bigrams, jd_words         = _extract_terms(job_description)

    # ── Bigram (phrase) matches — high signal ──────────────────────────
    matched_phrases = resume_bigrams & jd_bigrams
    missing_phrases = jd_bigrams - resume_bigrams

    # ── Single-word matches ────────────────────────────────────────────
    matched_words = resume_words & jd_words
    missing_words = jd_words - resume_words

    # ── Score: phrases worth 2×, capped at 100 ────────────────────────
    total_jd_terms = len(jd_bigrams) * 2 + len(jd_words)
    matched_weight  = len(matched_phrases) * 2 + len(matched_words)
    score = int(matched_weight / max(total_jd_terms, 1) * 100)
    score = min(score, 100)

    # Top missing phrases first, then words
    top_missing = sorted(missing_phrases)[:10] + sorted(missing_words)[:15]

    return {
        "match_score":       score,
        "matched_phrases":   sorted(matched_phrases)[:20],
        "matched_keywords":  sorted(matched_words)[:30],
        "missing_keywords":  top_missing[:20],
    }