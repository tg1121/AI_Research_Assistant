MERGE_SYSTEM = """You are merging partial answers about a research paper section.
You only output valid JSON. No explanations. No markdown. No code fences."""

QUESTIONS = [
    "Q1_problem", "Q2_insight", "Q3_mechanism",
    "Q4_evidence", "Q5_assumptions", "Q6_implications", "Q7_limitations"
]

def merge_prompt(section_title: str, chunk_answers: list[dict]) -> str:
    """
    chunk_answers: list of Q&A dicts, one per chunk.
    Each dict has the 7 question keys with string or null values.
    """
    blocks = []
    for i, qa in enumerate(chunk_answers):
        lines = [f"--- Chunk {i+1} ---"]
        for q in QUESTIONS:
            val = qa.get(q)
            if val and val != "null":
                lines.append(f"{q}: {val}")
        blocks.append("\n".join(lines))

    chunks_text = "\n\n".join(blocks)

    q_keys = "\n".join([f'  "{q}": "merged answer or null"' for q in QUESTIONS])

    return f"""These are partial answers about the '{section_title}' section of a research paper.
Each chunk covers a different part of the same section.

{chunks_text}

Merge these into one coherent answer per question.
Rules:
- Combine information from all chunks — do not drop unique points
- Remove repetition — if two chunks say the same thing, say it once
- Keep answers to 2-4 sentences
- If no chunk answered a question, write null
- Match the language style of the input answers

Return ONLY this JSON:
{{
{q_keys}
}}"""
