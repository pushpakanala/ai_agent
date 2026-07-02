"""
parser_service.py
-----------------
Extracts plain text from PDF and DOCX resume files.

DOCX FIX: Many resume templates (including two-column table layouts) put
bullet points and dates inside table cells as nested paragraph runs rather
than plain cell.text. The previous _render_table() only read cell.text,
which merges all runs into one blob — so bullets and dates in the right
column were lost or fused together.

Fix: walk every paragraph inside each table cell (cell.paragraphs), then
join their stripped run texts. This correctly extracts:
  • Left column: job title + company
  • Right column: date (which was the missing piece)
  • Following rows: bullet points stored as paragraphs in the cell
"""

import pymupdf as fitz  # PyMuPDF — do NOT use `pip install fitz` (wrong package)
from io import BytesIO
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


async def extract_pdf_text(file_bytes: bytes) -> str:
    text = ""
    pdf = fitz.open(stream=file_bytes, filetype="pdf")
    for page in pdf:
        text += page.get_text()
    pdf.close()
    return text.strip()


def _cell_text(cell) -> str:
    """
    Extract all text from a table cell by walking its paragraphs.
    Each paragraph becomes its own line so bullets aren't fused together.
    """
    lines = []
    for para in cell.paragraphs:
        # Join runs inside the paragraph (handles bold/italic run splits)
        line = "".join(run.text for run in para.runs).strip()
        if line:
            lines.append(line)
    # Fallback to cell.text if no paragraphs had content
    if not lines and cell.text.strip():
        lines.append(cell.text.strip())
    return "\n".join(lines)


def _render_table(table: Table) -> str:
    """
    Render a Word table as readable text.
    Each row becomes one or more lines; multi-paragraph cells are expanded
    so every bullet and date appears on its own line.

    Two-column resume templates (role | date) render as:
        Company Name | Software Engineer
        Jan 2022 – Aug 2024
        • Built ...
        • Optimized ...

    rather than the old single-line blob that lost all structure.
    """
    lines = []
    for row in table.rows:
        # Collect per-cell content (list of lines per cell)
        cell_contents = [_cell_text(cell).splitlines() for cell in row.cells]

        # Deduplicate adjacent identical cells (Word merges produce duplicates)
        seen = []
        for content in cell_contents:
            key = "\n".join(content)
            if key and key not in seen:
                seen.append(key)
                cell_contents_deduped = content
            else:
                cell_contents_deduped = []

        # Flatten: first line of each cell joins with " | ",
        # remaining lines go on their own lines
        first_lines = []
        extra_lines = []
        seen_keys = set()
        for content in [_cell_text(c).splitlines() for c in row.cells]:
            key = "\n".join(content)
            if not content or key in seen_keys:
                continue
            seen_keys.add(key)
            first_lines.append(content[0])
            extra_lines.extend(content[1:])

        if first_lines:
            lines.append(" | ".join(first_lines))
        lines.extend(extra_lines)

    return "\n".join(l for l in lines if l.strip())


async def extract_docx_text(file_bytes: bytes) -> str:
    """
    Walk paragraphs and tables in document order (not just document.paragraphs,
    which silently skips tables). Tables are expanded cell-by-cell so no
    content is lost regardless of whether the template uses:
      - plain paragraphs (single-column resumes)
      - tables for layout (two-column, sidebar, grid resumes)
      - mixed layouts (header table + paragraph body)
    """
    document = Document(BytesIO(file_bytes))
    parts = []

    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if text:
                parts.append(text)
        elif isinstance(item, Table):
            table_text = _render_table(item)
            if table_text:
                parts.append(table_text)

    return "\n".join(parts).strip()


async def extract_resume_text(filename: str, file_bytes: bytes) -> str:
    filename = filename.lower()
    if filename.endswith(".pdf"):
        return await extract_pdf_text(file_bytes)
    if filename.endswith(".docx"):
        return await extract_docx_text(file_bytes)
    raise Exception("Unsupported file type. Please upload a PDF or DOCX.")