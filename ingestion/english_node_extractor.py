"""
English node extractor — section-only graph for English/humanities papers.
No LLM calls; all LLM work is handled by english_synthesizer in a single call.
"""
from ingestion.document import Document
from graph.math_graph import Graph, Node


def extract_nodes(doc: Document, **_kwargs) -> Graph:
    graph = Graph()
    ordered_ids: list[str] = []

    for position, section in enumerate(doc.sections):
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
    return graph
