"""
intent_service.py
-----------------
Classifies every chat message into one of three intents before any
resume processing happens.

THREE INTENTS:

  EDIT      — user wants to change something in the resume
              e.g. "add Docker to skills", "make summary shorter"
              → routes to modify_resume() in chat_service

  ANALYZE   — user wants feedback or critique about their resume
              e.g. "what are my weak areas?", "score my bullets"
              → routes to analyze_resume() in analyze_service

  OFF_TOPIC — anything not about the resume at all
              e.g. "hi", "what's the weather", "tell me a joke"
              → returns a friendly redirect reply, no resume touched

IMPORTANT — OFF_TOPIC is intentionally narrow.
  Questions ABOUT resumes in general (e.g. "how long should a resume be?",
  "what font should I use?") are routed as ANALYZE, not OFF_TOPIC.
  Only things completely unrelated to the resume or job search are OFF_TOPIC.

TWO-LAYER APPROACH:
  Layer 1 — regex patterns (zero API cost, ~0ms)
    Catches obvious cases: greetings, single words, emoji-only, thanks, bye.
    Handles ~85% of off-topic cases without any API call.

  Layer 2 — tiny LLM call (max_tokens=10, temperature=0.0)
    Only fires when patterns are ambiguous.
    Returns exactly one word: EDIT, ANALYZE, or OFF_TOPIC.
    Cost is ~1% of a full resume rewrite call.
"""

import re
import random
from app.resume.services.claude_client import generate_text


# ── Layer 1: regex patterns ───────────────────────────────────────────────────

# Obvious off-topic — catch before any API call
_OFF_TOPIC_PATTERNS = [
    r"^(hi|hello|hey|hiya|howdy|sup|yo)\b",
    r"^(how are you|how r u|how's it going|how do you do)",
    r"^(good morning|good afternoon|good evening|good night)",
    r"^(thanks|thank you|thx|ty|cheers|great|awesome|nice|cool|ok|okay|got it|sounds good)",
    r"^(bye|goodbye|see you|cya|later|take care)",
    r"^(what('s| is) your name|who are you|what can you do)",
    r"^(lol|haha|hehe|😂|👍|❤️|🙏)",
    r"^\W*$",       # only punctuation / emoji / whitespace
    r"^\w{1,3}$",  # single very short word (not a real instruction)
]

_OFF_TOPIC_RE = re.compile(
    "|".join(_OFF_TOPIC_PATTERNS),
    re.IGNORECASE,
)

# Obvious edits — skip LLM classifier
_EDIT_PATTERNS = [
    r"\b(add|remove|delete|replace|change|update|rewrite|improve|fix|edit|"
    r"strengthen|quantify|rephrase|shorten|expand|include|insert|move|rename)\b",
    r"\b(make (it|the|my)|make .{1,30} (more|less|better|stronger|shorter|longer|clearer))\b",
    r"\b(use more|use less|use stronger|use better)\b",
]

_EDIT_RE = re.compile(
    "|".join(_EDIT_PATTERNS),
    re.IGNORECASE,
)

# Obvious analysis — skip LLM classifier
_ANALYZE_PATTERNS = [
    r"\b(review|analyze|analyse|evaluate|assess|critique|score|rate|check|"
    r"audit|tell me|what('s| is| are)|how (does|is|are|good|strong|weak)|"
    r"find|identify|suggest|recommend|advise|feedback|thoughts|opinion|"
    r"weak|strong|missing|lacking|what should|am i|is my|does my|"
    r"how long|what font|what format|should i|can i|would it)\b",
]

_ANALYZE_RE = re.compile(
    "|".join(_ANALYZE_PATTERNS),
    re.IGNORECASE,
)


# ── Off-topic replies ─────────────────────────────────────────────────────────

_OFF_TOPIC_REPLIES = [
    "I can only help with your resume. Try something like "
    "\"Strengthen my bullet points\" or \"What are my weakest areas?\"",

    "I'm built specifically for resume editing and feedback. "
    "Ask me to change something or give you a critique.",

    "That's outside what I can help with here. Try asking me to "
    "edit your resume or give you feedback on a specific section.",
]


def _off_topic_reply() -> str:
    return random.choice(_OFF_TOPIC_REPLIES)


# ── Layer 2: LLM classifier for ambiguous messages ────────────────────────────

_CLASSIFIER_SYSTEM = """Classify this resume chat message into exactly one category.
Reply with ONLY one word — nothing else, no punctuation.

EDIT     — user wants to change, rewrite, add, remove, or improve something in their resume
ANALYZE  — user wants feedback, critique, scoring, or analysis of their resume,
           OR is asking a general question about resumes or job searching
OFF_TOPIC — completely unrelated to resumes or job searching (greetings, small talk, jokes, etc.)

Examples:
"add Python to my skills"           → EDIT
"make my summary shorter"           → EDIT
"what are my weak areas?"           → ANALYZE
"score my bullet points"            → ANALYZE
"is my resume ATS friendly?"        → ANALYZE
"how long should a resume be?"      → ANALYZE
"what's the best resume format?"    → ANALYZE
"should I include a photo?"         → ANALYZE
"hi there"                          → OFF_TOPIC
"tell me a joke"                    → OFF_TOPIC
"what's the weather like?"          → OFF_TOPIC"""


async def _llm_classify(message: str) -> str:
    result = await generate_text(
        system_prompt=_CLASSIFIER_SYSTEM,
        user_content=message,
        max_tokens=10,
        temperature=0.0,
    )
    result = result.strip().upper().split()[0]  # take first word only, uppercase
    if result not in ("EDIT", "ANALYZE", "OFF_TOPIC"):
        # Safe fallback — treat unknown as ANALYZE rather than silently eating the message
        return "ANALYZE"
    return result


# ── Entry point ───────────────────────────────────────────────────────────────

async def classify_intent(message: str) -> dict:
    """
    Classify a chat message. Returns:
    {
        "intent": "EDIT" | "ANALYZE" | "OFF_TOPIC",
        "reply":  str | None,   # only set for OFF_TOPIC
        "source": "pattern" | "llm"
    }
    """
    msg = message.strip()

    # Empty message
    if not msg:
        return {
            "intent": "OFF_TOPIC",
            "reply":  "Type an instruction to edit your resume, or ask me for feedback on it.",
            "source": "pattern",
        }

    # Layer 1a: obvious off-topic
    if _OFF_TOPIC_RE.search(msg):
        return {
            "intent": "OFF_TOPIC",
            "reply":  _off_topic_reply(),
            "source": "pattern",
        }

    # Layer 1b: obvious edit
    if _EDIT_RE.search(msg):
        return {"intent": "EDIT", "reply": None, "source": "pattern"}

    # Layer 1c: obvious analysis
    if _ANALYZE_RE.search(msg):
        return {"intent": "ANALYZE", "reply": None, "source": "pattern"}

    # Layer 2: LLM classifier for anything ambiguous
    intent = await _llm_classify(msg)
    return {
        "intent": intent,
        "reply":  _off_topic_reply() if intent == "OFF_TOPIC" else None,
        "source": "llm",
    }