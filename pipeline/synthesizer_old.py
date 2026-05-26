import json
from groq import Groq
from prompts.synthesis_prompt import SYNTHESIS_SYSTEM, synthesis_prompt
from ingestion.document import Document

client = Groq()

# questions most important for holistic synthesis
KEY_QUESTIONS = ["Q1_problem", "Q2_insight", "Q3_mechanism", "Q6_implications", "Q7_limitations"]

def _compress_section_qa(section_qas: list[dict]) -> list[dict]:
    """Keep only key questions and truncate answers to reduce token count."""
    compressed = []
    for s in section_qas:
        if not s.get("qa"):
            continue
        # only include sections with meaningful roles
        if s.get("role") not in ["intro", "method", "results", "discussion", "limitations"]:
            continue
        qa_compressed = {}
        for q in KEY_QUESTIONS:
            answer = s["qa"].get(q)
            if answer and answer != "null":
                # truncate each answer to 150 chars
                qa_compressed[q] = answer[:150]
        if qa_compressed:
            compressed.append({
                "title": s["title"],
                "role": s["role"],
                "qa": qa_compressed
            })
    return compressed

def run_synthesis(doc: Document,
                  reader_expertise: float = 0.0,
                  scientific_knowledge: float = 0.0,
                  language_complexity: float = 0.0) -> Document:

    section_data = [
        {"title": s.title, "role": s.role, "qa": s.qa}
        for s in doc.sections
    ]

    compressed = _compress_section_qa(section_data)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        max_tokens=3000,
        messages=[
            {"role": "system", "content": SYNTHESIS_SYSTEM},
            {"role": "user", "content": synthesis_prompt(
                doc.title,
                compressed,
                doc.mathematical_chain,
                reader_expertise,
                scientific_knowledge,
                language_complexity
            )}
        ]
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    doc.holistic_summary = json.loads(raw)
    return doc