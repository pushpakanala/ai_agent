"""
job_browse_service.py
----------------------
Fetches job listings from multiple free sources in parallel and merges
them into a single deduplicated feed.

Sources:
  1. Adzuna API       — rich data, salary, 250 req/day (free key required)
  2. JSearch (RapidAPI) — Google Jobs aggregation, 200 req/month free
  3. Remotive         — remote jobs, unlimited, no key
  4. RemoteOK         — remote tech jobs, unlimited, no key
  5. The Muse         — curated companies, unlimited, no key

JSearch rate limit handling:
  - Every 429 from JSearch is recorded in MongoDB with a reset timestamp
    (first day of next month, since it's a monthly limit)
  - Before each JSearch call, we check if we're currently rate-limited
  - If limited: skip JSearch silently, continue with other sources
  - Once the month resets: the flag clears automatically and JSearch
    resumes being called

Cache:
  - Per-query MongoDB cache with 2-hour TTL
  - Cache key = hash of (query + location + job_type + date_posted)
  - Adzuna's 250/day limit is effectively unlimited with caching
"""

import asyncio
import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

from app.common.config import (
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    JSEARCH_API_KEY,
)

CACHE_TTL_SECS = 7200   # 2 hours
MAX_PER_SOURCE = 20     # jobs fetched per source per query


# ── Normalised job schema ─────────────────────────────────────────────────────

def _job(
    title: str,
    company: str,
    location: str,
    apply_url: str,
    source: str,
    description: str = "",
    salary: str = "",
    job_type: str = "",
    posted_at: str = "",
    is_remote: bool = False,
) -> dict:
    return {
        "id":          hashlib.md5(apply_url.encode()).hexdigest()[:12],
        "title":       title.strip(),
        "company":     company.strip(),
        "location":    location.strip(),
        "apply_url":   apply_url.strip(),
        "source":      source,
        "description": description[:400].strip(),   # cap for response size
        "salary":      salary.strip(),
        "job_type":    job_type.strip(),
        "posted_at":   posted_at,
        "is_remote":   is_remote,
    }


# ── JSearch rate-limit tracker ────────────────────────────────────────────────

def _jsearch_is_limited(db) -> bool:
    """
    Returns True if JSearch is currently rate-limited.
    The limit record stores a reset_at timestamp (first of next month).
    Once past that timestamp, the limit is cleared automatically.
    """
    record = db["api_rate_limits"].find_one({"api": "jsearch"})
    if not record:
        return False

    reset_at = record.get("reset_at")
    if reset_at and datetime.now(timezone.utc) >= reset_at.replace(tzinfo=timezone.utc):
        # Limit has reset — clear the record
        db["api_rate_limits"].delete_one({"api": "jsearch"})
        return False

    return True


def _jsearch_mark_limited(db):
    """
    Records that JSearch hit its monthly limit.
    Sets reset_at to the 1st of next month at midnight UTC.
    """
    now = datetime.now(timezone.utc)
    if now.month == 12:
        reset_at = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        reset_at = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    db["api_rate_limits"].update_one(
        {"api": "jsearch"},
        {"$set": {
            "api":        "jsearch",
            "limited_at": now,
            "reset_at":   reset_at,
        }},
        upsert=True,
    )


# ── Source fetchers ───────────────────────────────────────────────────────────

async def _fetch_adzuna(
    session: aiohttp.ClientSession,
    query: str,
    location: str,
    country: str = "us",
) -> list[dict]:
    """Adzuna REST API — full job data including salary."""
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []
    try:
        params = {
            "app_id":       ADZUNA_APP_ID,
            "app_key":      ADZUNA_APP_KEY,
            "results_per_page": MAX_PER_SOURCE,
            "what":         query,
            "content-type": "application/json",
        }
        if location:
            params["where"] = location

        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return []
            data = await r.json()

        jobs = []
        for item in data.get("results", []):
            salary = ""
            sal_min = item.get("salary_min")
            sal_max = item.get("salary_max")
            if sal_min and sal_max:
                salary = f"${int(sal_min):,} – ${int(sal_max):,}"
            elif sal_min:
                salary = f"From ${int(sal_min):,}"

            jobs.append(_job(
                title=item.get("title", ""),
                company=item.get("company", {}).get("display_name", ""),
                location=item.get("location", {}).get("display_name", ""),
                apply_url=item.get("redirect_url", ""),
                source="Adzuna",
                description=item.get("description", ""),
                salary=salary,
                job_type=item.get("contract_type", ""),
                posted_at=item.get("created", ""),
                is_remote="remote" in item.get("title", "").lower()
                          or "remote" in item.get("description", "").lower(),
            ))
        return jobs
    except Exception:
        return []


async def _fetch_jsearch(
    session: aiohttp.ClientSession,
    query: str,
    location: str,
    date_posted: str,
    country: str,
    db,
) -> list[dict]:
    """
    JSearch via RapidAPI — aggregates Google Jobs (LinkedIn, Indeed, Glassdoor).
    Checks rate limit before calling. Marks limit on 429.
    """
    if not JSEARCH_API_KEY:
        return []

    if _jsearch_is_limited(db):
        return []   # silently skip — other sources continue normally

    try:
        search_query = query
        if location:
            search_query += f" in {location}"
        elif country:
            # Map country code to name for better JSearch results
            country_names = {
                "us": "United States", "gb": "United Kingdom",
                "in": "India", "ca": "Canada", "au": "Australia",
                "de": "Germany", "fr": "France", "sg": "Singapore",
                "ae": "UAE", "nl": "Netherlands", "ie": "Ireland",
            }
            country_name = country_names.get(country.lower(), country.upper())
            search_query += f" in {country_name}"

        params = {
            "query":        search_query,
            "page":         "1",
            "num_pages":    "1",
            "date_posted":  date_posted or "month",
            "employment_types": "FULLTIME,PARTTIME,CONTRACTOR",
            "country":      country.upper() if country else "US",
        }
        # Supports both OpenWeb Ninja direct (x-api-key header)
        # and RapidAPI (X-RapidAPI-Key header) — set JSEARCH_VIA_RAPIDAPI=true
        # in env to use RapidAPI, otherwise defaults to OpenWeb Ninja direct.
        import os
        via_rapidapi = os.getenv("JSEARCH_VIA_RAPIDAPI", "").lower() == "true"

        if via_rapidapi:
            headers = {
                "X-RapidAPI-Key":  JSEARCH_API_KEY,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
            }
            search_url = "https://jsearch.p.rapidapi.com/search"
        else:
            headers = {"x-api-key": JSEARCH_API_KEY}
            search_url = "https://api.openwebninja.com/jobs/search"

        async with session.get(
            search_url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            # Rate limited — mark and skip for the rest of the month
            if r.status == 429:
                _jsearch_mark_limited(db)
                return []

            if r.status != 200:
                return []

            data = await r.json()

        jobs = []
        for item in data.get("data", []):
            salary = ""
            sal_min = item.get("job_min_salary")
            sal_max = item.get("job_max_salary")
            if sal_min and sal_max:
                salary = f"${int(sal_min):,} – ${int(sal_max):,}"

            jobs.append(_job(
                title=item.get("job_title", ""),
                company=item.get("employer_name", ""),
                location=item.get("job_city", "") + (
                    f", {item.get('job_state', '')}" if item.get("job_state") else ""
                ),
                apply_url=item.get("job_apply_link", ""),
                source="JSearch",
                description=item.get("job_description", ""),
                salary=salary,
                job_type=item.get("job_employment_type", ""),
                posted_at=item.get("job_posted_at_datetime_utc", ""),
                is_remote=item.get("job_is_remote", False),
            ))
        return jobs
    except Exception:
        return []


async def _fetch_remotive(
    session: aiohttp.ClientSession,
    query: str,
) -> list[dict]:
    """Remotive — remote jobs, no key, unlimited."""
    try:
        params = {"search": query, "limit": MAX_PER_SOURCE}
        async with session.get(
            "https://remotive.com/api/remote-jobs",
            params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status != 200:
                return []
            data = await r.json()

        jobs = []
        for item in data.get("jobs", []):
            # Strip HTML from description
            desc = re.sub(r"<[^>]+>", " ", item.get("description", ""))
            desc = re.sub(r"\s+", " ", desc).strip()

            jobs.append(_job(
                title=item.get("title", ""),
                company=item.get("company_name", ""),
                location=item.get("candidate_required_location", "Remote"),
                apply_url=item.get("url", ""),
                source="Remotive",
                description=desc,
                job_type=item.get("job_type", "full_time"),
                posted_at=item.get("publication_date", ""),
                is_remote=True,
            ))
        return jobs
    except Exception:
        return []


async def _fetch_remoteok(
    session: aiohttp.ClientSession,
    query: str,
) -> list[dict]:
    """RemoteOK — remote tech jobs, no key, unlimited."""
    try:
        async with session.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "Mozilla/5.0 (compatible; JobBrowser/1.0)"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status != 200:
                return []
            data = await r.json()

        # Expand query for better matching — RemoteOK uses full words in tags
        # e.g. "ai" → also match "artificial-intelligence", "machine-learning"
        query_lower = query.lower()
        query_words = set(query_lower.split())
        # Add common expansions
        expansions = {
            "ai": ["artificial", "intelligence", "machine", "learning", "ml"],
            "ml": ["machine", "learning", "artificial", "intelligence"],
            "swe": ["software", "engineer", "developer"],
            "fe": ["frontend", "front-end"],
            "be": ["backend", "back-end"],
        }
        expanded = set(query_words)
        for w in query_words:
            if w in expansions:
                expanded.update(expansions[w])

        jobs = []
        for item in data:
            if not isinstance(item, dict) or not item.get("position"):
                continue

            # Client-side keyword filter with expanded terms
            tags = item.get("tags", "")
            if isinstance(tags, list):
                tags = " ".join(tags)
            text = (item.get("position", "") + " " + tags).lower()
            if not any(w in text for w in expanded):
                continue

            jobs.append(_job(
                title=item.get("position", ""),
                company=item.get("company", ""),
                location="Remote",
                apply_url=item.get("url", f"https://remoteok.com/remote-jobs/{item.get('id','')}"),
                source="RemoteOK",
                description=re.sub(r"<[^>]+>", " ", item.get("description", "")),
                salary=item.get("salary", ""),
                job_type="Full-Time",
                posted_at=item.get("date", ""),
                is_remote=True,
            ))
            if len(jobs) >= MAX_PER_SOURCE:
                break

        return jobs
    except Exception:
        return []


async def _fetch_the_muse(
    session: aiohttp.ClientSession,
    query: str,
) -> list[dict]:
    """The Muse — curated companies, no key, unlimited."""
    try:
        # The Muse uses predefined categories — map common query terms
        # to their closest category. Falls back to broad search if no match.
        category_map = {
            "engineer": "Engineering",
            "developer": "Engineering",
            "software": "Engineering",
            "ai": "Engineering",
            "ml": "Data Science",
            "data": "Data Science",
            "scientist": "Data Science",
            "analyst": "Data Science",
            "product": "Product",
            "design": "Design",
            "marketing": "Marketing",
            "sales": "Sales",
            "finance": "Finance",
            "hr": "HR & Recruiting",
            "recruiter": "HR & Recruiting",
            "manager": "Management",
            "devops": "Engineering",
            "security": "Engineering",
        }
        q_lower = query.lower()
        category = next(
            (v for k, v in category_map.items() if k in q_lower),
            "Engineering",  # safe default
        )
        params = {
            "page":     1,
            "category": category,
            "level":    "Senior Level,Mid Level,Entry Level",
        }
        async with session.get(
            "https://www.themuse.com/api/public/jobs",
            params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status != 200:
                return []
            data = await r.json()

        jobs = []
        for item in data.get("results", [])[:MAX_PER_SOURCE]:
            # Location
            locs = item.get("locations", [])
            location = locs[0].get("name", "Remote") if locs else "Remote"

            # Description from contents array
            contents = item.get("contents", "")
            desc = re.sub(r"<[^>]+>", " ", contents)
            desc = re.sub(r"\s+", " ", desc).strip()

            jobs.append(_job(
                title=item.get("name", ""),
                company=item.get("company", {}).get("name", ""),
                location=location,
                apply_url=item.get("refs", {}).get("landing_page", ""),
                source="The Muse",
                description=desc,
                job_type=item.get("type", ""),
                posted_at=item.get("publication_date", ""),
                is_remote="flexible" in location.lower() or "remote" in location.lower(),
            ))
        return jobs
    except Exception:
        return []


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(jobs: list[dict]) -> list[dict]:
    """
    Deduplicate by URL hash (id field).
    Prefer jobs with more data (salary > no salary).
    """
    seen: dict[str, dict] = {}
    for job in jobs:
        job_id = job["id"]
        if job_id not in seen:
            seen[job_id] = job
        else:
            # Keep the richer record
            if job.get("salary") and not seen[job_id].get("salary"):
                seen[job_id] = job
    return list(seen.values())


# ── Client-side filters ───────────────────────────────────────────────────────

def _filter_jobs(
    jobs: list[dict],
    job_type: Optional[str],
    remote_only: bool,
    date_posted: Optional[str],
) -> list[dict]:
    result = jobs

    if remote_only:
        result = [j for j in result if j["is_remote"]]

    if job_type:
        jt = job_type.lower()
        result = [
            j for j in result
            if not j["job_type"] or jt in j["job_type"].lower()
        ]

    if date_posted == "today":
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        filtered = []
        for j in result:
            pt = j.get("posted_at", "")
            if not pt:
                filtered.append(j)   # keep if no date (can't filter out)
                continue
            try:
                dt = datetime.fromisoformat(pt.replace("Z", "+00:00"))
                if dt >= cutoff:
                    filtered.append(j)
            except Exception:
                filtered.append(j)
        result = filtered

    return result


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(query: str, location: str, job_type: str, date_posted: str, remote_only: bool) -> str:
    raw = f"{query}|{location}|{job_type}|{date_posted}|{remote_only}"
    return hashlib.md5(raw.lower().encode()).hexdigest()


def _get_cache(db, key: str) -> Optional[dict]:
    record = db["job_browse_cache"].find_one({"key": key})
    if not record:
        return None
    age = (datetime.now(timezone.utc) - record["cached_at"].replace(tzinfo=timezone.utc)).total_seconds()
    if age > CACHE_TTL_SECS:
        db["job_browse_cache"].delete_one({"key": key})
        return None
    return record["data"]


def _set_cache(db, key: str, data: dict):
    db["job_browse_cache"].update_one(
        {"key": key},
        {"$set": {"key": key, "data": data, "cached_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

async def browse_jobs(
    db,
    query: str,
    country: str,             # required — "us", "gb", "in", "ca", "au", etc.
    location: str = "",
    job_type: str = "",       # full-time | part-time | contract | ""
    date_posted: str = "",    # today | week | month | ""
    remote_only: bool = False,
    force_refresh: bool = False,
) -> dict:
    """
    Fetch jobs from all available sources, deduplicate, filter, cache.

    Returns:
    {
        "jobs": [...],
        "total": int,
        "sources_used": [...],
        "jsearch_limited": bool,
        "cached": bool,
        "query_used": str,
        "country": str
    }
    """
    cache_key = _cache_key(query, location, job_type, date_posted, remote_only) + f"|{country}"

    # Check cache first
    if not force_refresh:
        cached = _get_cache(db, cache_key)
        if cached:
            return {**cached, "cached": True}

    # Check JSearch status before launching requests
    jsearch_limited = _jsearch_is_limited(db)

    async with aiohttp.ClientSession() as session:
        tasks = [
            _fetch_adzuna(session, query, location, country=country),
            _fetch_remotive(session, query),
            _fetch_remoteok(session, query),
            _fetch_the_muse(session, query),
        ]

        # Only add JSearch if not rate-limited
        if not jsearch_limited and JSEARCH_API_KEY:
            tasks.append(_fetch_jsearch(session, query, location, date_posted, country, db))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten and track which sources returned data
    all_jobs = []
    sources_used = []
    source_names = ["Adzuna", "Remotive", "RemoteOK", "The Muse"]
    if not jsearch_limited and JSEARCH_API_KEY:
        source_names.append("JSearch")

    for source_name, result in zip(source_names, results):
        if isinstance(result, list) and result:
            all_jobs.extend(result)
            sources_used.append(source_name)

    # Re-check JSearch limit (may have been marked limited during this request)
    jsearch_limited = _jsearch_is_limited(db)

    # Deduplicate
    deduped = _deduplicate(all_jobs)

    # Apply filters
    filtered = _filter_jobs(deduped, job_type or None, remote_only, date_posted or None)

    # Sort: jobs with salary first, then by posted_at desc
    filtered.sort(key=lambda j: (
        0 if j.get("salary") else 1,
        j.get("posted_at", "") or "",
    ), reverse=False)
    # Re-sort posted_at descending within each salary group
    filtered.sort(key=lambda j: j.get("posted_at", "") or "", reverse=True)

    data = {
        "jobs":             filtered,
        "total":            len(filtered),
        "sources_used":     sources_used,
        "jsearch_limited":  jsearch_limited,
        "query_used":       query,
        "country":          country,
        "cached":           False,
    }

    _set_cache(db, cache_key, data)
    return data