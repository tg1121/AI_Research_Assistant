from pydantic import BaseModel
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from graph.math_graph import MathGraph

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
    # V8: proof type classification for proof sections
    proof_type: Optional[str] = None  # "direct" | "induction" | "contradiction" | None
    page: Optional[int] = None        # PDF page number (1-based), populated during parsing

class Document(BaseModel):
    paper_id: str
    title: str
    raw_markdown: str
    sections: list[Section] = []
    mathematical_chain: Optional[dict] = None
    holistic_summary: Optional[dict] = None
    # V8: graph stored as plain dict for pydantic serialization
    # access via graph_store.load_graph(paper_id) for the real MathGraph object
    graph_meta: Optional[dict] = None
