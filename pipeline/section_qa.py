import json
from prompts.section_prompt import SECTION_SYSTEM, section_prompt
from prompts.merge_prompt import MERGE_SYSTEM, merge_prompt
from ingestion.document import Document
from pipeline.llm_client import llm_call, clean_json, DailyTokenLimitError, InvalidAPIKeyError

CHUNK_CHARS = 4000
CHUNK_OVERLAP = 300

QUESTIONS = [
    "Q1_problem", "Q2_insight", "Q3_mechanism",
    "Q4_evidence", "Q5_assumptions", "Q6_implications", "Q7_limitations"
]


def _chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    chunks = []
    pos = 0
    while pos < len(text):
        end = pos + CHUNK_CHARS
        boundary = text.rfind("\n\n", pos + CHUNK_CHARS - 300, end)
        if boundary != -1:
            end = boundary
        chunks.append(text[pos:end].strip())
        pos = end - CHUNK_OVERLAP
        if pos >= len(text):
            break
    return [c for c in chunks if c]


def _parse(raw: str | None, context: str = "") -> dict:
    raw = clean_json(raw, context)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "parse_failed", "raw": raw}


def _call_qa(section_title, chunk_text, equations, chunk_idx, total_chunks,
             reader_expertise, scientific_knowledge, language_complexity,
             model, api_key) -> dict:
    position_note = ""
    if total_chunks > 1:
        position_note = f"[Chunk {chunk_idx + 1} of {total_chunks} — answer only from this excerpt]"

    raw = llm_call([
        {"role": "system", "content": SECTION_SYSTEM},
        {"role": "user", "content": section_prompt(
            section_title, chunk_text, equations,
            reader_expertise=reader_expertise,
            scientific_knowledge=scientific_knowledge,
            language_complexity=language_complexity,
            position_note=position_note,
        )}
    ], model=model, api_key=api_key)
    return _parse(raw)


def _merge_chunk_answers(section_title, chunk_results, model, api_key) -> dict:
    if len(chunk_results) == 1:
        return chunk_results[0]
    valid = [r for r in chunk_results if "error" not in r]
    if not valid:
        return chunk_results[0]
    if len(valid) == 1:
        return valid[0]
    raw = llm_call([
        {"role": "system", "content": MERGE_SYSTEM},
        {"role": "user", "content": merge_prompt(section_title, valid)}
    ], model=model, api_key=api_key)
    return _parse(raw) or valid[0]


def run_section_qa(doc: Document,
                   reader_expertise: float = 0.0,
                   scientific_knowledge: float = 0.0,
                   language_complexity: float = 0.0,
                   model: str = "groq/llama-3.3-70b-versatile",
                   api_key: str | None = None) -> Document:

    for section in doc.sections:
        if not section.raw_text.strip():
            continue

        eq_list = [{"role": e.role, "raw_latex": e.raw_latex} for e in section.equations]
        chunks = _chunk_text(section.raw_text)

        if len(chunks) > 1:
            print(f"    {section.section_id} '{section.title[:40]}' → {len(chunks)} chunks")

        chunk_results = [
            _call_qa(section.title, chunk, eq_list, i, len(chunks),
                     reader_expertise, scientific_knowledge, language_complexity,
                     model, api_key)
            for i, chunk in enumerate(chunks)
        ]
        section.qa = _merge_chunk_answers(section.title, chunk_results, model, api_key)

    return doc
