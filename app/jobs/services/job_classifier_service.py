"""
job_classifier_service.py
--------------------------
FIX: Added multi-layer company name extraction.

Problem: LLM sometimes returns empty company_name even when the company
is clearly mentioned in the email body (e.g. Caterpillar emails sent
via cat@myworkday.com where the company name appears in the signature).

Solution: Three-layer extraction approach:
  Layer 1: LLM classifies the full email (existing approach)
  Layer 2: If company_name empty → regex scan the ENTIRE email text
            for company name patterns (signature, phrases, etc.)
  Layer 3: If still empty → second targeted LLM call asking ONLY
            "what company sent this email?" with the full body

This ensures company_name is extracted even from ATS platform emails
(myworkday.com, greenhouse.io, lever.co, taleo.net etc.) where the
sending domain is the ATS platform not the actual company.
"""

import json
import os
import re

from openai import OpenAI
from app.jobs.prompts.job_classifier_prompt import JOB_CLASSIFIER_PROMPT

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Known ATS platforms — emails from these domains need company
# extracted from the body, not the sender domain
ATS_DOMAINS = {
    "myworkday.com", "greenhouse.io", "lever.co", "taleo.net",
    "icims.com", "jobvite.com", "smartrecruiters.com", "workable.com",
    "brassring.com", "successfactors.com", "oraclecloud.com",
    "bamboohr.com", "recruitee.com", "ashbyhq.com",
    # Job boards — real company in email body
    "linkedin.com", "indeed.com", "glassdoor.com",
    "ziprecruiter.com", "monster.com", "dice.com",
}


def _extract_company_from_text(subject: str, body: str, sender: str = "") -> str:
    """
    Layer 2: Regex-based extraction scanning the ENTIRE email.
    Checks every common pattern where company names appear.
    """
    full_text = f"{subject}\n{body}"
    lines = full_text.split("\n")

    # Pattern 0: LinkedIn "Your update from [Company]"
    m = re.search(
        r"Your update from ([A-Z][A-Za-z0-9&\s\-\.,\']+?)(?:\n|$)",
        full_text, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(".,!")
        if 2 < len(name) < 60:
            return name

    # Pattern 0b: "position at [Company]" or "role at [Company]"
    m = re.search(
        r"(?:position|role|opportunity) at ([A-Z][A-Za-z0-9&\s\-\.,\']+?)(?:\s+in|\.|,|!|\n|$)",
        full_text, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(".,!")
        if 2 < len(name) < 60:
            return name

    # Pattern 0c: LinkedIn header "[Role] · [Company] · Location"
    m = re.search(
        r"[A-Z][A-Za-z0-9&\s\-\.,\']+\s+[·•\|]\s+([A-Z][A-Za-z0-9&\s\-\.,\']+?)\s+[·•\|]",
        full_text
    )
    if m:
        name = m.group(1).strip().rstrip(".,!")
        if 2 < len(name) < 60:
            return name

    # Pattern 1: "career at X" / "careers at X"
    m = re.search(
        r"career(?:s)? at ([A-Z][A-Za-z0-9&\s\-\.,']+?)(?:\.|,|!|\n|$)",
        full_text, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(".,!")
        if 2 < len(name) < 60:
            return name

    # Pattern 2: "interest in X" / "interest in a career at X"
    m = re.search(
        r"interest in (?:a career at )?([A-Z][A-Za-z0-9&\s\-\.,']+?)(?:\.|,|!|\n|$)",
        full_text, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(".,!")
        if 2 < len(name) < 60:
            return name

    # Pattern 3: "joining X" / "join the X team" / "join X"
    m = re.search(
        r"join(?:ing)? (?:the )?([A-Z][A-Za-z0-9&\s\-\.,']+?)(?:\s+team|\.|,|!|\n|$)",
        full_text, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(".,!")
        if 2 < len(name) < 60:
            return name

    # Pattern 4: "X Recruiting Team" / "X Talent Acquisition" / "X HR Team"
    m = re.search(
        r"([A-Z][A-Za-z0-9&\s\-\.,']+?)\s+(?:Recruiting Team|Talent Acquisition|HR Team|Hiring Team)",
        full_text
    )
    if m:
        name = m.group(1).strip()
        if 2 < len(name) < 60:
            return name

    # Pattern 5: Last lines of email — company name often in signature
    # e.g. "Caterpillar Inc." or "Google LLC" at the bottom
    for line in reversed(lines):
        line = line.strip()
        # Look for "Company Name Inc/LLC/Corp/Ltd" pattern
        m = re.match(
            r"^([A-Z][A-Za-z0-9&\s\-\.,']+?)\s+(?:Inc\.?|LLC\.?|Corp\.?|Ltd\.?|GmbH|S\.A\.|PLC)$",
            line
        )
        if m:
            name = m.group(0).strip()
            if 2 < len(name) < 60:
                return name

    # Pattern 6: "at X" in subject line
    m = re.search(
        r"(?:at|@)\s+([A-Z][A-Za-z0-9&\s\-\.,']+?)(?:\s+for|\s+\-|\.|,|$)",
        subject, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip()
        if 2 < len(name) < 60:
            return name

    # Pattern 7: "applying to X" / "applied to X"
    m = re.search(
        r"appl(?:ying|ied) to ([A-Z][A-Za-z0-9&\s\-\.,']+?)(?:\s+for|\.|,|$)",
        full_text, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(".,")
        if 2 < len(name) < 60:
            return name

    # Pattern 8: "from X" in sender context
    if sender:
        sender_domain = sender.split("@")[-1].split(".")[0]
        # Only use sender domain if NOT an ATS platform
        if not any(ats in sender for ats in ATS_DOMAINS):
            # Capitalise the domain part as company name
            company = sender_domain.capitalize()
            if len(company) > 2:
                return company

    return ""


def _extract_company_via_llm(subject: str, body: str) -> str:
    """
    Layer 3: Dedicated LLM call asking ONLY for the company name.
    Only called when both Layer 1 and Layer 2 fail.
    """
    try:
        prompt = f"""Read this email and tell me the name of the COMPANY (employer) that sent it.

Return ONLY a JSON object: {{"company_name": "Company Name Here"}}

If you truly cannot find any company name, return: {{"company_name": ""}}

Do not guess. Only return a name that is explicitly mentioned in the email.

Subject: {subject}

Email body:
{body[:3000]}"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            max_tokens=50,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(response.choices[0].message.content)
        return (result.get("company_name") or "").strip()
    except Exception:
        return ""


# Keywords that strongly indicate NOT a job application email
_NON_JOB_PATTERNS = [
    r"take the survey",
    r"tell us about your (application|interview|experience)",
    r"candidate experience survey",
    r"feedback.*survey",
    r"survey.*feedback",
    r"new job opportunities",
    r"jobs you might like",
    r"job alert",
    r"profile is getting hits",
    r"someone viewed your profile",
    r"special price",
    r"wordpress",
    r"unsubscribe",
    r"stay connected with",
    r"your subscription",
]

_NON_JOB_RE = re.compile(
    "|".join(_NON_JOB_PATTERNS),
    re.IGNORECASE,
)


def _is_obviously_not_job(subject: str, body: str) -> bool:
    """Quick pre-check before calling LLM — catches obvious non-job emails."""
    text = f"{subject} {body[:500]}"
    return bool(_NON_JOB_RE.search(text))


def classify_job_email(subject: str, body: str, sender: str = "") -> dict:
    """
    Classify a job email with three-layer company name extraction.

    Layer 0: Pre-check for obviously non-job emails (no API cost)
    Layer 1: Full LLM classification
    Layer 2: Regex scan if company_name empty
    Layer 3: Dedicated LLM company extraction if Layer 2 also fails
    """
    # Layer 0 — fast pre-check, zero API cost
    if _is_obviously_not_job(subject, body):
        return {
            "is_job_email":   False,
            "company_name":   "",
            "role":           "",
            "job_id":         "",
            "status":         "",
            "confidence":     0,
            "interview_date": None,
        }
    prompt = f"""Subject:
{subject}

Body:
{body}"""

    try:
        # ── Layer 1: Full LLM classification ─────────────────────────────
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": JOB_CLASSIFIER_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        result = json.loads(response.choices[0].message.content)

        company_name = (result.get("company_name") or "").strip()
        role         = (result.get("role") or "").strip()
        job_id       = (result.get("job_id") or "").strip()
        status       = result.get("status", "applied")
        is_job_email = result.get("is_job_email", False)

        # ── Layer 2: Regex fallback if company_name empty ─────────────────
        if is_job_email and not company_name:
            company_name = _extract_company_from_text(subject, body, sender)

        # ── Layer 3: Dedicated LLM call if still empty ────────────────────
        if is_job_email and not company_name:
            company_name = _extract_company_via_llm(subject, body)

        return {
            "is_job_email":   is_job_email,
            "company_name":   company_name,
            "role":           role,
            "job_id":         job_id,
            "status":         status,
            "confidence":     result.get("confidence", 0),
            "interview_date": result.get("interview_date", None),
        }

    except Exception as e:
        print("Job classification error:", e)
        return {
            "is_job_email":   False,
            "company_name":   "",
            "role":           "",
            "job_id":         "",
            "status":         "",
            "confidence":     0,
            "interview_date": None,
        }