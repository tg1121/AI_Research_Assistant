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
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# Load .env from project root so ADMIN_MODE etc. are available before any module-level code
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Make the parent directory importable so existing pipeline code works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models import (
    ChatRequest, ChatResponse, LoginRequest, LoginResponse, SignupResponse,
    MarkerDecisionRequest, StatusResponse, UploadResponse,
)
from backend.state import PaperStore
from backend.auth import get_current_user
import backend.db as db
import backend.storage as storage

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
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()

store = PaperStore()
_executor     = ThreadPoolExecutor(max_workers=1)   # pipeline (long-running)
_api_executor = ThreadPoolExecutor(max_workers=4)   # provider API calls (quick)


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
    user_id: str | None = None,
):
    (parse_document, build_graph, run_synthesis,
     chat_turn, load_cached, save_cache, create_session) = _imports()

    cancel_event = store.get(paper_id).cancel_event

    try:
        store.update(paper_id, status="processing", progress_pct=5, progress_text="Starting…",
                     pipeline_params=dict(model=model, api_key=api_key, expertise=expertise,
                                          sci=sci, lang=lang, datalab_key=datalab_key,
                                          domain=domain, user_id=user_id))
        _check_cancelled(paper_id)

        store.update(paper_id, progress_pct=15, progress_text="1/4 — Parsing…")

        if domain == "auto":
            # Phase 1: fast PyMuPDF parse for domain detection (not cached)
            try:
                doc = parse_document(pdf_path, paper_id,
                                     cancel_event=cancel_event,
                                     domain="non-math",
                                     no_cache_save=True)
            except RuntimeError as exc:
                if str(exc) == "Cancelled":
                    store.update(paper_id, status="cancelled", progress_text="Cancelled")
                    return
                raise
            _check_cancelled(paper_id)

            from ingestion.domain_detector import detect_domain
            detected_domain, confidence = detect_domain(doc)
            print(f"    [domain] auto-detected: {detected_domain} (confidence={confidence:.2f})")

            if detected_domain == "math":
                # Pause pipeline — ask user whether to re-parse with Marker
                store.update(paper_id,
                             status="awaiting_marker_decision",
                             progress_pct=25,
                             progress_text="Math-heavy paper detected — waiting for your decision…",
                             detected_domain="math")
                state = store.get(paper_id)
                state.marker_decision_event.wait()   # unblocked by /marker_decision or cancel
                if cancel_event.is_set():            # re-upload replaced our state — exit
                    return
                _check_cancelled(paper_id)

                decision = state.marker_decision or {}
                if decision.get("use_marker"):
                    dk = decision.get("datalab_key") or datalab_key
                    store.update(paper_id, status="processing", progress_pct=30,
                                 progress_text="1/4 — Re-parsing with Marker…")
                    try:
                        doc = parse_document(pdf_path, paper_id,
                                             cancel_event=cancel_event,
                                             domain="math",
                                             datalab_api_key=dk)
                    except RuntimeError as exc:
                        if str(exc) == "Cancelled":
                            store.update(paper_id, status="cancelled", progress_text="Cancelled")
                            return
                        raise
                    _check_cancelled(paper_id)
                # else: keep the PyMuPDF doc as-is

        else:
            detected_domain = domain
            print(f"    [domain] user-selected: {detected_domain}")
            try:
                doc = parse_document(pdf_path, paper_id,
                                     datalab_api_key=datalab_key,
                                     cancel_event=cancel_event,
                                     domain=domain)
            except RuntimeError as exc:
                if str(exc) == "Cancelled":
                    store.update(paper_id, status="cancelled", progress_text="Cancelled")
                    return
                raise
            _check_cancelled(paper_id)

        graph, doc_map = None, None
        if detected_domain == "math":
            store.update(paper_id, progress_pct=40, progress_text="2/3 — Building knowledge graph…")
            graph, doc_map, _ = build_graph(doc, domain="math", model=model, api_key=api_key)
            from pipeline.output_cache import save_graph
            save_graph(paper_id, graph)
            _check_cancelled(paper_id)

        store.update(paper_id, progress_pct=65, progress_text="2/3 — Synthesis…" if detected_domain == "math" else "2/2 — Synthesis…")
        if detected_domain != "math":
            from pipeline.english_synthesizer import run_english_synthesis
            from ingestion.english_node_extractor import extract_nodes as eng_nodes
            doc, doc_map = run_english_synthesis(
                doc, expertise, sci, lang,
                model=model, api_key=api_key,
            )
            graph = eng_nodes(doc)  # section graph for chat retrieval
        else:
            doc = run_synthesis(
                doc, graph, doc_map, expertise, sci, lang,
                model=model, api_key=api_key,
            )
        _check_cancelled(paper_id)

        if detected_domain == "math":
            store.update(paper_id, progress_pct=85, progress_text="3/3 — Building equation chains…")
            from pipeline.chain_builder import run_chain_builder
            doc = run_chain_builder(doc, model=model, api_key=api_key)
            _check_cancelled(paper_id)

        save_cache(doc, expertise, sci, lang, model=model)

        session = create_session(paper_id, user_id=user_id)
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

        if user_id:
            try:
                db.save_paper(
                    user_id=user_id,
                    paper_id=paper_id,
                    title=getattr(doc, "title", None) or paper_id,
                    detected_domain=detected_domain,
                    pdf_size_bytes=os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0,
                )
            except Exception as e:
                print(f"[db] save_paper failed: {e}")

    except _Cancelled:
        pass  # status already set to "cancelled" by _check_cancelled
    except Exception as exc:
        store.update(paper_id, status="error", error=str(exc))
        raise


# ── endpoints ─────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    from supabase import create_client as _create_client
    sb = _create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    try:
        resp = sb.auth.sign_in_with_password({"email": req.email, "password": req.password})
        return LoginResponse(
            access_token=resp.session.access_token,
            user_id=str(resp.user.id),
            email=resp.user.email,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Login failed: {exc}")


@router.post("/auth/signup", response_model=SignupResponse)
async def signup(req: LoginRequest):
    from supabase import create_client as _create_client
    sb = _create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    try:
        resp = sb.auth.sign_up({"email": req.email, "password": req.password})
        if resp.session:
            return SignupResponse(
                access_token=resp.session.access_token,
                user_id=str(resp.user.id),
                email=resp.user.email,
                confirm_email=False,
            )
        return SignupResponse(email=req.email, confirm_email=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Sign up failed: {exc}")


@router.get("/info")
async def info():
    """Global app config — fetched once by the frontend on mount."""
    return {"admin_mode": os.environ.get("ADMIN_MODE", "").lower() == "true"}


@router.post("/paper/{paper_id}/marker_decision")
async def marker_decision(paper_id: str, req: MarkerDecisionRequest,
                          current_user=Depends(get_current_user)):
    state = store.get(paper_id)
    if not state:
        raise HTTPException(404, "Paper not found")
    if state.status != "awaiting_marker_decision":
        raise HTTPException(409, "Paper is not awaiting a marker decision")
    state.marker_decision = {"use_marker": req.use_marker, "datalab_key": req.datalab_key}
    state.marker_decision_event.set()
    return {"ok": True}


@router.get("/providers")
async def list_providers():
    """Return the full provider catalogue from llm_client.PROVIDERS."""
    from pipeline.llm_client import PROVIDERS
    return [
        {
            "name":          name,
            "prefix":        info["prefix"],
            "default_model": info["default_model"],
            "env_var":       info["env_var"],
            "key_hint":      info["key_hint"],
            "notes":         info["notes"],
            "models":        info["models"],
        }
        for name, info in PROVIDERS.items()
    ]


@router.get("/providers/{prefix}/models")
async def list_provider_models(prefix: str, api_key: str = ""):
    """Fetch the live model list for any provider via fetch_provider_models."""
    from pipeline.llm_client import fetch_provider_models
    loop = asyncio.get_event_loop()
    models = await loop.run_in_executor(
        _api_executor,
        fetch_provider_models,
        prefix,
        api_key or None,
    )
    return {"models": models}


@router.post("/upload", response_model=UploadResponse)
async def upload_paper(
    file: UploadFile = File(...),
    model: str = Form("groq/llama-3.3-70b-versatile"),
    api_key: str = Form(""),
    reader_expertise: float = Form(0.0),
    scientific_knowledge: float = Form(0.0),
    language_complexity: float = Form(0.0),
    datalab_api_key: str = Form(""),
    domain: str = Form("auto"),
    current_user=Depends(get_current_user),
):
    paper_id = file.filename.replace(".pdf", "")
    content  = await file.read()

    try:
        db.check_storage_limit(str(current_user.id), len(content))
    except db.StorageLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc))

    pdf_path = storage.save_pdf(str(current_user.id), paper_id, content)

    # Unblock any thread stuck waiting on the old state before replacing it
    old = store.get(paper_id)
    if old:
        old.cancelled = True
        old.cancel_event.set()
        old.marker_decision_event.set()

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
        str(current_user.id),
    )

    return UploadResponse(paper_id=paper_id, status="processing")


@router.post("/paper/{paper_id}/retry")
async def retry_paper(paper_id: str, current_user=Depends(get_current_user)):
    state = store.get(paper_id)
    if not state:
        raise HTTPException(404, "Paper not found")
    if state.status not in ("error", "cancelled"):
        raise HTTPException(409, f"Cannot retry — status is {state.status!r}")
    params = state.pipeline_params or {}
    store.reset_for_retry(paper_id)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor, _run_pipeline_sync,
        paper_id, state.pdf_path,
        params.get("model", "groq/llama-3.3-70b-versatile"),
        params.get("api_key"),
        params.get("expertise", 0.0),
        params.get("sci", 0.0),
        params.get("lang", 0.0),
        params.get("datalab_key"),
        params.get("domain", "auto"),
        params.get("user_id"),
    )
    return {"ok": True}


@router.post("/paper/{paper_id}/cancel")
async def cancel_paper(paper_id: str, current_user=Depends(get_current_user)):
    store.cancel(paper_id)
    return {"ok": True}


@router.get("/papers")
async def list_papers(current_user=Depends(get_current_user)):
    """Return all papers the user has ever processed, filtered to PDFs still on disk."""
    entries = db.get_papers(str(current_user.id))
    if os.environ.get("ADMIN_MODE", "").lower() == "true":
        return [e for e in entries if storage.exists_locally(e["paper_id"])]
    return entries


@router.delete("/paper/{paper_id}")
async def delete_paper(paper_id: str, current_user=Depends(get_current_user)):
    """Delete a paper: DB record, PDF, parsed markdown, output cache, and graph cache."""
    user_id = str(current_user.id)

    # Verify ownership
    entries = db.get_papers(user_id)
    if not any(e["paper_id"] == paper_id for e in entries):
        raise HTTPException(404, "Paper not found")

    db.delete_paper(user_id, paper_id)
    storage.delete_pdf(user_id, paper_id)

    # Remove parsed markdown cache
    from ingestion.parser import LOCAL_CACHE_DIR
    md_path = os.path.join(LOCAL_CACHE_DIR, f"{paper_id}.md")
    if os.path.exists(md_path):
        try:
            os.remove(md_path)
        except OSError:
            pass

    # Remove output + graph cache
    from pipeline.output_cache import delete_paper_cache
    delete_paper_cache(paper_id)

    # Evict from in-memory store
    store._store.pop(paper_id, None)

    return {"deleted": paper_id}


@router.post("/paper/{paper_id}/open")
async def open_paper(paper_id: str, current_user=Depends(get_current_user)):
    """
    Register an already-uploaded paper in the in-memory store so its PDF can
    be served and chat works. Tries to restore doc/graph/doc_map from the
    output cache; falls back to PDF-only mode if no cache exists.
    """
    user_papers = db.get_papers(str(current_user.id))
    db_entry = next((e for e in user_papers if e["paper_id"] == paper_id), None)
    if not db_entry:
        raise HTTPException(404, "Paper not found")

    pdf_path = storage.ensure_local(str(current_user.id), paper_id)
    if not pdf_path:
        raise HTTPException(404, "PDF not found in storage")

    existing = store.get(paper_id)
    if existing and existing.status == "done":
        return {"status": "done", "detected_domain": existing.detected_domain, "restored": True}

    store.create(paper_id, pdf_path)

    from pipeline.output_cache import list_cached_profiles, load_cached
    from ingestion.english_node_extractor import extract_nodes
    from graph.doc_map import build_english_doc_map

    profiles = list_cached_profiles(paper_id)
    if not profiles:
        store.update(paper_id, status="done")
        return {"status": "done", "restored": False}

    p = profiles[0]
    doc = load_cached(paper_id, p["reader_expertise"], p["scientific_knowledge"],
                      p["language_complexity"], p.get("model_slug", ""))
    if not doc:
        store.update(paper_id, status="done")
        return {"status": "done", "restored": False}

    # detected_domain from db record if available (db_entry already fetched above)
    db_entry = db_entry or {}
    detected_domain = db_entry.get("detected_domain") or "non-math"

    if detected_domain == "math":
        from pipeline.output_cache import load_graph
        from ingestion.graph_builder import build_graph
        graph = load_graph(paper_id)
        if graph is None:
            graph, _, _ = build_graph(doc, domain="math")
            from pipeline.output_cache import save_graph
            save_graph(paper_id, graph)
        from graph.doc_map import build_doc_map
        doc_map = build_doc_map(graph, paper_id, doc.title)
    else:
        graph   = extract_nodes(doc)
        doc_map = build_english_doc_map(doc, [{} for _ in doc.sections])

    store.update(paper_id, status="done", doc=doc, graph=graph, doc_map=doc_map,
                 detected_domain=detected_domain)
    return {"status": "done", "restored": True, "detected_domain": detected_domain}


@router.get("/paper/{paper_id}/status", response_model=StatusResponse)
async def get_status(paper_id: str, current_user=Depends(get_current_user)):
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


@router.get("/paper/{paper_id}/pdf")
async def get_pdf(paper_id: str, token: str = "", current_user=None):
    # PDF is loaded directly by the browser so we accept token as a query param
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    from backend.auth import _supabase
    try:
        resp = _supabase().auth.get_user(token)
        if not resp.user:
            raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if os.environ.get("ADMIN_MODE", "").lower() == "true":
        pdf_path = f"uploads/{paper_id}.pdf"
        if not os.path.exists(pdf_path):
            raise HTTPException(404, "PDF file not found on disk")
        return FileResponse(pdf_path, media_type="application/pdf")

    user_id = str(resp.user.id)
    signed_url = storage.get_signed_url(user_id, paper_id)
    if not signed_url:
        raise HTTPException(404, "PDF not found in storage")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=signed_url)


@router.get("/paper/{paper_id}/graph")
async def get_graph(paper_id: str, current_user=Depends(get_current_user)):
    state = store.get(paper_id)
    if not state:
        raise HTTPException(404, "Paper not found")
    if state.status != "done":
        raise HTTPException(409, f"Pipeline not complete (status={state.status})")
    if state.detected_domain != "math":
        return {"nodes": [], "edges": []}
    return state.graph.to_dict()


@router.get("/paper/{paper_id}/summary")
async def get_summary(paper_id: str, current_user=Depends(get_current_user)):
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


@router.post("/paper/{paper_id}/chat", response_model=ChatResponse)
async def chat(paper_id: str, req: ChatRequest, current_user=Depends(get_current_user)):
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

    # If backend lost its in-memory history (restart) but frontend saved it, restore it.
    if not state.chat_messages and req.prior_messages:
        state.chat_messages = [m for m in req.prior_messages if isinstance(m, dict) and "role" in m and "content" in m]

    # Guard: empty model string bypasses the Pydantic default when the field
    # is present in the request body (e.g. providers not yet loaded on frontend).
    model = req.model.strip() or "groq/llama-3.3-70b-versatile"

    # Gather all done papers — active paper first, then any additional IDs from
    # the request (the frontend sends all open tabs so the agent can search across them).
    all_ids = [paper_id] + [pid for pid in req.paper_ids if pid != paper_id]
    graphs, doc_maps, titles, ids = [], [], [], []
    for pid in all_ids:
        s = store.get(pid)
        if s and s.status == "done" and s.graph is not None and s.doc_map is not None:
            graphs.append(s.graph)
            doc_maps.append(s.doc_map)
            titles.append(s.doc.title)
            ids.append(pid)
    if not graphs:
        graphs, doc_maps, titles, ids = [state.graph], [state.doc_map], [state.doc.title], [paper_id]

    if len(ids) > 1:
        print(f"[CHAT] multi-paper context: {ids}")

    from pipeline.llm_client import DailyTokenLimitError, InvalidAPIKeyError

    loop = asyncio.get_event_loop()
    try:
        reply = await loop.run_in_executor(
            _executor,
            lambda: chat_turn(
                user_message=req.question,
                messages=state.chat_messages,
                graphs=graphs,
                doc_maps=doc_maps,
                paper_titles=titles,
                paper_ids=ids,
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


# ── Register all routes under /api, then serve React frontend ─────────
app.include_router(router, prefix="/api")

_frontend_dist = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "dist",
)
if os.path.exists(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="static")
