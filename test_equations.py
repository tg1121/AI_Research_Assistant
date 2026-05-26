from ingestion.equation_extractor import extract_equations

with open('marker_output.md', encoding='utf-8') as f:
    md = f.read()

equations = extract_equations(md)
print(f"EQUATIONS FOUND: {len(equations)}\n")
for i, eq in enumerate(equations):
    latex = eq['latex'][:80]
    print(f"[{i+1}] type={eq['type']}")
    print(f"     latex={latex}")
    print()