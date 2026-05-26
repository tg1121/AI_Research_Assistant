import json

with open('outputs/test_paper_RA.json', encoding='utf-8') as f:
    doc = json.load(f)

print("=== SECTIONS ===")
for s in doc['sections']:
    print(f"\n--- {s['section_id']}: {s['title']} (role={s['role']}) ---")
    print(f"    equations: {len(s['equations'])}")
    if s['qa']:
        for q, a in s['qa'].items():
            if a and a != 'null':
                print(f"    {q}: {str(a)[:120]}")
    else:
        print("    NO QA")

print("\n=== MATHEMATICAL CHAIN ===")
chain = doc.get('mathematical_chain')
if chain:
    print(f"Story: {chain.get('mathematical_story', '')}")
    for c in chain.get('chains', []):
        print(f"\n  {c['chain_id']}: {c['name']}")
        print(f"  Story: {c['story']}")
        print(f"  Depends on: {c['depends_on']}")
else:
    print("NO CHAIN")

print("\n=== HOLISTIC SUMMARY ===")
summary = doc.get('holistic_summary')
if summary:
    for key, val in summary.items():
        print(f"\n{key}:\n{val}")