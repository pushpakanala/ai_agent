"""
cover_letter_service.py
------------------------
Generates a tailored cover letter in a structured professional format
matching the following layout:

  Application for [Role] – [Company]     ← title (italic bold in PDF)

                              Place: [Location]   ← right-aligned

  Dear Hiring Team,

  [Opening paragraph — role + standout achievement]

  [Body paragraph — skills/experience matched to JD]

  [Motivation paragraph — why this company specifically]

  [Closing paragraph — contribution + eagerness]

  Thank you for your time and consideration. I look forward to the
  opportunity to discuss how I can contribute to your team.

                                          Sincerely,

                                          [Candidate Name]
                                          Mobile: [Phone if available]
"""

from openai import AsyncOpenAI
from app.common.config import OPENAI_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

_SYSTEM = """You are an expert cover letter writer and career coach.

Generate a professional cover letter in EXACTLY this format — follow the structure precisely:

---
Application for [ROLE] – [COMPANY]

Place: [LOCATION from resume, or leave blank if not found]

Dear Hiring Team,

[Opening paragraph: State the role you're applying for, mention one standout achievement or relevant experience that makes you a strong fit. Be specific and confident.]

[Second paragraph: Highlight 2-3 specific skills or experiences from the resume that directly match the job description requirements. Reference the company's work and how your background aligns with it.]

[Third paragraph: Express genuine enthusiasm for this specific company's mission, product, or impact. Connect your personal motivation to what they do. Be specific — not generic.]

[Fourth paragraph: State your eagerness to contribute. Mention what you would bring to the team specifically.]

Thank you for your time and consideration. I look forward to the opportunity to discuss how I can contribute to your team.

Sincerely,

[Candidate Full Name]
Mobile: [Phone number from resume if available]
---

STRICT RULES:
1. Follow the exact format above — do not add or remove sections
2. The title line must be: Application for [ROLE] – [COMPANY]
3. Use "Dear Hiring Team," as the salutation always
4. Write exactly 4 body paragraphs
5. End with exactly: "Thank you for your time and consideration. I look forward to the opportunity to discuss how I can contribute to your team."
6. Sign off with "Sincerely," then candidate name then mobile
7. Never invent experience not in the resume
8. Never use generic filler phrases — every sentence must be specific
9. Extract candidate name and phone from resume
10. Return ONLY the cover letter — no markdown, no backticks, no preamble"""

_TONE_GUIDE = {
    "professional":  "Formal, confident, results-focused. Use precise language.",
    "enthusiastic":  "Warm, energetic, shows genuine passion for the role and company mission.",
    "concise":       "Keep each paragraph to 2-3 sentences maximum. Tight and direct.",
}


async def generate_cover_letter(
    resume_text: str,
    job_description: str,
    company_name: str = "",
    tone: str = "professional",
) -> str:
    tone_note = _TONE_GUIDE.get(tone, _TONE_GUIDE["professional"])

    response = await client.chat.completions.create(
        model="gpt-4.1-mini",
        max_tokens=800,
        temperature=0.4,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": (
                f"TONE: {tone_note}\n"
                f"COMPANY: {company_name or 'the company'}\n\n"
                f"RESUME:\n{resume_text}\n\n"
                f"JOB DESCRIPTION:\n{job_description}"
            )},
        ],
    )

    return response.choices[0].message.content.strip()