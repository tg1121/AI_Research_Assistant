"""
RAG — retrieval over paper sections.

Uses lightweight keyword + TF-IDF-style scoring so it works with any
LLM provider without needing an embedding endpoint.
For small-to-medium papers (< ~100 sections) this is fast and accurate.
"""

import math
import re
from collections import Counter
from ingestion.document import Document, Section


# ── text utilities ────────────────────────────────────────────────────

def _tokenise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())

STOPWORDS = {
    "the","a","an","is","it","in","on","of","to","and","or","for",
    "with","this","that","are","was","be","as","at","by","from",
    "have","has","had","but","not","we","our","they","their","its",
    "which","who","when","what","how","also","can","will","may",
    "more","than","so","if","about","into","up","do","does","been",
}

def _content_tokens(text: str) -> list[str]:
    return [t for t in _tokenise(text) if t not in STOPWORDS and len(t) > 2]


# ── index ─────────────────────────────────────────────────────────────

class SectionIndex:
    """
    Builds a simple inverted index over section text + titles.
    Call build(doc) once, then retrieve(query, k) per query.
    """

    def __init__(self):
        self.sections: list[Section] = []
        self.tf: list[dict] = []        # term frequency per section
        self.idf: dict = {}             # inverse document frequency
        self._built = False

    def build(self, doc: Document) -> "SectionIndex":
        self.sections = [s for s in doc.sections if s.raw_text.strip()]
        n = len(self.sections)
        if n == 0:
            self._built = True
            return self

        # build TF per section (title weighted 3x)
        df: Counter = Counter()
        self.tf = []
        for section in self.sections:
            tokens = (
                _content_tokens(section.title) * 3
                + _content_tokens(section.raw_text)
            )
            freq = Counter(tokens)
            total = sum(freq.values()) or 1
            tf_norm = {t: c / total for t, c in freq.items()}
            self.tf.append(tf_norm)
            df.update(set(freq.keys()))

        # IDF
        self.idf = {t: math.log((n + 1) / (cnt + 1)) + 1 for t, cnt in df.items()}
        self._built = True
        return self

    def retrieve(self, query: str, k: int = 3) -> list[tuple[Section, float]]:
        """Return top-k (section, score) pairs for the query."""
        if not self._built or not self.sections:
            return []

        q_tokens = _content_tokens(query)
        if not q_tokens:
            return [(s, 0.0) for s in self.sections[:k]]

        scores = []
        for i, tf_map in enumerate(self.tf):
            score = sum(
                tf_map.get(t, 0.0) * self.idf.get(t, 0.0)
                for t in q_tokens
            )
            scores.append((self.sections[i], score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top = scores[:k]
        # if all scores are 0 (generic query, no keyword match),
        # fall back to the first k sections so context is never empty
        if all(s == 0.0 for _, s in top):
            return [(s, 0.0) for s in self.sections[:k]]
        return top


# ── context builder ───────────────────────────────────────────────────

def build_rag_context(index: SectionIndex, query: str, k: int = 3) -> str:
    """
    Retrieve top-k sections and format them as a context block
    for injection into the chat prompt.
    """
    hits = index.retrieve(query, k=k)
    if not hits:
        return ""

    parts = ["=== RELEVANT PAPER SECTIONS ==="]
    for section, score in hits:
        parts.append(f"\n[{section.section_id}] {section.title}")
        # include equations inline if present
        text = section.raw_text[:3000]  # cap to avoid context explosion
        if section.equations:
            eq_strs = [e.raw_latex for e in section.equations[:5]]
            text += "\n\nEquations: " + " | ".join(eq_strs)
        parts.append(text)
    parts.append("=== END SECTIONS ===")
    return "\n".join(parts)
