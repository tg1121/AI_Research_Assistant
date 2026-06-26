# CLAUDE.md — AI Research Assistant

> Update only with explicit user permission.

## Project
FastAPI + React. PDF → knowledge graph → LLM synthesis → agentic RAG chat.
HF Spaces (Docker). Supabase persistence.

## LLM
Default: OpenRouter (`openai/gpt-oss-120b:free`). Local override: `OLLAMA_BASE_URL` env var (default `http://localhost:11434`). Falls back to OpenRouter if unset. `model` and `api_key` always passed explicitly — no global state.

---

## Versions

### V12.1 — English Graph Fix
One LLM call per paper. 30% section sampling (start/mid/end). Single prompt → nodes + edges. Caps: 3 nodes/section, 2 edges/node, 40 total. Citation regex: APA `(Smith, 2020)` + numbered `[1]`, `[2,3]`. No LLM in edge extractor.

### V12.2 — LLM Simplification
Remove multi-provider BYOK UI, provider dropdown, and LiteLLM multi-provider routing. Single `OLLAMA_BASE_URL` controls the LLM endpoint everywhere. OpenRouter is the cloud fallback when unset. Simplifies `llm_client.py` to one call path.

### V12.3 — Proof Type Classifier
Replace regex proof classification with a fine-tuned `DeBERTa-v3-small` 3-class classifier (`direct | induction | contradiction`). Training: silver-label `wellecks/naturalproofs-gen` (~25k proofs) using existing regex as weak supervisor. Fine-tuning is CPU-feasible (~few hours, ~180MB model). Runs as a HuggingFace pipeline — no Ollama needed. Async task: auto-triggered on paper upload alongside graph build.

### V12.4 — Hypothesis Validation Engine
4-stage pipeline per paper, cached in `hypothesis_cache` (keyed by `paper_id`). Runs as async task (user-triggered).

1. **`hypothesis_extractor`** — scan for explicit claim language; if absent, generate from main contribution. Returns `{statement, source: extracted|generated, evidence[]}`.
2. **`counterexample_generator`** — 3–5 counterexamples: numerical/edge-case (math), boundary conditions (empirical), adversarial inputs (CS).
3. **`test_codegen`** — self-contained Python using `numpy / scipy / sympy / pandas`. One test block per counterexample + appropriate stat test.
4. **`sandbox_runner`** — `subprocess.run`, `timeout=30s`. Allowlist: `numpy scipy sympy pandas statsmodels math random`. Strip `os sys open exec eval __import__` before execution.

UI: collapsible accordion in Summary/Graph tab. Sub-sections: Hypothesis (extracted/generated badge) → Counterexamples → Code + ↺ Regenerate → Execution output.

**Fine-tuning plan:** QLoRA on Qwen 2.5 7B using Colab free T4 (no billing needed). Datasets: `UniverseTBD/hypogen-dr1` (HypoGen ~5.5k), `zifeng-ai/BioDSA-1K` (hypothesis + analysis code pairs), `CrossTrace` (1.4k grounded reasoning traces). Export to GGUF → serve locally via Ollama CPU → deploy to GCP Cloud Run (L4, scale-to-zero) using $300 free credits when ready.

### V13 — Web-Augmented Agent
Add `search_web(query)` and `fetch_url(url)` to the ReAct agent. New `agent/web_client.py`. Requires `WEB_SEARCH_API_KEY` env var.

### V13.1 — Bibliography as Graph Nodes
Parse bibliography → `BibEntry` objects → graph nodes (`bibliography_entry` type). Citation edges resolve to specific `BibEntry` nodes instead of the generic external placeholder. New `get_bibliography` agent tool.

### V14 — Projects + Sandbox Chat
Projects CRUD. `project_type: research | course`. Per-project AI agent + sandbox chat (SSE). Project memory → Supabase.

### V14.1 — Research Assistant Abstraction
Unified `research_assistants` table for AI and human members. Same roster slot, same UI.

### V14.2 — Human Team + Access Control
Invite flow for registered users. All `/projects/{id}/*` routes access-controlled to team members.

### V14.3 — Shared Workspace
Per-project papers, links, notes. `workspace_items` table. AI agents can add items.

### V14.4 — Open Offers
Projects post public open roles. Unauthenticated browsing. Apply / accept / reject pipeline.

### V14.5 — Per-User AI Companion
Personal AI per `(user_id, project_id)` + reader profile. Independent from project-level shared agent.

### V14.6 — Plug-and-Play Reader Profiles
Profiles switchable without pipeline rerun. Presets: beginner / intermediate / expert. Stored in `user_reader_profiles`, loaded fresh per request. Profile change takes effect on next chat turn.

### V15 — Background Task Queue
ThreadPoolExecutor worker. Task types: `process_paper`, `generate_project_summary`, `flag_findings`, `hypothesis_validation`, `proof_classification`. Auto-triggered on paper upload. Inbox badge + toast notifications in UI.

### V16 — Agent Manager + Professor View
Manager layer routes and synthesises across project agents. Professor gets unified command centre with cross-project visibility.

---

## Reader Profiles
Persisted per `(user_id, project_id)` in `user_reader_profiles`.
Course defaults: `professor | ta → depth=full, expert`; `student → depth=intermediate`. Overridable per user.

---

## Guardrails
- One LLM call per paper for graph extraction (V12.1+). Never per-section.
- Token budget logged per pipeline stage. Fail loudly at 2× expected.
- No LLM in deterministic passes. Proof classification via DeBERTa from V12.3 (not LLM, not regex).
- Auth required on all routes except `/login /signup /info /offers`.
- Project routes verify team membership (V14.2+).
- Reader profile from DB only — never from request body.
- `model` and `api_key` always explicit — no global state.
- `OLLAMA_BASE_URL` controls LLM endpoint (V12.2+). Falls back to OpenRouter if unset.
- Windows: `PDFTEXT_CPU_WORKERS=1` and `if __name__ == '__main__'` guards stay.

---

## Test Signals

| Version | Pass signal |
|---------|-------------|
| general | API key routing stable; login works; all V11 features intact |
| V12.1 | English paper → non-zero `total_edges`, semantic graph nodes |
| V12.2 | Provider dropdown gone; single endpoint routes correctly; OpenRouter fallback works |
| V12.3 | Proof nodes carry `proof_type` from DeBERTa, not regex; async completes on upload |
| V12.4 | Hypothesis accordion populates; code runs in sandbox; results cached to `hypothesis_cache` |
| V13 | Agent uses web tool for out-of-paper queries; `fetch_url` returns content |
| V13.1 | Bibliography → `BibEntry` nodes; citation edges resolve to specific entries |
| V14 | Project CRUD round-trips; SSE chat streams; memory persists across restart |
| V14.2 | Non-member receives 403 on all `/projects/{id}/*` routes |
| V14.5 | Two users in same project get independent histories and profiles |
| V14.6 | Profile switch → next turn reflects new depth without pipeline rerun |
| V15 | Upload → task auto-enqueued → report in inbox without manual trigger |
| V16 | Manager aggregates findings from 2+ project agents in one response |