"""
English edge extractor — builds directed edges between English paper nodes.

Pass 1 — Citation regex (APA/MLA):
  "(Smith, 2020)" or "Smith (2020)" → edge to External References node

Pass 2 — LLM semantic edges (per section):
  supports, contradicts, qualifies, exemplifies, applies_to, responds_to

Pass 3 — Section membership (same as math):
  every non-section node → its parent section
"""
import re
import json
from graph.math_graph import MathGraph, MathEdge, MathNode

_APA_CITE = re.compile(
    r'\((?:[A-Z][a-z]+(?:\s+(?:et\s+al\.|and|&)\s+[A-Z][a-z]+)?),?\s+\d{4}[a-z]?\)'
    r'|\b[A-Z][a-z]+\s+et\s+al\.\s+\(\d{4}\)'
    r'|\b[A-Z][a-z]+\s+\(\d{4}\)',
    re.MULTILINE,
)

EDGE_TYPES = frozenset({"supports", "contradicts", "qualifies", "exemplifies", "applies_to", "responds_to"})

_EDGE_PROMPT = """\
Given these nodes from one section of an academic paper, identify directed semantic relationships between them.

Nodes:
{nodes_json}

For each relationship, return an object with:
{{"from": "node_id", "to": "node_id", "type": "supports|contradicts|qualifies|exemplifies|applies_to|responds_to", "evidence": "brief phrase"}}

Type guide:
- supports: one node provides evidence or argument for another
- contradicts: one node directly opposes another
- qualifies: one node limits or nuances another
- exemplifies: one node is a concrete example of a concept or claim
- applies_to: a theory/concept is applied to a primary text or example
- responds_to: a claim or argument directly replies to a critic's view

Rules:
- Only create edges between the node_ids listed above.
- Maximum 6 edges.
- Only include edges with clear textual basis.
- Return ONLY a valid JSON array, no explanation. Return [] if none apply.
"""


def _llm_edges_for_section(sec_nodes: list, model: str, api_key) -> list[dict]:
    if len(sec_nodes) < 2:
        return []
    from pipeline.llm_client import llm_call, clean_json
    nodes_json = json.dumps([
        {
            "node_id":  n.node_id,
            "type":     n.node_type,
            "label":    n.label,
            "excerpt":  (n.raw_text or "")[:120],
        }
        for n in sec_nodes
    ], ensure_ascii=False)
    try:
        raw = llm_call(
            messages=[{"role": "user", "content": _EDGE_PROMPT.format(nodes_json=nodes_json)}],
            model=model,
            api_key=api_key,
            max_tokens=400,
        )
        edges = json.loads(clean_json(raw, context="english_edges"))
        return edges if isinstance(edges, list) else []
    except Exception as exc:
        print(f"      [english edges] LLM failed: {exc}")
        return []


def extract_edges(graph: MathGraph, model: str, api_key=None) -> MathGraph:
    nodes = graph.nodes

    # ── Pass 1: citation regex → External References node ────────────
    ext_id = "external_refs"
    if ext_id not in nodes:
        graph.add_node(MathNode(
            node_id=ext_id,
            label="External References",
            node_type="external",
            section_id=ext_id,
            raw_text="Cited works outside this paper",
            position=99999,
        ))

    for node in list(nodes.values()):
        if node.node_id == ext_id or node.node_type in {"section", "external"}:
            continue
        if _APA_CITE.search(node.raw_text or ""):
            graph.add_edge(MathEdge(
                from_id=node.node_id,
                to_id=ext_id,
                source="regex",
                evidence="citation",
                confidence="certain",
            ))

    # ── Pass 2: LLM semantic edges per section ────────────────────────
    by_section: dict[str, list] = {}
    for node in nodes.values():
        if node.node_type in {"section", "external"}:
            continue
        by_section.setdefault(node.section_id, []).append(node)

    for sec_nodes in by_section.values():
        for e in _llm_edges_for_section(sec_nodes, model, api_key):
            from_id  = e.get("from")
            to_id    = e.get("to")
            etype    = e.get("type", "")
            evidence = e.get("evidence", "")
            if from_id in nodes and to_id in nodes and etype in EDGE_TYPES:
                graph.add_edge(MathEdge(
                    from_id=from_id,
                    to_id=to_id,
                    source="llm",
                    evidence=evidence,
                    confidence="inferred",
                ))

    # ── Pass 3: section membership ────────────────────────────────────
    for node in list(nodes.values()):
        if node.node_type in {"section", "external"}:
            continue
        if node.section_id in nodes:
            graph.add_edge(MathEdge(
                from_id=node.node_id,
                to_id=node.section_id,
                source="section",
                evidence="belongs-to",
                confidence="certain",
            ))

    graph.finalize()
    return graph
