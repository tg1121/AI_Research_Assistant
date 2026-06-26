"""
ReAct planner — token-efficient version.

Key optimisations vs original:
  - Tool results NOT accumulated in message history (saves re-sending on each iteration)
  - Doc map sent once in system prompt, not repeated in user seed
  - Planner max_tokens capped at 100 (only needs TOOL/ARGS/ANSWER lines)
  - Tool result sampled start/middle/end before feeding back (budget=800 chars)
"""

import re
from pipeline.llm_client import llm_call
from graph.math_graph import Graph
from graph.doc_map import DocMap
from agent.tools import (
    consult_doc_map, retrieve_section,
    follow_reference, search_concept,
)

MAX_ITERATIONS = 4


def _sample_result(text: str, budget: int = 800) -> str:
    """Sample start/middle/end of a tool result to fit within budget chars."""
    text = text.strip()
    if len(text) <= budget:
        return text
    chunk = budget // 3
    mid_s = (len(text) - chunk) // 2
    return (
        text[:chunk]
        + "\n[...]\n"
        + text[mid_s:mid_s + chunk]
        + "\n[...]\n"
        + text[-chunk:]
    )


def _build_system(doc_map: DocMap) -> str:
    doc_map_block = consult_doc_map(doc_map)
    return f"""You are a research assistant. Answer questions by calling tools.

Paper structure:
{doc_map_block}

Tools:
  TOOL: consult_doc_map          → full paper structure
  TOOL: retrieve_section  ARGS: <section_id>
  TOOL: follow_reference  ARGS: <node_label>
  TOOL: search_concept    ARGS: <keyword>

Rules:
- Output ONLY: TOOL: <name> then ARGS: <arg>   OR   ANSWER: ready
- One tool per response. No explanation."""


def _parse_tool_call(text: str) -> tuple[str, str] | None:
    tm = re.search(r'TOOL:\s*(\w+)', text, re.IGNORECASE)
    am = re.search(r'ARGS:\s*(.+)', text, re.IGNORECASE)
    if tm:
        return tm.group(1).strip().lower(), (am.group(1).strip() if am else "")
    return None


def _execute(tool: str, args: str, graph: Graph, doc_map: DocMap) -> str:
    if tool == "consult_doc_map":
        return consult_doc_map(doc_map)
    if tool == "retrieve_section":
        return retrieve_section(graph, args.strip())
    if tool == "follow_reference":
        return follow_reference(graph, args.strip())
    if tool == "search_concept":
        return search_concept(graph, args.strip())
    return f"[Unknown tool: {tool}]"


def plan_and_retrieve(
    question: str,
    graph: Graph,
    doc_map: DocMap,
    model: str,
    api_key: str | None,
) -> list[str]:
    """
    Run ReAct loop. Returns list of context blocks for the synthesizer.
    Token-efficient: tool results are NOT kept in message history.
    """
    context_blocks: list[str] = []
    system = _build_system(doc_map)

    # Stateless loop: each planner call sees only system + current question + latest result
    # This avoids re-sending all previous tool results on each iteration
    last_result = ""

    for iteration in range(MAX_ITERATIONS):
        # Build minimal message: question + latest tool result only
        if iteration == 0:
            user_content = f"Question: {question}\n\nCall a tool or say ANSWER: ready."
        else:
            user_content = (
                f"Question: {question}\n\n"
                f"Last tool result (truncated):\n{_sample_result(last_result)}\n\n"
                f"Call another tool or say ANSWER: ready."
            )

        messages = [
            {"role": "system",  "content": system},
            {"role": "user",    "content": user_content},
        ]

        try:
            response = llm_call(messages, model=model,
                                api_key=api_key, max_tokens=100)
        except Exception as e:
            print(f"    [planner iter={iteration}] LLM ERROR: {e}")
            context_blocks.append(f"[Planner error: {e}]")
            break

        print(f"    [planner iter={iteration}] raw response: {response!r}")

        if "ANSWER:" in response.upper():
            print(f"    [planner iter={iteration}] → ANSWER detected, stopping")
            break

        parsed = _parse_tool_call(response)
        if not parsed:
            print(f"    [planner iter={iteration}] → no tool parsed, appending raw")
            context_blocks.append(response)
            break

        tool, args = parsed
        print(f"    [planner iter={iteration}] → TOOL={tool!r} ARGS={args[:60]!r}")

        result = _execute(tool, args, graph, doc_map)
        context_blocks.append(result)
        last_result = result

    return context_blocks
