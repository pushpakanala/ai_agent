"""
claude_client.py
-----------------
Token optimizations applied:

1. MAX_TOKENS 8192 → 3000
   A full resume in compact JSON is ~400 tokens. Even with verbose
   bullet points, 3000 output tokens is more than enough and avoids
   paying for 5000+ tokens of reserved-but-unused output budget.

2. Two model tiers:
   SONNET — for generate_resume_json() (structured output, tool use)
   HAIKU  — for generate_text() (intent classification, cover letters,
             analysis). Haiku is ~20× cheaper and fast enough for these.

3. Compact JSON in user_content
   Callers now pass json.dumps(resume, separators=(',',':')) instead of
   json.dumps(resume, indent=2). Saves ~200 tokens per chat/optimize call
   with zero loss of information.

4. MAX_RETRIES reduced 2 → 1
   Retries are rare once the schema is stable. Each retry costs a full
   round trip. One retry is enough to catch transient issues.
"""

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from app.common.config import CLAUDE_API_KEY
from app.resume.models.resume_schema import ResumeData

# Sonnet for tool-use / structured generation (must get schema right)
SONNET = "claude-sonnet-4-5"

# Haiku for plain-text generation (intent, analysis, cover letters)
# ~20x cheaper than Sonnet, fast, perfectly capable for prose tasks
HAIKU = "claude-haiku-4-5-20251001"

MAX_TOKENS  = 3000   # was 8192 — resumes fit in <2000 tokens output
MAX_RETRIES = 1      # was 2 — one retry is enough

client = AsyncAnthropic(api_key=CLAUDE_API_KEY)

_RESUME_TOOL_SCHEMA = ResumeData.model_json_schema()

_SCHEMA_RULES = (
    "Use ONLY the fields defined in the tool schema. "
    "Always use 'bullets' (never 'tasks','details','responsibilities'). "
    "Always use 'date_str' (never 'period','duration','completion_date'). "
    "Employer projects go in that experience entry's 'projects' list. "
    "Top-level 'projects' is ONLY for standalone personal projects. "
    "Never duplicate entries across sections."
)


async def generate_resume_json(
    system_prompt: str,
    user_content: str,
) -> dict:
    """
    Calls Sonnet with forced tool use constrained to ResumeData.
    Validates with Pydantic. Retries once on validation failure with
    proper tool_result block (fixes the 400 BadRequestError).
    """
    tool = {
        "name": "emit_resume",
        "description": "Emit the candidate's resume as structured data.",
        "input_schema": _RESUME_TOOL_SCHEMA,
    }

    full_system = f"{system_prompt}\n\n{_SCHEMA_RULES}"
    messages    = [{"role": "user", "content": user_content}]
    last_error  = None

    for attempt in range(MAX_RETRIES + 1):

        response = await client.messages.create(
            model=SONNET,
            max_tokens=MAX_TOKENS,
            system=full_system,
            tools=[tool],
            tool_choice={"type": "tool", "name": "emit_resume"},
            messages=messages,
        )

        tool_use_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )

        if tool_use_block is None:
            last_error = "Model did not return a tool call."
            break

        try:
            validated = ResumeData(**tool_use_block.input)
            return validated.model_dump()

        except ValidationError as e:
            last_error = str(e)
            if attempt >= MAX_RETRIES:
                break

            # Must use tool_result block — plain string causes 400
            messages.append({
                "role": "assistant",
                "content": response.content,
            })
            messages.append({
                "role": "user",
                "content": [{
                    "type":        "tool_result",
                    "tool_use_id": tool_use_block.id,
                    "content": (
                        f"Validation failed:\n{last_error}\n\n"
                        "Call emit_resume again with corrected data."
                    ),
                }],
            })

    raise ValueError(
        f"Failed to produce valid resume after {MAX_RETRIES + 1} "
        f"attempt(s): {last_error}"
    )


async def generate_text(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 800,
    temperature: float = 0.3,
) -> str:
    """
    Plain-text generation using Haiku — covers:
      - Intent classification  (~10 tokens out)
      - Resume analysis/critique (~600 tokens out)
      - Cover letters (~400 tokens out)

    Haiku is ~20× cheaper than Sonnet and handles prose tasks well.
    """
    response = await client.messages.create(
        model=HAIKU,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    return "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()