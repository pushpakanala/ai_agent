"""
routes.py  — Resume Analyzer (v3, simplified)
----------------------------------------------
Replaces the entire previous resume optimizer module.

What's GONE (removed):
  - Resume structuring to JSON (no more ResumeData schema)
  - Chat edits / modify_resume
  - Job optimizer / rewriting
  - Cover letter generation
  - DOCX/PDF download generation
  - Version history
  - Embedding / FAISS vector store
  - ATS score on upload
  - Intent classifier
  - Analyze endpoint (separate)
  - Prompt templates

What's HERE (new, slim):
  - Upload resume → extract text → store plain text only
  - Analyze resume against a JD → accurate LLM-based ATS score
  - List user's resumes
  - Delete a resume

Storage: resumes collection stores plain text only.
No resume_versions, no resume_chunks, no FAISS indexes.

Endpoints:
  POST /resume/upload          — upload PDF or DOCX, store plain text
  GET  /resume/                — list user's resumes
  GET  /resume/{resume_id}     — get a single resume's text
  DELETE /resume/{resume_id}   — delete a resume
  POST /resume/{resume_id}/analyze — analyze against a JD, return ATS report
"""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, field_validator

from app.auth.dependencies import get_current_user
from app.common.db import db

from app.resume.services.parser_service import extract_resume_text
from app.resume.services.validator_service import (
    validate_resume_file,
    validate_resume_text,
)
from app.resume.services.ats_analyzer_service import analyze_resume_against_jd
from app.resume.services.cover_letter_service import generate_cover_letter

router = APIRouter()


# ── Request Models ────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    job_description: str

    @field_validator("job_description", mode="before")
    @classmethod
    def clean_jd(cls, v):
        if isinstance(v, str):
            # Strip control characters that break JSON parsing
            return v.replace("\r\n", "\n").replace("\r", "\n").strip()
        return v


class CoverLetterRequest(BaseModel):
    job_description: str
    company_name: Optional[str] = ""
    tone: Optional[str] = "professional"   # professional | enthusiastic | concise

    @field_validator("job_description", mode="before")
    @classmethod
    def clean_jd(cls, v):
        if isinstance(v, str):
            return v.replace("\r\n", "\n").replace("\r", "\n").strip()
        return v


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_object_id(resume_id: str) -> ObjectId:
    try:
        return ObjectId(resume_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid resume ID format.")


def _require_resume(resume_object_id: ObjectId, current_user: str) -> dict:
    resume = db.db["resumes"].find_one({
        "_id": resume_object_id,
        "user_email": current_user,
    })
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return resume


# ── 1. Upload Resume ──────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """
    Upload a PDF or DOCX resume.
    Extracts plain text and stores it — nothing else.
    No JSON structuring, no ATS score, no version history.

    Response:
    {
        "resume_id": "64f1a2b3c4d5e6f7a8b9c0d1",
        "filename": "my_resume.pdf",
        "message": "Resume uploaded successfully."
    }
    """
    validate_resume_file(file.filename)
    file_bytes = await file.read()

    text = await extract_resume_text(file.filename, file_bytes)
    validate_resume_text(text)

    result = db.db["resumes"].insert_one({
        "user_email":  current_user,
        "filename":    file.filename,
        "text":        text,
        "created_at":  datetime.utcnow(),
    })

    return {
        "resume_id": str(result.inserted_id),
        "filename":  file.filename,
        "message":   "Resume uploaded successfully.",
    }


# ── 2. List Resumes ───────────────────────────────────────────────────────────

@router.get("/")
async def list_resumes(current_user=Depends(get_current_user)):
    """
    List all resumes uploaded by the current user.

    Response:
    [
        {
            "resume_id": "...",
            "filename": "my_resume.pdf",
            "created_at": "2026-07-03T10:00:00"
        }
    ]
    """
    cursor = db.db["resumes"].find(
        {"user_email": current_user},
        {"_id": 1, "filename": 1, "created_at": 1},
    ).sort("created_at", -1)

    results = []
    for doc in cursor:
        results.append({
            "resume_id":  str(doc["_id"]),
            "filename":   doc.get("filename", ""),
            "created_at": doc.get("created_at", "").isoformat() if doc.get("created_at") else "",
        })
    return results


# ── 3. Get Resume ─────────────────────────────────────────────────────────────

@router.get("/{resume_id}")
async def get_resume(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    """
    Get a single resume's text and metadata.

    Response:
    {
        "resume_id": "...",
        "filename": "my_resume.pdf",
        "text": "Jane Smith\njane@example.com\n...",
        "created_at": "2026-07-03T10:00:00"
    }
    """
    resume_object_id = _get_object_id(resume_id)
    resume = _require_resume(resume_object_id, current_user)

    return {
        "resume_id":  resume_id,
        "filename":   resume.get("filename", ""),
        "text":       resume.get("text", ""),
        "created_at": resume.get("created_at", "").isoformat() if resume.get("created_at") else "",
    }


# ── 4. Delete Resume ──────────────────────────────────────────────────────────

@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    """
    Delete a resume permanently.

    Response:
    {
        "message": "Resume deleted.",
        "resume_id": "..."
    }
    """
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)

    db.db["resumes"].delete_one({"_id": resume_object_id})

    return {"message": "Resume deleted.", "resume_id": resume_id}


# ── 5. Analyze Resume Against JD ──────────────────────────────────────────────

@router.post("/{resume_id}/analyze")
async def analyze_resume(
    resume_id: str,
    payload: AnalyzeRequest,
    current_user=Depends(get_current_user),
):
    """
    Analyze a resume against a job description using LLM-based ATS scoring.

    This is accurate because the model semantically understands both documents —
    "led a team" matches "team leadership", not just exact string overlap.

    Request:
    {
        "job_description": "We are looking for a Python engineer..."
    }

    Response:
    {
        "resume_id": "...",
        "overall_score": 67,
        "score_breakdown": {
            "keyword_match":        { "score": 26, "max": 40, "comment": "..." },
            "skills_alignment":     { "score": 18, "max": 25, "comment": "..." },
            "experience_relevance": { "score": 13, "max": 20, "comment": "..." },
            "education_fit":        { "score": 8,  "max": 10, "comment": "..." },
            "resume_structure":     { "score": 2,  "max": 5,  "comment": "..." }
        },
        "matched_keywords":  ["Python", "FastAPI", "REST API", "team leadership"],
        "missing_keywords":  ["Kubernetes", "Terraform", "GraphQL", "CI/CD"],
        "skill_gaps": [
            {
                "skill": "Kubernetes",
                "importance": "required",
                "reason": "Role involves managing containerised microservices at scale."
            }
        ],
        "experience_gaps": [
            "No demonstrated experience leading cross-functional teams of 5+ engineers"
        ],
        "strengths": [
            "Strong Python and FastAPI background directly matches core stack",
            "AWS experience aligns with cloud infrastructure requirements"
        ],
        "improvements": [
            {
                "section": "Skills",
                "issue": "Kubernetes not mentioned despite being a required skill",
                "suggestion": "Add Kubernetes to skills section if you have experience; if not, highlight container orchestration experience with Docker Compose or ECS"
            }
        ],
        "verdict": "This resume shows strong backend engineering fundamentals and aligns well with 60% of the requirements. The missing Kubernetes and Terraform experience is a significant gap for this DevOps-heavy role. A recruiter would likely pass this to the next stage only if the team is willing to train on those tools."
    }
    """
    resume_object_id = _get_object_id(resume_id)
    resume = _require_resume(resume_object_id, current_user)

    text = resume.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Resume text is empty.")

    jd = payload.job_description.strip().replace("\r\n", "\n").replace("\r", "\n")
    if not jd:
        raise HTTPException(status_code=400, detail="Job description is required.")

    analysis = await analyze_resume_against_jd(
        resume_text=text,
        job_description=jd,
    )

    return {
        "resume_id": resume_id,
        **analysis,
    }


# ── 6. Generate Cover Letter ──────────────────────────────────────────────────

@router.post("/{resume_id}/cover-letter")
async def cover_letter(
    resume_id: str,
    payload: CoverLetterRequest,
    current_user=Depends(get_current_user),
):
    """
    Generate a tailored cover letter from the resume + job description.

    Request:
    {
        "job_description": "We are looking for...",
        "company_name": "Stripe",          // optional
        "tone": "professional"             // professional | enthusiastic | concise
    }

    Response:
    {
        "resume_id": "...",
        "cover_letter": "Dear Hiring Manager,\n\nAs a software engineer...",
        "tone": "professional"
    }
    """
    resume_object_id = _get_object_id(resume_id)
    resume = _require_resume(resume_object_id, current_user)

    text = resume.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Resume text is empty.")

    jd = payload.job_description.strip().replace("\r\n", "\n").replace("\r", "\n")
    if not jd:
        raise HTTPException(status_code=400, detail="Job description is required.")

    letter = await generate_cover_letter(
        resume_text=text,
        job_description=jd,
        company_name=payload.company_name or "",
        tone=payload.tone or "professional",
    )

    return {
        "resume_id":    resume_id,
        "cover_letter": letter,
        "tone":         payload.tone,
    }