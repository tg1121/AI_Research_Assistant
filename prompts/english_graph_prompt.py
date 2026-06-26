from feedback.parameters import get_parameter_block

ENGLISH_GRAPH_SYSTEM = """You are a research paper summarizer. You only output valid JSON.
No explanations. No markdown. No code fences."""

SEMANTIC_NODE_TYPES = frozenset({"claim", "concept", "evidence", "critic_view", "primary_text"})
SEMANTIC_EDGE_TYPES = frozenset({"supports", "contradicts", "qualifies", "exemplifies", "applies_to", "responds_to"})

_NODE_GUIDE = """\
Node types — what to look for:
  claim        : A proposition or assertion the author makes and defends. Look for thesis
                 statements, argumentative moves, and conclusions the paper is trying to establish.
  concept      : A theoretical term, framework, or analytical lens the paper relies on
                 (e.g. "hegemony", "performativity", "the sublime"). Must be named and used
                 as a tool of analysis, not just mentioned in passing.
  evidence     : A specific piece of supporting material — a quote, case study, statistic,
                 historical event, or textual example deployed to back a claim.
  critic_view  : A position, argument, or interpretation held by another scholar that the
                 author engages with — agreeing, refuting, revising, or building on it.
  primary_text : A specific work, text, artwork, film, event, or dataset that the paper
                 takes as its object of analysis (what the paper is "about").\
"""

_EDGE_GUIDE = """\
Edge types — directional relationships:
  supports     : from_node provides evidence or argument for to_node
  contradicts  : from_node directly opposes or refutes to_node
  qualifies    : from_node limits, nuances, or complicates to_node
  exemplifies  : from_node is a concrete instance of to_node
  applies_to   : from_node (concept/framework) is used to analyse to_node (primary text/case)
  responds_to  : from_node (claim/argument) directly replies to to_node (critic_view)\
"""


def english_graph_prompt(
    title: str,
    section_data: list[dict],
    nodes_per_section_cap: int = 3,
    **params,
) -> str:
    """
    Single combined prompt: synthesis summary + semantic graph extraction.

    Each entry in section_data has:
      section_id — id used to anchor graph nodes (e.g. "s0", "s1")
      title      — section heading
      text       — full section text
    """
    parameter_block = get_parameter_block(params)

    required_ids = ", ".join(s["section_id"] for s in section_data)

    section_block = ""
    for s in section_data:
        section_block += f"\n\n--- {s['title']} (id: {s['section_id']}) ---\n"
        if s.get("text"):
            section_block += s["text"] + "\n"

    return f"""You are reading the full text of this paper: "{title}"

{parameter_block}
SECTIONS:
{section_block}

Return ONLY this JSON object — no explanation, no markdown fences:
{{
  "one_liner": "one sentence capturing the central argument",
  "arc1": "flowing prose 150-200 words: central argument, theoretical framework, key intervention",
  "arc2": "flowing prose 150-200 words: evidence, methodology, implications, limits",
  "Q1_problem": "1-2 sentences: what gap, question, or debate does this paper address?",
  "Q2_insight": "1-2 sentences: what is the central argument or thesis?",
  "Q3_mechanism": "1-2 sentences: how is the argument constructed — what methods or frameworks are used?",
  "Q7_limitations": "1-2 sentences: what is missing, contested, or unresolved?",
  "nodes": [
    {{"id": "unique_snake_case_id", "type": "claim|concept|evidence|critic_view|primary_text", "label": "short label max 8 words", "section_id": "sN"}}
  ],
  "edges": [
    {{"from": "node_id", "to": "node_id", "type": "supports|contradicts|qualifies|exemplifies|applies_to|responds_to", "evidence": "brief phrase from the text"}}
  ]
}}

{_NODE_GUIDE}

{_EDGE_GUIDE}

Graph constraints:
- You MUST include at least one node for each of these section IDs: {required_ids}
- Max {nodes_per_section_cap} node(s) per section. Use the section_id shown in the section header for each node.
- Max 2 edges per node. Max 40 edges total.
- Only create edges between node ids you define in "nodes".
- Node ids must be unique snake_case strings (e.g. "hegelian_dialectic", "claim_historicity").
- Only include edges with clear textual basis. Return [] for edges if none apply.

Summary rules:
- Match language and depth strictly to the reader profile parameters.
- Prose inside arc1 and arc2. No bullet points."""
