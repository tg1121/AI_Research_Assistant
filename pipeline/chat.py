"""
Chat pipeline — V8.

Replaces TF-IDF RAG with the ReAct agent planner.
Memory, learning signals, and sliding window compression kept from V7.

Flow per turn:
  1. Agent planner decides what to retrieve (up to 4 tool calls)
  2. Synthesizer generates answer from retrieved context
  3. Learning signals extracted and persisted
  4. Sliding window compression when needed
"""

import json
from pipeline.llm_client import llm_call, clean_json
from agent.planner import plan_and_retrieve
from graph.math_graph import Graph
from graph.doc_map import DocMap
from memory.store import (
    save_paper_memory, save_user_memory, build_memory_context
)
from feedback.parameters import get_parameter_block

COMPRESS_EVERY = 6
KEEP_RECENT    = 3


def _system_prompt(paper_titles: list[str],
                   memory_context: str,
                   reader_params: dict) -> str:
    param_block  = get_parameter_block(reader_params)
    memory_block = f"\n\n{memory_context}" if memory_context else ""
    if len(paper_titles) == 1:
        papers_block = (f'You are a research assistant helping a reader '
                        f'understand the paper: "{paper_titles[0]}".')
    else:
        titles_str   = "\n".join(f"  - {t}" for t in paper_titles)
        papers_block = (f"You are a research assistant helping a reader "
                        f"understand {len(paper_titles)} papers:\n{titles_str}\n"
                        f"When citing a section, mention which paper it is from.")
    return f"""{papers_block}

{param_block}{memory_block}

INSTRUCTIONS:
1. Each message begins with RETRIEVED PAPER SECTIONS — text the system pulled
   from the paper for you. Answer using ONLY that content.
2. Never say "the excerpts you provided" — the user did not provide them.
   Say "the paper states", "according to section X", etc.
3. SELF-CORRECTION: If your answer contradicts something you said earlier,
   explicitly say: "I need to correct what I said earlier — [old] is wrong;
   [new] is more accurate." Never silently change position.
4. If the answer is not in the retrieved sections, say so honestly.
   You may reason from general knowledge but label it clearly:
   "[general knowledge, not from paper]"
5. When mentioning a proof, state its type (direct, induction, or contradiction).
6. Keep explanations calibrated to the reader profile above.
"""


_EXTRACT_SYSTEM = """Extract learning signals from a conversation turn.
Return ONLY valid JSON, no markdown, no preamble.
Schema:
{
  "corrections": [],
  "self_revisions": [],
  "established_facts": [],
  "expertise_signals": [],
  "style_preferences": []
}
All arrays may be empty. One sentence max per item."""

_COMPRESS_SYSTEM = """Compress conversation turns into a dense 3-6 sentence summary.
Preserve: key facts, corrections, insights. Omit: pleasantries, repetition.
Return plain text."""


def _extract_signals(user_msg, assistant_msg, model, api_key) -> dict:
    try:
        raw = llm_call([
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user",   "content": f"User: {user_msg}\n\nAssistant: {assistant_msg}"},
        ], model=model, api_key=api_key, max_tokens=512)
        return json.loads(clean_json(raw, "signal_extraction"))
    except Exception:
        return {}


def _compress_turns(turns, model, api_key) -> str:
    transcript = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in turns)
    try:
        return llm_call([
            {"role": "system", "content": _COMPRESS_SYSTEM},
            {"role": "user",   "content": transcript},
        ], model=model, api_key=api_key, max_tokens=300)
    except Exception:
        return " | ".join(t["content"][:80] for t in turns if t["role"] == "user")


def _persist_signals(signals: dict, paper_id: str, user_id: str | None):
    if not user_id:
        return
    try:
        for c in signals.get("corrections", []):
            save_paper_memory(paper_id, user_id, "correction", c)
        for r in signals.get("self_revisions", []):
            save_paper_memory(paper_id, user_id, "self_revision", r)
        for f in signals.get("established_facts", []):
            save_paper_memory(paper_id, user_id, "established_fact", f)
        for e in signals.get("expertise_signals", []):
            save_user_memory(user_id, "expertise_signal", e)
        for s in signals.get("style_preferences", []):
            save_user_memory(user_id, "style_preference", s)
    except Exception:
        pass


def _maybe_compress(messages, paper_id, user_id, turn_number, model, api_key):
    n_turns = len(messages) // 2
    if n_turns <= COMPRESS_EVERY:
        return
    compress_n    = n_turns - KEEP_RECENT
    compress_msgs = messages[:compress_n * 2]
    keep_msgs     = messages[compress_n * 2:]
    start         = turn_number - n_turns + 1
    end           = turn_number - KEEP_RECENT
    summary       = _compress_turns(compress_msgs, model, api_key)
    if user_id:
        try:
            save_paper_memory(paper_id, user_id, "conversation_summary",
                              summary, f"{start}-{end}")
        except Exception:
            pass
    messages.clear()
    messages.extend(keep_msgs)


# ── public API ────────────────────────────────────────────────────────

def chat_turn(
    user_message: str,
    messages: list[dict],
    graphs: list[Graph],
    doc_maps: list[DocMap],
    paper_titles: list[str],
    paper_ids: list[str],
    reader_params: dict,
    model: str,
    api_key: str | None,
    turn_counter: list[int],
    user_id: str | None = None,
) -> str:
    """
    Process one user turn across one or more open papers.
    Returns the assistant reply string.
    """
    # 1. agent retrieval — run planner for each open paper
    all_context: list[str] = []
    for graph, doc_map, title in zip(graphs, doc_maps, paper_titles):
        context_blocks = plan_and_retrieve(
            user_message, graph, doc_map, model, api_key
        )
        # ── debug ─────────────────────────────────────────────────────
        print(f"\n[RETRIEVAL] paper={title!r}  {len(context_blocks)} block(s) returned")
        for i, block in enumerate(context_blocks):
            preview = block[:200].replace("\n", " ")
            print(f"  block[{i}]: {preview!r}")
        if not context_blocks:
            print("  (no context blocks — agent returned nothing)")
        # ──────────────────────────────────────────────────────────────
        if len(graphs) > 1:
            # label each paper's blocks
            labeled = [f"=== PAPER: {title} ===\n{b}" for b in context_blocks]
            all_context.extend(labeled)
        else:
            all_context.extend(context_blocks)

    rag_ctx = "\n\n".join(all_context)

    # 2. augment user message with retrieved context
    augmented = user_message
    if rag_ctx:
        augmented = f"RETRIEVED PAPER SECTIONS:\n{rag_ctx}\n\nUser question: {user_message}"

    # 3. memory context
    try:
        mem_parts = [build_memory_context(pid, user_id) for pid in paper_ids] if user_id else []
        memory_ctx = "\n\n".join(m for m in mem_parts if m)
    except Exception:
        memory_ctx = ""

    system = _system_prompt(paper_titles, memory_ctx, reader_params)

    # 4. LLM call
    call_messages = (
        [{"role": "system", "content": system}]
        + messages
        + [{"role": "user",  "content": augmented}]
    )
    reply = llm_call(call_messages, model=model, api_key=api_key, max_tokens=1024)

    # 5. update live window
    messages.append({"role": "user",      "content": user_message})
    messages.append({"role": "assistant", "content": reply})
    turn_counter[0] += 1

    # 6. learning signals (best-effort)
    signals = _extract_signals(user_message, reply, model, api_key)
    _persist_signals(signals, paper_ids[0] if paper_ids else "global", user_id)

    # 7. sliding window compression
    _maybe_compress(messages, paper_ids[0] if paper_ids else "global",
                    user_id, turn_counter[0], model, api_key)

    return reply
