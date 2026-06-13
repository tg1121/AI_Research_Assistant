"""
Agent tools — retrieval functions the ReAct planner calls.

  consult_doc_map(doc_map)
    → structural overview, ~300 tokens
    → use for: section listing, importance, overview questions

  retrieve_section(graph, section_id)
    → full section text + all math objects (with proof types)
    → use for: deep content of a known section

  follow_reference(graph, node_id_or_label, depth)
    → dependency chain: what this node needs + what needs it
    → use for: "what does Theorem 7 depend on?", proof chains

  search_concept(graph, query)
    → keyword match across all node texts, ranked
    → use for: finding where a concept is defined/discussed
"""

import re
from graph.math_graph import MathGraph, MathNode
from graph.doc_map import DocMap

_MAX_NODE_CHARS = 400

_STOPWORDS = {
    "the","a","an","is","it","in","on","of","to","and","or","for",
    "with","this","that","are","was","be","as","at","by","from",
    "we","our","which","who","when","what","how","also","can",
}


# ── Tool 1 ────────────────────────────────────────────────────────────

def consult_doc_map(doc_map: DocMap) -> str:
    return doc_map.to_prompt_block()


# ── Tool 2 ────────────────────────────────────────────────────────────

def _sample_section(text: str) -> str:
    """
    Return at least 50% of section text sampled from start, middle, and end.
    A flat head-truncation misses definitions that appear mid-section. Distributing
    the sample across three positions ensures the answer is covered regardless of
    where in the section the author placed it.
    """
    text = (text or "").strip()
    n = len(text)
    total = min(max(n // 2, 1200), 6000)  # 50% of section, clamped 1200–6000
    if n <= total:
        return text
    chunk  = total // 3
    start  = text[:chunk]
    mid_s  = (n - chunk) // 2
    middle = text[mid_s:mid_s + chunk]
    end    = text[n - chunk:]
    return f"{start}\n[...]\n{middle}\n[...]\n{end}"


def retrieve_section(graph: MathGraph, section_id: str) -> str:
    node = graph.nodes.get(section_id)
    if not node:
        return f"[Section '{section_id}' not found]"

    parts = [f"=== SECTION: {node.label} [{section_id}] ===",
             _sample_section(node.raw_text or "")]

    math_objs = graph.nodes_in_section(section_id)
    if math_objs:
        parts.append("--- Math objects ---")
        for obj in math_objs:
            pt = f" [{obj.proof_type}]" if obj.proof_type else ""
            header = (f"[{obj.node_type.upper()}{pt}] "
                      f"{obj.label} (in-degree={obj.in_degree})")
            snippet = (obj.raw_text or obj.raw_latex)[:_MAX_NODE_CHARS]
            parts.append(f"{header}\n{snippet}")

    parts.append("=== END SECTION ===")
    return "\n\n".join(parts)


# ── Tool 3 ────────────────────────────────────────────────────────────

def follow_reference(graph: MathGraph, node_id: str, depth: int = 2) -> str:
    node = graph.nodes.get(node_id)
    if not node:
        # try label resolution
        resolved = _resolve_label(graph, node_id)
        if not resolved:
            return f"[Node '{node_id}' not found]"
        node_id, node = resolved, graph.nodes[resolved]

    pt = f" [{node.proof_type}]" if node.proof_type else ""
    parts = [f"=== REFERENCE CHAIN: {node.label}{pt} ==="]

    if node.raw_text:
        parts.append(f"[{node.node_type.upper()}{pt}] {node.label}:")
        parts.append(node.raw_text[:_MAX_NODE_CHARS])

    ancestors = graph.get_ancestors(node_id, max_depth=depth)
    if ancestors:
        parts.append("--- Depends on ---")
        for anc in ancestors:
            apt = f" [{anc.proof_type}]" if anc.proof_type else ""
            snippet = (anc.raw_text or anc.raw_latex)[:300]
            parts.append(f"[{anc.node_type.upper()}{apt}] "
                         f"{anc.label} (section {anc.section_id})\n{snippet}")

    dependents = graph.get_dependents(node_id)
    if dependents:
        parts.append("--- Referenced by ---")
        for dep in dependents:
            dpt = f" [{dep.proof_type}]" if dep.proof_type else ""
            parts.append(f"[{dep.node_type.upper()}{dpt}] "
                         f"{dep.label} (section {dep.section_id})")

    if not ancestors and not dependents:
        parts.append("[No cross-references found for this node]")

    parts.append("=== END REFERENCE CHAIN ===")
    return "\n\n".join(parts)


# ── Tool 4 ────────────────────────────────────────────────────────────

def search_concept(graph: MathGraph, query: str, top_k: int = 4) -> str:
    q_tokens = set(_tokenise(query))
    if not q_tokens:
        return "[Empty query]"

    scored: list[tuple[float, MathNode]] = []
    for node in graph.nodes.values():
        text = f"{node.label} {node.raw_text} {node.raw_latex}".lower()
        overlap = len(q_tokens & set(_tokenise(text)))
        if overlap > 0:
            scored.append((overlap / max(len(q_tokens), 1), node))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    if not top:
        return f"[No results for '{query}']"

    parts = [f"=== CONCEPT SEARCH: '{query}' ({len(top)} results) ==="]
    for score, node in top:
        pt = f" [{node.proof_type}]" if node.proof_type else ""
        snippet = (node.raw_text or node.raw_latex)[:_MAX_NODE_CHARS]
        parts.append(
            f"[{node.node_type.upper()}{pt}] {node.label} "
            f"(section={node.section_id}, in-degree={node.in_degree}, "
            f"score={score:.2f})\n{snippet}"
        )
    parts.append("=== END SEARCH ===")
    return "\n\n".join(parts)


# ── helpers ───────────────────────────────────────────────────────────

def _tokenise(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())
            if t not in _STOPWORDS and len(t) > 2]


def _resolve_label(graph: MathGraph, query: str) -> str | None:
    q = query.lower().strip()
    if q in graph._label_index:
        return graph._label_index[q]
    for label, nid in graph._label_index.items():
        if q in label or label in q:
            return nid
    return None
