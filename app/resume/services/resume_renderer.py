"""
resume_renderer.py
------------------
Converts a structured resume dict → plain text for ATS scoring and storage.

Handles ANY incoming schema shape by normalizing through
resume_normalizer.normalize_resume() first — this file only ever
deals with the canonical schema after that.
"""

from app.resume.services.resume_normalizer import normalize_resume


def render_resume_text(resume: dict) -> str:
    resume = normalize_resume(resume)
    output = []

    # ─────────────────────────────────────────────────────────────
    # Header
    # ─────────────────────────────────────────────────────────────
    output.append(resume["candidate_name"])

    contact = resume["contact"]

    contact_parts = filter(
        None,
        [
            contact["phone"],
            contact["email"],
            contact["linkedin"],
            contact["github"],
            contact["portfolio"],
            contact["location"],
        ],
    )

    output.append(" | ".join(contact_parts))
    output.append("")

    # ─────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────
    if resume["summary"]:
        output.append("PROFESSIONAL SUMMARY")
        output.append(resume["summary"])
        output.append("")

    # ─────────────────────────────────────────────────────────────
    # Education
    # ─────────────────────────────────────────────────────────────
    if resume["education"]:

        output.append("EDUCATION")

        for edu in resume["education"]:

            degree_line = f"{edu['degree']} in {edu['field']}" if edu["field"] and edu["field"].lower() not in edu["degree"].lower() else edu["degree"]
            output.append(degree_line)

            institution_line = " | ".join(filter(None, [edu["institution"], edu["location"]]))
            if institution_line:
                output.append(institution_line)

            if edu["date_str"]:
                output.append(edu["date_str"])

            if edu["gpa"]:
                output.append(f"GPA: {edu['gpa']}")

            if edu["specialization"]:
                output.append("Relevant Coursework: " + ", ".join(edu["specialization"]))

            if edu["narrative"]:
                output.append(edu["narrative"])

            output.append("")

    # ─────────────────────────────────────────────────────────────
    # Skills
    # ─────────────────────────────────────────────────────────────
    if resume["skills"]:

        output.append("TECHNICAL SKILLS")

        for category, values in resume["skills"].items():
            output.append(f"{category}: {', '.join(values)}")

        output.append("")

    # ─────────────────────────────────────────────────────────────
    # Experience
    # ─────────────────────────────────────────────────────────────
    if resume["experience"]:

        output.append("WORK EXPERIENCE")

        for exp in resume["experience"]:

            output.append(exp["company"])

            role_line = " | ".join(filter(None, [exp["title"], exp["location"]]))
            if role_line:
                output.append(role_line)

            if exp["date_str"]:
                output.append(exp["date_str"])

            # Bullets directly on the experience (no sub-projects), e.g. an internship
            for task in exp["bullets"]:
                output.append(f"• {task}")

            # Nested projects inside experience
            for project in exp["projects"]:

                output.append("")
                output.append(f"Project: {project['name']}")

                if project["date_str"]:
                    output.append(project["date_str"])

                if project["description"]:
                    output.append(project["description"])

                for task in project["bullets"]:
                    output.append(f"  • {task}")

            output.append("")

    # ─────────────────────────────────────────────────────────────
    # Projects
    # ─────────────────────────────────────────────────────────────
    if resume["projects"]:

        output.append("PROJECTS")

        for project in resume["projects"]:

            output.append(project["name"])

            if project["tech"]:
                output.append("Tech: " + ", ".join(project["tech"]))

            if project["link"]:
                output.append(project["link"])

            for bullet in project["bullets"]:
                output.append(f"• {bullet}")

            output.append("")

    # ─────────────────────────────────────────────────────────────
    # Certifications
    # ─────────────────────────────────────────────────────────────
    if resume["certifications"]:

        output.append("CERTIFICATIONS")

        for cert in resume["certifications"]:
            output.append(f"• {cert}")

        output.append("")

    # ─────────────────────────────────────────────────────────────
    # Awards
    # ─────────────────────────────────────────────────────────────
    if resume["awards"]:

        output.append("AWARDS")

        for award in resume["awards"]:

            line = award["title"]

            if award["issuer"]:
                line += f" — {award['issuer']}"

            output.append(f"• {line}")

            if award["description"]:
                output.append(f"  {award['description']}")

        output.append("")

    return "\n".join(str(x) for x in output if x is not None)