"""
Graph store — disk cache for Graph and DocMap.

Files:
  graph_cache/{paper_id}.graph.json
  graph_cache/{paper_id}.docmap.json
"""

import os
import json
from graph.math_graph import Graph
from graph.doc_map import DocMap

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "graph_cache")


def _graph_path(paper_id: str) -> str:
    return os.path.join(CACHE_DIR, f"{paper_id}.graph.json")

def _docmap_path(paper_id: str) -> str:
    return os.path.join(CACHE_DIR, f"{paper_id}.docmap.json")


def save_graph(paper_id: str, graph: Graph, doc_map: DocMap):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_graph_path(paper_id), "w", encoding="utf-8") as f:
        f.write(graph.to_json())
    with open(_docmap_path(paper_id), "w", encoding="utf-8") as f:
        f.write(doc_map.to_json())
    print(f"  Graph cached: {paper_id} "
          f"({len(graph.nodes)} nodes, {len(graph.edges)} edges)")


def load_graph(paper_id: str) -> tuple[Graph, DocMap] | tuple[None, None]:
    gp, dp = _graph_path(paper_id), _docmap_path(paper_id)
    if not os.path.exists(gp) or not os.path.exists(dp):
        return None, None
    with open(gp, encoding="utf-8") as f:
        graph = Graph.from_json(f.read())
    with open(dp, encoding="utf-8") as f:
        doc_map = DocMap.from_json(f.read())
    print(f"  Graph loaded from cache: {paper_id} "
          f"({len(graph.nodes)} nodes, {len(graph.edges)} edges)")
    return graph, doc_map


def graph_cached(paper_id: str) -> bool:
    return (os.path.exists(_graph_path(paper_id))
            and os.path.exists(_docmap_path(paper_id)))
