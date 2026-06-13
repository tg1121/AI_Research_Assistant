"""
Detect whether a document is math-heavy or non-math.
Returns ("math" | "non-math", confidence: float 0-1).

Decision rule: math_score >= MATH_THRESHOLD → math, else non-math.
math_score = math-label hits + 0.5 × LaTeX equation markers.
"""
import re

_MATH_LABEL = re.compile(
    r'(?:^|\n)\s*\**\s*'
    r'(Theorem|Lemma|Definition|Proposition|Corollary|Proof|Conjecture|Claim)\b',
    re.IGNORECASE | re.MULTILINE,
)
_LATEX_EQ = re.compile(
    r'\$\$|\\\[|\\\(|\\begin\{(?:equation|align|gather|multline)\}'
)
# Rendered-text signals: Greek letters and math operators that survive PDF→text extraction
_UNICODE_MATH = re.compile(
    r'[∑∫∂∈∀∃∇≤≥≈≡≠±×→←↔⊂⊃∩∪∅∞√∝⊕⊗∧∨]'
    r'|[αβγδεζηθλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]'
)
_CITATION = re.compile(
    r'\((?:[A-Z][a-z]+(?:\s+(?:et\s+al\.|and|&)\s+[A-Z][a-z]+)?),?\s+\d{4}[a-z]?\)'
    r'|\b[A-Z][a-z]+\s+\(\d{4}\)',
    re.MULTILINE,
)
_ENGLISH_PHRASES = re.compile(
    r'\b(argues?|contends?|suggests?|posits?|claims?\s+that|thesis|literary|'
    r'narrative|novel|poem|rhetoric|discourse|metaphor|allegory|protagonist|'
    r'feminist|postcolonial|hermeneutic|epistemology|ontology|critique|canon)\b',
    re.IGNORECASE,
)

MATH_THRESHOLD = 5


def detect_domain(doc) -> tuple[str, float]:
    """Return (domain, confidence). domain is 'math' or 'non-math'."""
    all_text = "\n".join(s.raw_text for s in doc.sections)

    math_labels  = len(_MATH_LABEL.findall(all_text))
    latex_eqs    = len(_LATEX_EQ.findall(all_text))
    unicode_math = len(_UNICODE_MATH.findall(all_text))
    math_score   = math_labels + latex_eqs * 0.5 + unicode_math * 0.08

    citations       = len(_CITATION.findall(all_text))
    english_phrases = len(_ENGLISH_PHRASES.findall(all_text))
    english_score   = citations * 0.3 + english_phrases * 0.5

    print(f"      [detect_domain] labels={math_labels} latex_eq={latex_eqs} "
          f"unicode_math={unicode_math} → math_score={math_score:.1f} "
          f"(threshold={MATH_THRESHOLD}) | cit={citations} eng={english_phrases}")

    if math_score >= MATH_THRESHOLD:
        return "math", min(1.0, math_score / 20.0)

    return "non-math", min(1.0, english_score / 15.0)
