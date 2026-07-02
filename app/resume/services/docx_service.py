"""
docx_service.py
---------------
Generates a .docx file from a structured resume dict.

Handles ANY incoming schema shape by normalizing through
resume_normalizer.normalize_resume() first — this file only ever
deals with the canonical schema after that.
"""

from io import BytesIO
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from app.resume.services.resume_normalizer import normalize_resume


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _add_horizontal_rule(doc):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()

    pBdr = OxmlElement("w:pBdr")

    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "CCCCCC")

    pBdr.append(bottom)
    pPr.append(pBdr)

    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)

    return p


def _add_section_heading(doc, text: str):
    p = doc.add_paragraph()

    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)

    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(2)

    _add_horizontal_rule(doc)


def _add_bullets(doc, items):

    if not items:
        return

    for item in items:

        if not item:
            continue

        doc.add_paragraph(
            str(item),
            style="List Bullet",
        )


def _degree_line(edu: dict) -> str:
    if edu["field"] and edu["field"].lower() not in edu["degree"].lower():
        return f"{edu['degree']} in {edu['field']}" if edu["degree"] else edu["field"]
    return edu["degree"]


# ─────────────────────────────────────────────────────────────────────────────
# Main generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_docx_bytes(resume_json: dict) -> BytesIO:

    resume_json = normalize_resume(resume_json)

    doc = Document()

    # Global font
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    # Margins
    for section in doc.sections:
        section.top_margin = Pt(36)
        section.bottom_margin = Pt(36)
        section.left_margin = Pt(54)
        section.right_margin = Pt(54)

    # ─────────────────────────────────────────────────────────────────
    # Header
    # ─────────────────────────────────────────────────────────────────

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = p.add_run(resume_json["candidate_name"])
    run.bold = True
    run.font.size = Pt(20)
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)

    contact = resume_json["contact"]

    contact_parts = [
        v for v in [
            contact["phone"],
            contact["email"],
            contact["location"],
            contact["linkedin"],
            contact["github"],
            contact["portfolio"],
        ]
        if v
    ]

    if contact_parts:

        p2 = doc.add_paragraph(" | ".join(contact_parts))
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.runs[0].font.size = Pt(9)
        p2.runs[0].font.color.rgb = RGBColor(0x44, 0x44, 0x55)

    # ─────────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────────

    if resume_json["summary"]:

        _add_section_heading(doc, "Professional Summary")
        doc.add_paragraph(resume_json["summary"])

    # ─────────────────────────────────────────────────────────────────
    # Education
    # ─────────────────────────────────────────────────────────────────

    if resume_json["education"]:

        _add_section_heading(doc, "Education")

        for edu in resume_json["education"]:

            p = doc.add_paragraph()

            heading = _degree_line(edu)
            if edu["institution"]:
                heading = f"{heading} — {edu['institution']}" if heading else edu["institution"]

            p.add_run(heading).bold = True

            if edu["date_str"]:
                p.add_run(f"\n{edu['date_str']}")

            if edu["location"]:
                p.add_run(f"  ·  {edu['location']}")

            if edu["gpa"]:
                p.add_run(f"  |  GPA: {edu['gpa']}")

            if edu["specialization"]:
                p.add_run("\nCoursework: " + ", ".join(edu["specialization"]))

            if edu["narrative"]:
                doc.add_paragraph(edu["narrative"])

    # ─────────────────────────────────────────────────────────────────
    # Skills
    # ─────────────────────────────────────────────────────────────────

    if resume_json["skills"]:

        _add_section_heading(doc, "Technical Skills")

        for category, values in resume_json["skills"].items():

            p = doc.add_paragraph()
            p.add_run(f"{category}: ").bold = True
            p.add_run(", ".join(values))
            p.paragraph_format.space_after = Pt(1)

    # ─────────────────────────────────────────────────────────────────
    # Experience
    # ─────────────────────────────────────────────────────────────────

    if resume_json["experience"]:

        _add_section_heading(doc, "Work Experience")

        for exp in resume_json["experience"]:

            p = doc.add_paragraph()

            header = exp["company"]
            if exp["title"]:
                header = f"{header} | {exp['title']}" if header else exp["title"]

            p.add_run(header).bold = True

            if exp["date_str"]:
                p.add_run(f"\n{exp['date_str']}")

            if exp["location"]:
                p.add_run(f"  ·  {exp['location']}")

            # Bullets directly on the experience (no sub-projects), e.g. an internship
            _add_bullets(doc, exp["bullets"])

            # Nested projects support
            for project in exp["projects"]:

                proj_para = doc.add_paragraph(style="List Bullet")
                proj_para.add_run(f"Project: {project['name']}").italic = True

                if project["description"]:
                    doc.add_paragraph(project["description"])

                _add_bullets(doc, project["bullets"])

    # ─────────────────────────────────────────────────────────────────
    # Projects
    # ─────────────────────────────────────────────────────────────────

    if resume_json["projects"]:

        _add_section_heading(doc, "Projects")

        for project in resume_json["projects"]:

            p = doc.add_paragraph()
            p.add_run(project["name"]).bold = True

            if project["tech"]:
                p.add_run("\nTech: " + ", ".join(project["tech"]))

            if project["link"]:
                p.add_run(f"\n{project['link']}")

            _add_bullets(doc, project["bullets"])

    # ─────────────────────────────────────────────────────────────────
    # Certifications
    # ─────────────────────────────────────────────────────────────────

    if resume_json["certifications"]:

        _add_section_heading(doc, "Certifications")
        _add_bullets(doc, resume_json["certifications"])

    # ─────────────────────────────────────────────────────────────────
    # Awards
    # ─────────────────────────────────────────────────────────────────

    if resume_json["awards"]:

        _add_section_heading(doc, "Awards")

        for award in resume_json["awards"]:

            text = award["title"]

            if award["issuer"]:
                text += f" ({award['issuer']})"

            if award["description"]:
                text += f": {award['description']}"

            doc.add_paragraph(text, style="List Bullet")

    output = BytesIO()
    doc.save(output)
    output.seek(0)

    return output