"""
Memory store — Supabase persistence for per-paper and global user memory.

Two tables:
  memory_paper  — corrections, self-revisions, established facts,
                  conversation summaries (compressed sliding window)
  memory_user   — expertise signals and style preferences (cross-paper)

Raw chat messages are NEVER stored here. The in-session message list
lives in st.session_state. Only distilled knowledge lands in Supabase.
"""

import os
from supabase import create_client

_client = None

def _db():
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY env vars must be set.")
        _client = create_client(url, key)
    return _client


# ── paper memory ──────────────────────────────────────────────────────

PAPER_TYPES = {"correction", "self_revision", "established_fact", "conversation_summary"}

def save_paper_memory(paper_id: str, type_: str, content: str,
                      turn_range: str | None = None) -> dict:
    """Write one distilled memory item for a specific paper."""
    assert type_ in PAPER_TYPES, f"Unknown paper memory type: {type_!r}"
    row = {"paper_id": paper_id, "type": type_, "content": content}
    if turn_range:
        row["turn_range"] = turn_range
    result = _db().table("memory_paper").insert(row).execute()
    return result.data[0]


def load_paper_memory(paper_id: str) -> list[dict]:
    """Load all memory for a paper, ordered oldest-first."""
    result = (
        _db().table("memory_paper")
        .select("*")
        .eq("paper_id", paper_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def delete_paper_memory(paper_id: str, type_: str | None = None):
    """Delete memory for a paper. Optionally filter by type."""
    q = _db().table("memory_paper").delete().eq("paper_id", paper_id)
    if type_:
        q = q.eq("type", type_)
    q.execute()


# ── user memory ───────────────────────────────────────────────────────

USER_TYPES = {"expertise_signal", "style_preference"}

def save_user_memory(type_: str, content: str) -> dict:
    """Write one global user memory item."""
    assert type_ in USER_TYPES, f"Unknown user memory type: {type_!r}"
    result = _db().table("memory_user").insert(
        {"type": type_, "content": content}
    ).execute()
    return result.data[0]


def load_user_memory() -> list[dict]:
    """Load all global user memory, ordered oldest-first."""
    result = (
        _db().table("memory_user")
        .select("*")
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


# ── context builder ───────────────────────────────────────────────────

def build_memory_context(paper_id: str) -> str:
    """
    Assemble all persisted memory into a single context block
    to inject at the top of the chat system prompt.
    Returns empty string if no memory exists yet.
    """
    user_rows  = load_user_memory()
    paper_rows = load_paper_memory(paper_id)

    if not user_rows and not paper_rows:
        return ""

    lines = ["=== PERSISTENT MEMORY (from previous sessions) ==="]

    if user_rows:
        lines.append("\n[About this user — applies to all papers]")
        for r in user_rows:
            lines.append(f"  [{r['type']}] {r['content']}")

    if paper_rows:
        lines.append("\n[About this paper]")
        for r in paper_rows:
            tag = r["type"]
            if tag == "conversation_summary":
                turns = f" (turns {r['turn_range']})" if r.get("turn_range") else ""
                lines.append(f"  [summary{turns}] {r['content']}")
            else:
                lines.append(f"  [{tag}] {r['content']}")

    lines.append("=== END MEMORY ===")
    return "\n".join(lines)
