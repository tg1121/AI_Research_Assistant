import arxiv
import subprocess
import tempfile
import os
import re
from .document import Document, Section
from .marker_parser import _extract_title, _split_sections

def is_arxiv_id(paper_id: str) -> bool:
    return bool(re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', paper_id))

def fetch_arxiv_source(arxiv_id: str) -> Document:
    search = arxiv.Search(id_list=[arxiv_id])
    result = next(arxiv.Client().results(search))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result.download_source(dirpath=tmpdir)
        tex_content = _extract_tex(tmpdir)
        md = _tex_to_markdown(tex_content, tmpdir)

    title = result.title
    sections = _split_sections(md)

    return Document(
        paper_id=arxiv_id,
        title=title,
        raw_markdown=md,
        sections=sections
    )

def _extract_tex(dirpath: str) -> str:
    for f in os.listdir(dirpath):
        if f.endswith(".tar.gz"):
            subprocess.run(["tar", "-xzf", os.path.join(dirpath, f), "-C", dirpath])
    
    tex_files = [f for f in os.listdir(dirpath) if f.endswith(".tex")]
    main_tex = next((f for f in tex_files if "main" in f.lower()), tex_files[0] if tex_files else None)
    
    if not main_tex:
        raise RuntimeError("No .tex file found in arXiv source")
    
    with open(os.path.join(dirpath, main_tex)) as f:
        return f.read()

def _tex_to_markdown(tex: str, dirpath: str) -> str:
    tex_path = os.path.join(dirpath, "input.tex")
    md_path = os.path.join(dirpath, "output.md")
    with open(tex_path, "w") as f:
        f.write(tex)
    subprocess.run(["pandoc", tex_path, "-o", md_path], check=True)
    with open(md_path) as f:
        return f.read()