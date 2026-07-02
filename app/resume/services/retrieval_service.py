import faiss

from app.common.db import db

from app.resume.services.embedding_service import (
    generate_embeddings,
)


async def retrieve_relevant_chunks(
    resume_id: str,
    query: str,
    k: int = 3,
):

    index = faiss.read_index(
        f"storage/{resume_id}.index"
    )

    query_embedding = await generate_embeddings(
        [query]
    )

    distances, indices = index.search(
        query_embedding,
        k,
    )

    chunks = []

    for idx in indices[0]:

        doc = db.db[
            "resume_chunks"
        ].find_one(
            {
                "resume_id": resume_id,
                "chunk_index": int(idx),
            }
        )

        if doc:
            chunks.append(
                doc["text"]
            )

    return chunks