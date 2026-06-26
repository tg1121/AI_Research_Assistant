"""
English/humanities synthesizer — V12.1.

Pipeline:
  1. Detect bibliography sections → parse into bib_map, exclude from LLM prompt
  2. Single LLM call with full section text → summary JSON + semantic nodes + semantic edges
  3. Deterministic graph build:
       - regular section nodes
       - bib entry nodes (one per numbered bibliography entry)
       - LLM semantic nodes  (dynamic cap: 60 // n_sections, min 1, max 3)
       - section-membership edges  (semantic node → its parent section)
       - LLM semantic edges
       - numbered citation edges   ([1], [2,3] → specific bib_N nodes)
       - APA citation edges        ((Smith, 2020) → generic external_refs node)
"""

import json
import re

from prompts.english_graph_prompt import (
    ENGLISH_GRAPH_SYSTEM, english_graph_prompt,
    SEMANTIC_NODE_TYPES, SEMANTIC_EDGE_TYPES,
)
from ingestion.document import Document
from graph.doc_map import DocMap, build_english_doc_map
from graph.math_graph import Graph, Node, Edge
from pipeline.llm_client import llm_call, clean_json


# ── bibliography detection ────────────────────────────────────────────────────

_BIB_TITLE = re.compile(
    r'^\s*(references?|bibliography|works?\s+cited|reference\s+list'
    r'|literature\s+cited|sources?)\s*$',
    re.IGNORECASE,
)
# Individual bib entry that slipped through as its own section title
_BIB_ENTRY_TITLE = re.compile(r'^\[?\d{1,3}\][\.\)]?\s+[A-Z\(\"]', re.IGNORECASE)
_CITE_YEAR_IN_TITLE = re.compile(r'\(\d{4}[a-z]?\)')
_BIB_ENTRY = re.compile(r'^\s*\[?(\d+)\]?[\.\)]\s+(.{10,})', re.MULTILINE)
_BIB_TITLE_NUM = re.compile(r'^\[?(\d{1,3})\][\.\)]?\s+(.{5,})')


def _is_bibliography(title: str) -> bool:
    t = title.strip()
    return bool(
        _BIB_TITLE.match(t)          # "References", "Bibliography", etc.
        or _BIB_ENTRY_TITLE.match(t) # "[1] Smith..." bracketed entry
        or _CITE_YEAR_IN_TITLE.search(t)  # "Smith, J. (2020). Title..."
    )


def _parse_bib_entries(text: str) -> list[tuple[str, str]]:
    """Return list of (number_str, short_label) for numbered bib entries."""
    entries, seen = [], set()
    for m in _BIB_ENTRY.finditer(text):
        num = m.group(1)
        if num in seen:
            continue
        seen.add(num)
        excerpt = m.group(2).strip()[:100]
        entries.append((num, excerpt))
    return entries


# ── citation patterns ─────────────────────────────────────────────────────────

_APA_CITE = re.compile(
    r'\((?:[A-Z][a-z]+(?:\s+(?:et\s+al\.|and|&)\s+[A-Z][a-z]+)?),?\s+\d{4}[a-z]?\)'
    r'|\b[A-Z][a-z]+\s+et\s+al\.\s+\(\d{4}\)'
    r'|\b[A-Z][a-z]+\s+\(\d{4}\)',
    re.MULTILINE,
)
_NUMBERED_CITE = re.compile(r'\[(\d+(?:\s*[,;]\s*\d+)*)\]')


def _cited_numbers(text: str) -> set[str]:
    nums: set[str] = set()
    for m in _NUMBERED_CITE.finditer(text):
        for n in re.split(r'[,;\s]+', m.group(1)):
            n = n.strip()
            if n.isdigit():
                nums.add(n)
    return nums


# ── graph construction ────────────────────────────────────────────────────────

def _build_graph(
    doc: Document,
    regular_section_ids: set[str],
    bib_map: dict[str, dict],      # num_str → {"node_id": ..., "label": ..., "excerpt": ...}
    llm_nodes: list[dict],
    llm_edges: list[dict],
    nodes_per_sec_cap: int,
) -> Graph:
    graph = Graph()
    ordered_ids: list[str] = []

    # ── regular section nodes ─────────────────────────────────────────
    for position, section in enumerate(doc.sections):
        if section.section_id not in regular_section_ids:
            continue
        graph.add_node(Node(
            node_id=section.section_id,
            label=section.title,
            node_type="section",
            section_id=section.section_id,
            raw_text=section.raw_text,
            position=position,
        ))
        ordered_ids.append(section.section_id)
    graph.set_ordered_ids(ordered_ids)

    # ── bibliography entry nodes ──────────────────────────────────────
    for num, info in bib_map.items():
        graph.add_node(Node(
            node_id=info["node_id"],
            label=info["label"],
            node_type="external",
            section_id=info["node_id"],
            raw_text=info["excerpt"],
            position=99000 + int(num),
        ))

    # ── generic external_refs for APA citations ───────────────────────
    ext_id = "external_refs"

    # ── LLM semantic nodes ────────────────────────────────────────────
    nodes_per_section: dict[str, int] = {}
    valid_node_ids: set[str] = set(graph.nodes.keys())

    for n in llm_nodes:
        nid    = str(n.get("id", "")).strip()
        ntype  = n.get("type", "")
        label  = n.get("label", "")
        sec_id = n.get("section_id", "")
        if not nid or ntype not in SEMANTIC_NODE_TYPES:
            continue
        if sec_id not in regular_section_ids:
            continue
        if nid in valid_node_ids:
            continue
        if nodes_per_section.get(sec_id, 0) >= nodes_per_sec_cap:
            continue
        sec = next((s for s in doc.sections if s.section_id == sec_id), None)
        if not sec:
            continue
        graph.add_node(Node(
            node_id=nid,
            label=label,
            node_type=ntype,
            section_id=sec_id,
            raw_text=sec.raw_text[:200],
            position=sec.page or 0,
        ))
        valid_node_ids.add(nid)
        nodes_per_section[sec_id] = nodes_per_section.get(sec_id, 0) + 1

    # ── fallback: guarantee ≥1 semantic node per section ─────────────
    # The LLM sometimes skips short / transitional sections.
    for sec_id in sorted(regular_section_ids):  # sorted for stable IDs
        if nodes_per_section.get(sec_id, 0) == 0:
            sec = next((s for s in doc.sections if s.section_id == sec_id), None)
            if not sec:
                continue
            fallback_id = f"{sec_id}_key"
            if fallback_id not in valid_node_ids:
                graph.add_node(Node(
                    node_id=fallback_id,
                    label=(sec.title or sec_id)[:40],
                    node_type="concept",
                    section_id=sec_id,
                    raw_text=(sec.raw_text or "")[:200],
                    position=sec.page or 0,
                ))
                valid_node_ids.add(fallback_id)
                nodes_per_section[sec_id] = 1

    # ── section-membership edges (semantic → parent section) ──────────
    for nid, node in graph.nodes.items():
        if node.node_type in SEMANTIC_NODE_TYPES and node.section_id in regular_section_ids:
            graph.add_edge(Edge(
                from_id=nid,
                to_id=node.section_id,
                source="section",
                evidence="belongs-to",
                confidence="certain",
            ))

    # ── LLM semantic edges ────────────────────────────────────────────
    edges_per_node: dict[str, int] = {}
    total_llm_edges = 0
    for e in llm_edges:
        if total_llm_edges >= 40:
            break
        from_id  = str(e.get("from", "")).strip()
        to_id    = str(e.get("to", "")).strip()
        etype    = e.get("type", "")
        evidence = e.get("evidence", "")
        if from_id not in valid_node_ids or to_id not in valid_node_ids:
            continue
        if etype not in SEMANTIC_EDGE_TYPES:
            continue
        if edges_per_node.get(from_id, 0) >= 2:
            continue
        graph.add_edge(Edge(
            from_id=from_id, to_id=to_id,
            source="llm", evidence=evidence, confidence="inferred",
        ))
        edges_per_node[from_id] = edges_per_node.get(from_id, 0) + 1
        total_llm_edges += 1

    # ── citation edges ────────────────────────────────────────────────
    needs_generic_ext = False
    for section in doc.sections:
        if section.section_id not in regular_section_ids:
            continue
        text = section.raw_text or ""

        # numbered citations → specific bib nodes
        for num in _cited_numbers(text):
            if num in bib_map:
                graph.add_edge(Edge(
                    from_id=section.section_id,
                    to_id=bib_map[num]["node_id"],
                    source="regex",
                    evidence=f"cites [{num}]",
                    confidence="certain",
                ))

        # APA citations → generic external_refs
        if _APA_CITE.search(text):
            needs_generic_ext = True
            if ext_id not in graph.nodes:
                graph.add_node(Node(
                    node_id=ext_id,
                    label="External References",
                    node_type="external",
                    section_id=ext_id,
                    raw_text="Works cited via author-date notation",
                    position=99999,
                ))
            graph.add_edge(Edge(
                from_id=section.section_id,
                to_id=ext_id,
                source="regex",
                evidence="APA citation",
                confidence="certain",
            ))

    graph.finalize()
    return graph


# ── public API ────────────────────────────────────────────────────────────────

def run_english_synthesis(
    doc: Document,
    reader_expertise: float = 0.0,
    scientific_knowledge: float = 0.0,
    language_complexity: float = 0.0,
    model: str = "openrouter/openai/gpt-oss-120b:free",
    api_key: str | None = None,
) -> tuple[Document, DocMap, Graph]:
    """
    Build section keyword profiles, sample text, then make one LLM call
    to produce the holistic summary + semantic graph. Returns (doc, doc_map, graph).
    """
    # ── separate bibliography from regular sections ───────────────────
    bib_map: dict[str, dict] = {}          # num_str → node info
    regular_section_ids: set[str] = set()
    section_data: list[dict] = []

    for section in doc.sections:
        if _is_bibliography(section.title):
            for num, excerpt in _parse_bib_entries(section.raw_text or ""):
                if num not in bib_map:
                    bib_map[num] = {
                        "node_id": f"bib_{num}",
                        "label":   f"[{num}] {excerpt[:60]}",
                        "excerpt": excerpt,
                    }
            m = _BIB_TITLE_NUM.match(section.title.strip())
            if m:
                num, excerpt = m.group(1), m.group(2).strip()[:100]
                if num not in bib_map:
                    bib_map[num] = {
                        "node_id": f"bib_{num}",
                        "label":   f"[{num}] {excerpt[:60]}",
                        "excerpt": excerpt,
                    }
            print(f"    [english graph] bib section '{section.title[:50]}' → {len(bib_map)} entries")
            continue

        regular_section_ids.add(section.section_id)
        section_data.append({
            "section_id": section.section_id,
            "title":      section.title,
            "text":       section.raw_text or "",
        })

    n_regular = len(section_data)
    nodes_per_sec_cap = max(1, min(3, 60 // max(n_regular, 1)))
    print(f"    [english synthesis] {n_regular} sections (+ {len(bib_map)} bib entries), "
          f"cap={nodes_per_sec_cap} nodes/section, 1 LLM call (full text)")

    raw = llm_call(
        [
            {"role": "system", "content": ENGLISH_GRAPH_SYSTEM},
            {"role": "user",   "content": english_graph_prompt(
                doc.title, section_data,
                nodes_per_section_cap=nodes_per_sec_cap,
                reader_expertise=reader_expertise,
                scientific_knowledge=scientific_knowledge,
                language_complexity=language_complexity,
            )},
        ],
        model=model,
        api_key=api_key,
        max_tokens=6000,
    )

    raw = clean_json(raw, "english_synthesizer")
    data = json.loads(raw)

    summary_keys = {"one_liner", "arc1", "arc2", "Q1_problem", "Q2_insight", "Q3_mechanism", "Q7_limitations"}
    doc.holistic_summary = {k: v for k, v in data.items() if k in summary_keys}

    llm_nodes = data.get("nodes", []) if isinstance(data.get("nodes"), list) else []
    llm_edges = data.get("edges", []) if isinstance(data.get("edges"), list) else []
    llm_sec_ids = {n.get("section_id") for n in llm_nodes}
    missing_from_llm = regular_section_ids - llm_sec_ids
    print(f"    [english graph] {len(llm_nodes)} LLM nodes, {len(llm_edges)} LLM edges before validation")
    if missing_from_llm:
        print(f"    [english graph] LLM skipped {len(missing_from_llm)} sections → fallback nodes will fill them: {sorted(missing_from_llm)[:10]}")

    graph = _build_graph(
        doc, regular_section_ids, bib_map,
        llm_nodes, llm_edges, nodes_per_sec_cap,
    )
    print(f"    [english graph] final: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    doc_map = build_english_doc_map(doc, section_data)
    return doc, doc_map, graph
