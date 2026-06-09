"""
Edge extractor — builds directed edges between math nodes.

Pass 1 — Regex (explicit numbered references):
  "by Theorem 5"     → edge to thm_5
  "see Lemma 1"      → edge to lem_1
  "Proposition 18"   → edge to prop_18

Pass 2 — Positional (directional refs with known direction AND count):
  "the preceding lemma"     → 1 above, type=lemma
  "the above theorem"       → 1 above, type=theorem
  "the following corollary" → 1 below, type=corollary
  "both of the above"       → 2 above, any type

DROP RULE: if direction OR count is unknown → no edge.

Pass 3 — Section membership:
  Every non-section node gets a structural edge to its parent section.
  source="section", no arrow, low opacity — shows which section owns it.
"""

import re
from graph.math_graph import MathGraph, MathEdge

_KEYWORDS = (
    "theorem", "lemma", "definition", "proposition", "corollary",
    "proof", "remark", "example", "claim", "equation", "fact", "notation",
)

_EXPLICIT_REF = re.compile(
    r'(?:' + '|'.join(_KEYWORDS) + r')\s+([\d]+(?:\.[\d]+)*)',
    re.IGNORECASE,
)
_EQ_REF = re.compile(r'\beq(?:uation)?s?\.?\s*\(?([\d]+(?:\.[\d]+)*)\)?', re.IGNORECASE)

_ABOVE = r'(?:preceding|previous|above|prior|earlier|last)'
_BELOW = r'(?:following|next|below|subsequent)'

_POSITIONAL: list[tuple[str, int, str | None, re.Pattern]] = []
for _kw in _KEYWORDS:
    _POSITIONAL.append(("above", 1, _kw,
        re.compile(rf'(?:the\s+)?{_ABOVE}\s+{_kw}', re.IGNORECASE)))
    _POSITIONAL.append(("below", 1, _kw,
        re.compile(rf'(?:the\s+)?{_BELOW}\s+{_kw}', re.IGNORECASE)))
    _POSITIONAL.append(("above", 2, _kw,
        re.compile(rf'(?:previous\s+two|two\s+{_ABOVE})\s+{_kw}s?', re.IGNORECASE)))
    _POSITIONAL.append(("below", 2, _kw,
        re.compile(rf'(?:following\s+two|two\s+{_BELOW})\s+{_kw}s?', re.IGNORECASE)))

_POSITIONAL.append(("above", 2, None,
    re.compile(r'both\s+(?:of\s+)?(?:the\s+)?above', re.IGNORECASE)))
_POSITIONAL.append(("above", 2, None,
    re.compile(r'both\s+(?:results?|statements?|facts?|observations?)\s+above',
               re.IGNORECASE)))


def _resolve_positional(pos, direction, count, type_filter, ordered_ids, nodes):
    if direction == "above":
        candidates = [nid for nid in reversed(ordered_ids[:pos]) if nid in nodes]
    else:
        candidates = [nid for nid in ordered_ids[pos + 1:] if nid in nodes]
    results = []
    for nid in candidates:
        if type_filter is None or nodes[nid].node_type == type_filter:
            results.append(nid)
            if len(results) == count:
                break
    return results


def extract_edges(graph: MathGraph) -> MathGraph:
    ordered_ids  = graph._ordered_node_ids
    nodes        = graph.nodes
    number_index = getattr(graph, "_number_index", {})

    for node in list(nodes.values()):
        text = node.raw_text
        if not text:
            continue
        pos = node.position

        # Pass 1: explicit numbered refs
        for m in _EXPLICIT_REF.finditer(text):
            full, number = m.group(0).lower(), m.group(1)
            for kw in _KEYWORDS:
                if full.startswith(kw):
                    tid = (number_index.get(f"{kw}_{number}") or
                           number_index.get(f"{kw}_{number.replace('.','_')}"))
                    if tid and tid != node.node_id:
                        graph.add_edge(MathEdge(
                            from_id=node.node_id, to_id=tid,
                            source="regex", evidence=m.group(0),
                            confidence="certain"))
                    break

        for m in _EQ_REF.finditer(text):
            tid = number_index.get(f"eq_{m.group(1)}")
            if tid and tid != node.node_id:
                graph.add_edge(MathEdge(
                    from_id=node.node_id, to_id=tid,
                    source="regex", evidence=m.group(0),
                    confidence="certain"))

        # Pass 2: positional refs
        for direction, count, type_filter, pattern in _POSITIONAL:
            if not pattern.search(text):
                continue
            for tid in _resolve_positional(pos, direction, count,
                                           type_filter, ordered_ids, nodes):
                if tid != node.node_id:
                    graph.add_edge(MathEdge(
                        from_id=node.node_id, to_id=tid,
                        source="positional", evidence=pattern.pattern,
                        confidence="certain"))

    # Pass 3: section membership — every math object → its parent section
    for node in list(nodes.values()):
        if node.node_type == "section":
            continue
        if node.section_id in nodes:
            graph.add_edge(MathEdge(
                from_id=node.node_id,
                to_id=node.section_id,
                source="section",
                evidence="belongs-to",
                confidence="certain",
            ))

    # Pass 4: external references node
    # Any node that cites something outside the paper (Munkres, Hatcher, etc.)
    # gets an edge to a special "External References" node.
    _EXTERNAL_PATTERN = re.compile(
        r'\b(Munkres|Hatcher|Eilenberg|Steenrod|Spanier|Hurewicz|Wallman|'
        r'Nagami|Nagata|Kodama|Hurewicz|Vick|Lee|Dieudonne|Wikipedia|'
        r'exercise|page\s+\d+|pp\.\s*\d+)\b',
        re.IGNORECASE,
    )
    # Add the external references node
    from graph.math_graph import MathNode
    ext_id = "external_refs"
    if ext_id not in nodes:
        graph.add_node(MathNode(
            node_id=ext_id,
            label="External References",
            node_type="section",
            section_id=ext_id,
            raw_text="Citations to works outside this paper",
            position=99999,
        ))

    for node in list(graph.nodes.values()):
        if node.node_id == ext_id:
            continue
        if _EXTERNAL_PATTERN.search(node.raw_text or ""):
            graph.add_edge(MathEdge(
                from_id=node.node_id,
                to_id=ext_id,
                source="regex",
                evidence="external citation",
                confidence="certain",
            ))

    # Pass 4: external references node
    # Nodes that cite works outside this paper get an edge to a shared
    # "External References" node, making outside dependencies visible.
    _EXT_PATTERN = re.compile(
        r'\b(Munkres|Hatcher|Eilenberg|Steenrod|Spanier|Hurewicz|Wallman|'
        r'Nagami|Nagata|Kodama|Vick|Lee|Dieudonne|Wikipedia|'
        r'exercise|see page|pp\.\s*\d+|ibid)\b',
        re.IGNORECASE,
    )
    from graph.math_graph import MathNode
    ext_id = "external_refs"
    if ext_id not in nodes:
        graph.add_node(MathNode(
            node_id=ext_id,
            label="External References",
            node_type="external",
            section_id=ext_id,
            raw_text="Citations to works outside this paper",
            position=99999,
        ))

    for node in list(graph.nodes.values()):
        if node.node_id == ext_id or node.node_type == "section":
            continue
        if _EXT_PATTERN.search(node.raw_text or ""):
            graph.add_edge(MathEdge(
                from_id=node.node_id,
                to_id=ext_id,
                source="regex",
                evidence="external citation",
                confidence="certain",
            ))

    graph.finalize()
    return graph
