from feedback.parameters import get_parameter_block

SYNTHESIS_SYSTEM = """You are a research paper summarizer. You only output valid JSON.
No explanations. No markdown. No code fences."""

def synthesis_prompt(title: str, section_qas: list[dict],
                     mathematical_chain: dict = None,
                     **params) -> str:

    parameter_block = get_parameter_block(params)

    qa_block = ""
    for s in section_qas:
        if s.get("qa"):
            qa_block += f"\n\n--- {s['title']} ({s['role']}) ---\n"
            for q, a in s["qa"].items():
                if a and a != "null":
                    qa_block += f"{q}: {a}\n"

    chain_block = ""
    if mathematical_chain:
        chain_block = f"""
MATHEMATICAL STORY:
{mathematical_chain.get('mathematical_story', '')}

EQUATION CHAINS:
"""
        for c in mathematical_chain.get('chains', []):
            chain_block += f"- {c['name']}: {c['story']}\n"
            if c.get('depends_on'):
                chain_block += f"  (builds on: {', '.join(c['depends_on'])})\n"

    return f"""You have the section-by-section analysis of this paper: "{title}"

{parameter_block}

{chain_block}

SECTION Q&A:
{qa_block}

Write a complete summary calibrated to the reader profile above.
Return ONLY this JSON:
{{
  "one_liner": "one sentence the reader would remember",
  "arc1": "flowing prose 150-200 words: problem, insight, mechanism. Use mathematical chain as backbone.",
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