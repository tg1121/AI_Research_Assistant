"""
English node extractor — extracts intellectual nodes from humanities/literary papers.

Node types:
  claim        — argument or assertion the paper itself makes
  concept      — theoretical/critical term being defined or deployed
  evidence     — textual quotation, close reading, or specific textual example
  critic_view  — a position attributed to another scholar
  primary_text — the literary/historical text(s) being analyzed
  section      — one per document section (same as math path)

Extraction uses one LLM call per section. Falls back to section-only nodes on failure.
"""
import re
import json
from ingestion.document import Document
from graph.math_graph import MathGraph, MathNode

_SLUG_MAP = {
    "claim":        "clm",
    "concept":      "con",
    "evidence":     "ev",
    "critic_view":  "cv",
    "primary_text": "pt",
}

_NODE_PROMPT = """\
You are analyzing a section of an academic English or literary studies paper.
Extract the key intellectual nodes from this section.

Section title: {title}
Section text:
{text}

Return a JSON array. Each item must have exactly these keys:
- "type": one of "claim", "concept", "evidence", "critic_view", "primary_text"
- "label": short 3-6 word label in title case
- "excerpt": 1-2 sentence excerpt from the text (exact quote, max 150 chars)
- "slug_suffix": short unique slug (lowercase letters, digits, underscores only)

Type definitions:
- claim: An argument the paper itself makes. Signals: "I argue", "this paper contends", "I suggest", "my thesis".
- concept: A theoretical/critical term being defined or deployed. Signals: "by X I mean", "X refers to", "the concept of X".
- evidence: A textual quotation or close reading. Signals: block quotes, line citations, "As X writes/shows/demonstrates".
- critic_view: A position attributed to another scholar. Signals: "Smith argues", "According to Foucault", "Butler contends".
- primary_text: The literary or historical work being analyzed (novel, poem, play, document).

Rules:
- Return at most 5 nodes per section.
- Return [] if the section has no significant intellectual content (e.g. bibliography, abstract, acknowledgements).
- Only include nodes with clear textual evidence.
- Return ONLY valid JSON, no explanation.
"""


def _extract_section_nodes(section, model: str, api_key) -> list[dict]:
    from pipeline.llm_client import llm_call, clean_json
    text = (section.raw_text or "")[:1400]
    if len(text.strip()) < 80:
        return []
    prompt = _NODE_PROMPT.format(title=section.title, text=text)
    try:
        raw = llm_call(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            api_key=api_key,
            max_tokens=600,
        )
        items = json.loads(clean_json(raw, context=f"english_nodes:{section.section_id}"))
        return items if isinstance(items, list) else []
    except Exception as exc:
        print(f"      [english nodes] {section.section_id} LLM failed: {exc}")
        return []


def extract_nodes(doc: Document, model: str, api_key=None) -> MathGraph:
    graph = MathGraph()
    position = 0
    ordered_ids: list[str] = []
    seen_ids: set[str] = set()

    for section in doc.sections:
        graph.add_node(MathNode(
            node_id=section.section_id,
            label=section.title,
            node_type="section",
            section_id=section.section_id,
            raw_text=section.raw_text,
            position=position,
        ))
        ordered_ids.append(section.section_id)
        seen_ids.add(section.section_id)
        position += 1

        items = _extract_section_nodes(section, model, api_key)

        for item in items:
            ntype = item.get("type", "")
            if ntype not in _SLUG_MAP:
                continue
            label   = (item.get("label") or "").strip()
            excerpt = (item.get("excerpt") or "").strip()
            suffix  = re.sub(r'[^a-z0-9_]', '',
                             (item.get("slug_suffix") or "").lower().replace(" ", "_"))[:24]
            if not suffix:
                suffix = re.sub(r'\W+', '_', label.lower())[:20]

            node_id = f"{_SLUG_MAP[ntype]}_{suffix}"
            # deduplicate
            base_id, counter = node_id, 1
            while node_id in seen_ids:
                node_id = f"{base_id}_{counter}"
                counter += 1

            seen_ids.add(node_id)
            graph.add_node(MathNode(
                node_id=node_id,
                label=label or ntype.replace("_", " ").title(),
                node_type=ntype,
                section_id=section.section_id,
                raw_text=excerpt,
                position=position,
            ))
            ordered_ids.append(node_id)
            graph._label_index[label.lower()] = node_id
            position += 1

    graph.set_ordered_ids(ordered_ids)
    return graph
