"""
DocMap — lightweight structural index built from the MathGraph.

The agent reads this first for every question (~300 tokens).
Answers structural questions with zero retrieval:
  - what sections exist?
  - which are most important?
  - what does section X depend on?
  - what type of paper is this?

Built once at ingestion, cached to disk, never rebuilt unless graph changes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import json

from graph.math_graph import MathGraph


@dataclass
class SectionEntry:
    section_id: str
    title: str
    importance: int           # sum of in-degrees of all nodes in this section
    math_object_count: int    # theorems + lemmas + defs + etc. in this section
    proof_count: int          # number of proof nodes in this section
    depends_on: list[str]     # section_ids this section's nodes reference
    referenced_by: list[str]  # section_ids that reference this section's nodes


@dataclass
class DocMap:
    paper_id: str
    paper_title: str
    sections: list[SectionEntry]   # document order
    top_nodes: list[dict]          # top-10 nodes by in-degree (non-section)
    total_nodes: int
    total_edges: int
    dominant_type: str             # e.g. "theorem-heavy"

    # ── queries ───────────────────────────────────────────────────────

    def section_by_id(self, section_id: str) -> Optional[SectionEntry]:
        for s in self.sections:
            if s.section_id == section_id:
                return s
        return None

    def most_important_sections(self, n: int = 3) -> list[SectionEntry]:
        return sorted(self.sections, key=lambda s: s.importance, reverse=True)[:n]

    def to_prompt_block(self) -> str:
        """Compact text for agent prompt injection. ~300 tokens."""
        lines = [
            f'Paper: "{self.paper_title}"',
            f"Sections ({len(self.sections)} total, "
            f"{self.total_edges} cross-references, {self.dominant_type}):",
        ]
        for s in self.sections:
            dep_str = (f" → depends on: {', '.join(s.depends_on)}"
                       if s.depends_on else "")
            lines.append(
                f"  [{s.section_id}] {s.title} "
                f"(importance={s.importance}, "
                f"math_objects={s.math_object_count}, "
                f"proofs={s.proof_count})"
                f"{dep_str}"
            )
        if self.top_nodes:
            lines.append("\nMost referenced nodes:")
            for n in self.top_nodes[:5]:
                pt = f", proof_type={n['proof_type']}" if n.get("proof_type") else ""
                lines.append(
                    f"  {n['label']} "
                    f"({n['node_type']}, in-degree={n['in_degree']}{pt})"
                )
        return "\n".join(lines)

    # ── serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "paper_title": self.paper_title,
            "sections": [s.__dict__ for s in self.sections],
            "top_nodes": self.top_nodes,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "dominant_type": self.dominant_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocMap":
        return cls(
            paper_id=data["paper_id"],
            paper_title=data["paper_title"],
            sections=[SectionEntry(**s) for s in data["sections"]],
            top_nodes=data["top_nodes"],
            total_nodes=data["total_nodes"],
            total_edges=data["total_edges"],
            dominant_type=data["dominant_type"],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "DocMap":
        return cls.from_dict(json.loads(s))


# ── builder ───────────────────────────────────────────────────────────

def build_doc_map(graph: MathGraph, paper_id: str, paper_title: str) -> DocMap:
    """Build DocMap from a finalized MathGraph. No LLM calls."""

    # inter-section dependency sets
    sec_depends_on: dict[str, set[str]] = {}
    sec_referenced_by: dict[str, set[str]] = {}
    for node in graph.nodes.values():
        if node.node_type == "section":
            sec_depends_on.setdefault(node.section_id, set())
            sec_referenced_by.setdefault(node.section_id, set())

    for edge in graph.edges:
        fn = graph.nodes.get(edge.from_id)
        tn = graph.nodes.get(edge.to_id)
        if not fn or not tn:
            continue
        fs, ts = fn.section_id, tn.section_id
        if fs != ts:
            sec_depends_on.setdefault(fs, set()).add(ts)
            sec_referenced_by.setdefault(ts, set()).add(fs)

    # per-section counts
    math_counts: dict[str, int] = {}
    proof_counts: dict[str, int] = {}
    sec_importance: dict[str, int] = {}
    for node in graph.nodes.values():
        sid = node.section_id
        sec_importance[sid] = sec_importance.get(sid, 0) + node.in_degree
        if node.node_type == "proof":
            proof_counts[sid] = proof_counts.get(sid, 0) + 1
        elif node.node_type != "section":
            math_counts[sid] = math_counts.get(sid, 0) + 1

    # section entries in document order
    sections = []
    for sn in graph.section_nodes():
        sid = sn.section_id
        sections.append(SectionEntry(
            section_id=sid,
            title=sn.label,
            importance=sec_importance.get(sid, 0),
            math_object_count=math_counts.get(sid, 0),
            proof_count=proof_counts.get(sid, 0),
            depends_on=sorted(sec_depends_on.get(sid, set())),
            referenced_by=sorted(sec_referenced_by.get(sid, set())),
        ))

    # top non-section nodes by in-degree
    top_nodes = [
        {"node_id": n.node_id, "label": n.label, "node_type": n.node_type,
         "section_id": n.section_id, "in_degree": n.in_degree,
         "proof_type": n.proof_type}
        for n in graph.nodes_by_importance()
        if n.node_type != "section" and n.in_degree > 0
    ][:10]

    # dominant type
    type_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        if node.node_type not in ("section", "proof"):
            type_counts[node.node_type] = type_counts.get(node.node_type, 0) + 1
    dominant = max(type_counts, key=lambda k: type_counts[k]) if type_counts else "mixed"
    dominant_type = f"{dominant}-heavy"

    return DocMap(
        paper_id=paper_id,
        paper_title=paper_title,
        sections=sections,
        top_nodes=top_nodes,
        total_nodes=len(graph.nodes),
        total_edges=len(graph.edges),
        dominant_type=dominant_type,
    )
