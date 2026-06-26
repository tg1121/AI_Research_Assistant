import json
from prompts.chain_prompt import CHAIN_SYSTEM, chain_prompt
from ingestion.document import Document
from ingestion.equation_extractor import extract_equations
from pipeline.llm_client import llm_call, clean_json

def run_chain_builder(doc: Document,
                      model: str = "openrouter/openai/gpt-oss-120b:free",
                      api_key: str | None = None) -> Document:
    all_equations = extract_equations(doc.raw_markdown)

    if not all_equations:
        print("  No equations found — skipping chain builder")
        doc.mathematical_chain = None
        return doc

    print(f"  Building mathematical chain from {len(all_equations)} equations...")

    raw = llm_call([
        {"role": "system", "content": CHAIN_SYSTEM},
        {"role": "user", "content": chain_prompt(doc.raw_markdown, all_equations)}
    ], model=model, api_key=api_key, max_tokens=2048)

    raw = clean_json(raw, "chain_builder")
    print(f"\n  DEBUG chain raw:\n{raw[:400]}\n")

    try:
        data = json.loads(raw)
        doc.mathematical_chain = data
        print(f"  Chain built: {len(data.get('chains', []))} chains found")
    except json.JSONDecodeError as e:
        print(f"  WARNING: chain JSON parse failed: {e}")
        doc.mathematical_chain = None

    return doc
