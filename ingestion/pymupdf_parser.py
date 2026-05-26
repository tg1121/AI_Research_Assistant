import fitz  # PyMuPDF
import re
from .document import Document, Section

def parse_with_pymupdf(pdf_path: str, paper_id: str) -> Document:
    doc = fitz.open(pdf_path)
    
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    
    doc.close()
    
    title = _extract_title(full_text)
    sections = _split_sections(full_text)
    
    return Document(
        paper_id=paper_id,
        title=title,
        raw_markdown=full_text,
        sections=sections
    )

def _extract_title(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[0] if lines else "Unknown Title"

def _split_sections(text: str) -> list[Section]:
    # split on numbered section headings like "1.", "2.", "1.1" etc
    pattern = r'(\n\d+\.[\d\.]*\s+[A-Z][^\n]+)'
    parts = re.split(pattern, text)
    
    sections = []
    current_title = "preamble"
    current_text = []
    section_idx = 0

    for part in parts:
        if re.match(r'\n\d+\.[\d\.]*\s+[A-Z]', part):
            if current_text:
                body = "\n".join(current_text).strip()
                if body:
                    sections.append(Section(
                        section_id=f"s{section_idx}",
                        title=current_title,
                        raw_text=body
                    ))
                    section_idx += 1
            current_title = part.strip()
            current_text = []
        else:
            current_text.append(part)

    if current_text:
        body = "\n".join(current_text).strip()
        if body:
            sections.append(Section(
                section_id=f"s{section_idx}",
                title=current_title,
                raw_text=body
            ))

    return sections