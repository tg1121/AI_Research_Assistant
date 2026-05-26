"""
Unified parser — three modes:
  1. LOCAL MARKER  : ADMIN_MODE=true env var → runs marker locally (your machine)
  2. MARKER API    : user provides DATALAB_API_KEY in sidebar → calls datalab.to API
  3. PYMUPDF       : default for all deployed users → lightweight, no API needed

Cache strategy:
  - Local (ADMIN_MODE=true) → local file cache in marker_output/
  - Deployed               → Supabase cache
"""

import os
import re
import time
import requests
import fitz  # PyMuPDF
from .document import Document, Section
from supabase import create_client

_IS_LOCAL = os.environ.get("ADMIN_MODE", "").lower() == "true"
LOCAL_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "marker_output")

_sb_client = None

def _db():
    global _sb_client
    if _sb_client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY env vars must be set.")
        _sb_client = create_client(url, key)
    return _sb_client

# ── Cache: local files (admin) or Supabase (deployed) ────────────────

def _load_from_cache(paper_id: str) -> str | None:
    if _IS_LOCAL:
        path = os.path.join(LOCAL_CACHE_DIR, f"{paper_id}.md")
        if os.path.exists(path):
            print(f"  Local cache hit: {paper_id}")
            with open(path, encoding="utf-8") as f:
                return f.read()
        return None
    # Supabase
    try:
        result = (
            _db().table("parsed_docs")
            .select("raw_markdown")
            .eq("paper_id", paper_id)
            .not_.is_("raw_markdown", "null")
            .limit(1)
            .execute()
        )
        if result.data:
            print(f"  Supabase cache hit: {paper_id}")
            return result.data[0]["raw_markdown"]
    except Exception as e:
        print(f"  Cache read failed: {e}")
    return None

def _save_to_cache(paper_id: str, raw_md: str):
    if _IS_LOCAL:
        os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
        path = os.path.join(LOCAL_CACHE_DIR, f"{paper_id}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw_md)
        print(f"  Saved to local cache: {path}")
        return
    # Supabase
    try:
        _db().table("parsed_docs").upsert(
            {"paper_id": paper_id, "raw_markdown": raw_md}
        ).execute()
        print(f"  Saved to Supabase cache: {paper_id}")
    except Exception as e:
        print(f"  Cache write failed (non-fatal): {e}")

# ── Parser implementations ────────────────────────────────────────────

def _parse_pymupdf(pdf_path: str) -> str:
    """Lightweight PDF parser using PyMuPDF."""
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()
    return full_text

def _parse_marker_local(pdf_path: str) -> str:
    """Run marker models locally — only used in ADMIN_MODE."""
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered
    global _local_converter
    if _local_converter is None:
        print("  Loading marker models (one-time)...")
        _local_converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = _local_converter(pdf_path)
    raw_md, _, _ = text_from_rendered(rendered)
    return raw_md

_local_converter = None

def _parse_marker_api(pdf_path: str, api_key: str) -> str:
    """Call Datalab Marker API — used when user provides DATALAB_API_KEY."""
    MARKER_URL    = "https://www.datalab.to/api/v1/marker"
    POLL_INTERVAL = 5
    MAX_POLLS     = 60
    headers       = {"X-Api-Key": api_key}

    with open(pdf_path, "rb") as f:
        response = requests.post(
            MARKER_URL,
            files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
            data={"output_format": "markdown"},
            headers=headers,
            timeout=60
        )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"Marker API submission failed: {data}")

    check_url = data["request_check_url"]
    for _ in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        poll = requests.get(check_url, headers=headers, timeout=30)
        poll.raise_for_status()
        result = poll.json()
        if result.get("status") == "complete":
            return result["markdown"]
        if result.get("status") == "error":
            raise RuntimeError(f"Marker API error: {result}")

    raise RuntimeError("Marker API timed out after 5 minutes.")

# ── Main entry point ──────────────────────────────────────────────────

def parse_document(pdf_path: str, paper_id: str,
                   datalab_api_key: str | None = None) -> Document:
    """
    Parse a PDF, using cache if available.
    Mode selection:
      - ADMIN_MODE=true  → local marker (no API key needed)
      - datalab_api_key  → Datalab Marker API
      - default          → PyMuPDF
    """
    # 1. Check cache first
    raw_md = _load_from_cache(paper_id)

    if not raw_md:
        admin_mode = os.environ.get("ADMIN_MODE", "").lower() == "true"

        if admin_mode:
            print(f"  [Admin] Running marker locally: {pdf_path}")
            raw_md = _parse_marker_local(pdf_path)
        elif datalab_api_key:
            print(f"  [API] Calling Datalab Marker API: {paper_id}")
            raw_md = _parse_marker_api(pdf_path, datalab_api_key)
        else:
            print(f"  [PyMuPDF] Parsing: {pdf_path}")
            raw_md = _parse_pymupdf(pdf_path)

        _save_to_cache(paper_id, raw_md)

    is_markdown = raw_md.strip().startswith("#") or "\n##" in raw_md
    title    = _extract_title_md(raw_md) if is_markdown else _extract_title_plain(raw_md)
    sections = _split_sections_md(raw_md) if is_markdown else _split_sections_plain(raw_md)

    return Document(
        paper_id=paper_id,
        title=title,
        raw_markdown=raw_md,
        sections=sections
    )

# ── Text processing ───────────────────────────────────────────────────

def _clean_title(title: str) -> str:
    title = re.sub(r'<span[^>]*>', '', title)
    title = re.sub(r'</span>', '', title)
    title = re.sub(r'<[^>]+>', '', title)
    return title.strip()

def _extract_title_md(md: str) -> str:
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return _clean_title(line[2:].strip())
    lines = [l.strip() for l in md.splitlines() if l.strip()]
    return _clean_title(lines[0]) if lines else "Unknown Title"

def _extract_title_plain(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[0] if lines else "Unknown Title"

_SKIP_TITLES = {
    "contents", "table of contents", "acknowledgements", "acknowledgments",
    "list of figures", "list of tables", "index", "notation", "glossary"
}

def _should_skip_section(title: str, body: str) -> bool:
    t = title.lower().strip()
    if t in _SKIP_TITLES:
        return True
    if len(body.split()) < 15:
        return True
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    if len(lines) > 3:
        digit_end = sum(1 for l in lines if re.search(r'\d+\s*$', l))
        if digit_end / len(lines) > 0.5:
            return True
    return False

def _split_sections_md(md: str) -> list[Section]:
    pattern = r'(^#{1,3} .+$)'
    parts   = re.split(pattern, md, flags=re.MULTILINE)

    abstract_idx  = None
    heading_parts = [(i, p) for i, p in enumerate(parts) if re.match(r'^#{1,3} ', p)]
    for i, p in heading_parts:
        title = _clean_title(p.lstrip("#").strip())
        if title.lower() in ("abstract", "introduction", "motivation", "overview"):
            abstract_idx = i
            break
    if abstract_idx is not None:
        parts = parts[abstract_idx:]

    sections      = []
    current_title = "preamble"
    current_text  = []
    section_idx   = 0

    for part in parts:
        if re.match(r'^#{1,3} ', part):
            if current_text:
                body    = "\n".join(current_text).strip()
                clean_t = _clean_title(current_title)
                if body and not _should_skip_section(clean_t, body):
                    sections.append(Section(section_id=f"s{section_idx}",
                                            title=clean_t, raw_text=body))
                    section_idx += 1
            current_title = part.lstrip("#").strip()
            current_text  = []
        else:
            current_text.append(part)

    if current_text:
        body    = "\n".join(current_text).strip()
        clean_t = _clean_title(current_title)
        if body and not _should_skip_section(clean_t, body):
            sections.append(Section(section_id=f"s{section_idx}",
                                    title=clean_t, raw_text=body))

    return [s for s in sections if s.raw_text.strip()]

def _split_sections_plain(text: str) -> list[Section]:
    pattern = r'(\n\d+\.[\d\.]*\s+[A-Z][^\n]+)'
    parts   = re.split(pattern, text)

    sections      = []
    current_title = "preamble"
    current_text  = []
    section_idx   = 0

    for part in parts:
        if re.match(r'\n\d+\.[\d\.]*\s+[A-Z]', part):
            if current_text:
                body = "\n".join(current_text).strip()
                if body:
                    sections.append(Section(section_id=f"s{section_idx}",
                                            title=current_title, raw_text=body))
                    section_idx += 1
            current_title = part.strip()
            current_text  = []
        else:
            current_text.append(part)

    if current_text:
        body = "\n".join(current_text).strip()
        if body:
            sections.append(Section(section_id=f"s{section_idx}",
                                    title=current_title, raw_text=body))

    return sections
