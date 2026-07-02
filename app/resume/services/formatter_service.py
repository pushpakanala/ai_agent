from io import BytesIO
from docx import Document
from docx.shared import Pt

from app.resume.models.resume_schema import ResumeData


def add_heading(doc, text):
    p = doc.add_paragraph()

    run = p.add_run(text.upper())

    run.bold = True
    run.font.size = Pt(14)

    p.space_before = Pt(8)
    p.space_after = Pt(4)


def generate_docx(resume: ResumeData):

    doc = Document()

    sections = doc.sections

    for section in sections:
        section.top_margin = Pt(40)
        section.bottom_margin = Pt(40)

    # HEADER

    p = doc.add_paragraph()

    p.alignment = 1

    run = p.add_run(
        resume.candidate_name
    )

    run.bold = True
    run.font.size = Pt(20)

    doc.add_paragraph(
        f"{resume.contact.phone} | "
        f"{resume.contact.email} | "
        f"{resume.contact.linkedin}"
    )

    # SUMMARY

    add_heading(
        doc,
        "Professional Summary"
    )

    doc.add_paragraph(
        resume.summary
    )

    # SKILLS

    add_heading(
        doc,
        "Technical Skills"
    )

    for key, value in resume.skills.items():

        p = doc.add_paragraph()

        p.add_run(
            f"{key}: "
        ).bold = True

        p.add_run(
            ", ".join(value)
        )

    # EXPERIENCE

    add_heading(
        doc,
        "Experience"
    )

    for exp in resume.experience:

        p = doc.add_paragraph()

        p.add_run(
            exp.company
        ).bold = True

        p.add_run(
            f", {exp.location}"
        )

        p2 = doc.add_paragraph()

        p2.add_run(
            exp.role
        ).bold = True

        p2.add_run(
            f" ({exp.start_date} - {exp.end_date})"
        )

        for bullet in exp.bullets:

            doc.add_paragraph(
                bullet,
                style="List Bullet"
            )

    # PROJECTS

    add_heading(
        doc,
        "Projects"
    )

    for project in resume.projects:

        p = doc.add_paragraph()

        p.add_run(
            project.title
        ).bold = True

        doc.add_paragraph(
            f"Tech Stack: {project.tech_stack}"
        )

        for bullet in project.bullets:

            doc.add_paragraph(
                bullet,
                style="List Bullet"
            )

    # CERTIFICATIONS

    add_heading(
        doc,
        "Certifications"
    )

    for cert in resume.certifications:

        doc.add_paragraph(
            cert,
            style="List Bullet"
        )

    # AWARDS

    add_heading(
        doc,
        "Awards"
    )

    for award in resume.awards:

        doc.add_paragraph(
            award,
            style="List Bullet"
        )

    buffer = BytesIO()

    doc.save(buffer)

    buffer.seek(0)

    return buffer