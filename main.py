import json
import os
import sys
from ingestion.marker_parser import parse_with_marker
from pipeline.tagger import run_tagging
from pipeline.chain_builder import run_chain_builder
from pipeline.section_qa import run_section_qa
from pipeline.synthesizer import run_synthesis
from pipeline.output_cache import load_cached, save_cache

def run(input_path: str,
        reader_expertise: float = 0.0,
        scientific_knowledge: float = 0.0,
        language_complexity: float = 0.0):

    paper_id = os.path.basename(input_path).replace(".pdf", "")

    # ── cache check ────────────────────────────────────────────────
    cached = load_cached(paper_id, reader_expertise, scientific_knowledge, language_complexity)
    if cached:
        print(f"[cache hit] Loaded existing result for '{paper_id}' at this profile")
        if cached.holistic_summary:
            print(f"\nOne-liner: {cached.holistic_summary.get('one_liner', '')}")
        return

    print(f"[1/5] Ingesting: {input_path}")
    paper_id = os.path.basename(input_path).replace(".pdf", "")
    doc = parse_with_marker(input_path, paper_id)

    print(f"[2/5] Tagging {len(doc.sections)} sections")
    doc = run_tagging(doc)

    print(f"[3/5] Building mathematical chain")
    doc = run_chain_builder(doc)

    print(f"[4/5] Running section Q&A (expertise={reader_expertise:.2f}, sci={scientific_knowledge:.2f}, lang={language_complexity:.2f})")
    doc = run_section_qa(doc,
                         reader_expertise=reader_expertise,
                         scientific_knowledge=scientific_knowledge,
                         language_complexity=language_complexity)

    print(f"[5/5] Synthesizing holistic summary")
    doc = run_synthesis(doc, reader_expertise, scientific_knowledge, language_complexity)

    out_path = save_cache(doc, reader_expertise, scientific_knowledge, language_complexity)

    print(f"\n=== SUMMARY ===")
    if doc.holistic_summary:
        print(f"\nOne-liner: {doc.holistic_summary.get('one_liner', '')}")
        print(f"\nARC 1:\n{doc.holistic_summary.get('arc1', '')}")
        print(f"\nARC 2:\n{doc.holistic_summary.get('arc2', '')}")
        print(f"\nQ1: {doc.holistic_summary.get('Q1_problem', '')}")
        print(f"\nQ2: {doc.holistic_summary.get('Q2_insight', '')}")
    print(f"\nFull output saved to {out_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <pdf_path> [reader_expertise] [scientific_knowledge] [language_complexity]")
        print("  Parameters are floats 0.0-1.0. Defaults to 0.0 (plain English) if not provided.")
        sys.exit(1)

    expertise = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    sci = float(sys.argv[3]) if len(sys.argv) > 3 else expertise
    lang = float(sys.argv[4]) if len(sys.argv) > 4 else expertise

    run(sys.argv[1], expertise, sci, lang)
