"""
news_service.py
---------------
Fetches tech news from RSS feeds, parses articles, and scores each
article for relevance against the user's profile (skills + companies).

Two sections returned:
  personalised  — articles scored >0 against user's profile, sorted by score
  general       — all remaining articles sorted by date, deduplicated

Architecture:
  - All RSS feeds fetched concurrently via asyncio.gather()
  - feedparser handles XML parsing (handles malformed feeds gracefully)
  - Relevance scoring is pure Python keyword matching — no AI cost
  - Results cached in MongoDB per user for 30 minutes to avoid
    re-fetching on every page load

Feed categories:
  GENERAL  — broad tech news shown to everyone
  AI_ML    — AI/ML specific (matched to users with AI skills)
  STARTUP  — funding, companies (matched to applied companies)
  DEV      — engineering/developer focused
  SECURITY — cybersecurity
"""

import asyncio
import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import aiohttp
import feedparser

# ── RSS Feed Catalog ──────────────────────────────────────────────────────────

FEEDS = [
    # General tech
    {"url": "https://techcrunch.com/feed",              "source": "TechCrunch",       "category": "general"},
    {"url": "https://www.theverge.com/rss/index.xml",   "source": "The Verge",        "category": "general"},
    {"url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "source": "Ars Technica", "category": "general"},
    {"url": "https://feeds.feedburner.com/venturebeat/SZYF", "source": "VentureBeat", "category": "general"},
    {"url": "https://www.wired.com/feed/rss",           "source": "Wired",            "category": "general"},

    # AI / ML
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed", "source": "TechCrunch AI", "category": "ai_ml"},
    {"url": "https://arstechnica.com/ai/feed",          "source": "Ars Technica AI",  "category": "ai_ml"},

    # Startups / companies
    {"url": "https://techcrunch.com/category/startups/feed", "source": "TechCrunch Startups", "category": "startup"},

    # Developer / engineering
    {"url": "https://feed.infoq.com",                   "source": "InfoQ",            "category": "dev"},
    {"url": "https://thenewstack.io/feed",               "source": "The New Stack",    "category": "dev"},
    {"url": "https://hnrss.org/frontpage?points=100",   "source": "Hacker News",      "category": "dev"},

    # Security
    {"url": "https://krebsonsecurity.com/feed",          "source": "Krebs on Security","category": "security"},
    {"url": "https://feeds.feedburner.com/TheHackersNews", "source": "The Hacker News","category": "security"},
]

# Max articles per feed to keep response size reasonable
MAX_PER_FEED    = 10
# Cache TTL in seconds (30 minutes)
CACHE_TTL_SECS  = 1800
# Max total articles in response
MAX_GENERAL     = 30
MAX_PERSONALISED = 10


# ── Article parsing ───────────────────────────────────────────────────────────

def _parse_date(entry) -> datetime:
    """Parse published date from feed entry, fallback to now."""
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return parsedate_to_datetime(val).replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _clean_summary(text: str, max_chars: int = 200) -> str:
    """Strip HTML tags and truncate."""
    clean = re.sub(r"<[^>]+>", "", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_chars] + "…" if len(clean) > max_chars else clean


def _article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _parse_feed(raw: str, feed_meta: dict) -> list[dict]:
    """Parse raw XML into article dicts."""
    parsed = feedparser.parse(raw)
    articles = []
    for entry in parsed.entries[:MAX_PER_FEED]:
        url   = entry.get("link", "")
        title = entry.get("title", "").strip()
        if not url or not title:
            continue

        summary = _clean_summary(
            entry.get("summary", "")
            or entry.get("description", "")
        )

        articles.append({
            "id":         _article_id(url),
            "title":      title,
            "summary":    summary,
            "url":        url,
            "source":     feed_meta["source"],
            "category":   feed_meta["category"],
            "published":  _parse_date(entry).isoformat(),
        })
    return articles


# ── Async feed fetcher ────────────────────────────────────────────────────────

async def _fetch_feed(session: aiohttp.ClientSession, feed_meta: dict) -> list[dict]:
    """Fetch one RSS feed, return parsed articles. Silent on error."""
    try:
        async with session.get(
            feed_meta["url"],
            timeout=aiohttp.ClientTimeout(total=8),
            headers={"User-Agent": "Mozilla/5.0 (compatible; TechNewsBot/1.0)"},
        ) as resp:
            if resp.status != 200:
                return []
            raw = await resp.text(errors="replace")
            return _parse_feed(raw, feed_meta)
    except Exception:
        return []


async def _fetch_all_feeds() -> list[dict]:
    """Fetch all feeds concurrently, flatten into one list."""
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_fetch_feed(session, f) for f in FEEDS],
            return_exceptions=True,
        )

    articles = []
    seen_ids = set()
    for batch in results:
        if isinstance(batch, list):
            for article in batch:
                if article["id"] not in seen_ids:
                    seen_ids.add(article["id"])
                    articles.append(article)

    # Sort newest first
    articles.sort(key=lambda a: a["published"], reverse=True)
    return articles


# ── Relevance scoring ─────────────────────────────────────────────────────────

def _build_keyword_set(
    skills: list[str],
    companies: list[str],
    roles: list[str],
) -> set[str]:
    """
    Build a flat set of lowercase keywords from user profile.
    Splits multi-word skills into individual words too so
    "machine learning" matches articles containing just "machine" or "learning".
    """
    keywords = set()
    for item in skills + companies + roles:
        lower = item.lower().strip()
        keywords.add(lower)
        # also add individual words for multi-word terms
        for word in lower.split():
            if len(word) > 3:  # skip short words like "and", "for"
                keywords.add(word)
    return keywords


def _score_article(article: dict, keywords: set[str]) -> int:
    """
    Score an article for relevance to user profile.
    Title match = 3 points, summary match = 1 point per keyword.
    """
    if not keywords:
        return 0

    title_lower   = article["title"].lower()
    summary_lower = article["summary"].lower()
    score = 0

    for kw in keywords:
        if kw in title_lower:
            score += 3
        elif kw in summary_lower:
            score += 1

    return score


# ── User profile extraction ───────────────────────────────────────────────────

def _extract_skills_from_text(resume_text: str) -> list[str]:
    """
    Extract skills from plain resume text using common section markers.

    v3 change: resumes are stored as plain text, not structured JSON.
    We find the skills section and extract individual terms from it.
    Works for both "Skills:" lists and "Technical Skills" sections.
    """
    import re

    skills = []
    lines  = resume_text.splitlines()

    # Find lines that look like a skills section
    in_skills = False
    for line in lines:
        stripped = line.strip()
        lower    = stripped.lower()

        # Detect start of skills section
        if any(marker in lower for marker in [
            "technical skills", "skills", "core competencies",
            "technologies", "tools", "stack",
        ]):
            in_skills = True
            continue

        # Detect end of skills section (next major heading)
        if in_skills and stripped and stripped.isupper():
            break
        if in_skills and any(marker in lower for marker in [
            "experience", "education", "projects", "certifications",
            "awards", "summary", "objective",
        ]):
            break

        # Extract terms from skills lines
        if in_skills and stripped:
            # Handle "Category: skill1, skill2, skill3" format
            if ":" in stripped:
                _, _, rest = stripped.partition(":")
                terms = [t.strip() for t in re.split(r"[,|·•]", rest) if t.strip()]
            else:
                terms = [t.strip() for t in re.split(r"[,|·•]", stripped) if t.strip()]

            # Filter out very short or very long terms
            skills.extend(t for t in terms if 2 < len(t) < 40)

    return skills[:60]  # cap to avoid noise


def _extract_user_profile(db, user_email: str) -> tuple[list, list, list]:
    """
    Pull skills, applied company names, and target roles from:
      - Latest resume (plain text — v3 storage)
      - Jobs collection (company_name, role)
    Returns (skills, companies, roles) as flat lists of strings.

    FIX: Previously read from resume_versions.optimized_resume_json
    which no longer exists in v3. Now reads plain text directly from
    the resumes collection and extracts skills via regex.
    """
    skills    = []
    companies = []
    roles     = []

    # From resume — read plain text directly (v3)
    resume = db["resumes"].find_one(
        {"user_email": user_email},
        sort=[("created_at", -1)],
    )
    if resume:
        text = resume.get("text", "")
        if text:
            skills = _extract_skills_from_text(text)

    # From job tracker — unchanged
    job_cursor = db["jobs"].find(
        {"user_email": user_email},
        {"company_name": 1, "role": 1},
    ).limit(50)
    for job in job_cursor:
        if job.get("company_name"):
            companies.append(job["company_name"])
        if job.get("role"):
            roles.append(job["role"])

    return skills, companies, roles


# ── Main entry point ──────────────────────────────────────────────────────────

async def get_news(db, user_email: str, force_refresh: bool = False) -> dict:
    """
    Returns:
    {
        "personalised": [...],   # articles relevant to user's profile
        "general":      [...],   # remaining articles, newest first
        "cached":       bool,
        "fetched_at":   str,
        "profile_used": {
            "skills":    [...],
            "companies": [...],
            "roles":     [...]
        }
    }
    """
    # ── Check cache ───────────────────────────────────────────────────────────
    if not force_refresh:
        cached = db["news_cache"].find_one({"user_email": user_email})
        if cached:
            age = (datetime.now(timezone.utc) - cached["fetched_at"].replace(tzinfo=timezone.utc)).total_seconds()
            if age < CACHE_TTL_SECS:
                return {**cached["data"], "cached": True}

    # ── Fetch fresh ───────────────────────────────────────────────────────────
    articles = await _fetch_all_feeds()

    # ── Score for personalisation ─────────────────────────────────────────────
    skills, companies, roles = _extract_user_profile(db, user_email)
    keywords = _build_keyword_set(skills, companies, roles)

    scored = []
    for article in articles:
        score = _score_article(article, keywords)
        scored.append({**article, "relevance_score": score})

    personalised = sorted(
        [a for a in scored if a["relevance_score"] > 0],
        key=lambda a: a["relevance_score"],
        reverse=True,
    )[:MAX_PERSONALISED]

    personalised_ids = {a["id"] for a in personalised}
    general = [a for a in scored if a["id"] not in personalised_ids][:MAX_GENERAL]

    fetched_at = datetime.now(timezone.utc).isoformat()

    data = {
        "personalised": personalised,
        "general":      general,
        "cached":       False,
        "fetched_at":   fetched_at,
        "profile_used": {
            "skills":    skills[:20],
            "companies": list(set(companies))[:20],
            "roles":     list(set(roles))[:10],
        },
    }

    # ── Store in cache ────────────────────────────────────────────────────────
    db["news_cache"].update_one(
        {"user_email": user_email},
        {"$set": {
            "user_email": user_email,
            "fetched_at": datetime.now(timezone.utc),
            "data":       data,
        }},
        upsert=True,
    )

    return data