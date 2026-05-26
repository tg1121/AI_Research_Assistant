from pydantic import BaseModel
from typing import Optional

class Equation(BaseModel):
    raw_latex: str
    role: Optional[str] = None
    section_id: str

class Section(BaseModel):
    section_id: str
    title: str
    role: Optional[str] = None
    raw_text: str
    equations: list[Equation] = []
    qa: Optional[dict] = None

class Document(BaseModel):
    paper_id: str
    title: str
    raw_markdown: str
    sections: list[Section] = []
    mathematical_chain: Optional[dict] = None
    holistic_summary: Optional[dict] = None