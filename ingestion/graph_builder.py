"""
Graph builder — builds Graph and DocMap.

Supports two domains:
  "math"     — regex-based (Theorem/Lemma/Definition/…) with full node/edge extraction
  "non-math" — section-only graph; all LLM work done in english_synthesizer
  "auto"     — detect domain from document content (default)
"""

from ingestion.document import Document
from ingestion.domain_detector import detect_domain
from ingestion.node_extractor import extract_nodes as math_extract_nodes
from ingestion.edge_extractor import extract_edges as math_extract_edges
from graph.doc_map import build_doc_map
from graph.math_graph import Graph
from graph.doc_map import DocMap


def build_graph(
    doc: Document,
    domain: str = "auto",
    model: str | None = None,
    api_key: str | None = None,
) -> tuple[Graph, DocMap, str]:
    """
    Build Graph and DocMap.
    Returns (graph, doc_map, resolved_domain).
    domain: "auto" | "math" | "english"
    """
    print(f"  Building graph for '{doc.title}'...")

    if domain == "auto":
        resolved, confidence = detect_domain(doc)
        print(f"    [domain] auto-detected: {resolved} (confidence={confidence:.2f})")
    else:
        resolved = domain
        print(f"    [domain] user-selected: {resolved}")

    if resolved == "math":
        print("    [1/3] Extracting nodes (math)...")
        graph = math_extract_nodes(doc)
        n_proofs        = sum(1 for n in graph.nodes.values() if n.node_type == "proof")
        n_direct        = sum(1 for n in graph.nodes.values() if n.proof_type == "direct")
        n_induction     = sum(1 for n in graph.nodes.values() if n.proof_type == "induction")
        n_contradiction = sum(1 for n in graph.nodes.values() if n.proof_type == "contradiction")
        print(f"      {len(graph.nodes)} nodes "
              f"({n_proofs} proofs: "
              f"{n_direct} direct, {n_induction} induction, "
              f"{n_contradiction} contradiction)")

        print("    [2/3] Extracting edges (math)...")
        graph = math_extract_edges(graph)
        print(f"      {len(graph.edges)} edges "
              f"({sum(1 for e in graph.edges if e.source=='regex')} regex, "
              f"{sum(1 for e in graph.edges if e.source=='positional')} positional, "
              f"{sum(1 for e in graph.edges if e.source=='section')} belongs-to)")

    else:  # non-math — section-only graph, LLM work done in english_synthesizer
        from ingestion.english_node_extractor import extract_nodes as eng_nodes
        graph = eng_nodes(doc)
        print(f"    [non-math] {len(graph.nodes)} section nodes")

    print("    [3/3] Building document map...")
    doc_map = build_doc_map(graph, doc.paper_id, doc.title)

    return graph, doc_map, resolved
