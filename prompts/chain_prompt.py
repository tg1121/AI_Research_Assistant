CHAIN_SYSTEM = """You are a mathematical storyteller. You explain how equations 
in a research paper connect to form a complete argument.
Return JSON only. No preamble. No explanation outside the JSON."""

def chain_prompt(mmd_text: str, equations: list[dict]) -> str:
    eq_block = ""
    for i, eq in enumerate(equations):
        eq_block += f"[{i+1}] {eq['latex'][:150]}\n"

    return f"""This is a research paper. It contains these equations in order:

{eq_block}

Mathematical papers contain chains of equations where each equation depends on 
previous ones. Multiple such chains exist in a paper and the chains themselves 
depend on each other. Equations within a chain can be clustered if they form 
part of the same logical move.

Given these equations and the paper text below, identify the dependency chains,
cluster related equations, and narrate what each chain is doing in plain English —
showing how the chains connect to tell the complete mathematical story of the paper.

PAPER TEXT:
{mmd_text[:6000]}

Return ONLY this JSON:
{{
  "mathematical_story": "2-3 sentence plain English overview of the full mathematical argument",
  "chains": [
    {{
      "chain_id": "c0",
      "name": "short name for this chain",
      "equations": ["equation latex here", "equation latex here"],
      "story": "plain English: what this chain is doing and why it is needed",
      "depends_on": ["c1", "c2"]
    }}
  ]
}}

Rules:
- Plain English only in story fields. No symbols, no LaTeX in story text.
- depends_on lists which other chains this chain builds upon. Empty list [] if none.
- Cluster equations that form part of the same logical move into one chain.
- Return ONLY the JSON."""