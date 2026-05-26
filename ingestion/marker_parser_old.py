import os
import re
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from .document import Document, Section

MARKER_CACHE = os.path.join(os.path.dirname(__file__), "..", "marker_output")

# load models once at module level so they aren't reloaded every call
_converter = None

def _get_converter():
    global _converter
    if _converter is None:
        _converter = PdfConverter(artifact_dict=create_model_dict())
    return _converter

def parse_with_marker(pdf_path: str, paper_id: str) -> Document:
    os.makedirs(MARKER_CACHE, exist_ok=True)
    cache_path = os.path.join(MARKER_CACHE, f"{paper_id}.md")

    if os.path.exists(cache_path):
        print(f"  Using cached marker output: {cache_path}")
        with open(cache_path, encoding="utf-8") as f:
            raw_md = f.read()
    else:
        print(f"  Running marker on {pdf_path}...")
        converter = _get_converter()
        rendered = converter(pdf_path)
        raw_md, _, _ = text_from_rendered(rendered)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(raw_md)
        print(f"  Cached to {cache_path}")

    title = _extract_title(raw_md)
    sections = _split_sections(raw_md)

    return Document(
        paper_id=paper_id,
        title=title,
        raw_markdown=raw_md,
        sections=sections
    )

def _clean_title(title: str) -> str:
    """Remove HTML spans and other marker artifacts from section titles."""
    # strip <span id="..."></span> patterns
    title = re.sub(r'<span[^>]*>', '', title)
    title = re.sub(r'</span>', '', title)
    # strip any remaining HTML tags
    title = re.sub(r'<[^>]+>', '', title)
    return title.strip()

def _extract_title(md: str) -> str:
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return _clean_title(line[2:].strip())
    lines = [l.strip() for l in md.splitlines() if l.strip()]
    return _clean_title(lines[0]) if lines else "Unknown Title"

# Section titles to skip — pure noise with no content value
_SKIP_TITLES = {
    "contents", "table of contents",
    "acknowledgements", "acknowledgments",
    "list of figures", "list of tables",
    "index", "notation", "glossary"
}

def _should_skip_section(title: str, body: str) -> bool:
    """Return True if this section is noise and should not be processed."""
    t = title.lower().strip()

    # skip by exact title match
    if t in _SKIP_TITLES:
        return True

    # skip if body is too short to be substantive (< 15 words)
    if len(body.split()) < 15:
        return True

    # skip if body looks like a table of contents (lots of lines ending in digits)
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    if len(lines) > 3:
        digit_end_count = sum(1 for l in lines if re.search(r'\d+\s*$', l))
        if digit_end_count / len(lines) > 0.5:
            return True

    return False

# section_qa.py handles long sections via chunking — no truncation needed here

def _split_sections(md: str) -> list[Section]:
    # Only split on ## and ### — treat #### and deeper as body text within their parent section
    # This prevents lone definition/theorem headings from becoming orphan sections
    pattern = r'(^#{1,3} .+$)'
    parts = re.split(pattern, md, flags=re.MULTILINE)

    sections = []
    current_title = "preamble"
    current_text = []
    section_idx = 0

    for part in parts:
        if re.match(r'^#{1,3} ', part):
            if current_text:
                body = "\n".join(current_text).strip()
                clean_t = _clean_title(current_title)
                if body and not _should_skip_section(clean_t, body):
                    sections.append(Section(
                        section_id=f"s{section_idx}",
                        title=clean_t,
                        raw_text=body
                    ))
                    section_idx += 1
            current_title = part.lstrip("#").strip()
            current_text = []
        else:
            current_text.append(part)

    if current_text:
        body = "\n".join(current_text).strip()
        clean_t = _clean_title(current_title)
        if body and not _should_skip_section(clean_t, body):
            sections.append(Section(
                section_id=f"s{section_idx}",
                title=clean_t,
                raw_text=body
            ))

    return [s for s in sections if s.raw_text.strip()]
