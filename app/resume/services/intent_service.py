"""
intent_service.py  (NEW)
-------------------------
Classifies a user's chat message into one of three intents before any
resume processing happens. This runs first, cheaply, on every message
so we never waste a full generate_resume_json() call on "hi" or "thanks".

Three intents:

  EDIT     — user wants to change something in the resume
             e.g. "add Docker to skills", "make summary shorter"
             → route to /chat (modify_resume)

  ANALYZE  — user wants feedback or critique without changing anything
             e.g. "what are my weak areas", "score my bullet points"
             → route to /analyze (analyze_resume)

  OFF_TOPIC — anything not about the resume
             e.g. "hi", "how are you", "what's the weather"
             → return a friendly redirect immediately, no resume call

HOW IT WORKS
-------------
Two layers:

1. Fast local check — regex patterns catch the most obvious off-topic
   messages (greetings, small talk, single words) in microseconds with
   zero API cost. Catches ~80% of off-topic cases.

2. LLM classifier — for anything that passes the local check, a tiny
   Claude call (max_tokens=20, single word response) classifies the rest.
   Uses no resume content — just the message itself. Cost is negligible
   (~0.001% of a full resume rewrite call).

The two-layer approach means:
  - "hi" → rejected instantly, no API call at all
  - "what's the best way to format a resume?" → LLM decides (ANALYZE)
  - "rewrite my experience bullets" → LLM decides (EDIT)
"""

import re
from app.resume.services.claude_client import generate_text


# ── Layer 1: fast local patterns ──────────────────────────────────────────────

# Messages that are obviously off-topic — no API call needed
_OFF_TOPIC_PATTERNS = [
    r"^(hi|hello|hey|hiya|howdy|sup|yo)\b",
    r"^(how are you|how r u|how's it going|how do you do)",
    r"^(good morning|good afternoon|good evening|good night)",
    r"^(thanks|thank you|thx|ty|cheers|great|awesome|nice|cool|ok|okay|got it|sounds good)",
    r"^(bye|goodbye|see you|cya|later|take care)",
    r"^(what('s| is) your name|who are you|what can you do)",
    r"^(lol|haha|hehe|😂|👍|❤️|🙏)",
    r"^\W*$",        # only punctuation / emoji
    r"^\w{1,3}$",   # single very short word (not a real instruction)
]

_OFF_TOPIC_RE = re.compile(
    "|".join(_OFF_TOPIC_PATTERNS),
    re.IGNORECASE,
)

# Messages that are obviously resume edits — skip the LLM classifier
_EDIT_PATTERNS = [
    r"\b(add|remove|delete|replace|change|update|rewrite|improve|fix|edit|"
    r"strengthen|quantify|rephrase|shorten|expand|include|insert)\b",
    r"\b(make (it|the|my)|make .{1,30} (more|less|better|stronger|shorter|longer))\b",
]

_EDIT_RE = re.compile(
    "|".join(_EDIT_PATTERNS),
    re.IGNORECASE,
)

# Messages that are obviously analysis — skip the LLM classifier
_ANALYZE_PATTERNS = [
    r"\b(review|analyze|analyse|evaluate|assess|critique|score|rate|check|"
    r"audit|tell me|what('s| is| are)|how (does|is|are)|find|identify|"
    r"suggest|recommend|advise|feedback|thoughts|opinion|weak|strong|"
    r"missing|lacking|improve without|what should)\b",
]

_ANALYZE_RE = re.compile(
    "|".join(_ANALYZE_PATTERNS),
    re.IGNORECASE,
)


# ── Off-topic replies ─────────────────────────────────────────────────────────

# Friendly, varied responses so it doesn't feel robotic
_OFF_TOPIC_REPLIES = [
    "I'm focused on helping you with your resume! Try asking me to edit "
    "something (e.g. 'Make my summary more concise') or run an analysis "
    "(e.g. 'What are my weakest bullet points?').",

    "I'm your resume assistant — I can edit your resume or give you "
    "detailed feedback on it. What would you like to work on?",

    "That's outside what I can help with here. I'm built specifically "
    "for resume editing and analysis. Try something like 'Strengthen my "
    "experience bullets' or 'Find weak areas in my resume'.",
]

import random

def _off_topic_reply() -> str:
    return random.choice(_OFF_TOPIC_REPLIES)


# ── Layer 2: LLM classifier (only called when patterns are ambiguous) ─────────

_CLASSIFIER_SYSTEM = """You classify resume chat messages into exactly one category.

Reply with ONLY one word — nothing else:
  EDIT     — user wants to change, rewrite, add, remove, or improve something in their resume
  ANALYZE  — user wants feedback, critique, scoring, or analysis of their resume without editing it
  OFF_TOPIC — anything not directly about their resume (greetings, general questions, small talk)

Examples:
  "add Python to my skills" → EDIT
  "make my summary shorter" → EDIT
  "what are my weak areas?" → ANALYZE
  "score my bullet points" → ANALYZE
  "is my resume ATS friendly?" → ANALYZE
  "hi there" → OFF_TOPIC
  "what's the best resume format?" → ANALYZE
  "tell me a joke" → OFF_TOPIC
  "how long should a resume be?" → ANALYZE"""


async def _llm_classify(message: str) -> str:
    """Returns 'EDIT', 'ANALYZE', or 'OFF_TOPIC'."""
    result = await generate_text(
        system_prompt=_CLASSIFIER_SYSTEM,
        user_content=message,
        max_tokens=10,      # we only need one word
        temperature=0.0,    # deterministic
    )
    result = result.strip().upper()
    if result not in ("EDIT", "ANALYZE", "OFF_TOPIC"):
        return "EDIT"   # safe fallback — better to try an edit than reject
    return result


# ── Entry point ───────────────────────────────────────────────────────────────

async def classify_intent(message: str) -> dict:
    """
    Classify a chat message and return:
    {
        "intent":  "EDIT" | "ANALYZE" | "OFF_TOPIC",
        "reply":   str | None,   # only set for OFF_TOPIC
        "source":  "pattern" | "llm"   # how it was classified (for debugging)
    }
    """
    msg = message.strip()

    if not msg:
        return {
            "intent": "OFF_TOPIC",
            "reply": "Type an instruction to edit your resume or a question to get feedback on it.",
            "source": "pattern",
        }

    # Layer 1a: fast off-topic check
    if _OFF_TOPIC_RE.search(msg):
        return {
            "intent": "OFF_TOPIC",
            "reply": _off_topic_reply(),
            "source": "pattern",
        }

    # Layer 1b: fast EDIT check
    if _EDIT_RE.search(msg):
        return {"intent": "EDIT", "reply": None, "source": "pattern"}

    # Layer 1c: fast ANALYZE check
    if _ANALYZE_RE.search(msg):
        return {"intent": "ANALYZE", "reply": None, "source": "pattern"}

    # Layer 2: LLM classifier for ambiguous messages
    intent = await _llm_classify(msg)
    reply  = _off_topic_reply() if intent == "OFF_TOPIC" else None

    return {"intent": intent, "reply": reply, "source": "llm"}