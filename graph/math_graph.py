"""
Graph — core data structure.

Every theorem, lemma, definition, corollary, proof, section, claim,
concept, and evidence node becomes a Node. Every cross-reference becomes
a directed Edge.

Node importance = in-degree (how many other nodes reference this one).
Proof nodes additionally carry proof_type:
  "direct"        — construction / direct proof
  "induction"     — proof by induction
  "contradiction" — proof by contradiction or counterexample
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import json

try:
    import networkx as nx
    _NX = True
except ImportError:
    _NX = False


NODE_TYPES = {
    # math
    "definition", "theorem", "lemma", "proof", "corollary",
    "proposition", "remark", "example", "equation", "section",
    # english/humanities
    "claim", "concept", "evidence", "critic_view", "primary_text", "external",
}

PROOF_TYPES = {"direct", "induction", "contradiction"}


@dataclass
class Node:
    node_id: str         # e.g. "thm_5", "def_lebesgue", "s2"
    label: str           # display label e.g. "Theorem 5"
    node_type: str       # one of NODE_TYPES
    section_id: str      # which section this lives in
    raw_text: str = ""   # text excerpt
    raw_latex: str = ""  # latex if equation node
    position: int = 0    # document order position
    in_degree: int = 0   # computed after graph finalized
    proof_type: Optional[str] = None  # only for node_type=="proof"
    qa: Optional[dict] = None         # filled by section_qa pipeline


@dataclass
class Edge:
    from_id: str
    to_id: str
    source: str          # "regex" | "positional" | "llm"
    evidence: str = ""   # text span that triggered this edge
    confidence: str = "certain"  # "certain" | "inferred"


class Graph:
    """
    Holds all nodes and edges for one paper.
    Wraps networkx DiGraph when available, falls back to
    pure-Python lookups otherwise.
    """

    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._graph = nx.DiGraph() if _NX else None
        self._ordered_node_ids: list[str] = []
        self._label_index: dict[str, str] = {}   # "theorem 5" → "thm_5"
        self._number_index: dict[str, str] = {}  # "thm_5" → node_id

    # ── building ──────────────────────────────────────────────────────

    def add_node(self, node: Node):
        self.nodes[node.node_id] = node
        if _NX:
            self._graph.add_node(node.node_id,
                label=node.label, node_type=node.node_type,
                section_id=node.section_id, position=node.position,
                proof_type=node.proof_type)

    def add_edge(self, edge: Edge):
        if edge.from_id not in self.nodes or edge.to_id not in self.nodes:
            return
        if edge.from_id == edge.to_id:
            return
        for e in self.edges:
            if e.from_id == edge.from_id and e.to_id == edge.to_id:
                return
        self.edges.append(edge)
        if _NX:
            self._graph.add_edge(edge.from_id, edge.to_id,
                source=edge.source, evidence=edge.evidence,
                confidence=edge.confidence)

    def set_ordered_ids(self, ids: list[str]):
        self._ordered_node_ids = ids

    def finalize(self):
        """Compute in-degrees after all nodes and edges added."""
        in_counts: dict[str, int] = {nid: 0 for nid in self.nodes}
        for edge in self.edges:
            in_counts[edge.to_id] = in_counts.get(edge.to_id, 0) + 1
        for nid, node in self.nodes.items():
            node.in_degree = in_counts.get(nid, 0)

    # ── queries ───────────────────────────────────────────────────────

    def get_ancestors(self, node_id: str, max_depth: int = 3) -> list[Node]:
        """Nodes this node depends on — walk edges backwards."""
        if not _NX or node_id not in self._graph:
            return []
        visited, result, frontier, depth = set(), [], [node_id], 0
        while frontier and depth < max_depth:
            next_f = []
            for nid in frontier:
                for pred in self._graph.predecessors(nid):
                    if pred not in visited:
                        visited.add(pred)
                        result.append(self.nodes[pred])
                        next_f.append(pred)
            frontier = next_f
            depth += 1
        return result

    def get_dependents(self, node_id: str) -> list[Node]:
        """Nodes that reference this node."""
        if not _NX or node_id not in self._graph:
            return []
        return [self.nodes[s] for s in self._graph.successors(node_id)
                if s in self.nodes]

    def topological_sections(self) -> list[str]:
        """Section ids in dependency order. Falls back to document order."""
        if not _NX:
            return self._doc_order_sections()
        try:
            topo = list(nx.topological_sort(self._graph))
            seen: list[str] = []
            for nid in topo:
                node = self.nodes.get(nid)
                if node and node.section_id not in seen:
                    seen.append(node.section_id)
            return seen
        except nx.NetworkXUnfeasible:
            return self._doc_order_sections()

    def _doc_order_sections(self) -> list[str]:
        seen: list[str] = []
        for nid in self._ordered_node_ids:
            node = self.nodes.get(nid)
            if node and node.section_id not in seen:
                seen.append(node.section_id)
        return seen

    def nodes_by_importance(self) -> list[Node]:
        return sorted(self.nodes.values(), key=lambda n: n.in_degree, reverse=True)

    def section_nodes(self) -> list[Node]:
        return [self.nodes[nid] for nid in self._ordered_node_ids
                if nid in self.nodes and self.nodes[nid].node_type == "section"]

    def nodes_in_section(self, section_id: str) -> list[Node]:
        return [self.nodes[nid] for nid in self._ordered_node_ids
                if nid in self.nodes
                and self.nodes[nid].section_id == section_id
                and self.nodes[nid].node_type != "section"]

    def proof_nodes(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.node_type == "proof"]

    # ── serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "nodes": {nid: {
                "node_id": n.node_id, "label": n.label,
                "node_type": n.node_type, "section_id": n.section_id,
                "raw_text": n.raw_text, "raw_latex": n.raw_latex,
                "position": n.position, "in_degree": n.in_degree,
                "proof_type": n.proof_type, "qa": n.qa,
            } for nid, n in self.nodes.items()},
            "edges": [{"from_id": e.from_id, "to_id": e.to_id,
                       "source": e.source, "evidence": e.evidence,
                       "confidence": e.confidence}
                      for e in self.edges],
            "ordered_node_ids": self._ordered_node_ids,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Graph":
        g = cls()
        for nd in data.get("nodes", {}).values():
            g.add_node(Node(
                node_id=nd["node_id"], label=nd["label"],
                node_type=nd["node_type"], section_id=nd["section_id"],
                raw_text=nd.get("raw_text", ""), raw_latex=nd.get("raw_latex", ""),
                position=nd.get("position", 0), in_degree=nd.get("in_degree", 0),
                proof_type=nd.get("proof_type"), qa=nd.get("qa"),
            ))
        for ed in data.get("edges", []):
            g.add_edge(Edge(
                from_id=ed["from_id"], to_id=ed["to_id"],
                source=ed["source"], evidence=ed.get("evidence", ""),
                confidence=ed.get("confidence", "certain"),
            ))
        g.set_ordered_ids(data.get("ordered_node_ids", []))
        g.finalize()
        return g

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Graph":
        return cls.from_dict(json.loads(s))


# backward-compat aliases — remove once all callers updated
MathGraph = Graph
MathNode = Node
MathEdge = Edge
