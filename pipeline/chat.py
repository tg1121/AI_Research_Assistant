"""
Chat pipeline — conversational Q&A over a paper.

Features:
  - RAG: retrieves relevant sections per query
  - Memory injection: loads persisted memory from Supabase at start
  - Self-correction: LLM is prompted to detect and flag conflicts
    with its own earlier answers
  - Sliding window: every COMPRESS_EVERY turns, oldest turns are
    compressed into a summary stored in Supabase; live window stays lean
  - Learning: after each turn, extracts corrections, expertise signals,
    and style preferences and writes them to Supabase
"""

import json
from pipeline.llm_client import llm_call, clean_json
from pipeline.rag import SectionIndex, build_rag_context
from memory.store import (
    save_paper_memory, save_user_memory, build_memory_context
)
from feedback.parameters import get_parameter_block

# Number of live turns to keep before compressing the oldest half
COMPRESS_EVERY = 6   # compress when window exceeds this
KEEP_RECENT    = 3   # always keep this many recent turns uncompressed


# ── system prompt ─────────────────────────────────────────────────────

def _system_prompt(paper_titles: list[str],
                   memory_context: str,
                   reader_params: dict) -> str:
    param_block = get_parameter_block(reader_params)
    memory_block = f"\n\n{memory_context}" if memory_context else ""
    if len(paper_titles) == 1:
        papers_block = f'You are a research assistant helping a reader understand the paper: "{paper_titles[0]}".'
    else:
        titles_str = "\n".join(f"  - {t}" for t in paper_titles)
        papers_block = f"You are a research assistant helping a reader understand {len(paper_titles)} papers:\n{titles_str}\nWhen citing a section, mention which paper it is from."
    return f"""{papers_block}

{param_block}{memory_block}

INSTRUCTIONS:
1. Answer based on the paper sections provided in each message.
2. SELF-CORRECTION: Before finalising your answer, check whether it
   contradicts anything you said earlier in this conversation. If it does,
   explicitly say: "I need to correct what I said earlier — [old claim] is
   wrong; [new claim] is more accurate." Never silently change position.
3. If the answer isn't in the retrieved sections, say so honestly rather
   than guessing. You may reason from general knowledge but mark it clearly
   as "[general knowledge, not from paper]".
4. Keep your explanation style consistent with the reader profile above.
5. Be concise — the reader can ask follow-ups.
"""


# ── extraction prompt ─────────────────────────────────────────────────

_EXTRACT_SYSTEM = """You extract learning signals from a conversation turn.
Return ONLY valid JSON, no markdown fences, no extra text.

Schema:
{
  "corrections": [],        // strings: facts the user explicitly corrected
  "self_revisions": [],     // strings: facts the assistant revised itself
  "established_facts": [],  // strings: claims both parties agreed on
  "expertise_signals": [],  // strings: evidence of user's domain knowledge level
  "style_preferences": []   // strings: preferences about explanation style
}

All arrays may be empty. Keep each string concise (one sentence max).
"""

def _extract_signals(user_msg: str, assistant_msg: str,
                     model: str, api_key: str | None) -> dict:
    """Extract learning signals from one conversation turn."""
    prompt = f"User: {user_msg}\n\nAssistant: {assistant_msg}"
    try:
        raw = llm_call(
            [{"role": "system", "content": _EXTRACT_SYSTEM},
             {"role": "user",   "content": prompt}],
            model=model, api_key=api_key, max_tokens=512,
        )
        return json.loads(clean_json(raw, "signal_extraction"))
    except Exception:
        return {}  # non-fatal — learning is best-effort


# ── compression prompt ────────────────────────────────────────────────

_COMPRESS_SYSTEM = """Compress a block of conversation turns into a single dense summary.
Preserve: key facts established, corrections made, questions asked, insights reached.
Omit: pleasantries, redundant restatements, formatting.
Return plain text, 3-6 sentences maximum."""

def _compress_turns(turns: list[dict], model: str, api_key: str | None) -> str:
    """Summarise a list of {role, content} turns into one string."""
    transcript = "\n".join(
        f"{t['role'].upper()}: {t['content']}" for t in turns
    )
    try:
        return llm_call(
            [{"role": "system", "content": _COMPRESS_SYSTEM},
             {"role": "user",   "content": transcript}],
            model=model, api_key=api_key, max_tokens=300,
        )
    except Exception:
        # fallback: just join the user messages
        return " | ".join(t["content"][:80] for t in turns if t["role"] == "user")


# ── public API ────────────────────────────────────────────────────────

def chat_turn(
    user_message: str,
    messages: list[dict],          # live in-session message list (mutated in place)
    indices: list[SectionIndex],   # one per open paper
    paper_titles: list[str],       # one per open paper
    paper_ids: list[str],          # one per open paper
    reader_params: dict,
    model: str,
    api_key: str | None,
    turn_counter: list[int],       # [n] — mutable single-element list as counter
) -> str:
    """
    Process one user turn across one or more open papers.
    Returns the assistant reply string.
    """
    # 1. retrieve relevant sections from ALL open papers
    rag_parts = []
    for idx, title in zip(indices, paper_titles):
        k = len(idx.sections) if len(idx.sections) <= 6 else 4
        ctx = build_rag_context(idx, user_message, k=k)
        if ctx:
            # label each paper's context block
            if len(indices) > 1:
                rag_parts.append(f"=== PAPER: {title} ===\n{ctx}")
            else:
                rag_parts.append(ctx)
    rag_ctx = "\n\n".join(rag_parts)

    # 2. build the user message with RAG context embedded
    augmented = user_message
    if rag_ctx:
        augmented = f"{rag_ctx}\n\nUser question: {user_message}"

    # 3. build memory context from all open papers — silently skip if tables missing
    try:
        mem_parts = [build_memory_context(pid) for pid in paper_ids]
        memory_ctx = "\n\n".join(m for m in mem_parts if m)
    except Exception:
        memory_ctx = ""
    system = _system_prompt(paper_titles, memory_ctx, reader_params)

    # 4. call LLM
    call_messages = (
        [{"role": "system", "content": system}]
        + messages
        + [{"role": "user", "content": augmented}]
    )
    reply = llm_call(call_messages, model=model, api_key=api_key, max_tokens=1024)

    # 5. append raw (un-augmented) turns to live window
    messages.append({"role": "user",      "content": user_message})
    messages.append({"role": "assistant", "content": reply})
    turn_counter[0] += 1

    # 6. extract and persist learning signals (best-effort, non-blocking)
    signals = _extract_signals(user_message, reply, model, api_key)
    _persist_signals(signals, paper_ids[0] if paper_ids else "global")

    # 7. sliding window compression
    _maybe_compress(messages, paper_ids[0] if paper_ids else "global", turn_counter[0], model, api_key)

    return reply


def _persist_signals(signals: dict, paper_id: str):
    """Write extracted signals to Supabase. All failures are silent."""
    try:
        for c in signals.get("corrections", []):
            save_paper_memory(paper_id, "correction", c)
        for r in signals.get("self_revisions", []):
            save_paper_memory(paper_id, "self_revision", r)
        for f in signals.get("established_facts", []):
            save_paper_memory(paper_id, "established_fact", f)
        for e in signals.get("expertise_signals", []):
            save_user_memory("expertise_signal", e)
        for s in signals.get("style_preferences", []):
            save_user_memory("style_preference", s)
    except Exception:
        pass


def _maybe_compress(messages: list[dict], paper_id: str,
                    turn_number: int, model: str, api_key: str | None):
    """
    If the live window exceeds COMPRESS_EVERY turns (pairs),
    compress the oldest turns and store the summary in Supabase.
    Keep KEEP_RECENT recent turns uncompressed.
    """
    # messages is a flat list: [user, assistant, user, assistant, ...]
    # each "turn" = 2 messages
    n_turns = len(messages) // 2
    if n_turns <= COMPRESS_EVERY:
        return

    compress_n = n_turns - KEEP_RECENT          # how many turns to compress
    compress_msgs = messages[: compress_n * 2]  # oldest turns (pairs)
    keep_msgs     = messages[compress_n * 2 :]  # recent turns to keep

    # derive turn range for the summary label
    start_turn = turn_number - n_turns + 1
    end_turn   = turn_number - KEEP_RECENT
    turn_range = f"{start_turn}-{end_turn}"

    summary = _compress_turns(compress_msgs, model, api_key)
    try:
        save_paper_memory(paper_id, "conversation_summary", summary, turn_range)
    except Exception:
        pass

    # replace messages in-place with compressed summary + recent turns
    messages.clear()
    messages.extend(keep_msgs)
