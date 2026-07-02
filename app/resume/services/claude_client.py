"""
claude_client.py
-----------------
Shared Anthropic client + structured-generation helper constrained to
ResumeData via forced tool use.

BUG FIX: The retry loop was appending a plain-string user message after an
assistant message that contained a `tool_use` block. The Anthropic API
requires that every `tool_use` block is immediately followed by a user
message containing a matching `tool_result` block — a plain string causes:

  400 BadRequestError: `tool_use` ids were found without `tool_result`
  blocks immediately after: toolu_01...

Fix: on each retry, the user message now wraps the correction text inside
a proper `tool_result` content block with the matching tool_use_id, which
satisfies the API's turn structure requirement.
"""

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from app.common.config import CLAUDE_API_KEY
from app.resume.models.resume_schema import ResumeData

MODEL      = "claude-sonnet-4-5"
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
    Calls Claude with a forced tool call constrained to ResumeData's exact
    shape, validates with Pydantic, and retries on validation failure.

    FIX: retry messages now include a tool_result block (required by the
    Anthropic API after any assistant message that contains tool_use).
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

            # FIX: append the assistant turn (which contains tool_use),
            # then a user turn with a tool_result block whose tool_use_id
            # matches the tool_use block. Without this matching tool_result
            # the API returns 400: "tool_use ids found without tool_result".
            messages.append({
                "role": "assistant",
                "content": response.content,   # contains the tool_use block
            })
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,   # must match exactly
                        "content": (
                            f"Validation failed. Errors:\n{last_error}\n\n"
                            "Please call emit_resume again with corrected data "
                            "that resolves every error listed above."
                        ),
                    }
                ],
            })

    raise ValueError(
        f"Failed to generate a schema-valid resume after "
        f"{MAX_RETRIES + 1} attempt(s): {last_error}"
    )


async def generate_text(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 600,
    temperature: float = 0.4,
) -> str:
    """Plain text generation (cover letters etc.) — no tool use needed."""
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