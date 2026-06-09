from feedback.parameters import get_parameter_block

SYNTHESIS_SYSTEM = """You are a research paper summarizer. You only output valid JSON.
No explanations. No markdown. No code fences."""


def synthesis_prompt(
    title: str,
    section_summaries: list[dict],
    mathematical_chain: dict = None,
    **params,
) -> str:
    """
    Build the synthesis prompt from graph-derived section data.

    Each entry in section_summaries has:
      title        — section heading
      importance   — sum of node in-degrees (higher = more cross-referenced)
      math_objects — list of theorem/lemma/definition/corollary labels
      proof_types  — dict {proof_type: count}
      text         — first 1500 chars of raw section text
    """
    parameter_block = get_parameter_block(params)

    # ── section block ─────────────────────────────────────────────────
    section_block = ""
    for s in section_summaries:
        section_block += f"\n\n--- {s['title']} (importance={s['importance']}) ---\n"
        if s["math_objects"]:
            section_block += "Key results: " + ", ".join(s["math_objects"]) + "\n"
        if s["proof_types"]:
            pt = ", ".join(
                f"{k} ({v})" for k, v in s["proof_types"].items()
            )
            section_block += f"Proof methods: {pt}\n"
        if s["text"]:
            section_block += f"Text excerpt:\n{s['text']}\n"

    # ── mathematical chain block ──────────────────────────────────────
    chain_block = ""
    if mathematical_chain:
        chain_block = (
            "\nMATHEMATICAL SPINE (top nodes by cross-reference count):\n"
            + mathematical_chain.get("mathematical_story", "") + "\n"
        )
        for c in mathematical_chain.get("chains", []):
            chain_block += f"  - {c['name']}: {c['story']}\n"

    return f"""You have the knowledge-graph analysis of this paper: "{title}"

{parameter_block}
{chain_block}
SECTION SUMMARIES (from knowledge graph):
{section_block}

Write a complete summary calibrated to the reader profile above.
Return ONLY this JSON:
{{
  "one_liner": "one sentence the reader would remember",
  "arc1": "flowing prose 150-200 words: problem, insight, mechanism. Use key results as backbone.",
  "arc2": "flowing prose 150-200 words: evidence, assumptions, implications, limits",
  "Q1_problem": "2-3 sentences: what was broken or impossible before?",
  "Q2_insight": "2-3 sentences: what was the clever idea?",
  "Q3_mechanism": "2-3 sentences: how does it work in plain English?",
  "Q4_evidence": "2-3 sentences: does it work and how convincing is the proof?",
  "Q5_assumptions": "2-3 sentences: what needs to be true for this to hold?",
  "Q6_implications": "2-3 sentences: what does this change or make possible?",
  "Q7_limitations": "2-3 sentences: what is still missing or does not work?"
}}

Rules:
- Match language and depth strictly to the reader profile parameters.
- Prose inside arc1 and arc2. No bullet points.
- Return ONLY the JSON object."""
