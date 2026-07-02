"""
pdf_service.py
--------------
Generates a PDF from a structured resume dict.

Handles ANY incoming schema shape by normalizing through
resume_normalizer.normalize_resume() first — this file only ever
deals with the canonical schema after that.
"""

from io import BytesIO

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
)

from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)

from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.colors import HexColor

from app.resume.services.resume_normalizer import normalize_resume


NAVY = HexColor("#1A1A2E")
SLATE = HexColor("#444455")
SILVER = HexColor("#CCCCCC")
BLACK = HexColor("#111111")


def _degree_line(edu: dict) -> str:
    if edu["field"] and edu["field"].lower() not in edu["degree"].lower():
        return f"{edu['degree']} in {edu['field']}" if edu["degree"] else edu["field"]
    return edu["degree"]


def _build_styles():

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="ResumeName", fontName="Helvetica-Bold", fontSize=22,
        textColor=NAVY, alignment=TA_CENTER, spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        name="ResumeContact", fontName="Helvetica", fontSize=9,
        textColor=SLATE, alignment=TA_CENTER, spaceAfter=14,
    ))

    styles.add(ParagraphStyle(
        name="SectionHeading", fontName="Helvetica-Bold", fontSize=10,
        textColor=NAVY, spaceBefore=10, spaceAfter=2, leading=13,
    ))

    styles.add(ParagraphStyle(
        name="ResumeBody", fontName="Helvetica", fontSize=10,
        textColor=BLACK, leading=14, spaceAfter=3,
    ))

    styles.add(ParagraphStyle(
        name="BulletText", fontName="Helvetica", fontSize=10,
        textColor=BLACK, leading=14, leftIndent=14, spaceAfter=2,
    ))

    return styles


def generate_pdf_bytes(resume_json: dict):

    resume_json = normalize_resume(resume_json)

    output = BytesIO()

    doc = SimpleDocTemplate(
        output,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = _build_styles()
    elements = []

    def hr():
        elements.append(HRFlowable(width="100%", thickness=0.5, color=SILVER, spaceAfter=6))

    # ==================================================
    # Header
    # ==================================================

    elements.append(Paragraph(resume_json["candidate_name"], styles["ResumeName"]))

    contact = resume_json["contact"]

    contact_parts = [
        v for v in [
            contact["phone"], contact["email"], contact["location"],
            contact["linkedin"], contact["github"], contact["portfolio"],
        ]
        if v
    ]

    if contact_parts:
        elements.append(Paragraph(" | ".join(contact_parts), styles["ResumeContact"]))

    # ==================================================
    # Summary
    # ==================================================

    if resume_json["summary"]:

        elements.append(Paragraph("PROFESSIONAL SUMMARY", styles["SectionHeading"]))
        hr()
        elements.append(Paragraph(resume_json["summary"], styles["ResumeBody"]))
        elements.append(Spacer(1, 6))

    # ==================================================
    # Education
    # ==================================================

    if resume_json["education"]:

        elements.append(Paragraph("EDUCATION", styles["SectionHeading"]))
        hr()

        for edu in resume_json["education"]:

            content = f"<b>{_degree_line(edu)}</b><br/>{edu['institution']}"

            if edu["location"]:
                content += f", {edu['location']}"

            if edu["date_str"]:
                content += f"<br/>{edu['date_str']}"

            if edu["gpa"]:
                content += f"<br/>GPA: {edu['gpa']}"

            if edu["specialization"]:
                content += "<br/>Relevant Coursework: " + ", ".join(edu["specialization"])

            elements.append(Paragraph(content, styles["ResumeBody"]))

            if edu["narrative"]:
                elements.append(Paragraph(edu["narrative"], styles["ResumeBody"]))

        elements.append(Spacer(1, 6))

    # ==================================================
    # Skills
    # ==================================================

    if resume_json["skills"]:

        elements.append(Paragraph("TECHNICAL SKILLS", styles["SectionHeading"]))
        hr()

        for category, values in resume_json["skills"].items():
            elements.append(Paragraph(f"<b>{category}:</b> {', '.join(values)}", styles["ResumeBody"]))

        elements.append(Spacer(1, 6))

    # ==================================================
    # Experience
    # ==================================================

    if resume_json["experience"]:

        elements.append(Paragraph("WORK EXPERIENCE", styles["SectionHeading"]))
        hr()

        for exp in resume_json["experience"]:

            header = f"<b>{exp['company']}</b>"
            if exp["title"]:
                header += f"<br/>{exp['title']}"
            if exp["location"]:
                header += f" | {exp['location']}"
            if exp["date_str"]:
                header += f"<br/>{exp['date_str']}"

            elements.append(Paragraph(header, styles["ResumeBody"]))

            # Bullets directly on the experience (no sub-projects), e.g. an internship
            for task in exp["bullets"]:
                elements.append(Paragraph(f"• {task}", styles["BulletText"]))

            # Nested projects
            for project in exp["projects"]:

                elements.append(Paragraph(f"<b>Project: {project['name']}</b>", styles["ResumeBody"]))

                if project["description"]:
                    elements.append(Paragraph(project["description"], styles["ResumeBody"]))

                for task in project["bullets"]:
                    elements.append(Paragraph(f"• {task}", styles["BulletText"]))

            elements.append(Spacer(1, 6))

    # ==================================================
    # Projects
    # ==================================================

    if resume_json["projects"]:

        elements.append(Paragraph("PROJECTS", styles["SectionHeading"]))
        hr()

        for project in resume_json["projects"]:

            elements.append(Paragraph(f"<b>{project['name']}</b>", styles["ResumeBody"]))

            if project["tech"]:
                elements.append(Paragraph(f"<b>Tech:</b> {', '.join(project['tech'])}", styles["ResumeBody"]))

            if project["link"]:
                elements.append(Paragraph(project["link"], styles["ResumeBody"]))

            for bullet in project["bullets"]:
                elements.append(Paragraph(f"• {bullet}", styles["BulletText"]))

            elements.append(Spacer(1, 6))

    # ==================================================
    # Certifications
    # ==================================================

    if resume_json["certifications"]:

        elements.append(Paragraph("CERTIFICATIONS", styles["SectionHeading"]))
        hr()

        for cert in resume_json["certifications"]:
            elements.append(Paragraph(f"• {cert}", styles["BulletText"]))

        elements.append(Spacer(1, 6))

    # ==================================================
    # Awards
    # ==================================================

    if resume_json["awards"]:

        elements.append(Paragraph("AWARDS", styles["SectionHeading"]))
        hr()

        for award in resume_json["awards"]:

            elements.append(Paragraph(f"• <b>{award['title']}</b>", styles["BulletText"]))

            if award["description"]:
                elements.append(Paragraph(award["description"], styles["ResumeBody"]))

    doc.build(elements)
    output.seek(0)

    return output