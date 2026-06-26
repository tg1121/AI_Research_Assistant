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
import sys
import time
import requests
import fitz  # PyMuPDF
from .document import Document, Section
from supabase import create_client

# On Windows, pdftext's multiprocessing conflicts with Streamlit's process model.
# Force single-worker mode automatically to prevent BrokenProcessPool errors.
if sys.platform == "win32" and "PDFTEXT_CPU_WORKERS" not in os.environ:
    os.environ["PDFTEXT_CPU_WORKERS"] = "1"

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
                raw = f.read()
            # Migrate old cache files that still have {N}--- separators instead of \f
            if '\f' not in raw and _PAGE_SEP_RE.search(raw):
                raw = _PAGE_SEP_RE.sub('\f', raw)
            return raw
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

# Marker's page separator when paginate_output=True.
# Format: "{N}------------------------------------------------" where N is the 0-based page index.
_PAGE_SEP_RE = re.compile(r'\n\{\d+\}-+\n')


def _parse_pymupdf(pdf_path: str) -> str:
    """Lightweight PDF parser using PyMuPDF. Injects \\f between pages."""
    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\f".join(pages)


def _parse_marker_local(pdf_path: str, cancel_event=None) -> str:
    """Run marker models locally — only used in ADMIN_MODE."""
    import threading as _threading
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered
    global _local_converter
    if _local_converter is None:
        print("  Loading marker models (one-time)...")
        _local_converter = PdfConverter(
            artifact_dict=create_model_dict(),
            config={"paginate_output": True},
        )

    result_holder = [None]
    exc_holder = [None]

    def _run():
        try:
            rendered = _local_converter(pdf_path)
            raw, _, _ = text_from_rendered(rendered)
            result_holder[0] = _PAGE_SEP_RE.sub('\f', raw)
        except Exception as e:
            exc_holder[0] = e

    t = _threading.Thread(target=_run, daemon=True)
    t.start()
    while t.is_alive():
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Cancelled")
        t.join(timeout=0.5)

    if exc_holder[0]:
        raise exc_holder[0]
    return result_holder[0]


_local_converter = None


def _parse_marker_api(pdf_path: str, api_key: str, cancel_event=None) -> str:
    """Call Datalab Marker API — used when user provides DATALAB_API_KEY."""
    MARKER_URL    = "https://www.datalab.to/api/v1/marker"
    POLL_INTERVAL = 5
    MAX_POLLS     = 60
    headers       = {"X-Api-Key": api_key}

    with open(pdf_path, "rb") as f:
        response = requests.post(
            MARKER_URL,
            files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
            data={"output_format": "markdown", "paginate_output": "true"},
            headers=headers,
            timeout=60
        )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"Marker API submission failed: {data}")

    check_url = data["request_check_url"]
    for _ in range(MAX_POLLS):
        # Wait POLL_INTERVAL seconds, but wake up immediately if cancelled
        if cancel_event and cancel_event.wait(POLL_INTERVAL):
            raise RuntimeError("Cancelled")
        elif not cancel_event:
            time.sleep(POLL_INTERVAL)
        poll = requests.get(check_url, headers=headers, timeout=30)
        poll.raise_for_status()
        result = poll.json()
        if result.get("status") == "complete":
            md = result["markdown"]
            md = _PAGE_SEP_RE.sub('\f', md)
            return md
        if result.get("status") == "error":
            raise RuntimeError(f"Marker API error: {result}")

    raise RuntimeError("Marker API timed out after 5 minutes.")

# ── Main entry point ──────────────────────────────────────────────────

def parse_document(pdf_path: str, paper_id: str,
                   datalab_api_key: str | None = None,
                   cancel_event=None,
                   domain: str | None = None,
                   no_cache_save: bool = False) -> Document:
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

        # Local Marker only for explicit "math" — "auto" is always resolved before calling here
        if admin_mode and domain == "math":
            print(f"  [Admin] Running marker locally: {pdf_path}")
            try:
                raw_md = _parse_marker_local(pdf_path, cancel_event=cancel_event)
            except Exception as exc:
                print(f"  [Admin] Marker failed ({exc}), falling back to PyMuPDF")
                raw_md = _parse_pymupdf(pdf_path)
        elif datalab_api_key and domain != "non-math":
            print(f"  [API] Calling Datalab Marker API: {paper_id}")
            raw_md = _parse_marker_api(pdf_path, datalab_api_key, cancel_event=cancel_event)
        else:
            print(f"  [PyMuPDF] Parsing: {pdf_path}")
            raw_md = _parse_pymupdf(pdf_path)

        if not no_cache_save:
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

# Dotted leader in TOC title: "1. Introduction ........ 4"
_TOC_DOTS_RE   = re.compile(r'\.{3,}')
# Numbered bib entry title with brackets: "[1] Smith..." or "[12]."
_BIB_BRACKET_RE = re.compile(r'^\[\d{1,3}\][\.\)]?\s+\S')
# Year-in-parentheses in title → likely APA citation: "Smith, J. (2020). Title..."
_CITE_YEAR_RE  = re.compile(r'\(\d{4}[a-z]?\)')
# Body line that is a numbered bib entry: "[1] ..." or "1) ..."
_BIB_LINE_RE   = re.compile(r'^\s*(\[\d+\]|\d+[\.\)])\s+[A-Z\(]')
# Body line that has a citation year: signals dense bib block
_BIB_YEAR_RE   = re.compile(r'\(\d{4}[a-z]?\)')


def _should_skip_section(title: str, body: str) -> bool:
    t = title.lower().strip()
    if t in _SKIP_TITLES:
        return True

    # TOC entry: title contains dotted leaders ("Introduction ........ 4")
    if _TOC_DOTS_RE.search(title):
        return True

    # Numbered bib entry as title: "[1] Smith, J. ..."
    if _BIB_BRACKET_RE.match(title.strip()):
        return True

    # APA citation as title: "Smith, J. (2020). Title of paper..."
    if _CITE_YEAR_RE.search(title):
        return True

    if len(body.split()) < 15:
        return True

    lines = [l.strip() for l in body.splitlines() if l.strip()]

    # Body that looks like a TOC: >50% of lines end with digits
    if len(lines) > 3:
        digit_end = sum(1 for l in lines if re.search(r'\d+\s*$', l))
        if digit_end / len(lines) > 0.5:
            return True

    # Body that is a block of numbered bibliography entries
    bib_lines = sum(1 for l in lines if _BIB_LINE_RE.match(l))
    if len(lines) >= 3 and bib_lines / len(lines) > 0.5:
        return True

    # Body that is a dense APA bibliography block (many lines with years)
    year_lines = sum(1 for l in lines if _BIB_YEAR_RE.search(l))
    if len(lines) >= 4 and year_lines / len(lines) > 0.5:
        return True

    return False

def _page_at(original: str, offset: int) -> int:
    """Return 1-based page number at a character offset by counting \\f markers."""
    return original[:offset].count('\f') + 1


def _split_sections_md(md: str) -> list[Section]:
    # Work on a clean copy (\f→\n) for regex; use original for page lookup.
    # Both chars are 1 byte so character offsets are identical in both strings.
    clean   = md.replace('\f', '\n')
    pattern = r'(^#{1,3} .+$)'
    parts   = re.split(pattern, clean, flags=re.MULTILINE)

    abstract_idx  = None
    heading_parts = [(i, p) for i, p in enumerate(parts) if re.match(r'^#{1,3} ', p)]
    for i, p in heading_parts:
        title = _clean_title(p.lstrip("#").strip())
        if title.lower() in ("abstract", "introduction", "motivation", "overview"):
            abstract_idx = i
            break

    # cursor must start at the byte offset of the first kept part in the original md,
    # not at 0 — otherwise _page_at counts \f from the beginning and everything is page 1.
    cursor = sum(len(p) for p in parts[:abstract_idx]) if abstract_idx is not None else 0
    if abstract_idx is not None:
        parts = parts[abstract_idx:]

    sections      = []
    current_title = "preamble"
    current_page  = 1
    current_text  = []
    section_idx   = 0

    for part in parts:
        if re.match(r'^#{1,3} ', part):
            if current_text:
                body    = "\n".join(current_text).strip()
                clean_t = _clean_title(current_title)
                if body and not _should_skip_section(clean_t, body):
                    sections.append(Section(section_id=f"s{section_idx}",
                                            title=clean_t, raw_text=body,
                                            page=current_page))
                    section_idx += 1
            current_title = part.lstrip("#").strip()
            current_page  = _page_at(md, cursor)
            current_text  = []
        else:
            current_text.append(part)
        cursor += len(part)

    if current_text:
        body    = "\n".join(current_text).strip()
        clean_t = _clean_title(current_title)
        if body and not _should_skip_section(clean_t, body):
            sections.append(Section(section_id=f"s{section_idx}",
                                    title=clean_t, raw_text=body,
                                    page=current_page))

    return [s for s in sections if s.raw_text.strip()]


def _split_sections_plain(text: str) -> list[Section]:
    clean   = text.replace('\f', '\n')
    pattern = r'(\n\d+\.[\d\.]*\s+[A-Z][^\n]+)'
    parts   = re.split(pattern, clean)

    sections      = []
    current_title = "preamble"
    current_page  = 1
    current_text  = []
    section_idx   = 0
    cursor        = 0

    for part in parts:
        if re.match(r'\n\d+\.[\d\.]*\s+[A-Z]', part):
            if current_text:
                body = "\n".join(current_text).strip()
                if body and not _should_skip_section(current_title, body):
                    sections.append(Section(section_id=f"s{section_idx}",
                                            title=current_title, raw_text=body,
                                            page=current_page))
                    section_idx += 1
            current_title = part.strip()
            current_page  = _page_at(text, cursor)
            current_text  = []
        else:
            current_text.append(part)
        cursor += len(part)

    if current_text:
        body = "\n".join(current_text).strip()
        if body and not _should_skip_section(current_title, body):
            sections.append(Section(section_id=f"s{section_idx}",
                                    title=current_title, raw_text=body,
                                    page=current_page))

    return sections
