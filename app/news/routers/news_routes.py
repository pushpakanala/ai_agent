"""
news_routes.py
--------------
FastAPI router for the Tech News module.

Mount in main.py:
    from app.news.routes import router as news_router
    app.include_router(news_router, prefix="/news", tags=["News"])

Endpoints:
    GET  /news          — fetch personalised + general feed (cached 30min)
    GET  /news/refresh  — force refresh, bypass cache
    GET  /news/sources  — list all RSS sources the app uses
"""

from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user
from app.common.db import db
from app.news.services.news_service import get_news, FEEDS

router = APIRouter()


# ── 1. Get News Feed ──────────────────────────────────────────────────────────

@router.get("/")
async def get_news_feed(current_user=Depends(get_current_user)):
    """
    Returns personalised + general tech news.
    Cached per user for 30 minutes — fast on repeat loads.

    Response:
    {
        "personalised": [
            {
                "id": "abc123",
                "title": "OpenAI launches new model",
                "summary": "OpenAI has released...",
                "url": "https://techcrunch.com/...",
                "source": "TechCrunch AI",
                "category": "ai_ml",
                "published": "2026-07-02T10:00:00+00:00",
                "relevance_score": 9
            }
        ],
        "general": [
            {
                "id": "def456",
                "title": "Apple announces Vision Pro 2",
                "summary": "...",
                "url": "https://theverge.com/...",
                "source": "The Verge",
                "category": "general",
                "published": "2026-07-02T09:00:00+00:00",
                "relevance_score": 0
            }
        ],
        "cached": true,
        "fetched_at": "2026-07-02T10:00:00+00:00",
        "profile_used": {
            "skills":    ["Python", "FastAPI", "LangChain", "AWS"],
            "companies": ["ADP", "Stripe", "Wipro"],
            "roles":     ["Software Engineer"]
        }
    }

    personalised: articles that matched the user's skills, applied companies,
                  or target roles — sorted by relevance_score descending.
                  Empty list if the user has no resume or job applications yet.

    general: all other recent articles, sorted newest first.
             Always has content regardless of profile.

    profile_used: what the backend extracted from the user's resume and
                  job tracker to build the personalised section.
                  Useful for the UI to show "Based on your skills: Python, AWS..."
    """
    return await get_news(db.db, current_user)


# ── 2. Force Refresh ──────────────────────────────────────────────────────────

@router.get("/refresh")
async def refresh_news_feed(current_user=Depends(get_current_user)):
    """
    Bypasses the 30-minute cache and fetches fresh articles from all feeds.
    Use for a manual "Refresh" button in the UI.
    Takes ~3-6 seconds (all feeds fetched concurrently).
    """
    return await get_news(db.db, current_user, force_refresh=True)


# ── 3. List Sources ───────────────────────────────────────────────────────────

@router.get("/sources")
async def list_sources():
    """
    Returns all RSS sources the app aggregates from.
    No auth required — static list.

    Response:
    {
        "sources": [
            {
                "source": "TechCrunch",
                "category": "general",
                "url": "https://techcrunch.com/feed"
            },
            ...
        ],
        "categories": {
            "general":  "Broad tech news",
            "ai_ml":    "AI and machine learning",
            "startup":  "Startups and funding",
            "dev":      "Engineering and development",
            "security": "Cybersecurity"
        }
    }
    """
    return {
        "sources": [
            {"source": f["source"], "category": f["category"], "url": f["url"]}
            for f in FEEDS
        ],
        "categories": {
            "general":  "Broad tech news",
            "ai_ml":    "AI and machine learning",
            "startup":  "Startups and funding",
            "dev":      "Engineering and development",
            "security": "Cybersecurity",
        },
    }