"""
embedding_service.py
----------------------
INTENTIONALLY STILL ON OPENAI — Anthropic's API does not offer an
embeddings endpoint, so this file cannot be converted to "Claude API" the
way the other services were. Options if you want off OpenAI entirely:

  1. Leave this on OpenAI (keep OPENAI_API_KEY just for this file) while
     everything else uses CLAUDE_API_KEY.
  2. Switch to Voyage AI (voyageai package), which is Anthropic's
     recommended embeddings partner — different SDK, different env var
     (VOYAGE_API_KEY), not a drop-in swap. Ask if you want this done.

NOTE: as of the last audit, retrieval_service.py / vector_store_service.py
/ this file aren't wired into routes.py yet (no active endpoint uses the
RAG chunking flow), so this isn't blocking anything today — just flagging
it so it's not silently left half-migrated.
"""

from openai import AsyncOpenAI

from app.common.config import OPENAI_API_KEY


client = AsyncOpenAI(
    api_key=OPENAI_API_KEY
)


async def generate_embeddings(
    texts: list[str]
):

    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )

    return [
        item.embedding
        for item in response.data
    ]