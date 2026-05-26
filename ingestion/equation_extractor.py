import re

def extract_equations(mmd_text: str) -> list[dict]:
    equations = []

    display = re.findall(r'\$\$(.*?)\$\$', mmd_text, re.DOTALL)
    for eq in display:
        eq = eq.strip()
        if not eq:
            continue
        # remove all \tag{...} and whitespace, check if anything meaningful remains
        stripped = re.sub(r'\\tag\{[^}]*\}', '', eq).strip()
        if not stripped:
            continue
        # must contain at least one letter, digit, or math command
        if not re.search(r'[a-zA-Z0-9\\]', stripped):
            continue
        equations.append({
            "latex": eq,
            "type": "display"
        })

    return equations

def extract_equations_per_section(sections: list) -> dict:
    result = {}
    for section in sections:
        result[section.section_id] = extract_equations(section.raw_text)
    return result