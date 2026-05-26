"""
Parameter registry — define all parameters here.
Each parameter has a name, description, range, and default value.
New parameters can be added here without touching any other file.
"""

PARAMETER_REGISTRY = {
    "reader_expertise": {
        "label": "Reader Expertise",
        "description": "0 = no scientific background, 1 = domain expert",
        "min": 0.0,
        "max": 1.0,
        "default": 0.0,
        "affects": ["scientific_knowledge", "language_complexity"],  # drives these when linked
    },
    "scientific_knowledge": {
        "label": "Scientific Knowledge",
        "description": "0 = replace all math with analogies, 1 = full mathematical precision",
        "min": 0.0,
        "max": 1.0,
        "default": 0.0,
        "affects": [],
    },
    "language_complexity": {
        "label": "Language Complexity",
        "description": "0 = simplest possible sentences, 1 = dense academic prose",
        "min": 0.0,
        "max": 1.0,
        "default": 0.0,
        "affects": [],
    },
}

def get_defaults() -> dict:
    return {k: v["default"] for k, v in PARAMETER_REGISTRY.items()}

def get_parameter_block(params: dict) -> str:
    """
    Generate the parameter instruction block for any prompt.
    Pass a dict of {param_name: value}.
    New parameters automatically appear here without prompt changes.
    """
    lines = ["READER PROFILE (all parameters on a scale of 0.0 to 1.0):"]
    for name, value in params.items():
        if name in PARAMETER_REGISTRY:
            reg = PARAMETER_REGISTRY[name]
            lines.append(
                f"- {name}: {value:.2f} — {reg['description']}"
            )
    lines.append(
        "\nCalibrate every sentence of your response to these exact parameter values."
    )
    return "\n".join(lines)