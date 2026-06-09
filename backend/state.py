"""Thread-safe in-memory store for per-paper pipeline state."""
import threading
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class PaperState:
    paper_id: str
    pdf_path: str
    status: str = "pending"      # pending | processing | done | error | cancelled
    progress_pct: int = 0
    progress_text: str = "Queued"
    doc: Optional[Any] = None
    graph: Optional[Any] = None
    doc_map: Optional[Any] = None
    chat_messages: list = field(default_factory=list)
    turn_counter: list = field(default_factory=lambda: [0])
    session_id: Optional[str] = None
    error: Optional[str] = None
    detected_domain: Optional[str] = None
    cancelled: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)


class PaperStore:
    def __init__(self):
        self._store: dict[str, PaperState] = {}
        self._lock = threading.Lock()

    def create(self, paper_id: str, pdf_path: str) -> PaperState:
        with self._lock:
            state = PaperState(paper_id=paper_id, pdf_path=pdf_path)
            self._store[paper_id] = state
            return state

    def get(self, paper_id: str) -> Optional[PaperState]:
        return self._store.get(paper_id)

    def update(self, paper_id: str, **kwargs):
        with self._lock:
            state = self._store.get(paper_id)
            if state:
                for k, v in kwargs.items():
                    setattr(state, k, v)

    def cancel(self, paper_id: str):
        with self._lock:
            state = self._store.get(paper_id)
            if state:
                state.cancelled = True
                state.cancel_event.set()

    def exists(self, paper_id: str) -> bool:
        return paper_id in self._store
