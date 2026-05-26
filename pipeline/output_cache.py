"""
Output cache — saves and loads pipeline results keyed by paper_id + reader profile + model.

Profile is bucketed to 1 decimal place so minor slider jitter (0.501 vs 0.499)
doesn't produce cache misses. The cache lives in outputs/ as:

    outputs/<paper_id>__e<expertise>_s<sci>_l<lang>__<model_slug>.json

e.g. outputs/Thesis-2010110690__e0.0_s0.0_l0.0__groq-llama-3.3-70b-versatile.json

Model slug strips the provider prefix and replaces unsafe filename chars with '-'.
"""

import json
import os
import re
from ingestion.document import Document

OUTPUTS_DIR = "outputs"


def _model_slug(model: str) -> str:
    """
    Turn a full litellm model string into a safe filename component.
    'openrouter/google/gemma-4-26b:free' -> 'google-gemma-4-26b-free'
    'groq/llama-3.3-70b-versatile'       -> 'llama-3.3-70b-versatile'
    """
    # drop the provider prefix (everything up to and including the first '/')
    parts = model.split("/", 1)
    slug = parts[-1]  # keep everything after the first slash (or the whole string if no slash)
    # replace any character that's not alphanumeric, dash, or dot with a dash
    slug = re.sub(r"[^a-zA-Z0-9.\-]", "-", slug)
    # collapse multiple dashes
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "unknown-model"


def _profile_key(reader_expertise: float,
                 scientific_knowledge: float,
                 language_complexity: float) -> str:
    e = round(reader_expertise, 1)
    s = round(scientific_knowledge, 1)
    l = round(language_complexity, 1)
    return f"e{e}_s{s}_l{l}"


def cache_path(paper_id: str,
               reader_expertise: float,
               scientific_knowledge: float,
               language_complexity: float,
               model: str = "") -> str:
    key = _profile_key(reader_expertise, scientific_knowledge, language_complexity)
    if model:
        return os.path.join(OUTPUTS_DIR, f"{paper_id}__{key}__{_model_slug(model)}.json")
    # legacy fallback (no model in filename)
    return os.path.join(OUTPUTS_DIR, f"{paper_id}__{key}.json")


def load_cached(paper_id: str,
                reader_expertise: float,
                scientific_knowledge: float,
                language_complexity: float,
                model: str = ""):
    """Return a Document if a cached result exists for this paper + profile + model, else None."""
    path = cache_path(paper_id, reader_expertise, scientific_knowledge, language_complexity, model)
    if not os.path.exists(path):
        return None
    print(f"  [cache hit] Loading {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return Document.model_validate(data)


def save_cache(doc: Document,
               reader_expertise: float,
               scientific_knowledge: float,
               language_complexity: float,
               model: str = "") -> str:
    """Save doc to cache. Returns the path written."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    path = cache_path(doc.paper_id, reader_expertise, scientific_knowledge, language_complexity, model)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc.model_dump_json(indent=2))
    print(f"  [cache saved] {path}")
    return path


def list_cached_profiles(paper_id: str) -> list[dict]:
    """Return all cached profiles for a given paper_id as a list of dicts."""
    if not os.path.exists(OUTPUTS_DIR):
        return []
    profiles = []
    prefix = f"{paper_id}__"
    for fname in sorted(os.listdir(OUTPUTS_DIR)):
        if fname.startswith(prefix) and fname.endswith(".json"):
            inner = fname[len(prefix):-5]  # e.g. "e0.5_s0.3_l0.7__llama-3.3-70b"
            try:
                # split off optional model slug
                if "__" in inner:
                    profile_part, model_slug = inner.split("__", 1)
                else:
                    profile_part, model_slug = inner, ""

                tokens = profile_part.split("_")
                parsed = {}
                for t in tokens:
                    parsed[t[0]] = float(t[1:])

                profiles.append({
                    "file":                 fname,
                    "reader_expertise":     parsed.get("e", 0.0),
                    "scientific_knowledge": parsed.get("s", 0.0),
                    "language_complexity":  parsed.get("l", 0.0),
                    "model_slug":           model_slug,
                })
            except Exception:
                pass
    return profiles
