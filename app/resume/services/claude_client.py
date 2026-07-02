"""
claude_client.py
-----------------
Shared Anthropic (Claude) client + a structured-generation helper used by
every resume service that needs the model to produce a ResumeData-shaped
JSON object.

WHY THIS REPLACES THE OLD PATTERN
-----------------------------------
The old services called OpenAI with either no response_format at all, or
response_format={"type": "json_object"} — both just ASK the model to
produce JSON matching a schema described in the prompt text. Nothing
enforces it, which is why every upload/edit produced a slightly different
shape (period vs completion_date vs duration, tasks vs details vs
responsibilities, etc.) and downstream rendering kept breaking.

This module instead:
1. Gives Claude exactly one tool, `emit_resume`, whose input_schema is
   generated directly FROM app.resume.models.resume_schema.ResumeData —
   so the schema Claude is constrained to and the schema we validate
   against can never drift apart.
2. Forces the tool call via `tool_choice`, so Claude can't reply with
   prose or a differently-shaped JSON blob.
3. Validates the tool call's arguments with Pydantic before trusting them.
   If validation ever fails, the exact error is fed back to Claude and it's
   asked to correct itself, up to MAX_RETRIES times.

Nothing is returned to the caller (and therefore nothing is saved to
Mongo) until it passes validation.
"""

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from app.common.config import CLAUDE_API_KEY
from app.resume.models.resume_schema import ResumeData

# Check your Anthropic account for the exact model string you want to use.
MODEL = "claude-sonnet-5"

MAX_TOKENS = 8192
MAX_RETRIES = 2

client = AsyncAnthropic(api_key=CLAUDE_API_KEY)

_RESUME_TOOL_SCHEMA = ResumeData.model_json_schema()

_SCHEMA_RULES = (
    "Use ONLY the fields defined in the tool schema. Never invent alternate "
    "field names — always use 'bullets' (never 'tasks', 'details', or "
    "'responsibilities'), and always use 'date_str' (never 'period', "
    "'duration', or 'completion_date'). A project that belongs to a "
    "specific employer goes under that experience entry's 'projects' list "
    "— the top-level 'projects' list is ONLY for standalone personal "
    "projects with no employer. Do not duplicate the same project or "
    "experience in two places."
)


async def generate_resume_json(
    system_prompt: str,
    user_content: str,
) -> dict:
    """
    Calls Claude with a forced tool call so the response is constrained to
    ResumeData's exact shape, then validates it with Pydantic. Retries with
    the validation error fed back to the model if needed.

    Returns a plain dict matching ResumeData, ready to store as
    optimized_resume_json. Raises ValueError if Claude can't produce valid
    output within MAX_RETRIES + 1 attempts.
    """
    tool = {
        "name": "emit_resume",
        "description": "Emit the candidate's resume as structured data matching the exact schema.",
        "input_schema": _RESUME_TOOL_SCHEMA,
    }

    full_system = f"{system_prompt}\n\n{_SCHEMA_RULES}"
    messages = [{"role": "user", "content": user_content}]

    last_error = None

    for attempt in range(MAX_RETRIES + 1):

        response = await client.messages.create(
            model=MODEL,
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

            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": (
                    "Your last response didn't match the required schema. "
                    f"Validation errors:\n{last_error}\n\n"
                    "Please call emit_resume again with corrected data that "
                    "resolves these errors exactly."
                ),
            })

    raise ValueError(
        f"Failed to generate a schema-valid resume after {MAX_RETRIES + 1} attempt(s): {last_error}"
    )


async def generate_text(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 600,
    temperature: float = 0.4,
) -> str:
    """Plain text generation (e.g. cover letters) — no tool use needed."""
    response = await client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    return "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
