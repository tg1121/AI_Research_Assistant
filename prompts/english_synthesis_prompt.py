from feedback.parameters import get_parameter_block

ENGLISH_SYNTHESIS_SYSTEM = """You are a research paper summarizer. You only output valid JSON.
No explanations. No markdown. No code fences."""


def english_synthesis_prompt(
    title: str,
    section_data: list[dict],
    **params,
) -> str:
    """
    English/humanities synthesis prompt.

    Each entry in section_data has:
      title         — section heading
      keywords      — top TF-IDF terms distinctive to this section
      named_phrases — capitalized multi-word phrases (author names, theory names)
      text_sample   — 1500 chars sampled from start, middle, and end of section
    """
    parameter_block = get_parameter_block(params)

    section_block = ""
    for s in section_data:
        section_block += f"\n\n--- {s['title']} ---\n"
        if s.get("keywords"):
            section_block += "Keywords: " + ", ".join(s["keywords"]) + "\n"
        if s.get("named_phrases"):
            section_block += "Theories/names: " + ", ".join(s["named_phrases"]) + "\n"
        if s.get("text_sample"):
            section_block += f"Text:\n{s['text_sample']}\n"

    return f"""You have section-by-section analysis of this paper: "{title}"

{parameter_block}
SECTIONS:
{section_block}

Write a complete summary calibrated to the reader profile above.
Return ONLY this JSON:
{{
  "one_liner": "one sentence capturing the central argument",
  "arc1": "flowing prose 150-200 words: central argument, theoretical framework, key intervention",
  "arc2": "flowing prose 150-200 words: evidence, methodology, implications, limits",
  "Q1_problem": "2-3 sentences: what gap, question, or debate does this paper address?",
  "Q2_insight": "2-3 sentences: what is the central argument or thesis?",
  "Q3_mechanism": "2-3 sentences: how is the argument constructed — what methods or frameworks are used?",
  "Q4_evidence": "2-3 sentences: what evidence, texts, or cases does it draw on?",
  "Q5_assumptions": "2-3 sentences: what theoretical assumptions underpin the argument?",
  "Q6_implications": "2-3 sentences: what does this contribute to the field?",
  "Q7_limitations": "2-3 sentences: what is missing, contested, or unresolved?"
}}

Rules:
- Match language and depth strictly to the reader profile parameters.
- Prose inside arc1 and arc2. No bullet points.
- Return ONLY the JSON object."""
