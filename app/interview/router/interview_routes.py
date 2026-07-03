"""
interview_routes.py
--------------------
FastAPI router for the Interview Coach module.

Mount in main.py:
    from app.interview.routes import router as interview_router
    app.include_router(interview_router, prefix="/interview", tags=["Interview"])

Endpoint:
    POST /interview/prep   — generate interview prep from company + role

No job_id needed. The frontend passes company_name and role directly
from whichever job card the user clicked. Optional JD and resume_id
improve the output but are never required.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.common.db import db
from app.interview.service.interview_prep_service import generate_interview_prep

router = APIRouter()


# ── Request model ─────────────────────────────────────────────────────────────

class InterviewPrepRequest(BaseModel):
    company_name: str               # from the job card — always present
    role: str                       # from the job card — always present
    job_description: Optional[str] = None   # optional paste — makes questions specific
    resume_id: Optional[str] = None         # optional — personalises STAR answers


# ── Helper: fetch resume text if resume_id provided ───────────────────────────

def _get_resume_text(resume_id: str, current_user: str) -> str | None:
    """
    Fetches the latest version's plain text for a resume_id.
    Returns None silently if not found or belongs to a different user.
    Resume is optional — never hard-fail the whole request over it.
    """
    try:
        from bson import ObjectId
        resume_object_id = ObjectId(resume_id)
        resume = db.db["resumes"].find_one({
            "_id": resume_object_id,
            "user_email": current_user,
        })
        if not resume:
            return None
        latest = db.db["resume_versions"].find_one(
            {"resume_id": resume_object_id},
            sort=[("version", -1)],
        )
        return latest.get("optimized_text") if latest else None
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

    The frontend passes company_name and role directly from the job card.
    No job_id needed — the backend doesn't look up any job record.

    Optional inputs that improve output quality:
      job_description — questions pulled from actual JD requirements
      resume_id       — STAR answers use the candidate's real experience

    Always generates fresh — no caching at this endpoint.
    If you want caching, do it on the frontend (store by company+role key).

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
        "is_personalised": false,
        "has_jd": false,
        "prep": {
            "questions": {
                "behavioral": [
                    {"question": "Tell me about a time...", "why_asked": "Tests ownership"}
                ],
                "technical": [
                    {"question": "Design a scalable API...", "why_asked": "Tests system design"}
                ]
            },
            "company_brief": {
                "interview_style": "Wipro typically...",
                "what_they_value": ["teamwork", "delivery", "communication", "ownership"],
                "red_flags_to_avoid": ["vague answers", "no examples"],
                "tips": ["Have STAR examples ready", "Research their clients"],
                "typical_process": "Usually 3-4 rounds..."
            },
            "answer_frameworks": {
                "frameworks": [
                    {
                        "question": "Tell me about a time you led a project",
                        "situation": "At ADP, I was leading...",
                        "task": "I was responsible for...",
                        "action": "I first mapped all dependencies...",
                        "result": "Reduced onboarding time by 40%",
                        "tip": "Lead with the business impact"
                    }
                ]
            }
        }
    }
    """
    if not payload.company_name.strip() or not payload.role.strip():
        raise HTTPException(
            status_code=400,
            detail="company_name and role are required.",
        )

    # Resolve optional resume text — silent None if not found
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