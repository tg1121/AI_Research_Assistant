import json
import os
import sys

QUESTIONS = ["Q1_problem", "Q2_insight", "Q3_mechanism",
             "Q4_evidence", "Q5_assumptions", "Q6_implications", "Q7_limitations"]

def evaluate(paper_id: str):
    gt_path = f"eval/ground_truth/{paper_id}.json"
    out_path = f"outputs/{paper_id}.json"

    if not os.path.exists(gt_path):
        print(f"No ground truth found at {gt_path}")
        return
    if not os.path.exists(out_path):
        print(f"No pipeline output found at {out_path}")
        return

    with open(gt_path, encoding="utf-8") as f:
        gt = json.load(f)
    with open(out_path, encoding="utf-8") as f:
        output = json.load(f)

    summary = output.get("holistic_summary", {})
    chain = output.get("mathematical_chain", {})

    print(f"\n=== EVAL: {paper_id} ===")
    print(f"\nONE-LINER:\n  {summary.get('one_liner', '')}")

    print(f"\nMATHEMATICAL STORY:\n  {chain.get('mathematical_story', 'MISSING')}")

    print(f"\nCHAINS:")
    for c in chain.get("chains", []):
        print(f"  {c['chain_id']}: {c['name']} → {c['story'][:100]}")

    print(f"\n{'='*60}")
    print("QUESTION COMPARISON")
    print('='*60)

    for q in QUESTIONS:
        expected = gt.get(q, "NOT IN GROUND TRUTH")
        got = summary.get(q, "MISSING FROM PIPELINE")
        print(f"\n--- {q} ---")
        print(f"EXPECTED : {expected}")
        print(f"PIPELINE : {got}")
        print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python eval/runner.py <paper_id>")
        sys.exit(1)
    evaluate(sys.argv[1])