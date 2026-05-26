TAG_SYSTEM = """You are a structured data extractor. You only output valid JSON.
Never explain. Never add text before or after the JSON object."""

def tag_prompt(sections: list) -> str:
    """
    sections: list of {id, title, equations: [{latex, type}]}
    """
    sections_text = ""
    for s in sections:
        eq_lines = "\n".join([f"    - {e['latex'][:120]}" for e in s['equations']])
        eq_block = eq_lines if eq_lines else "    none"
        sections_text += f"""
Section {s['id']}: {s['title']}
Equations:
{eq_block}
"""

    return f"""Classify each section and tag each equation by its role.

{sections_text}

Return ONLY this JSON:
{{
  "sections": [
    {{
      "section_id": "s0",
      "title": "title here",
      "role": "intro",
      "equations": [
        {{
          "raw_latex": "latex here",
          "role": "definition"
        }}
      ]
    }}
  ]
}}

Section role: intro | method | results | limitations | discussion | other
Equation role: definition | objective | metric | bound | approximation | other
Return ONLY the JSON. Start with {{ end with }}."""