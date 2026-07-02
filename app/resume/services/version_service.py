"""
version_service.py
------------------
Creates the initial resume record and version 1.

FIX: accepts ats_score parameter so version 1 is never stored as null.
"""

from datetime import datetime
import os

import faiss

from app.common.db import db
from app.resume.services.embedding_service import generate_embeddings
from app.resume.services.vector_store_service import chunk_resume, build_faiss_index


async def create_resume(
    user_email: str,
    title: str,
    text: str,
    metadata: dict,
    resume_json: dict,
    ats_score: int | None = None,   # FIX: accept score from upload route
) -> str:

    # ── Chunk + embed ────────────────────────────────────────────────────
    chunks     = chunk_resume(text)
    embeddings = await generate_embeddings(chunks)
    index      = build_faiss_index(embeddings)

    # ── Store resume document ────────────────────────────────────────────
    resume = {
        "user_email":      user_email,
        "title":           title,
        "candidate_name":  metadata.get("candidate_name"),
        "original_text":   text,
        "skills":          metadata.get("skills", []),
        "num_chunks":      len(chunks),
        "created_at":      datetime.utcnow(),
        "current_version": 1,
    }

    result    = db.db["resumes"].insert_one(resume)
    resume_id = result.inserted_id

    # ── Persist FAISS index ──────────────────────────────────────────────
    os.makedirs("storage", exist_ok=True)
    faiss.write_index(index, f"storage/{resume_id}.index")

    # ── Store text chunks ────────────────────────────────────────────────
    db.db["resume_chunks"].insert_many([
        {"resume_id": resume_id, "chunk_index": idx, "text": chunk}
        for idx, chunk in enumerate(chunks)
    ])

    # ── Create Version 1 ────────────────────────────────────────────────
    db.db["resume_versions"].insert_one({
        "resume_id":             resume_id,
        "version":               1,
        "change_reason":         "Initial Upload",
        "optimized_text":        text,
        "optimized_resume_json": resume_json,
        # FIX: was always None — now stores the real upload-time score
        "ats_score":             ats_score,
        "created_at":            datetime.utcnow(),
    })

    return str(resume_id)