"""
English/humanities synthesizer.

Pipeline:
  1. Per section — extract TF-IDF keywords + capitalized named phrases (no LLM)
  2. Per section — sample 1500 chars spread across start, middle, end
  3. Single LLM call across all sections → holistic summary JSON
"""

import json
import math
import re
from collections import Counter

from prompts.english_synthesis_prompt import ENGLISH_SYNTHESIS_SYSTEM, english_synthesis_prompt
from ingestion.document import Document
from graph.doc_map import DocMap, build_english_doc_map
from pipeline.llm_client import llm_call, clean_json


# ── keyword extraction ────────────────────────────────────────────────────────

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "this",
    "that", "these", "those", "it", "its", "we", "our", "they", "their",
    "he", "she", "his", "her", "i", "my", "you", "your", "not", "no",
    "so", "if", "then", "than", "also", "such", "more", "most", "all",
    "both", "each", "other", "which", "who", "what", "when", "where",
    "how", "into", "through", "about", "between", "while", "after",
    "before", "however", "therefore", "thus", "hence", "paper", "study",
    "research", "work", "article", "author", "authors", "section",
    "result", "results", "show", "shows", "shown", "use", "used",
    "using", "present", "proposed", "approach", "method", "methods",
    "based", "new", "two", "three", "one", "first", "second", "third",
    "figure", "table", "et", "al", "cf", "see", "note", "here", "there",
    "very", "well", "just", "even", "only", "since", "like",
})

_CAP_PHRASE = re.compile(r'\b([A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,}){1,})\b')


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
            if w not in _STOPWORDS]


def _tfidf_keywords(texts: list[str], top_n: int = 8) -> list[list[str]]:
    """TF-IDF across sections — highlights what's distinctive to each section."""
    N = len(texts)
    if N == 0:
        return []
    tokenized = [_tokenize(t) for t in texts]

    df: dict[str, int] = {}
    for tokens in tokenized:
        for w in set(tokens):
            df[w] = df.get(w, 0) + 1

    results = []
    for tokens in tokenized:
        if not tokens:
            results.append([])
            continue
        tf = Counter(tokens)
        total = len(tokens)
        scores = {
            w: (count / total) * math.log((N + 1) / (df.get(w, 1) + 1))
            for w, count in tf.items()
        }
        top = sorted(scores, key=scores.__getitem__, reverse=True)[:top_n]
        results.append(top)
    return results


def _named_phrases(text: str, max_phrases: int = 6) -> list[str]:
    """Extract capitalized multi-word phrases: author names, theory names, book titles."""
    seen: set[str] = set()
    phrases: list[str] = []
    for m in _CAP_PHRASE.finditer(text):
        p = m.group(1)
        key = p.lower()
        if key not in seen:
            seen.add(key)
            phrases.append(p)
        if len(phrases) >= max_phrases:
            break
    return phrases


def _sample_text(text: str, total: int = 1500) -> str:
    """Return up to `total` chars sampled from start, middle, and end of text."""
    text = (text or "").strip()
    if len(text) <= total:
        return text
    chunk = total // 3
    n = len(text)
    start  = text[:chunk]
    mid_s  = (n - chunk) // 2
    middle = text[mid_s:mid_s + chunk]
    end    = text[n - chunk:]
    return f"{start} [...] {middle} [...] {end}"


# ── public API ────────────────────────────────────────────────────────────────

def run_english_synthesis(
    doc: Document,
    reader_expertise: float = 0.0,
    scientific_knowledge: float = 0.0,
    language_complexity: float = 0.0,
    model: str = "gemini/gemini-2.0-flash",
    api_key: str | None = None,
) -> tuple[Document, DocMap]:
    """
    Build section keyword profiles, sample text, then make one LLM call
    to produce the holistic summary. Populates doc.holistic_summary.
    """
    texts    = [(s.raw_text or "") for s in doc.sections]
    kw_lists = _tfidf_keywords(texts)

    section_data = []
    for i, section in enumerate(doc.sections):
        section_data.append({
            "title":         section.title,
            "keywords":      kw_lists[i] if i < len(kw_lists) else [],
            "named_phrases": _named_phrases(section.raw_text or ""),
            "text_sample":   _sample_text(section.raw_text or ""),
        })

    print(f"    [english synthesis] {len(section_data)} sections, 1 LLM call")

    raw = llm_call(
        [
            {"role": "system", "content": ENGLISH_SYNTHESIS_SYSTEM},
            {"role": "user",   "content": english_synthesis_prompt(
                doc.title, section_data,
                reader_expertise=reader_expertise,
                scientific_knowledge=scientific_knowledge,
                language_complexity=language_complexity,
            )},
        ],
        model=model,
        api_key=api_key,
        max_tokens=3000,
    )

    raw = clean_json(raw, "english_synthesizer")
    doc.holistic_summary = json.loads(raw)
    doc_map = build_english_doc_map(doc, section_data)
    return doc, doc_map
