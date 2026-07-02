"""
resume_normalizer.py
---------------------
Converts a resume dict of ANY shape into one canonical schema that every
renderer (docx, pdf, ATS text) consumes. This is the single place that
"guesses" which key means what — renderers should never need their own
fallback chains again.

STRATEGY
--------
For every field, try in order:
  1. Exact match against a list of known key names seen in the wild
     (fast path — covers every shape we've encountered so far).
  2. Fuzzy match: scan all keys on the dict and pick the first one whose
     name *contains* a relevant keyword, filtered by expected type
     (string vs list-of-strings). This is the safety net for a key name
     nobody has explicitly listed yet — e.g. "key_responsibilities",
     "job_duties", "highlights", "achievements_list", etc.
  3. If nothing matches, return an empty/blank value rather than crash.

CANONICAL SCHEMA
-----------------
{
  "candidate_name": str,
  "summary": str,
  "contact": {phone, email, linkedin, github, portfolio, location},
  "skills": {category: [items]},
  "education": [
    {degree, field, institution, location, date_str, gpa,
     specialization: [str], narrative}
  ],
  "experience": [
    {company, title, location, date_str, bullets: [str],
     projects: [{name, date_str, description, bullets: [str]}]}
  ],
  "projects": [{name, tech: [str], bullets: [str], link}],
  "certifications": [str],
  "awards": [{title, issuer, description}]
}
"""

from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Generic pick helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pick_str(d: dict, keys: list) -> str:
    """Exact-key match for a non-empty string field."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _pick_list(d: dict, keys: list) -> list:
    """Exact-key match for a non-empty list field."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, list) and v:
            return v
    return []


def _fuzzy_str(d: dict, keywords: list, exclude_keys: tuple = ()) -> str:
    """Fallback: any string-valued key whose name contains a keyword."""
    for k, v in d.items():
        if k in exclude_keys:
            continue
        if isinstance(v, str) and v.strip() and any(kw in k.lower() for kw in keywords):
            return v.strip()
    return ""


def _fuzzy_list_of_str(d: dict, keywords: list, exclude_keys: tuple = ()) -> list:
    """Fallback: any list-of-strings key whose name contains a keyword."""
    for k, v in d.items():
        if k in exclude_keys:
            continue
        if (
            isinstance(v, list)
            and v
            and all(isinstance(x, str) for x in v)
            and any(kw in k.lower() for kw in keywords)
        ):
            return v
    return []


def _stringify_bullet(item: Any) -> str:
    """A 'bullet' is sometimes a dict itself (e.g. {'text': '...'}) — flatten it."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for k in ("text", "content", "description", "point", "value"):
            v = item.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        # last resort: join any string values found
        parts = [v for v in item.values() if isinstance(v, str) and v.strip()]
        if parts:
            return " — ".join(parts)
    return str(item)


# ─────────────────────────────────────────────────────────────────────────────
# Field-level extractors (used across education/experience/projects/etc.)
# ─────────────────────────────────────────────────────────────────────────────

_BULLET_EXACT_KEYS = ["bullets", "tasks", "responsibilities", "points", "achievements", "highlights", "duties"]
_BULLET_FUZZY_KEYWORDS = ["bullet", "task", "responsib", "point", "achieve", "duty", "duties", "highlight"]

_NARRATIVE_EXACT_KEYS = ["narrative", "description", "overview", "summary", "about"]
_NARRATIVE_FUZZY_KEYWORDS = ["description", "overview", "narrative", "about"]

_DATE_EXACT_KEYS = ["date_str", "period", "date", "duration", "completion_date", "dates", "timeframe", "year", "graduation_date"]
_DATE_FUZZY_KEYWORDS = ["date", "period", "duration", "timeframe", "year"]


def _get_bullets(d: dict) -> list:
    """
    Resolve a bullet list. 'details' is special-cased: it's sometimes a
    list of bullets and sometimes a single descriptive paragraph string,
    so only treat it as bullets when it's actually a list.
    """
    details = d.get("details")
    if isinstance(details, list) and details:
        raw = details
    else:
        raw = (
            _pick_list(d, _BULLET_EXACT_KEYS)
            or _fuzzy_list_of_str(d, _BULLET_FUZZY_KEYWORDS)
        )
    return [_stringify_bullet(b) for b in raw if b]


def _get_narrative(d: dict) -> str:
    """A descriptive paragraph that isn't a bullet list."""
    details = d.get("details")
    if isinstance(details, str) and details.strip():
        return details.strip()
    return (
        _pick_str(d, _NARRATIVE_EXACT_KEYS)
        or _fuzzy_str(d, _NARRATIVE_FUZZY_KEYWORDS)
    )


def _get_date_str(d: dict) -> str:
    exact = _pick_str(d, _DATE_EXACT_KEYS)
    if exact:
        return exact
    start = _pick_str(d, ["start_date", "from_date", "start"])
    end = _pick_str(d, ["end_date", "to_date", "end"])
    if start or end:
        return f"{start} - {end}".strip(" -")
    return _fuzzy_str(d, _DATE_FUZZY_KEYWORDS, exclude_keys=("start_date", "end_date"))


# ─────────────────────────────────────────────────────────────────────────────
# Section normalizers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_contact(d: dict) -> dict:
    d = d or {}
    return {
        "phone": _pick_str(d, ["phone", "phone_number", "mobile", "contact_number"]),
        "email": _pick_str(d, ["email", "email_address"]),
        "linkedin": _pick_str(d, ["linkedin", "linkedin_url"]),
        "github": _pick_str(d, ["github", "github_url"]),
        "portfolio": _pick_str(d, ["portfolio", "website", "personal_site"]),
        "location": _pick_str(d, ["location", "address", "city"]),
    }


def _normalize_education(items: list) -> list:
    out = []
    for edu in items or []:
        if not isinstance(edu, dict):
            continue
        degree = _pick_str(edu, ["degree", "degree_name", "qualification"])
        field = _pick_str(edu, ["field", "major", "concentration", "specialization_field"])
        institution = _pick_str(edu, ["institution", "school", "university", "college"])
        location = _pick_str(edu, ["location", "city"])
        gpa = _pick_str(edu, ["gpa", "grade", "score"])
        specialization = _pick_list(edu, ["specialization", "coursework", "relevant_courses"])
        out.append({
            "degree": degree,
            "field": field,
            "institution": institution,
            "location": location,
            "date_str": _get_date_str(edu),
            "gpa": gpa,
            "specialization": [s for s in specialization if isinstance(s, str)],
            "narrative": _get_narrative(edu),
        })
    return out


def _normalize_experience_project(proj: dict) -> dict:
    return {
        "name": _pick_str(proj, ["name", "title", "project_name"]),
        "date_str": _get_date_str(proj),
        "description": _get_narrative(proj),
        "bullets": _get_bullets(proj),
    }


def _normalize_experience(items: list) -> list:
    out = []
    for exp in items or []:
        if not isinstance(exp, dict):
            continue
        company = _pick_str(exp, ["company", "employer", "organization"])
        title = _pick_str(exp, ["title", "role", "position", "designation", "job_title"])
        location = _pick_str(exp, ["location", "city"])
        sub_projects = _pick_list(exp, ["projects", "sub_projects"])
        out.append({
            "company": company,
            "title": title,
            "location": location,
            "date_str": _get_date_str(exp),
            "bullets": _get_bullets(exp),
            "projects": [
                _normalize_experience_project(p) for p in sub_projects if isinstance(p, dict)
            ],
        })
    return out


def _normalize_projects(items: list) -> list:
    out = []
    for proj in items or []:
        if not isinstance(proj, dict):
            continue
        tech = _pick_list(proj, ["tech", "tech_stack", "technologies", "stack", "tools"])
        link = _pick_str(proj, ["demo", "note", "link", "url", "live_demo"])
        bullets = _get_bullets(proj) or [
            b for b in _pick_list(proj, ["description"]) if isinstance(b, str)
        ]
        out.append({
            "name": _pick_str(proj, ["name", "title", "project_name"]),
            "tech": [t for t in tech if isinstance(t, str)],
            "bullets": bullets,
            "link": link,
        })
    return out


def _normalize_certifications(items: list) -> list:
    out = []
    for cert in items or []:
        if isinstance(cert, str):
            out.append(cert)
        elif isinstance(cert, dict):
            out.append(_pick_str(cert, ["name", "title", "certification"]) or str(cert))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Structural repair: some pipeline outputs misplace an experience's
# sub-projects under the top-level "projects" key instead of nesting them
# inside "experience". Each misplaced item looks like an experience block
# itself (company/role/duration + its own nested "projects" list) rather
# than a real standalone project (name/tech/bullets). Detect and merge
# these back into the matching experience entry instead of rendering them
# as blank project cards.
# ─────────────────────────────────────────────────────────────────────────────

def _looks_like_experience_wrapper(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    has_company_or_role = bool(
        _pick_str(item, ["company", "employer", "organization"])
        or _pick_str(item, ["role", "title", "position", "designation", "job_title"])
    )
    has_nested_projects = bool(_pick_list(item, ["projects", "sub_projects"]))
    return has_company_or_role and has_nested_projects


def _companies_match(a: str, b: str) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    if not a or not b:
        return False
    return a in b or b in a


def _split_projects_section(raw_projects: list, experience: list) -> list:
    """
    Walk the raw top-level 'projects' list. Anything that looks like a
    misplaced experience block gets merged into the matching experience
    entry (by loose company match) or appended as a new experience entry
    if no match is found. Returns the remaining items that are genuinely
    standalone projects.
    """
    standalone = []

    for item in raw_projects or []:

        if not _looks_like_experience_wrapper(item):
            standalone.append(item)
            continue

        wrapper = _normalize_experience([item])[0]
        company = wrapper["company"]

        merged = False
        for exp in experience:
            if _companies_match(company, exp["company"]):
                exp["date_str"] = exp["date_str"] or wrapper["date_str"]
                exp["title"] = exp["title"] or wrapper["title"]
                exp["location"] = exp["location"] or wrapper["location"]
                exp["bullets"] = exp["bullets"] or wrapper["bullets"]
                exp["projects"] = exp["projects"] or wrapper["projects"]
                merged = True
                break

        if not merged:
            experience.append(wrapper)

    return standalone


def _normalize_awards(items: list) -> list:
    out = []
    for award in items or []:
        if isinstance(award, str):
            out.append({"title": award, "issuer": "", "description": ""})
        elif isinstance(award, dict):
            out.append({
                "title": _pick_str(award, ["title", "name", "award", "honor"]),
                "issuer": _pick_str(award, ["issuer", "organization", "company", "from"]),
                "description": _pick_str(award, ["description", "details", "reason"]),
            })
    return out


def _normalize_skills(skills: Any) -> dict:
    if isinstance(skills, dict):
        return {
            str(category): [str(v) for v in values]
            for category, values in skills.items()
            if isinstance(values, list) and values
        }
    if isinstance(skills, list):
        # Flat list of skills with no categories
        flat = [str(s) for s in skills if isinstance(s, (str, int, float))]
        return {"Skills": flat} if flat else {}
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def normalize_resume(raw: dict) -> dict:
    """
    Convert any incoming resume JSON shape into the canonical schema.
    Safe to call multiple times (idempotent) and safe on partial/missing data.
    """
    raw = raw or {}

    experience = _normalize_experience(raw.get("experience", []))
    standalone_project_items = _split_projects_section(raw.get("projects", []), experience)

    return {
        "candidate_name": _pick_str(raw, ["candidate_name", "name", "full_name", "fullName"]),
        "summary": _pick_str(raw, ["summary", "professional_summary", "objective", "profile"])
                   or _fuzzy_str(raw, ["summary", "objective", "profile"]),
        "contact": _normalize_contact(raw.get("contact", {})),
        "skills": _normalize_skills(raw.get("skills", {})),
        "education": _normalize_education(raw.get("education", [])),
        "experience": experience,
        "projects": _normalize_projects(standalone_project_items),
        "certifications": _normalize_certifications(raw.get("certifications", [])),
        "awards": _normalize_awards(raw.get("awards", [])),
    }