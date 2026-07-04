"""
job_browse_router.py
---------------------
Routes for the Job Browse feature.

Mount in main.py:
    from app.jobs.routers.job_browse_router import router as job_browse_router
    app.include_router(job_browse_router, prefix="/jobs", tags=["Jobs"])

Endpoints:
    GET  /jobs/browse              — search jobs from all sources
    POST /jobs/track               — add a browsed job to the tracker
    GET  /jobs/jsearch-status      — check if JSearch is rate-limited
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.common.db import db
from app.job_browse.services.job_browse_service import browse_jobs, _jsearch_is_limited

router = APIRouter()


# ── 1. Browse Jobs ────────────────────────────────────────────────────────────

# Supported country codes with display names — shown in the UI dropdown
SUPPORTED_COUNTRIES = {
    "us": "United States",
    "gb": "United Kingdom",
    "in": "India",
    "ca": "Canada",
    "au": "Australia",
    "de": "Germany",
    "fr": "France",
    "sg": "Singapore",
    "ae": "UAE",
    "nl": "Netherlands",
    "ie": "Ireland",
}


@router.get("/browse")
async def browse_jobs_endpoint(
    query: str = Query(..., description="Job title or keywords e.g. 'Python developer'"),
    country: str = Query(..., description="Country code — us, gb, in, ca, au, de, fr, sg, ae, nl, ie"),
    location: str = Query("", description="City or region e.g. 'Louisville KY' — optional within the country"),
    job_type: str = Query("", description="full-time | part-time | contract | ''"),
    date_posted: str = Query("", description="today | week | month | ''"),
    remote_only: bool = Query(False, description="Show remote jobs only"),
    refresh: bool = Query(False, description="Bypass 2-hour cache"),
    current_user=Depends(get_current_user),
):
    """
    Search jobs across Adzuna, JSearch, Remotive, RemoteOK, and The Muse.
    country is required — results are filtered to that country.
    Results are cached per query+country for 2 hours.
    JSearch is automatically skipped when its monthly limit is reached
    and resumes at the start of the next month.

    Required params:
      query   — job title or keywords
      country — country code (us, gb, in, ca, au, de, fr, sg, ae, nl, ie)

    Optional params:
      location    — city/region within the country
      job_type    — full-time | part-time | contract
      date_posted — today | week | month
      remote_only — true/false
      refresh     — bypass cache

    Response:
    {
        "jobs": [
            {
                "id": "abc123",
                "title": "Senior Python Developer",
                "company": "Stripe",
                "location": "New York, NY",
                "apply_url": "https://...",
                "source": "Adzuna",
                "description": "We are looking for...",
                "salary": "$120,000 – $160,000",
                "job_type": "Full-Time",
                "posted_at": "2026-07-04T10:00:00Z",
                "is_remote": false
            }
        ],
        "total": 42,
        "sources_used": ["Adzuna", "Remotive", "RemoteOK", "The Muse"],
        "jsearch_limited": false,
        "cached": true,
        "query_used": "Python developer",
        "country": "us"
    }

    When jsearch_limited is true, JSearch results are excluded automatically.
    """
    # Normalise and validate country code
    country = country.lower().strip()
    if country not in SUPPORTED_COUNTRIES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported country code '{country}'. "
                   f"Supported: {', '.join(SUPPORTED_COUNTRIES.keys())}",
        )

    return await browse_jobs(
        db=db.db,
        query=query,
        country=country,
        location=location,
        job_type=job_type,
        date_posted=date_posted,
        remote_only=remote_only,
        force_refresh=refresh,
    )


@router.get("/browse/countries")
async def list_countries():
    """
    Returns the list of supported country codes for the country filter dropdown.
    No auth required.

    Response:
    {
        "countries": [
            { "code": "us", "name": "United States" },
            { "code": "gb", "name": "United Kingdom" },
            ...
        ]
    }
    """
    return {
        "countries": [
            {"code": code, "name": name}
            for code, name in SUPPORTED_COUNTRIES.items()
        ]
    }


# ── 2. Save a Job ────────────────────────────────────────────────────────────

class SaveJobRequest(BaseModel):
    job_id: str        # the id field from the browse response
    title: str
    company: str
    location: str
    apply_url: str
    source: str
    salary: Optional[str] = ""
    job_type: Optional[str] = ""
    description: Optional[str] = ""


@router.post("/save")
async def save_job(
    payload: SaveJobRequest,
    current_user=Depends(get_current_user),
):
    """
    Save a job from the browse feed to the user's saved jobs list.
    This is a bookmark — NOT a tracker entry. Gmail watch handles tracking
    automatically once the user actually applies.

    Saved jobs are stored in a separate saved_jobs collection, not the
    jobs collection (which is owned by the Gmail tracker).

    Duplicate saves return the existing record without error.

    Request:
    {
        "job_id": "a7ebbef71d08",
        "title": "Senior Python Developer",
        "company": "Stripe",
        "location": "New York, NY",
        "apply_url": "https://...",
        "source": "Adzuna",
        "salary": "$120,000 – $160,000",
        "job_type": "Full-Time",
        "description": "..."
    }

    Response:
    {
        "message": "Job saved.",
        "job_id": "a7ebbef71d08",
        "already_saved": false
    }
    """
    existing = db.db["saved_jobs"].find_one({
        "user_email": current_user,
        "job_id":     payload.job_id,
    })
    if existing:
        return {
            "message":      "Already saved.",
            "job_id":       payload.job_id,
            "already_saved": True,
        }

    db.db["saved_jobs"].insert_one({
        "user_email":  current_user,
        "job_id":      payload.job_id,
        "title":       payload.title,
        "company":     payload.company,
        "location":    payload.location,
        "apply_url":   payload.apply_url,
        "source":      payload.source,
        "salary":      payload.salary,
        "job_type":    payload.job_type,
        "description": payload.description,
        "saved_at":    datetime.utcnow(),
    })

    return {
        "message":      "Job saved.",
        "job_id":       payload.job_id,
        "already_saved": False,
    }


@router.get("/saved")
async def list_saved_jobs(current_user=Depends(get_current_user)):
    """
    Returns all jobs the user has saved.

    Response:
    {
        "saved_jobs": [
            {
                "job_id": "a7ebbef71d08",
                "title": "Senior Python Developer",
                "company": "Stripe",
                "location": "New York, NY",
                "apply_url": "https://...",
                "source": "Adzuna",
                "salary": "$120,000",
                "saved_at": "2026-07-04T10:00:00"
            }
        ],
        "total": 3
    }
    """
    cursor = db.db["saved_jobs"].find(
        {"user_email": current_user},
    ).sort("saved_at", -1)

    saved = []
    for doc in cursor:
        doc.pop("_id", None)
        doc.pop("user_email", None)
        if doc.get("saved_at"):
            doc["saved_at"] = doc["saved_at"].isoformat()
        saved.append(doc)

    return {"saved_jobs": saved, "total": len(saved)}


@router.delete("/saved/{job_id}")
async def unsave_job(
    job_id: str,
    current_user=Depends(get_current_user),
):
    """
    Remove a job from saved jobs.

    Response:
    { "message": "Job removed from saved.", "job_id": "a7ebbef71d08" }
    """
    db.db["saved_jobs"].delete_one({
        "user_email": current_user,
        "job_id":     job_id,
    })
    return {"message": "Job removed from saved.", "job_id": job_id}