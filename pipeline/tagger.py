import json
from prompts.tag_prompt import TAG_SYSTEM, tag_prompt
from ingestion.document import Document, Equation
from ingestion.equation_extractor import extract_equations_per_section
from pipeline.llm_client import llm_call, clean_json

def run_tagging(doc: Document,
                model: str = "groq/llama-3.3-70b-versatile",
                api_key: str | None = None) -> Document:
    eq_map = extract_equations_per_section(doc.sections)
    sections_data = [
        {"id": s.section_id, "title": s.title, "equations": eq_map.get(s.section_id, [])}
        for s in doc.sections
    ]

    raw = llm_call([
        {"role": "system", "content": TAG_SYSTEM},
        {"role": "user", "content": tag_prompt(sections_data)}
    ], model=model, api_key=api_key, max_tokens=2048)

    raw = clean_json(raw, "tagger")
    print(f"\nDEBUG tagger raw:\n{raw[:400]}\n")

    try:
        data = json.loads(raw)
        tag_map = {s["section_id"]: s for s in data["sections"]}
        for section in doc.sections:
            if section.section_id in tag_map:
                tagged = tag_map[section.section_id]
                section.role = tagged.get("role")
                section.equations = [
                    Equation(raw_latex=e["raw_latex"], role=e.get("role"), section_id=section.section_id)
                    for e in tagged.get("equations", [])
                ]
        print("Tagging results:")
        for s in doc.sections:
            print(f"  {s.section_id}: '{s.title}' → role={s.role}, equations={len(s.equations)}")
    except json.JSONDecodeError as e:
        print(f"WARNING: JSON parse failed: {e}")

    return doc
