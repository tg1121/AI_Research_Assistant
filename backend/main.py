"""
FastAPI backend for the Research Paper Assistant.

Endpoints:
  POST /upload                        — upload PDF, run full pipeline, return paper_id
  GET  /paper/{paper_id}/status       — pipeline progress
  GET  /paper/{paper_id}/pdf          — serve the raw PDF file
  GET  /paper/{paper_id}/graph        — vis-network-ready nodes + edges JSON
  GET  /paper/{paper_id}/summary      — holistic_summary + section QA
  POST /paper/{paper_id}/chat         — agentic chat turn, returns answer + messages

The existing pipeline (ingestion/, graph/, agent/, pipeline/, etc.) is imported
unchanged. The only wiring is sys.path + async thread-pool execution.
"""

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Make the parent directory importable so existing pipeline code works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models import (
    ChatRequest, ChatResponse, StatusResponse, UploadResponse,
)
from backend.state import PaperStore

# ── lazy pipeline imports (avoid circular imports at module level) ─────
def _imports():
    from ingestion.parser import parse_document
    from ingestion.graph_builder import build_graph
    from pipeline.synthesizer import run_synthesis
    from pipeline.chat import chat_turn
    from pipeline.output_cache import load_cached, save_cache

    # parameter_manager connects to Supabase at import time; fall back to a
    # no-op stub when SUPABASE_URL / SUPABASE_KEY are not configured locally.
    try:
        from feedback.parameter_manager import create_session
    except Exception:
        def create_session(paper_id: str) -> dict:
            import uuid
            return {"id": str(uuid.uuid4())}

    return (parse_document, build_graph, run_synthesis,
            chat_turn, load_cached, save_cache, create_session)


app = FastAPI(title="Research Paper Assistant API", version="8.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = PaperStore()
_executor = ThreadPoolExecutor(max_workers=2)


# ── pipeline worker (runs in thread pool) ─────────────────────────────

class _Cancelled(Exception):
    pass


def _check_cancelled(paper_id: str):
    state = store.get(paper_id)
    if state and state.cancelled:
        store.update(paper_id, status="cancelled", progress_text="Cancelled")
        raise _Cancelled()


def _run_pipeline_sync(
    paper_id: str,
    pdf_path: str,
    model: str,
    api_key: str | None,
    expertise: float,
    sci: float,
    lang: float,
    datalab_key: str | None,
    domain: str = "auto",
):
    (parse_document, build_graph, run_synthesis,
     chat_turn, load_cached, save_cache, create_session) = _imports()

    cancel_event = store.get(paper_id).cancel_event

    try:
        store.update(paper_id, status="processing", progress_pct=5, progress_text="Starting…")
        _check_cancelled(paper_id)

        store.update(paper_id, progress_pct=15, progress_text="1/4 — Parsing…")
        try:
            doc = parse_document(pdf_path, paper_id,
                                 datalab_api_key=datalab_key,
                                 cancel_event=cancel_event)
        except RuntimeError as exc:
            if str(exc) == "Cancelled":
                store.update(paper_id, status="cancelled", progress_text="Cancelled")
                return
            raise
        _check_cancelled(paper_id)

        store.update(paper_id, progress_pct=45, progress_text="2/4 — Building knowledge graph…")
        graph, doc_map, detected_domain = build_graph(doc, domain=domain, model=model, api_key=api_key)
        _check_cancelled(paper_id)

        store.update(paper_id, progress_pct=65, progress_text="3/4 — Synthesis…")
        doc = run_synthesis(
            doc, graph, doc_map, expertise, sci, lang,
            model=model, api_key=api_key,
        )
        _check_cancelled(paper_id)

        store.update(paper_id, progress_pct=85, progress_text="4/4 — Building equation chains…")
        from pipeline.chain_builder import run_chain_builder
        doc = run_chain_builder(doc, model=model, api_key=api_key)
        _check_cancelled(paper_id)

        save_cache(doc, expertise, sci, lang, model=model)

        session = create_session(paper_id)
        store.update(
            paper_id,
            status="done",
            progress_pct=100,
            progress_text="Done",
            doc=doc,
            graph=graph,
            doc_map=doc_map,
            session_id=session["id"],
            detected_domain=detected_domain,
        )

    except _Cancelled:
        pass  # status already set to "cancelled" by _check_cancelled
    except Exception as exc:
        store.update(paper_id, status="error", error=str(exc))
        raise


# ── endpoints ─────────────────────────────────────────────────────────

@app.get("/providers")
async def list_providers():
    """Return the full provider catalogue from llm_client.PROVIDERS."""
    from pipeline.llm_client import PROVIDERS
    return [
        {
            "name":          name,
            "prefix":        info["prefix"],
            "default_model": info["default_model"],
            "key_hint":      info["key_hint"],
            "notes":         info["notes"],
            "models":        info["models"],
        }
        for name, info in PROVIDERS.items()
    ]


@app.get("/providers/openrouter/models")
async def list_openrouter_models(api_key: str = ""):
    """Fetch the live free-model list from OpenRouter via fetch_openrouter_free_models."""
    from pipeline.llm_client import fetch_openrouter_free_models
    loop = asyncio.get_event_loop()
    models = await loop.run_in_executor(
        _executor,
        fetch_openrouter_free_models,
        api_key or None,
    )
    return {"models": models}


@app.post("/upload", response_model=UploadResponse)
async def upload_paper(
    file: UploadFile = File(...),
    model: str = Form("groq/llama-3.3-70b-versatile"),
    api_key: str = Form(""),
    reader_expertise: float = Form(0.0),
    scientific_knowledge: float = Form(0.0),
    language_complexity: float = Form(0.0),
    datalab_api_key: str = Form(""),
    domain: str = Form("auto"),
):
    paper_id = file.filename.replace(".pdf", "")

    os.makedirs("uploads", exist_ok=True)
    pdf_path = f"uploads/{file.filename}"
    content = await file.read()
    with open(pdf_path, "wb") as f:
        f.write(content)

    # Overwrite any previous state for this paper_id
    store.create(paper_id, pdf_path)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor,
        _run_pipeline_sync,
        paper_id, pdf_path,
        model, api_key or None,
        reader_expertise, scientific_knowledge, language_complexity,
        datalab_api_key or None,
        domain,
    )

    return UploadResponse(paper_id=paper_id, status="processing")


@app.post("/paper/{paper_id}/cancel")
async def cancel_paper(paper_id: str):
    store.cancel(paper_id)
    return {"ok": True}


@app.get("/paper/{paper_id}/status", response_model=StatusResponse)
async def get_status(paper_id: str):
    state = store.get(paper_id)
    if not state:
        raise HTTPException(404, "Paper not found")
    return StatusResponse(
        paper_id=state.paper_id,
        status=state.status,
        progress_pct=state.progress_pct,
        progress_text=state.progress_text,
        error=state.error,
        detected_domain=state.detected_domain,
    )


@app.get("/paper/{paper_id}/pdf")
async def get_pdf(paper_id: str):
    state = store.get(paper_id)
    if not state:
        raise HTTPException(404, "Paper not found")
    path = state.pdf_path
    if not path or not os.path.exists(path):
        raise HTTPException(404, "PDF file not found on disk")
    return FileResponse(path, media_type="application/pdf")


@app.get("/paper/{paper_id}/graph")
async def get_graph(paper_id: str):
    state = store.get(paper_id)
    if not state:
        raise HTTPException(404, "Paper not found")
    if state.status != "done":
        raise HTTPException(409, f"Pipeline not complete (status={state.status})")
    return state.graph.to_dict()


@app.get("/paper/{paper_id}/summary")
async def get_summary(paper_id: str):
    state = store.get(paper_id)
    if not state:
        raise HTTPException(404, "Paper not found")
    if state.status != "done":
        raise HTTPException(409, f"Pipeline not complete (status={state.status})")
    section_qa = [
        {"section_id": s.section_id, "title": s.title,
         "role": s.role, "qa": s.qa, "page": s.page}
        for s in state.doc.sections
    ]
    return {
        "title":              state.doc.title,
        "holistic_summary":   state.doc.holistic_summary,
        "mathematical_chain": state.doc.mathematical_chain,
        "section_qa":         section_qa,
    }


@app.post("/paper/{paper_id}/chat", response_model=ChatResponse)
async def chat(paper_id: str, req: ChatRequest):
    state = store.get(paper_id)
    if not state:
        raise HTTPException(404, "Paper not found")
    if state.status != "done":
        raise HTTPException(409, f"Pipeline not complete (status={state.status})")

    (_pd, _bg, _syn, chat_turn, *_rest) = _imports()  # noqa: F841

    # ── debug ──────────────────────────────────────────────────────────
    print(f"\n[CHAT] paper_id={paper_id!r}  exists={store.exists(paper_id)}")
    print(f"[CHAT] graph : {'None' if state.graph is None else f'{len(state.graph.nodes)} nodes, {len(state.graph.edges)} edges'}")
    print(f"[CHAT] doc_map: {'None' if state.doc_map is None else f'present ({len(state.doc_map.sections)} sections)'}")
    print(f"[CHAT] question: {req.question!r}")
    # ───────────────────────────────────────────────────────────────────

    # Guard: empty model string bypasses the Pydantic default when the field
    # is present in the request body (e.g. providers not yet loaded on frontend).
    model = req.model.strip() or "groq/llama-3.3-70b-versatile"

    from pipeline.llm_client import DailyTokenLimitError, InvalidAPIKeyError

    loop = asyncio.get_event_loop()
    try:
        reply = await loop.run_in_executor(
            _executor,
            lambda: chat_turn(
                user_message=req.question,
                messages=state.chat_messages,
                graphs=[state.graph],
                doc_maps=[state.doc_map],
                paper_titles=[state.doc.title],
                paper_ids=[paper_id],
                reader_params=req.reader_params,
                model=model,
                api_key=req.api_key,
                turn_counter=state.turn_counter,
            ),
        )
    except InvalidAPIKeyError as exc:
        raise HTTPException(401, f"API key rejected: {exc}")
    except DailyTokenLimitError as exc:
        raise HTTPException(429, f"Token limit reached: {exc}")
    except Exception as exc:
        raise HTTPException(500, f"Chat pipeline error: {exc}")

    return ChatResponse(answer=reply, messages=list(state.chat_messages))
