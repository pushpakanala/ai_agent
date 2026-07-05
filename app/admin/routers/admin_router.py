"""
admin_router.py
---------------
Admin dashboard API — all collections match the actual codebase:
  job_applications  ← from job_repository.py
  users             ← from user_repository.py
  resumes           ← from resume/routes.py
  saved_jobs        ← from job_browse/routers
  news_cache        ← from news/services
  job_browse_cache  ← from job_browse/services
  api_rate_limits   ← from job_browse/services (JSearch limit)

Mount in main.py:
    from app.admin.admin_router import router as admin_router
    app.include_router(admin_router, prefix="/admin", tags=["Admin"])
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from app.admin.admin_dependencies import require_admin
from app.common.db import db

router = APIRouter()


# ── 1. Overview Stats ─────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(admin: str = Depends(require_admin)):
    """
    Overview numbers for the admin dashboard.

    Response:
    {
        "total_users": 4,
        "new_users_today": 0,
        "new_users_this_week": 0,
        "active_users_7d": 2,
        "total_applications": 12,
        "total_resumes": 1,
        "total_saved_jobs": 3,
        "applications_by_status": { "applied": 8, "interview": 3, "offer": 1 },
        "top_companies": [{ "company": "Stripe", "count": 3 }]
    }
    """
    now      = datetime.now(timezone.utc)
    today    = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_ago = now - timedelta(days=7)

    total_users   = db.db["users"].count_documents({})
    new_today     = db.db["users"].count_documents({"created_at": {"$gte": today}})
    new_this_week = db.db["users"].count_documents({"created_at": {"$gte": week_ago}})

    active_emails = db.db["job_applications"].distinct(
        "user_email",
        {"last_updated": {"$gte": week_ago}},
    )

    total_applications = db.db["job_applications"].count_documents({})
    total_resumes      = db.db["resumes"].count_documents({})
    total_saved_jobs   = db.db["saved_jobs"].count_documents({})

    status_pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    applications_by_status = {
        r["_id"]: r["count"]
        for r in db.db["job_applications"].aggregate(status_pipeline)
        if r["_id"]
    }

    company_pipeline = [
        {"$group": {"_id": "$company_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_companies = [
        {"company": r["_id"], "count": r["count"]}
        for r in db.db["job_applications"].aggregate(company_pipeline)
        if r["_id"]
    ]

    return {
        "total_users":            total_users,
        "new_users_today":        new_today,
        "new_users_this_week":    new_this_week,
        "active_users_7d":        len(active_emails),
        "total_applications":     total_applications,
        "total_resumes":          total_resumes,
        "total_saved_jobs":       total_saved_jobs,
        "applications_by_status": applications_by_status,
        "top_companies":          top_companies,
    }


# ── 2. User List ──────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    admin: str = Depends(require_admin),
):
    query = {}
    if search:
        query = {"$or": [
            {"email": {"$regex": search, "$options": "i"}},
            {"name":  {"$regex": search, "$options": "i"}},
        ]}

    total = db.db["users"].count_documents(query)
    users_raw = list(
        db.db["users"]
        .find(query, {"_id": 0, "email": 1, "name": 1, "created_at": 1, "updated_at": 1})
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )

    users = []
    for u in users_raw:
        email = u.get("email", "")
        app_count    = db.db["job_applications"].count_documents({"user_email": email})
        resume_count = db.db["resumes"].count_documents({"user_email": email})
        last_job     = db.db["job_applications"].find_one(
            {"user_email": email},
            {"last_updated": 1},
            sort=[("last_updated", -1)],
        )
        users.append({
            "email":             email,
            "name":              u.get("name", ""),
            "created_at":        u["created_at"].isoformat() if u.get("created_at") else None,
            "application_count": app_count,
            "resume_count":      resume_count,
            "last_application":  last_job["last_updated"].isoformat()
                                 if last_job and last_job.get("last_updated") else None,
        })

    return {
        "users": users,
        "total": total,
        "page":  page,
        "pages": (total + limit - 1) // limit,
    }


# ── 3. Single User Detail ─────────────────────────────────────────────────────

@router.get("/users/{email}")
async def get_user_detail(
    email: str,
    admin: str = Depends(require_admin),
):
    user = db.db["users"].find_one(
        {"email": email},
        {"_id": 0, "access_token": 0, "refresh_token": 0},
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.get("created_at"):
        user["created_at"] = user["created_at"].isoformat()
    if user.get("updated_at"):
        user["updated_at"] = user["updated_at"].isoformat()

    applications = list(
        db.db["job_applications"]
        .find({"user_email": email}, {"_id": 0, "gmail_id": 0})
        .sort("last_updated", -1)
        .limit(10)
    )
    for app in applications:
        for f in ("date_applied", "last_updated"):
            if app.get(f):
                app[f] = app[f].isoformat()

    resumes = list(
        db.db["resumes"]
        .find({"user_email": email}, {"_id": 1, "filename": 1, "created_at": 1})
        .sort("created_at", -1)
    )
    for r in resumes:
        r["resume_id"] = str(r.pop("_id"))
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()

    status_pipeline = [
        {"$match": {"user_email": email}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    by_status = {
        r["_id"]: r["count"]
        for r in db.db["job_applications"].aggregate(status_pipeline)
        if r["_id"]
    }
    saved_count = db.db["saved_jobs"].count_documents({"user_email": email})

    return {
        "user":         user,
        "applications": applications,
        "resumes":      resumes,
        "saved_jobs_count": saved_count,
        "stats": {
            "total_applications": db.db["job_applications"].count_documents({"user_email": email}),
            "by_status": by_status,
        },
    }


# ── 4. Delete User ────────────────────────────────────────────────────────────

@router.delete("/users/{email}")
async def delete_user(
    email: str,
    admin: str = Depends(require_admin),
):
    user = db.db["users"].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    deleted = {}
    deleted["job_applications"] = db.db["job_applications"].delete_many({"user_email": email}).deleted_count
    deleted["saved_jobs"]       = db.db["saved_jobs"].delete_many({"user_email": email}).deleted_count
    deleted["news_cache"]       = db.db["news_cache"].delete_many({"user_email": email}).deleted_count

    resume_ids = [r["_id"] for r in db.db["resumes"].find({"user_email": email}, {"_id": 1})]
    if resume_ids:
        db.db["resume_versions"].delete_many({"resume_id": {"$in": resume_ids}})
        db.db["resume_chunks"].delete_many({"resume_id": {"$in": resume_ids}})

    deleted["resumes"] = db.db["resumes"].delete_many({"user_email": email}).deleted_count
    deleted["user"]    = db.db["users"].delete_one({"email": email}).deleted_count

    return {
        "message": f"User {email} and all their data permanently deleted.",
        "deleted": deleted,
    }


# ── 5. All Applications ───────────────────────────────────────────────────────

@router.get("/applications")
async def get_all_applications(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    admin: str = Depends(require_admin),
):
    query = {}
    if status:
        query["status"] = status
    if company:
        query["company_name"] = {"$regex": company, "$options": "i"}

    total = db.db["job_applications"].count_documents(query)
    apps  = list(
        db.db["job_applications"]
        .find(query, {
            "_id": 0, "user_email": 1, "company_name": 1,
            "role": 1, "status": 1, "date_applied": 1, "last_updated": 1,
        })
        .sort("last_updated", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    for app in apps:
        for f in ("date_applied", "last_updated"):
            if app.get(f):
                app[f] = app[f].isoformat()

    return {
        "applications": apps,
        "total":        total,
        "page":         page,
        "pages":        (total + limit - 1) // limit,
    }


# ── 6. System Health ──────────────────────────────────────────────────────────

@router.get("/system")
async def system_health(admin: str = Depends(require_admin)):
    # MongoDB
    try:
        db.db.command("ping")
        mongo_status = "connected"
    except Exception:
        mongo_status = "error"

    # JSearch rate limit
    jsearch_record   = db.db["api_rate_limits"].find_one({"api": "jsearch"})
    jsearch_limited  = False
    jsearch_resets_at = None
    if jsearch_record:
        reset_at = jsearch_record.get("reset_at")
        if reset_at and datetime.now(timezone.utc) < reset_at.replace(tzinfo=timezone.utc):
            jsearch_limited   = True
            jsearch_resets_at = reset_at.isoformat()

    # News cache age
    news_cache        = db.db["news_cache"].find_one({}, sort=[("fetched_at", -1)])
    cache_age_minutes = None
    if news_cache and news_cache.get("fetched_at"):
        fetched = news_cache["fetched_at"].replace(tzinfo=timezone.utc)
        cache_age_minutes = int((datetime.now(timezone.utc) - fetched).total_seconds() / 60)

    # Gmail watches
    now  = datetime.now(timezone.utc)
    soon = now + timedelta(days=2)
    active_watches  = db.db["users"].count_documents({"watch_expiry": {"$gt": now}})
    expiring_soon   = db.db["users"].count_documents({"watch_expiry": {"$gt": now, "$lt": soon}})

    return {
        "mongodb":                     mongo_status,
        "jsearch_limited":             jsearch_limited,
        "jsearch_resets_at":           jsearch_resets_at,
        "news_cache_age_minutes":      cache_age_minutes,
        "gmail_watches_active":        active_watches,
        "gmail_watches_expiring_soon": expiring_soon,
    }


# ── 7. Usage Stats ────────────────────────────────────────────────────────────

@router.get("/usage")
async def get_usage(admin: str = Depends(require_admin)):
    interview_preps    = db.db["job_applications"].count_documents(
        {"interview_prep": {"$exists": True}}
    )
    browse_cache_count = db.db["job_browse_cache"].count_documents({})
    saved_jobs_total   = db.db["saved_jobs"].count_documents({})

    cache_entries = list(
        db.db["job_browse_cache"].find({}, {"data.query_used": 1, "_id": 0}).limit(200)
    )
    query_counts: dict = {}
    for entry in cache_entries:
        q = entry.get("data", {}).get("query_used", "")
        if q:
            query_counts[q] = query_counts.get(q, 0) + 1

    top_searches = sorted(
        [{"query": q, "count": c} for q, c in query_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    return {
        "resume_uploads_total":    db.db["resumes"].count_documents({}),
        "interview_preps_total":   interview_preps,
        "saved_jobs_total":        saved_jobs_total,
        "job_browse_cache_entries": browse_cache_count,
        "top_job_searches":        top_searches,
    }