from feedback.parameters import get_parameter_block

SECTION_SYSTEM = """You are explaining a section of a research paper to a reader.
Calibrate your language and depth strictly to the reader profile you will receive.
Return JSON only. No preamble."""

QUESTIONS = [
    "Q1_problem",
    "Q2_insight",
    "Q3_mechanism",
    "Q4_evidence",
    "Q5_assumptions",
    "Q6_implications",
    "Q7_limitations"
]

Q_DESCRIPTIONS = {
    "Q1_problem": "What was broken or impossible before this section's contribution?",
    "Q2_insight": "What was the clever idea or shift in perspective in this section?",
    "Q3_mechanism": "How does the method or idea in this section actually work — described like a story, no symbols?",
    "Q4_evidence": "What evidence or results does this section provide, and how convincing is it?",
    "Q5_assumptions": "What needs to be true for this section's claims to hold?",
    "Q6_implications": "What does this section make possible or change?",
    "Q7_limitations": "What does this section not address or where does it fall short?"
}

# How to calibrate language based on reader profile
_CALIBRATION_GUIDE = """
Language calibration rules (apply strictly):
- scientific_knowledge < 0.3: replace ALL math/symbols with plain analogies; no field jargon without instant explanation
- scientific_knowledge 0.3-0.7: explain key equations in words alongside them; define field terms on first use
- scientific_knowledge > 0.7: use precise technical language; include equation references; assume field literacy
- language_complexity < 0.3: short sentences, active voice, concrete examples; a curious 16-year-old should follow
- language_complexity 0.3-0.7: mixed prose; some complex sentences allowed; graduate student level
- language_complexity > 0.7: dense academic prose acceptable; assume reader comfortable with abstraction
"""

def section_prompt(section_title: str, section_text: str, equations: list,
                   reader_expertise: float = 0.0,
                   scientific_knowledge: float = 0.0,
                   language_complexity: float = 0.0,
                   position_note: str = "") -> str:

    params = {
        "reader_expertise": reader_expertise,
        "scientific_knowledge": scientific_knowledge,
        "language_complexity": language_complexity,
    }
    parameter_block = get_parameter_block(params)

    eq_block = "\n".join(
        [f"- [{e['role']}]: {e['raw_latex']}" for e in equations]
    ) if equations else "None"

    q_block = "\n".join(
        [f'"{q}": "{Q_DESCRIPTIONS[q]}"' for q in QUESTIONS]
    )

    position_line = f"\n{position_note}" if position_note else ""

    return f"""This is the '{section_title}' section of a research paper.{position_line}

{parameter_block}
{_CALIBRATION_GUIDE}

EQUATIONS IN THIS SECTION (understand their meaning, do not reproduce them):
{eq_block}

SECTION TEXT:
{section_text}

Answer each question below about this section only.
If a question is not relevant to this section, write null.
Return ONLY this JSON:

{{
  {q_block.replace(': "', ': "answer here or null — ')}
}}

Rules:
- Match language and depth EXACTLY to the reader profile parameters above.
- Answers should be 2-4 sentences each. Null if genuinely not applicable.
- Return ONLY the JSON object."""
