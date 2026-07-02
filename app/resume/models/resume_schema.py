# app/resume/models/resume_schema.py
"""
resume_schema.py
-----------------
THE single source of truth for what a resume JSON object looks like.

This is the strict contract handed to Claude at generation time (via
app.resume.services.claude_client) and validated against immediately
after every generation call. Key points:

- One field name per concept (e.g. bullets — never tasks/details/responsibilities;
  date_str — never period/duration/completion_date).
- No ambiguous alternate locations for the same data (e.g. a project's
  sub-projects can ONLY live under experience[].projects, never duplicated
  under a top-level "projects" wrapper).
- extra="forbid" on every model so Claude can't invent new keys we'd then
  have to guess about later.

For reading OLD/legacy documents already in Mongo that predate this schema
being enforced, use app.resume.services.resume_normalizer.normalize_resume()
— that's the permanent, lenient safety net. This file is the strict layer
for everything generated from now on.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field


class ContactInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: Optional[str] = None
    email: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    location: Optional[str] = None


class Education(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: str
    field: Optional[str] = Field(None, description="Major/field of study, e.g. 'Computer Science'")
    institution: str
    location: Optional[str] = None
    date_str: Optional[str] = Field(
        None,
        description="Human-readable date range or completion date, e.g. 'Aug 2024 - May 2026' or 'May 2019' or 'Present'",
    )
    gpa: Optional[str] = None
    specialization: List[str] = Field(default_factory=list, description="Relevant coursework or specialization areas")
    narrative: Optional[str] = Field(None, description="Free-text description paragraph, if any (not a bullet list)")


class ExperienceProject(BaseModel):
    """A sub-project nested under a work experience entry."""
    model_config = ConfigDict(extra="forbid")

    name: str
    date_str: Optional[str] = None
    description: Optional[str] = Field(None, description="One summary paragraph, NOT a bullet list")
    bullets: List[str] = Field(default_factory=list, description="Bullet points describing accomplishments on this project")


class Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str
    title: str
    location: Optional[str] = None
    date_str: Optional[str] = Field(None, description="Human-readable date range, e.g. 'July 2022 - Aug 2024'")
    bullets: List[str] = Field(
        default_factory=list,
        description="Bullet points directly on this role, used when there are no distinct sub-projects",
    )
    projects: List[ExperienceProject] = Field(
        default_factory=list,
        description="Distinct projects worked on during this role. Put ALL project-specific bullets here, "
                     "NOT in a separate top-level projects list.",
    )


class Project(BaseModel):
    """
    A genuinely standalone personal/portfolio project — NOT tied to an
    employer. If a project belongs to a job, it goes under that
    experience entry's 'projects' list instead, never here.
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    tech: List[str] = Field(default_factory=list)
    bullets: List[str] = Field(default_factory=list)
    link: Optional[str] = Field(None, description="Demo/live link or note, e.g. 'Live Demo'")


class Award(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    issuer: Optional[str] = None
    description: Optional[str] = None


class ResumeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_name: str
    summary: str
    contact: ContactInfo
    skills: Dict[str, List[str]]
    education: List[Education] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    projects: List[Project] = Field(
        default_factory=list,
        description="ONLY standalone personal projects not tied to any employer. "
                     "Employer-related projects belong under experience[].projects.",
    )
    certifications: List[str] = Field(default_factory=list)
    awards: List[Award] = Field(default_factory=list)
