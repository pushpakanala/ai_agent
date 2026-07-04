"""
interview_routes.py
--------------------
FastAPI router for the Interview Coach module.

Mount in main.py:
    from app.interview.router.interview_routes import router as interview_router
    app.include_router(interview_router, prefix="/interview", tags=["Interview"])

UPDATED for resume v3:
  _get_resume_text() now reads directly from the resumes collection (text field)
  instead of querying resume_versions (which no longer exists).
"""

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.common.db import db
from app.interview.service.interview_prep_service import generate_interview_prep

router = APIRouter()


# ── Request model ─────────────────────────────────────────────────────────────

class InterviewPrepRequest(BaseModel):
    company_name: str
    role: str
    job_description: Optional[str] = None
    resume_id: Optional[str] = None


# ── Helper: fetch resume text ─────────────────────────────────────────────────

def _get_resume_text(resume_id: str, current_user: str) -> str | None:
    """
    Fetches plain text directly from the resumes collection.

    FIX: Previously queried resume_versions collection which no longer
    exists in v3. Resumes now store plain text directly on the document.
    Returns None silently — resume is optional, never hard-fail over it.
    """
    try:
        resume = db.db["resumes"].find_one({
            "_id":        ObjectId(resume_id),
            "user_email": current_user,
        })
        if not resume:
            return None
        # v3: plain text stored directly on the resume document
        return resume.get("text") or None
    except Exception:
        return None


# ── Generate Interview Prep ───────────────────────────────────────────────────

@router.post("/prep")
async def get_interview_prep(
    payload: InterviewPrepRequest,
    current_user=Depends(get_current_user),
):
    """
    Generate interview prep for a role at a company.

    Frontend passes company_name and role from the job card.
    Both resume_id and job_description are optional but improve output.

    Request:
    {
        "company_name": "Wipro",
        "role": "Software Engineer",
        "job_description": "We are looking for...",   // optional
        "resume_id": "64f1a2b3c4d5e6f7a8b9c0d1"      // optional
    }

    Response:
    {
        "company_name": "Wipro",
        "role": "Software Engineer",
        "is_personalised": true,
        "has_jd": true,
        "prep": {
            "questions": {
                "behavioral": [{"question": "...", "why_asked": "..."}],
                "technical":  [{"question": "...", "why_asked": "..."}]
            },
            "company_brief": {
                "interview_style": "...",
                "what_they_value": [...],
                "red_flags_to_avoid": [...],
                "tips": [...],
                "typical_process": "..."
            },
            "answer_frameworks": {
                "frameworks": [{
                    "question": "...",
                    "situation": "...",
                    "task": "...",
                    "action": "...",
                    "result": "...",
                    "tip": "..."
                }]
            }
        }
    }
    """
    if not payload.company_name.strip() or not payload.role.strip():
        raise HTTPException(
            status_code=400,
            detail="company_name and role are required.",
        )

    resume_text = None
    if payload.resume_id:
        resume_text = _get_resume_text(payload.resume_id, current_user)

    prep = await generate_interview_prep(
        company_name=payload.company_name.strip(),
        role=payload.role.strip(),
        job_description=payload.job_description or None,
        resume_text=resume_text,
    )

    return {
        "company_name":    payload.company_name,
        "role":            payload.role,
        "is_personalised": resume_text is not None,
        "has_jd":          payload.job_description is not None,
        "prep":            prep,
    }