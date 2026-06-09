"""
Node extractor — scans sections and creates MathGraph nodes.

Creates:
  1. One 'section' node per section
  2. One node per labelled math object (Theorem N, Lemma N, Proof, ...)
  3. One node per tagged display equation (\tag{N})

NUMBERING RULE FOR UNNUMBERED OBJECTS:
  Math objects with no explicit number (e.g. bare "Definition", "Proof")
  are assigned a positional number derived from their neighbours:
    - Find the previous numbered node in document order → its number is P
    - Find the next numbered node → its number is N
    - Assign: P + "1" appended   e.g. between 3.1 and 3.2 → 3.11
    - If no previous numbered node exists, use "0.1", "0.2" etc.
    - If no next numbered node, append "1" to the previous: 3.1 → 3.11
  This ensures every node has a unique, referenceable label.

PROOF TYPE CLASSIFICATION (for proof nodes):
  "induction"     — contains induction language
  "contradiction" — contains contradiction / counterexample language
  "direct"        — default (construction, direct argument)

All detection is mechanical (regex). No LLM calls.
"""

import re
from ingestion.document import Document
from graph.math_graph import MathGraph, MathNode

# ── math object label pattern ─────────────────────────────────────────

_MATH_LABEL = re.compile(
    r"""
    (?:^|\n)
    \**\s*
    (Theorem|Lemma|Definition|Proposition|Corollary|
     Proof|Remark|Example|Claim|Fact|Conjecture|Notation|Sketch)
    \s*
    ([\d]+(?:\.[\d]+)*)?   # optional number
    \s*[.\-:]?\s*
    \**
    """,
    re.VERBOSE | re.IGNORECASE,
)

_DISPLAY_EQ = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
_TAG        = re.compile(r'\\tag\{([^}]+)\}|\\label\{([^}]+)\}')

# ── proof type detection ──────────────────────────────────────────────

_INDUCTION_PATTERNS = re.compile(
    r'\b(by\s+induction|proof\s+by\s+induction|inductive\s+(step|hypothesis|base)'
    r'|base\s+case|inductive\s+case|assume\s+(it\s+holds|the\s+result\s+holds)\s+for'
    r'|strong\s+induction|mathematical\s+induction)\b',
    re.IGNORECASE,
)

_CONTRADICTION_PATTERNS = re.compile(
    r'\b(suppose\s+(not|for\s+contradiction|the\s+contrary)'
    r'|assume\s+for\s+contradiction|proof\s+by\s+contradiction'
    r'|assume\s+(to\s+the\s+contrary|the\s+opposite)'
    r'|this\s+contradicts|we\s+reach\s+a\s+contradiction'
    r'|counterexample|a\s+contradiction\s+follows'
    r'|leads\s+to\s+a\s+contradiction)\b',
    re.IGNORECASE,
)


def _classify_proof_type(text: str) -> str:
    if _INDUCTION_PATTERNS.search(text):
        return "induction"
    if _CONTRADICTION_PATTERNS.search(text):
        return "contradiction"
    return "direct"


# ── slugify helpers ───────────────────────────────────────────────────

_SLUG_MAP = {
    "theorem": "thm", "lemma": "lem", "definition": "def",
    "proposition": "prop", "corollary": "cor", "proof": "prf",
    "remark": "rem", "example": "ex", "claim": "claim",
    "fact": "fact", "conjecture": "conj", "notation": "not",
    "sketch": "sketch",
}

_TYPE_MAP = {
    "theorem": "theorem", "lemma": "lemma", "definition": "definition",
    "proposition": "proposition", "corollary": "corollary", "proof": "proof",
    "remark": "remark", "example": "example", "claim": "theorem",
    "fact": "theorem", "conjecture": "theorem", "notation": "definition",
    "sketch": "proof",
}


def _slugify(keyword: str, number: str) -> str:
    prefix = _SLUG_MAP.get(keyword.lower(), keyword[:4].lower())
    num_clean = number.replace(".", "_") if number else ""
    return f"{prefix}_{num_clean}" if num_clean else f"{prefix}_"


def _node_type(keyword: str) -> str:
    return _TYPE_MAP.get(keyword.lower(), "theorem")


# ── positional numbering ──────────────────────────────────────────────

def _assign_positional_numbers(raw_items: list[dict]) -> list[dict]:
    """
    Assign positional numbers to unnumbered math objects.

    Numbering rule:
      - Find the previous numbered item's number P
      - Consecutive unnumbered items after P get: P.1, P.2, P.3, ...
      - If no previous numbered item exists, use 0.1, 0.2, 0.3, ...

    Examples:
      Unnumbered after Lemma 1         -> Proof 1.1, Remark 1.2, ...
      Unnumbered after Proposition 3.2 -> Definition 3.2.1, Proof 3.2.2, ...
      Unnumbered at document start     -> Definition 0.1, Example 0.2, ...
    """
    current_prev: str | None = None
    run_count = 0

    for item in raw_items:
        if item["number"]:
            current_prev = item["number"]
            run_count = 0
        else:
            run_count += 1
            base = current_prev if current_prev is not None else "0"
            item["number"] = f"{base}.{run_count}"

    return raw_items


# ── main ──────────────────────────────────────────────────────────────

def extract_nodes(doc: Document) -> MathGraph:
    """
    Scan all sections and return a MathGraph with nodes only.
    Unnumbered math objects are assigned positional numbers.
    Edges are added separately by edge_extractor.
    """
    graph = MathGraph()
    position = 0
    ordered_ids: list[str] = []

    for section in doc.sections:

        # 1. section node
        graph.add_node(MathNode(
            node_id=section.section_id,
            label=section.title,
            node_type="section",
            section_id=section.section_id,
            raw_text=section.raw_text,
            position=position,
        ))
        ordered_ids.append(section.section_id)
        position += 1

        text = section.raw_text

        # ── collect all raw math object matches ───────────────────────
        raw_items = []
        for match in _MATH_LABEL.finditer(text):
            keyword = match.group(1)
            number  = (match.group(2) or "").strip()
            excerpt = text[match.end():match.end() + 600].strip()
            raw_items.append({
                "keyword":   keyword,
                "number":    number,
                "match_end": match.end(),
                "text":      excerpt,
            })

        # ── assign positional numbers to unnumbered items ─────────────
        raw_items = _assign_positional_numbers(raw_items)

        # ── create nodes ──────────────────────────────────────────────
        for item in raw_items:
            keyword = item["keyword"]
            number  = item["number"]
            excerpt = item["text"]

            label   = f"{keyword.capitalize()} {number}".strip()
            node_id = _slugify(keyword, number)

            # deduplicate
            if node_id in graph.nodes:
                node_id = f"{node_id}_{section.section_id}"
            if node_id in graph.nodes:
                continue

            ntype      = _node_type(keyword)
            proof_type = _classify_proof_type(excerpt) if ntype == "proof" else None

            graph.add_node(MathNode(
                node_id=node_id,
                label=label,
                node_type=ntype,
                section_id=section.section_id,
                raw_text=excerpt,
                position=position,
                proof_type=proof_type,
            ))
            ordered_ids.append(node_id)

            # register for edge resolution
            graph._label_index[label.lower()] = node_id
            if number:
                key1 = f"{keyword.lower()}_{number}"
                key2 = f"{keyword.lower()}_{number.replace('.', '_')}"
                graph._number_index[key1] = node_id
                graph._number_index[key2] = node_id

            position += 1

        # 3. tagged display equations
        for eq_match in _DISPLAY_EQ.finditer(text):
            latex = eq_match.group(1).strip()
            if not latex:
                continue
            tag_m = _TAG.search(latex)
            if not tag_m:
                continue
            tag = (tag_m.group(1) or tag_m.group(2) or "").strip()
            if not tag:
                continue

            node_id = f"eq_{tag.replace(' ', '_').replace('.', '_')}"
            if node_id in graph.nodes:
                continue

            graph.add_node(MathNode(
                node_id=node_id,
                label=f"Equation ({tag})",
                node_type="equation",
                section_id=section.section_id,
                raw_latex=latex,
                position=position,
            ))
            ordered_ids.append(node_id)
            graph._number_index[f"eq_{tag}"] = node_id
            position += 1

    graph.set_ordered_ids(ordered_ids)
    return graph
