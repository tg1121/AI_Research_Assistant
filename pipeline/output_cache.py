"""
Output cache — saves and loads pipeline results keyed by paper_id + reader profile + model.

Cache strategy:
  - Local (ADMIN_MODE=true) → outputs/ directory as JSON files
  - Deployed               → Supabase 'output_cache' table

Profile is bucketed to 1 decimal place so minor slider jitter doesn't produce cache misses.
"""

import json
import os
import re
from ingestion.document import Document
from graph.math_graph import Graph

OUTPUTS_DIR = "outputs"
_IS_LOCAL   = os.environ.get("ADMIN_MODE", "").lower() == "true"

# ── Supabase client (deployed only) ──────────────────────────────────
_sb_client = None

def _db():
    global _sb_client
    if _sb_client is None:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY env vars must be set.")
        _sb_client = create_client(url, key)
    return _sb_client

# ── Key helpers ───────────────────────────────────────────────────────

def _model_slug(model: str) -> str:
    parts = model.split("/", 1)
    slug  = parts[-1]
    slug  = re.sub(r"[^a-zA-Z0-9.\-]", "-", slug)
    slug  = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "unknown-model"

def _profile_key(reader_expertise: float,
                 scientific_knowledge: float,
                 language_complexity: float) -> str:
    e = round(reader_expertise, 1)
    s = round(scientific_knowledge, 1)
    l = round(language_complexity, 1)
    return f"e{e}_s{s}_l{l}"

def _cache_key(paper_id: str, profile_key: str, model: str) -> str:
    return f"{paper_id}__{profile_key}__{_model_slug(model)}" if model else f"{paper_id}__{profile_key}"

def cache_path(paper_id, reader_expertise, scientific_knowledge, language_complexity, model=""):
    key = _profile_key(reader_expertise, scientific_knowledge, language_complexity)
    if model:
        return os.path.join(OUTPUTS_DIR, f"{paper_id}__{key}__{_model_slug(model)}.json")
    return os.path.join(OUTPUTS_DIR, f"{paper_id}__{key}.json")

# ── Load ──────────────────────────────────────────────────────────────

def load_cached(paper_id, reader_expertise, scientific_knowledge, language_complexity, model=""):
    profile = _profile_key(reader_expertise, scientific_knowledge, language_complexity)
    key     = _cache_key(paper_id, profile, model)

    if _IS_LOCAL:
        path = cache_path(paper_id, reader_expertise, scientific_knowledge, language_complexity, model)
        if not os.path.exists(path):
            return None
        print(f"  [local cache hit] {path}")
        with open(path, encoding="utf-8") as f:
            return Document.model_validate(json.load(f))

    # Supabase
    try:
        result = (
            _db().table("output_cache")
            .select("doc_json")
            .eq("cache_key", key)
            .limit(1)
            .execute()
        )
        if result.data:
            print(f"  [supabase cache hit] {key}")
            return Document.model_validate(json.loads(result.data[0]["doc_json"]))
    except Exception as e:
        print(f"  [cache read failed] {e}")
    return None

# ── Save ──────────────────────────────────────────────────────────────

def save_cache(doc, reader_expertise, scientific_knowledge, language_complexity, model=""):
    profile = _profile_key(reader_expertise, scientific_knowledge, language_complexity)
    key     = _cache_key(doc.paper_id, profile, model)

    if _IS_LOCAL:
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        path = cache_path(doc.paper_id, reader_expertise, scientific_knowledge, language_complexity, model)
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc.model_dump_json(indent=2))
        print(f"  [local cache saved] {path}")
        return path

    # Supabase
    try:
        _db().table("output_cache").upsert({
            "cache_key": key,
            "paper_id":  doc.paper_id,
            "doc_json":  doc.model_dump_json(),
        }).execute()
        print(f"  [supabase cache saved] {key}")
    except Exception as e:
        print(f"  [cache save failed] {e}")
    return key

# ── Graph cache (math papers only, keyed by paper_id alone) ──────────

def save_graph(paper_id: str, graph: Graph) -> None:
    graph_json = graph.to_json()
    if _IS_LOCAL:
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        path = os.path.join(OUTPUTS_DIR, f"{paper_id}__graph.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(graph_json)
        print(f"  [local graph saved] {path}")
        return
    try:
        _db().table("output_cache").upsert({
            "cache_key": f"{paper_id}__graph",
            "paper_id":  paper_id,
            "doc_json":  graph_json,
        }).execute()
        print(f"  [supabase graph saved] {paper_id}__graph")
    except Exception as e:
        print(f"  [graph save failed] {e}")


def load_graph(paper_id: str) -> Graph | None:
    if _IS_LOCAL:
        path = os.path.join(OUTPUTS_DIR, f"{paper_id}__graph.json")
        if not os.path.exists(path):
            return None
        print(f"  [local graph hit] {path}")
        with open(path, encoding="utf-8") as f:
            return Graph.from_json(f.read())
    try:
        result = (
            _db().table("output_cache")
            .select("doc_json")
            .eq("cache_key", f"{paper_id}__graph")
            .limit(1)
            .execute()
        )
        if result.data:
            print(f"  [supabase graph hit] {paper_id}__graph")
            return Graph.from_json(result.data[0]["doc_json"])
    except Exception as e:
        print(f"  [graph load failed] {e}")
    return None


# ── Delete all cached data for a paper ───────────────────────────────

def delete_paper_cache(paper_id: str) -> None:
    if _IS_LOCAL:
        if os.path.exists(OUTPUTS_DIR):
            prefix = f"{paper_id}__"
            for fname in os.listdir(OUTPUTS_DIR):
                if fname.startswith(prefix) and fname.endswith(".json"):
                    try:
                        os.remove(os.path.join(OUTPUTS_DIR, fname))
                    except OSError:
                        pass
        return
    try:
        _db().table("output_cache").delete().eq("paper_id", paper_id).execute()
    except Exception as e:
        print(f"  [cache delete failed] {e}")


# ── List cached profiles ──────────────────────────────────────────────

def list_cached_profiles(paper_id: str) -> list[dict]:
    if _IS_LOCAL:
        if not os.path.exists(OUTPUTS_DIR):
            return []
        profiles = []
        prefix = f"{paper_id}__"
        for fname in sorted(os.listdir(OUTPUTS_DIR)):
            if fname.startswith(prefix) and fname.endswith(".json"):
                inner = fname[len(prefix):-5]
                if inner == "graph":
                    continue
                try:
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

    # Supabase
    try:
        result = (
            _db().table("output_cache")
            .select("cache_key")
            .eq("paper_id", paper_id)
            .execute()
        )
        profiles = []
        for row in (result.data or []):
            key = row["cache_key"]
            inner = key[len(paper_id) + 2:]  # strip "paper_id__"
            if inner == "graph":
                continue
            try:
                if "__" in inner:
                    profile_part, model_slug = inner.split("__", 1)
                else:
                    profile_part, model_slug = inner, ""
                tokens = profile_part.split("_")
                parsed = {}
                for t in tokens:
                    parsed[t[0]] = float(t[1:])
                profiles.append({
                    "file":                 key,
                    "reader_expertise":     parsed.get("e", 0.0),
                    "scientific_knowledge": parsed.get("s", 0.0),
                    "language_complexity":  parsed.get("l", 0.0),
                    "model_slug":           model_slug,
                })
            except Exception:
                pass
        return profiles
    except Exception as e:
        print(f"  [list profiles failed] {e}")
        return []
