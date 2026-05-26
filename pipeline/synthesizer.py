import json
from prompts.synthesis_prompt import SYNTHESIS_SYSTEM, synthesis_prompt
from ingestion.document import Document
from pipeline.llm_client import llm_call, clean_json

KEY_QUESTIONS = ["Q1_problem", "Q2_insight", "Q3_mechanism", "Q6_implications", "Q7_limitations"]

def _compress_section_qa(section_qas: list[dict]) -> list[dict]:
    compressed = []
    for s in section_qas:
        if not s.get("qa"):
            continue
        if s.get("role") not in ["intro", "method", "results", "discussion", "limitations"]:
            continue
        qa_compressed = {}
        for q in KEY_QUESTIONS:
            answer = s["qa"].get(q)
            if answer and answer != "null":
                qa_compressed[q] = answer[:150]
        if qa_compressed:
            compressed.append({"title": s["title"], "role": s["role"], "qa": qa_compressed})
    return compressed

def run_synthesis(doc: Document,
                  reader_expertise: float = 0.0,
                  scientific_knowledge: float = 0.0,
                  language_complexity: float = 0.0,
                  model: str = "groq/llama-3.3-70b-versatile",
                  api_key: str | None = None) -> Document:

    section_data = [
        {"title": s.title, "role": s.role, "qa": s.qa}
        for s in doc.sections
    ]
    compressed = _compress_section_qa(section_data)

    raw = llm_call([
        {"role": "system", "content": SYNTHESIS_SYSTEM},
        {"role": "user", "content": synthesis_prompt(
            doc.title, compressed, doc.mathematical_chain,
            reader_expertise=reader_expertise,
            scientific_knowledge=scientific_knowledge,
            language_complexity=language_complexity,
        )}
    ], model=model, api_key=api_key, max_tokens=3000)

    raw = clean_json(raw, "synthesizer")
    doc.holistic_summary = json.loads(raw)
    return doc
