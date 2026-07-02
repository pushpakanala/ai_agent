"""
routes.py
---------
FastAPI router for the Resume Optimizer module.

ATS SCORING STRATEGY (important — read before changing):

  calculate_quality_score(text)
    → Sections + action verbs + metrics. No JD. Honest structural quality.
    → Used by: /upload, /chat (edit intent), /ats-score
    → UI label: "Resume Quality Score"

  calculate_ats_match(text, jd)
    → Keyword overlap with JD. SAME algorithm as /job-match so numbers agree.
    → Used by: /optimize-for-job only
    → UI label: "ATS Match Score"

  /job-match uses calculate_match() from job_match_service (unchanged).
  /optimize-for-job uses calculate_ats_match() which is the same algorithm,
  so the score before optimization (from /job-match) and after (from
  /optimize-for-job) are directly comparable — no more 100 → 60 confusion.
"""

from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.common.db import db

from app.resume.services.analyze_service import analyze_resume
from app.resume.services.ats_service import (
    calculate_quality_score,
    calculate_ats_match,
)
from app.resume.services.chat_service import modify_resume
from app.resume.services.cover_letter_service import generate_cover_letter
from app.resume.services.docx_service import generate_docx_bytes
from app.resume.services.intent_service import classify_intent
from app.resume.services.job_match_service import calculate_match
from app.resume.services.job_optimizer_service import optimize_for_job
from app.resume.services.metadata_service import extract_resume_metadata
from app.resume.services.parser_service import extract_resume_text
from app.resume.services.pdf_service import generate_pdf_bytes
from app.resume.services.structure_service import structure_resume
from app.resume.services.validator_service import validate_resume_file, validate_resume_text
from app.resume.services.version_service import create_resume

router = APIRouter()


# ── Request Models ────────────────────────────────────────────────────────────

class ResumeChatRequest(BaseModel):
    message: str


class JobMatchRequest(BaseModel):
    job_description: str


class JobOptimizationRequest(BaseModel):
    job_description: str


class CoverLetterRequest(BaseModel):
    job_description: str
    company_name: Optional[str] = ""
    tone: Optional[str] = "professional"




# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_object_id(resume_id: str) -> ObjectId:
    try:
        return ObjectId(resume_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid resume ID format.")


def _require_resume(resume_object_id: ObjectId, current_user: str) -> dict:
    resume = db.db["resumes"].find_one(
        {"_id": resume_object_id, "user_email": current_user}
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return resume


def _require_latest_version(resume_object_id: ObjectId) -> dict:
    latest = db.db["resume_versions"].find_one(
        {"resume_id": resume_object_id},
        sort=[("version", -1)],
    )
    if not latest:
        raise HTTPException(status_code=404, detail="No resume versions found.")
    return latest


# ── 1. List All Resumes ───────────────────────────────────────────────────────

@router.get("/")
async def list_resumes(current_user=Depends(get_current_user)):
    cursor = db.db["resumes"].find(
        {"user_email": current_user},
        {"_id": 1, "title": 1, "candidate_name": 1, "current_version": 1, "created_at": 1},
    ).sort("created_at", -1)

    results = []
    for doc in cursor:
        doc["resume_id"] = str(doc.pop("_id"))
        results.append(doc)
    return results


# ── 2. Upload Resume ──────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    validate_resume_file(file.filename)
    file_bytes = await file.read()

    text        = await extract_resume_text(file.filename, file_bytes)
    validate_resume_text(text)

    metadata    = await extract_resume_metadata(text)
    resume_json = await structure_resume(text)

    # Quality score only — no JD available at upload time.
    # UI should label this "Resume Quality Score", not "ATS Score".
    quality = calculate_quality_score(text)

    resume_id = await create_resume(
        user_email=current_user,
        title=file.filename,
        text=text,
        metadata=metadata,
        resume_json=resume_json,
        ats_score=quality["overall_score"],
    )

    return {
        "resume_id":      resume_id,
        "candidate_name": metadata.get("candidate_name"),
        "version":        1,
        "resume_preview": resume_json,
        "quality_score":  quality,   # renamed from ats_score — no JD context yet
        "message":        "Resume uploaded and scored successfully.",
    }


# ── 3. Smart Chat ─────────────────────────────────────────────────────────────

@router.post("/{resume_id}/chat")
async def chat_with_resume(
    resume_id: str,
    payload: ResumeChatRequest,
    current_user=Depends(get_current_user),
):
    """
    Classifies message intent before doing anything:
      OFF_TOPIC → friendly reply, no resume touched
      ANALYZE   → feedback markdown, no version saved
      EDIT      → rewrites resume, saves new version

    Response always includes `intent` field for frontend routing.
    """
    classification = await classify_intent(payload.message)
    intent = classification["intent"]

    if intent == "OFF_TOPIC":
        return {
            "intent":  "off_topic",
            "reply":   classification["reply"],
            "message": classification["reply"],
        }

    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    current_json = latest.get("optimized_resume_json")
    if not current_json:
        raise HTTPException(
            status_code=500,
            detail="Structured resume JSON not found for this version.",
        )

    if intent == "ANALYZE":
        feedback = await analyze_resume(
            resume_json=current_json,
            mode="free",
            custom_message=payload.message,
        )
        return {
            "intent":         "analyze",
            "feedback":       feedback,
            "resume_version": latest["version"],
            "message":        "Analysis complete.",
        }

    # EDIT — quality score only (no JD in chat context)
    updated_json, updated_text = await modify_resume(current_json, payload.message)
    quality      = calculate_quality_score(updated_text)
    next_version = latest["version"] + 1

    db.db["resume_versions"].insert_one({
        "resume_id":             resume_object_id,
        "version":               next_version,
        "change_reason":         payload.message,
        "optimized_text":        updated_text,
        "optimized_resume_json": updated_json,
        "ats_score":             quality["overall_score"],
        "created_at":            datetime.utcnow(),
    })

    db.db["resumes"].update_one(
        {"_id": resume_object_id},
        {"$set": {"current_version": next_version}},
    )

    return {
        "intent":        "edit",
        "version":       next_version,
        "resume":        updated_json,
        "updated_text":  updated_text,
        "quality_score": quality,   # structural quality — no JD
        "message":       "Resume updated successfully.",
    }


# ── 4. Get Version History ────────────────────────────────────────────────────

@router.get("/{resume_id}/versions")
async def get_resume_versions(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)

    versions = list(
        db.db["resume_versions"]
        .find(
            {"resume_id": resume_object_id},
            {"_id": 0, "version": 1, "change_reason": 1, "ats_score": 1, "created_at": 1},
        )
        .sort("version", -1)
    )
    return versions


# ── 5. Preview Latest Resume ──────────────────────────────────────────────────

@router.get("/{resume_id}/preview")
async def preview_latest_resume(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    return {
        "resume_id":       resume_id,
        "current_version": latest["version"],
        "resume":          latest.get("optimized_resume_json"),
        "text":            latest.get("optimized_text"),
        "ats_score":       latest.get("ats_score"),
        "updated_at":      latest["created_at"],
    }


# ── 6. Preview Specific Version ───────────────────────────────────────────────

@router.get("/{resume_id}/preview/{version}")
async def preview_version(
    resume_id: str,
    version: int,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)

    doc = db.db["resume_versions"].find_one(
        {"resume_id": resume_object_id, "version": version}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Version not found.")

    return {
        "resume_id":     resume_id,
        "version":       doc["version"],
        "resume":        doc.get("optimized_resume_json"),
        "text":          doc.get("optimized_text"),
        "ats_score":     doc.get("ats_score"),
        "updated_at":    doc["created_at"],
        "change_reason": doc.get("change_reason"),
    }


# ── 7. Restore a Version ──────────────────────────────────────────────────────

@router.post("/{resume_id}/restore/{version}")
async def restore_version(
    resume_id: str,
    version: int,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)

    target = db.db["resume_versions"].find_one(
        {"resume_id": resume_object_id, "version": version}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Version not found.")

    latest       = _require_latest_version(resume_object_id)
    next_version = latest["version"] + 1

    db.db["resume_versions"].insert_one({
        "resume_id":             resume_object_id,
        "version":               next_version,
        "change_reason":         f"Restored from version {version}",
        "optimized_text":        target["optimized_text"],
        "optimized_resume_json": target["optimized_resume_json"],
        "ats_score":             target.get("ats_score"),
        "created_at":            datetime.utcnow(),
    })

    db.db["resumes"].update_one(
        {"_id": resume_object_id},
        {"$set": {"current_version": next_version}},
    )

    return {
        "message":       f"Restored version {version} as new version {next_version}.",
        "new_version":   next_version,
        "restored_from": version,
    }


# ── 8. Delete Resume ──────────────────────────────────────────────────────────

@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)

    db.db["resume_versions"].delete_many({"resume_id": resume_object_id})
    db.db["resume_chunks"].delete_many({"resume_id": resume_object_id})
    db.db["resumes"].delete_one({"_id": resume_object_id})

    return {"message": "Resume and all versions deleted.", "resume_id": resume_id}


# ── 9. Download DOCX ──────────────────────────────────────────────────────────

@router.get("/{resume_id}/download/docx")
async def download_docx(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    resume = _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    docx_file      = generate_docx_bytes(latest["optimized_resume_json"])
    candidate_name = resume.get("candidate_name") or "resume"
    filename       = f"{candidate_name}_v{latest['version']}.docx"

    return StreamingResponse(
        docx_file,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 10. Download PDF ──────────────────────────────────────────────────────────

@router.get("/{resume_id}/download/pdf")
async def download_pdf(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    resume = _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    pdf_file       = generate_pdf_bytes(latest["optimized_resume_json"])
    candidate_name = resume.get("candidate_name") or "resume"
    filename       = f"{candidate_name}_v{latest['version']}.pdf"

    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 11. Resume Quality Score ──────────────────────────────────────────────────

@router.get("/{resume_id}/ats-score")
async def get_ats_score(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    """
    Returns structural quality score (sections, verbs, metrics).
    No JD needed. Label in UI: "Resume Quality Score".
    """
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    return calculate_quality_score(latest["optimized_text"])


# ── 12. Job Match ─────────────────────────────────────────────────────────────

@router.post("/{resume_id}/job-match")
async def job_match(
    resume_id: str,
    payload: JobMatchRequest,
    current_user=Depends(get_current_user),
):
    """
    Keyword overlap score between resume and JD.
    Label in UI: "ATS Match Score".
    Use BEFORE /optimize-for-job to see the gap.
    The score from /optimize-for-job uses the same algorithm — numbers are comparable.
    """
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    return calculate_match(latest["optimized_text"], payload.job_description)


# ── 13. Optimize for Job ──────────────────────────────────────────────────────

@router.post("/{resume_id}/optimize-for-job")
async def optimize_for_job_endpoint(
    resume_id: str,
    payload: JobOptimizationRequest,
    current_user=Depends(get_current_user),
):
    """
    Full JD-targeted resume rewrite.

    ATS scoring uses calculate_ats_match() which is the SAME algorithm
    as /job-match (calculate_match). So match_score_before and
    ats_score.overall_score after are directly comparable — no more
    inflated-100-then-drops-on-recheck problem.
    """
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    current_json     = latest["optimized_resume_json"]
    match_result     = calculate_match(latest["optimized_text"], payload.job_description)
    missing_keywords = match_result["missing_keywords"]

    updated_json, updated_text = await optimize_for_job(
        resume_json=current_json,
        job_description=payload.job_description,
        missing_keywords=missing_keywords,
    )

    # Use calculate_ats_match — same algorithm as calculate_match above
    # so match_score_before and overall_score are on the same scale
    ats_match    = calculate_ats_match(updated_text, payload.job_description)
    next_version = latest["version"] + 1

    db.db["resume_versions"].insert_one({
        "resume_id":             resume_object_id,
        "version":               next_version,
        "change_reason":         "Optimized for Job Description",
        "optimized_text":        updated_text,
        "optimized_resume_json": updated_json,
        "ats_score":             ats_match["overall_score"],
        "created_at":            datetime.utcnow(),
    })

    db.db["resumes"].update_one(
        {"_id": resume_object_id},
        {"$set": {"current_version": next_version}},
    )

    return {
        "version":            next_version,
        "match_score_before": match_result["match_score"],
        "match_score_after":  ats_match["overall_score"],
        "missing_keywords":   missing_keywords,
        "ats_score":          ats_match,
        "resume":             updated_json,
        "message":            "Resume optimized for the job description.",
    }


# ── 14. Generate Cover Letter ─────────────────────────────────────────────────

@router.post("/{resume_id}/cover-letter")
async def generate_cover_letter_endpoint(
    resume_id: str,
    payload: CoverLetterRequest,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    cover_letter = await generate_cover_letter(
        resume_json=latest["optimized_resume_json"],
        job_description=payload.job_description,
        company_name=payload.company_name or "",
        tone=payload.tone or "professional",
    )

    return {
        "cover_letter":   cover_letter,
        "resume_version": latest["version"],
        "tone":           payload.tone,
    }