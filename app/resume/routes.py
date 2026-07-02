"""
routes.py
---------
FastAPI router for the Resume Optimizer module.

All endpoints:
  1.  GET    /                          — list all resumes
  2.  POST   /upload                    — upload a resume (PDF or DOCX)
  3.  POST   /{resume_id}/chat          — smart chat: auto-routes to edit / analyze / off-topic
  4.  GET    /{resume_id}/versions      — version history
  5.  GET    /{resume_id}/preview       — preview latest version
  6.  GET    /{resume_id}/preview/{v}   — preview specific version
  7.  POST   /{resume_id}/restore/{v}   — restore an older version
  8.  DELETE /{resume_id}               — delete resume and all versions
  9.  GET    /{resume_id}/download/docx — download as Word
  10. GET    /{resume_id}/download/pdf  — download as PDF
  11. GET    /{resume_id}/ats-score     — get ATS score for latest version
  12. POST   /{resume_id}/job-match     — score resume vs job description
  13. POST   /{resume_id}/optimize-for-job — full JD-targeted rewrite
  14. POST   /{resume_id}/cover-letter  — generate tailored cover letter
  15. POST   /{resume_id}/analyze       — analysis/critique (no version saved)
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
from app.resume.services.ats_service import calculate_ats_score
from app.resume.services.chat_service import modify_resume
from app.resume.services.cover_letter_service import generate_cover_letter
from app.resume.services.docx_service import generate_docx_bytes
from app.resume.services.intent_service import classify_intent
from app.resume.services.job_match_service import calculate_match
from app.resume.services.job_optimizer_service import optimize_for_job
from app.resume.services.metadata_service import extract_resume_metadata
from app.resume.services.parser_service import extract_resume_text
from app.resume.services.pdf_service import generate_pdf_bytes
from app.resume.services.resume_renderer import render_resume_text
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
    tone: Optional[str] = "professional"   # professional | enthusiastic | concise


class ResumeAnalyzeRequest(BaseModel):
    mode: Literal[
        "recruiter_scan",
        "deep_critique",
        "bullet_audit",
        "positioning",
        "final_polish",
        "quick_wins",
        "free",
    ] = "free"
    message: str = ""   # required for mode="free", optional context for others


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
    """Return all resumes belonging to the current user, newest first."""
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
    ats_result  = calculate_ats_score(text)

    resume_id = await create_resume(
        user_email=current_user,
        title=file.filename,
        text=text,
        metadata=metadata,
        resume_json=resume_json,
        ats_score=ats_result["overall_score"],
    )

    return {
        "resume_id":      resume_id,
        "candidate_name": metadata.get("candidate_name"),
        "version":        1,
        "resume_preview": resume_json,
        "ats_score":      ats_result,
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
    Smart chat endpoint. Classifies every message before touching the resume:

      OFF_TOPIC → friendly redirect reply, no resume loaded, zero extra API cost
      ANALYZE   → analyze_resume() — returns markdown feedback, no version saved
      EDIT      → modify_resume()  — rewrites resume, saves new version

    Response always includes an `intent` field so the frontend knows
    how to render the result:
      "off_topic" → show reply text as a chat bubble, nothing else updates
      "analyze"   → show feedback markdown in chat panel, preview unchanged
      "edit"      → update resume preview, ATS ring, and version history
    """

    # ── Step 1: classify intent (regex first, tiny LLM call as fallback) ─────
    classification = await classify_intent(payload.message)
    intent = classification["intent"]

    # ── Step 2: off-topic — return immediately, no resume touched ─────────────
    if intent == "OFF_TOPIC":
        return {
            "intent":  "off_topic",
            "reply":   classification["reply"],
            "message": classification["reply"],
        }

    # ── Step 3: load resume (only needed for EDIT and ANALYZE) ───────────────
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    current_json = latest.get("optimized_resume_json")
    if not current_json:
        raise HTTPException(
            status_code=500,
            detail="Structured resume JSON not found for this version.",
        )

    # ── Step 4a: ANALYZE — return feedback, no version saved ─────────────────
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

    # ── Step 4b: EDIT — rewrite resume, save new version ─────────────────────
    updated_json, updated_text = await modify_resume(current_json, payload.message)
    ats_result   = calculate_ats_score(updated_text)
    next_version = latest["version"] + 1

    db.db["resume_versions"].insert_one({
        "resume_id":             resume_object_id,
        "version":               next_version,
        "change_reason":         payload.message,
        "optimized_text":        updated_text,
        "optimized_resume_json": updated_json,
        "ats_score":             ats_result["overall_score"],
        "created_at":            datetime.utcnow(),
    })

    db.db["resumes"].update_one(
        {"_id": resume_object_id},
        {"$set": {"current_version": next_version}},
    )

    return {
        "intent":       "edit",
        "version":      next_version,
        "resume":       updated_json,
        "updated_text": updated_text,
        "ats_score":    ats_result,
        "message":      "Resume updated successfully.",
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
    """
    Restores an older version by creating a new version with the same content.
    Non-destructive — full history is always preserved.
    """
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


# ── 11. ATS Score ─────────────────────────────────────────────────────────────

@router.get("/{resume_id}/ats-score")
async def get_ats_score(
    resume_id: str,
    current_user=Depends(get_current_user),
):
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    return calculate_ats_score(latest["optimized_text"])


# ── 12. Job Match ─────────────────────────────────────────────────────────────

@router.post("/{resume_id}/job-match")
async def job_match(
    resume_id: str,
    payload: JobMatchRequest,
    current_user=Depends(get_current_user),
):
    """
    Scores how well the current resume matches a given job description.
    Returns match_score, matched keywords/phrases, and missing keywords.
    Use BEFORE /optimize-for-job to see the gap, and AFTER to confirm improvement.
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

    Flow:
      1. Calculate keyword gaps with job_match_service.
      2. Call job_optimizer_service with a specialist ATS-optimization prompt.
      3. Recalculate ATS score using the JD for dynamic keyword evaluation.
      4. Save as a new version with change_reason = 'Optimized for Job Description'.
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

    ats_result   = calculate_ats_score(updated_text, payload.job_description)
    next_version = latest["version"] + 1

    db.db["resume_versions"].insert_one({
        "resume_id":             resume_object_id,
        "version":               next_version,
        "change_reason":         "Optimized for Job Description",
        "optimized_text":        updated_text,
        "optimized_resume_json": updated_json,
        "ats_score":             ats_result["overall_score"],
        "created_at":            datetime.utcnow(),
    })

    db.db["resumes"].update_one(
        {"_id": resume_object_id},
        {"$set": {"current_version": next_version}},
    )

    return {
        "version":            next_version,
        "match_score_before": match_result["match_score"],
        "missing_keywords":   missing_keywords,
        "ats_score":          ats_result,
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
    """
    Generates a tailored cover letter from the latest resume version
    and the provided job description. Does not create a new version.
    """
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


# ── 15. Analyze Resume ────────────────────────────────────────────────────────

@router.post("/{resume_id}/analyze")
async def analyze_resume_endpoint(
    resume_id: str,
    payload: ResumeAnalyzeRequest,
    current_user=Depends(get_current_user),
):
    """
    Returns AI feedback/critique on the resume as plain markdown text.
    Does NOT create a new version — purely read-only analysis.

    mode options:
      recruiter_scan  — 10-second first-impression test
      deep_critique   — find every weakness systematically
      bullet_audit    — score and rewrite every bullet point
      positioning     — industry alignment and summary rewrite
      final_polish    — executive language refinement pass
      quick_wins      — top 3 highest-impact changes right now
      free            — any custom question (requires message field)

    Called directly when the user picks a prompt template chip.
    Also called automatically from /chat when the intent classifier
    detects an analysis request in a free-typed message.
    """
    resume_object_id = _get_object_id(resume_id)
    _require_resume(resume_object_id, current_user)
    latest = _require_latest_version(resume_object_id)

    resume_json = latest.get("optimized_resume_json")
    if not resume_json:
        raise HTTPException(
            status_code=500,
            detail="Resume JSON not found for this version.",
        )

    if payload.mode == "free" and not payload.message.strip():
        raise HTTPException(
            status_code=400,
            detail="message is required when mode is 'free'.",
        )

    feedback = await analyze_resume(
        resume_json=resume_json,
        mode=payload.mode,
        custom_message=payload.message,
    )

    return {
        "intent":         "analyze",
        "mode":           payload.mode,
        "feedback":       feedback,
        "resume_version": latest["version"],
    }


# ── 16. Get Prompt Templates ──────────────────────────────────────────────────

@router.get("/prompt-templates")
async def get_prompt_templates():
    """
    Returns all available prompt templates for the chat panel.
    No auth required — these are static UI definitions.

    The frontend renders these as clickable chips above the chat input.
    Each template has:
      - mode:        maps to the /analyze endpoint's mode field
                     OR "edit" for templates that call /chat
      - type:        "analyze" or "edit" — tells the frontend which
                     endpoint to call and how to render the response
      - label:       short chip label shown in the UI
      - description: one-line hint shown under the chip
      - message:     the exact prompt text sent to the backend
                     (frontend populates the chat input with this,
                      user can edit before sending — or send directly
                      for template chips that bypass the input)

    For type="analyze": call POST /{resume_id}/analyze with { mode, message }
    For type="edit":    call POST /{resume_id}/chat with { message }
    """
    return {
        "templates": [
            {
                "id":          "recruiter_scan",
                "type":        "analyze",
                "mode":        "recruiter_scan",
                "label":       "10-second scan",
                "description": "What a recruiter sees in the first 10 seconds",
                "message":     "",   # no free-text needed — mode drives the prompt
            },
            {
                "id":          "deep_critique",
                "type":        "analyze",
                "mode":        "deep_critique",
                "label":       "Find every weak area",
                "description": "Raw assessment of what could get you skipped",
                "message":     "",
            },
            {
                "id":          "bullet_audit",
                "type":        "analyze",
                "mode":        "bullet_audit",
                "label":       "Audit bullet points",
                "description": "Score every bullet and rewrite the weak ones",
                "message":     "",
            },
            {
                "id":          "positioning",
                "type":        "analyze",
                "mode":        "positioning",
                "label":       "Reposition for industry",
                "description": "Align summary and skills to your target field",
                "message":     "",
            },
            {
                "id":          "final_polish",
                "type":        "analyze",
                "mode":        "final_polish",
                "label":       "Final polish pass",
                "description": "Hunt vague phrases, weak verbs, inconsistencies",
                "message":     "",
            },
            {
                "id":          "quick_wins",
                "type":        "analyze",
                "mode":        "quick_wins",
                "label":       "Quick wins",
                "description": "Top 3 highest-impact changes right now",
                "message":     "",
            },
        ]
    }