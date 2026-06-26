"""
Synthesizer — V8 (graph-driven, no section Q&A).

Pipeline: parse → build graph → synthesize.
Section data is derived entirely from the Graph and DocMap:
  - section title
  - all theorem/lemma/definition/corollary/proposition labels in that section
  - proof types present (direct/induction/contradiction) with counts
  - section importance (sum of node in-degrees from doc_map)
  - first 1500 chars of raw section text
"""

import json
from prompts.synthesis_prompt import SYNTHESIS_SYSTEM, synthesis_prompt
from ingestion.document import Document
from graph.math_graph import Graph
from graph.doc_map import DocMap
from pipeline.llm_client import llm_call, clean_json

MATH_TYPES = {"theorem", "lemma", "definition", "corollary", "proposition"}


def _build_section_summaries(
    doc: Document,
    graph: Graph,
    doc_map: DocMap,
) -> list[dict]:
    """
    Build a rich summary for each section purely from graph data.
    No LLM calls — all fields come from already-extracted Graph nodes.
    """
    summaries = []
    for section in doc.sections:
        nodes = graph.nodes_in_section(section.section_id)

        # Labels of all theorem/lemma/definition/corollary/proposition nodes
        math_objects = [n.label for n in nodes if n.node_type in MATH_TYPES]

        # Proof type counts for this section
        proof_types: dict[str, int] = {}
        for n in nodes:
            if n.node_type == "proof" and n.proof_type:
                proof_types[n.proof_type] = proof_types.get(n.proof_type, 0) + 1

        # Section importance from doc_map (sum of node in-degrees)
        entry = doc_map.section_by_id(section.section_id)
        importance = entry.importance if entry else 0

        summaries.append({
            "title":        section.title,
            "importance":   importance,
            "math_objects": math_objects,
            "proof_types":  proof_types,
            "text":         (section.raw_text or "")[:1500],
        })
    return summaries


def _proof_summary(graph: Graph) -> str:
    """Paper-level summary of proof methods for the math_chain block."""
    counts: dict[str, int] = {}
    for node in graph.nodes.values():
        if node.node_type == "proof" and node.proof_type:
            counts[node.proof_type] = counts.get(node.proof_type, 0) + 1
    if not counts:
        return ""
    parts = [f"{v} {k}" for k, v in sorted(counts.items(),
                                             key=lambda x: x[1], reverse=True)]
    return "Proof methods: " + ", ".join(parts) + "."


def run_synthesis(
    doc: Document,
    graph: Graph,
    doc_map: DocMap,
    reader_expertise: float = 0.0,
    scientific_knowledge: float = 0.0,
    language_complexity: float = 0.0,
    model: str = "openrouter/openai/gpt-oss-120b:free",
    api_key: str | None = None,
) -> Document:
    """
    Generate holistic summary from graph-derived section data.
    Returns updated doc with doc.holistic_summary populated.
    """
    section_summaries = _build_section_summaries(doc, graph, doc_map)

    # Top-5 nodes by in-degree give the mathematical spine for arc1
    proof_note = _proof_summary(graph)
    top_nodes = doc_map.top_nodes[:5]
    math_chain = {
        "mathematical_story": (
            proof_note + " Key results by importance: " +
            ", ".join(n["label"] for n in top_nodes)
        ).strip(),
        "chains": [
            {
                "name":  n["label"],
                "story": (
                    f"{n['node_type']} in section {n['section_id']}, "
                    f"in-degree {n['in_degree']}"
                    + (f", proof: {n['proof_type']}" if n.get("proof_type") else "")
                ),
            }
            for n in top_nodes
        ],
    }

    raw = llm_call([
        {"role": "system", "content": SYNTHESIS_SYSTEM},
        {"role": "user",   "content": synthesis_prompt(
            doc.title, section_summaries, math_chain,
            reader_expertise=reader_expertise,
            scientific_knowledge=scientific_knowledge,
            language_complexity=language_complexity,
        )},
    ], model=model, api_key=api_key, max_tokens=3000)

    raw = clean_json(raw, "synthesizer")
    doc.holistic_summary = json.loads(raw)
    return doc
