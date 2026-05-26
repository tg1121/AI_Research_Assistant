import streamlit as st
import os
import json
import base64
from ingestion.parser import parse_document
from pipeline.tagger import run_tagging
from pipeline.chain_builder import run_chain_builder
from pipeline.section_qa import run_section_qa
from pipeline.llm_client import PROVIDERS, fetch_openrouter_free_models, DailyTokenLimitError, InvalidAPIKeyError, resolve_model
from pipeline.synthesizer import run_synthesis
from pipeline.output_cache import load_cached, save_cache, list_cached_profiles
from pipeline.rag import SectionIndex
from pipeline.chat import chat_turn
from feedback.parameter_manager import (
    create_session, get_session, update_session_parameters,
    apply_feedback, record_feedback
)

st.set_page_config(
    page_title="Research Paper Assistant",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS — sidebar visibility driven by session_state.sidebar_open
_sb_open = st.session_state.get("sidebar_open", True)
_sb_style = "min-width:300px;max-width:300px;" if _sb_open else "display:none !important;"
st.markdown(f"""
<style>
.block-container {{ padding-top: 3.5rem; padding-bottom: 0; }}
.main .block-container {{ max-width: 100% !important; }}
section[data-testid="stSidebar"] {{ {_sb_style} }}
[data-testid="collapsedControl"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)

# ── session state ────────────────────────────────────────────────────
for key, default in [
    ("llm_provider",         "Groq (free tier)"),
    ("llm_model",            "llama-3.3-70b-versatile"),
    ("llm_api_key",          ""),
    ("reader_expertise",     0.0),
    ("scientific_knowledge", 0.0),
    ("language_complexity",  0.0),
    ("mode",                 None),
    ("papers",               []),
    ("active_paper_idx",     0),
    ("chat_messages",        []),
    ("chat_turn_counter",    [0]),
    ("chat_ready",           False),
    ("split_mid",            3),
    ("split_right",          7),
    ("sidebar_open",         True),
    ("datalab_api_key",      ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── helpers ──────────────────────────────────────────────────────────
def get_llm():
    model   = resolve_model(st.session_state.llm_provider, st.session_state.llm_model)
    api_key = st.session_state.llm_api_key or os.environ.get(
        PROVIDERS[st.session_state.llm_provider]["env_var"], "") or None
    return model, api_key

def reader_params():
    return {
        "reader_expertise":     st.session_state.reader_expertise,
        "scientific_knowledge": st.session_state.scientific_knowledge,
        "language_complexity":  st.session_state.language_complexity,
    }

def _check_key():
    _, api_key = get_llm()
    if not api_key:
        st.error(f"🔑 No API key for **{st.session_state.llm_provider}**. Set it in the sidebar.")
        st.stop()

def active_paper():
    idx = st.session_state.active_paper_idx
    if 0 <= idx < len(st.session_state.papers):
        return st.session_state.papers[idx]
    return None

def _run_pipeline(uploaded_file, expertise, sci, lang, llm_model, llm_api_key,
                  progress=None, run_qa=False):
    def _prog(pct, txt):
        if progress: progress.progress(pct, text=txt)
    paper_id  = uploaded_file.name.replace(".pdf", "")
    save_path = f"uploads/{uploaded_file.name}"
    os.makedirs("uploads", exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    steps = 4 if run_qa else 3
    _prog(10,  f"1/{steps} — Parsing…")
    doc = parse_document(save_path, paper_id,
                         datalab_api_key=st.session_state.get("datalab_api_key") or None)
    _prog(35,  f"2/{steps} — Tagging…")
    doc = run_tagging(doc, model=llm_model, api_key=llm_api_key)
    _prog(60,  f"3/{steps} — Math chain…")
    doc = run_chain_builder(doc, model=llm_model, api_key=llm_api_key)
    if run_qa:
        _prog(80, f"4/{steps} — Q&A…")
        doc = run_section_qa(doc, expertise, sci, lang, model=llm_model, api_key=llm_api_key)
    _prog(90,  f"{steps}/{steps} — Synthesis…")
    doc = run_synthesis(doc, expertise, sci, lang, model=llm_model, api_key=llm_api_key)
    _prog(100, "Done")
    save_cache(doc, expertise, sci, lang, model=llm_model)
    return doc

def _parse_only(uploaded_file):
    paper_id  = uploaded_file.name.replace(".pdf", "")
    save_path = f"uploads/{uploaded_file.name}"
    os.makedirs("uploads", exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return parse_document(save_path, paper_id,
                          datalab_api_key=st.session_state.get("datalab_api_key") or None)


# ════════════════════════════════════════════════════════════════════
# SIDEBAR — settings (always present, native Streamlit sidebar)
# ════════════════════════════════════════════════════════════════════
with st.sidebar:
    if st.session_state.mode is None:
        st.markdown("### ⚙️ Settings")
    else:
        mode_label = {"summary": "📄 Summary", "chat": "💬 Chat", "both": "🔬 Summary + Chat"}[st.session_state.mode]
        st.markdown(f"### ⚙️ Settings — {mode_label}")
        if st.button("← Change Mode", use_container_width=True):
            for k, v in [("mode", None), ("papers", []), ("active_paper_idx", 0),
                         ("chat_messages", []), ("chat_turn_counter", [0]), ("chat_ready", False)]:
                st.session_state[k] = v
            st.rerun()

    st.markdown("---")

    # LLM provider
    provider_label = st.selectbox(
        "Provider",
        options=list(PROVIDERS.keys()),
        index=list(PROVIDERS.keys()).index(st.session_state.llm_provider),
    )
    info = PROVIDERS[provider_label]
    st.caption(info["notes"])

    key_wk    = f"sb_api_{provider_label.replace(' ','_').replace('(','').replace(')','')}"
    saved_key = st.session_state.llm_api_key if st.session_state.llm_provider == provider_label else ""
    api_key_input = st.text_input("API Key", value=saved_key, type="password",
                                   placeholder=info["key_hint"], key=key_wk)
    if st.button("Apply Key", use_container_width=True):
        st.session_state.llm_provider = provider_label
        st.session_state.llm_api_key  = api_key_input or os.environ.get(info["env_var"], "") or ""
        st.success("Key saved ✓")

    resolved_key = api_key_input or os.environ.get(info["env_var"], "") or None
    if provider_label == "OpenRouter (free models)":
        with st.spinner("Fetching models…"):
            free_models = fetch_openrouter_free_models(resolved_key)
        models_list = free_models or [info["default_model"]]
        def_idx = models_list.index(st.session_state.llm_model) if st.session_state.llm_model in models_list else 0
        selected_model = st.selectbox("Model", options=models_list, index=def_idx, key="sb_or_model")
    else:
        models_list = info.get("models", [info["default_model"]])
        def_idx = models_list.index(st.session_state.llm_model) if st.session_state.llm_model in models_list else 0
        selected_model = st.selectbox("Model", options=models_list, index=def_idx, key="sb_model")

    st.session_state.llm_provider = provider_label
    st.session_state.llm_model    = selected_model
    if not st.session_state.llm_api_key:
        st.session_state.llm_api_key = os.environ.get(info["env_var"], "") or ""

    st.markdown("---")

    # PDF Parser
    _admin_mode = os.environ.get("ADMIN_MODE", "").lower() == "true"
    if not _admin_mode:
        st.markdown("**PDF Parser**")
        _datalab_key = st.text_input(
            "Datalab API Key (optional)",
            value=st.session_state.datalab_api_key,
            type="password",
            placeholder="For high-quality math/table parsing",
            help="Leave blank to use PyMuPDF (default). Get a free key at datalab.to"
        )
        st.session_state.datalab_api_key = _datalab_key
        if _datalab_key:
            st.caption("✅ Using Marker API")
        else:
            st.caption("Using PyMuPDF (default)")

    st.markdown("---")
    st.markdown("**Reader Profile**")
    linked = st.toggle("Link parameters", value=True)
    if linked:
        expertise = st.slider("Expertise", 0.0, 1.0,
                               float(st.session_state.reader_expertise), 0.05)
        sci = lang = expertise
        st.slider("Scientific", 0.0, 1.0, float(expertise), 0.05, disabled=True)
        st.slider("Language",   0.0, 1.0, float(expertise), 0.05, disabled=True)
    else:
        sci  = st.slider("Scientific", 0.0, 1.0,
                          float(st.session_state.scientific_knowledge), 0.05)
        lang = st.slider("Language",   0.0, 1.0,
                          float(st.session_state.language_complexity),  0.05)
        expertise = round((sci + lang) / 2, 2)
        st.metric("Expertise (derived)", value=expertise)

    st.markdown("---")

    if st.session_state.mode is not None:
        needs_summary = st.session_state.mode in ("summary", "both")
        btn_label = "Apply & Resynthesize" if needs_summary else "Apply Parameters"
        ap = active_paper()
        if st.button(btn_label, use_container_width=True, type="primary"):
            st.session_state.reader_expertise     = expertise
            st.session_state.scientific_knowledge = sci
            st.session_state.language_complexity  = lang
            if needs_summary and ap and ap.get("doc"):
                _check_key()
                llm_model, llm_api_key = get_llm()
                cached = load_cached(ap["paper_id"], expertise, sci, lang, model=llm_model)
                if cached:
                    st.session_state.papers[st.session_state.active_paper_idx]["doc"] = cached
                    st.session_state.papers[st.session_state.active_paper_idx]["rag_index"] = SectionIndex().build(cached)
                    st.success("Loaded from cache ✓")
                    st.rerun()
                else:
                    update_session_parameters(ap["session_id"], expertise, sci, lang)
                    with st.spinner("Resynthesizing…"):
                        try:
                            doc = run_synthesis(ap["doc"], expertise, sci, lang,
                                                model=llm_model, api_key=llm_api_key)
                            save_cache(doc, expertise, sci, lang, model=llm_model)
                            st.session_state.papers[st.session_state.active_paper_idx]["doc"] = doc
                            st.session_state.papers[st.session_state.active_paper_idx]["rag_index"] = SectionIndex().build(doc)
                            st.success("Done ✓")
                            st.rerun()
                        except DailyTokenLimitError:
                            st.error("🚫 Daily limit reached.")
                        except InvalidAPIKeyError:
                            st.error("🔑 Key rejected.")
            else:
                st.session_state.reader_expertise     = expertise
                st.session_state.scientific_knowledge = sci
                st.session_state.language_complexity  = lang
                st.success("Parameters applied ✓")

        # cached profiles
        if ap:
            profiles = list_cached_profiles(ap["paper_id"])
            if profiles:
                st.markdown("---")
                st.caption("Cached profiles:")
                for p in profiles:
                    ml  = f" ({p['model_slug']})" if p.get("model_slug") else ""
                    lbl = f"E={p['reader_expertise']} S={p['scientific_knowledge']} L={p['language_complexity']}{ml}"
                    if st.button(lbl, key=f"cache_{p['file']}", use_container_width=True):
                        llm_model, _ = get_llm()
                        cached = load_cached(ap["paper_id"],
                                              p["reader_expertise"],
                                              p["scientific_knowledge"],
                                              p["language_complexity"],
                                              model=llm_model)
                        if cached:
                            st.session_state.papers[st.session_state.active_paper_idx]["doc"] = cached
                            st.session_state.papers[st.session_state.active_paper_idx]["rag_index"] = SectionIndex().build(cached)
                            st.session_state.reader_expertise     = p["reader_expertise"]
                            st.session_state.scientific_knowledge = p["scientific_knowledge"]
                            st.session_state.language_complexity  = p["language_complexity"]
                            st.rerun()

        st.markdown("---")
        st.caption("Panel widths")
        st.session_state.split_mid   = st.slider("Papers", 1, 5,
                                                   st.session_state.split_mid,   key="w_mid")
        st.session_state.split_right = st.slider("Content", 1, 9,
                                                   st.session_state.split_right, key="w_right")
    else:
        # page 1 — still persist slider values
        st.session_state.reader_expertise     = expertise
        st.session_state.scientific_knowledge = sci
        st.session_state.language_complexity  = lang


# ════════════════════════════════════════════════════════════════════
# PAGE 1 — MODE SELECTOR
# ════════════════════════════════════════════════════════════════════
if st.session_state.mode is None:
    st.markdown("## Research Paper Assistant")
    st.markdown("#### What would you like to do?")
    st.markdown("")

    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.markdown("##### 📄 Summary")
        st.markdown("Full pipeline: one-liner, arcs, 7 questions, math chain.")
        if st.button("Get Summary", use_container_width=True, type="primary", key="m_summary"):
            st.session_state.mode = "summary"
            st.rerun()
    with c2:
        st.markdown("##### 💬 Chat")
        st.markdown("Fast start — ask anything, grounded in the paper text.")
        if st.button("Chat with Paper", use_container_width=True, type="primary", key="m_chat"):
            st.session_state.mode = "chat"
            st.rerun()
    with c3:
        st.markdown("##### 🔬 Summary + Chat")
        st.markdown("Full pipeline then chat with summary as context.")
        if st.button("Summary + Chat", use_container_width=True, type="primary", key="m_both"):
            st.session_state.mode = "both"
            st.rerun()
    st.stop()


# ════════════════════════════════════════════════════════════════════
# PAGE 2 — WORKSPACE  (2-column: papers | content)
# ════════════════════════════════════════════════════════════════════
mode          = st.session_state.mode
needs_summary = mode in ("summary", "both")
needs_chat    = mode in ("chat", "both")
mode_label    = {"summary": "📄 Summary", "chat": "💬 Chat", "both": "🔬 Summary + Chat"}[mode]

# top bar: settings toggle | mode label
_tb_tog, _tb_title = st.columns([1, 8])
with _tb_tog:
    _icon = "◀" if st.session_state.sidebar_open else "▶"
    if st.button(_icon, key="tog_sidebar", help="Toggle settings panel"):
        st.session_state.sidebar_open = not st.session_state.sidebar_open
        st.rerun()
with _tb_title:
    st.markdown(f"**Research Paper Assistant** — {mode_label}")

col_papers, col_content = st.columns(
    [st.session_state.split_mid, st.session_state.split_right],
    gap="medium"
)

# ════════════════════════════════════════════════════════════════════
# LEFT COLUMN — papers panel
# ════════════════════════════════════════════════════════════════════
with col_papers:
    st.markdown("#### 📚 Papers")

    new_upload = st.file_uploader("Upload PDF", type="pdf", key="ws_upload",
                                   label_visibility="collapsed")
    if new_upload:
        pid     = new_upload.name.replace(".pdf", "")
        already = [p["paper_id"] for p in st.session_state.papers]
        if pid not in already:
            if st.button("➕ Add Paper", use_container_width=True, type="primary"):
                _check_key()
                llm_model, llm_api_key = get_llm()
                e = st.session_state.reader_expertise
                s = st.session_state.scientific_knowledge
                l = st.session_state.language_complexity
                prog = st.progress(0, text="Starting…")
                try:
                    if needs_summary:
                        cached = load_cached(pid, e, s, l, model=llm_model)
                        doc = cached if cached else _run_pipeline(
                            new_upload, e, s, l, llm_model, llm_api_key, prog)
                        if cached: prog.progress(100, text="Loaded from cache")
                    else:
                        with st.spinner("Parsing…"):
                            doc = _parse_only(new_upload)
                        prog.progress(100, text="Parsed")

                    idx     = SectionIndex().build(doc)
                    session = create_session(pid)
                    st.session_state.papers.append({
                        "paper_id":   pid,
                        "doc":        doc,
                        "rag_index":  idx,
                        "session_id": session["id"],
                        "pdf_path":   f"uploads/{new_upload.name}",
                    })
                    st.session_state.active_paper_idx = len(st.session_state.papers) - 1
                    st.session_state.chat_ready = True
                    st.rerun()
                except (DailyTokenLimitError, InvalidAPIKeyError) as exc:
                    prog.empty()
                    st.error(str(exc))
        else:
            st.caption(f"'{pid}' already open.")

    # paper list
    papers = st.session_state.papers
    if not papers:
        st.caption("No papers yet. Upload one above.")
    else:
        st.markdown("---")
        for i, p in enumerate(papers):
            is_active = (i == st.session_state.active_paper_idx)
            c_btn, c_x = st.columns([5, 1])
            with c_btn:
                lbl = f"{'▶ ' if is_active else ''}{p['paper_id'][:24]}"
                if st.button(lbl, key=f"sel_{i}", use_container_width=True,
                              type="primary" if is_active else "secondary"):
                    st.session_state.active_paper_idx = i
                    st.rerun()
            with c_x:
                if st.button("✕", key=f"del_{i}"):
                    st.session_state.papers.pop(i)
                    st.session_state.active_paper_idx = max(0, i - 1)
                    if not st.session_state.papers:
                        st.session_state.chat_ready = False
                    st.rerun()

    # PDF viewer
    ap = active_paper()
    if ap and ap.get("pdf_path") and os.path.exists(ap["pdf_path"]):
        st.markdown("---")
        pdf_height = st.slider("Viewer height", 300, 1400, 700, 50, key="pdf_h")
        with open(ap["pdf_path"], "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" '
            f'width="100%" height="{pdf_height}px" '
            f'style="border:1px solid #444;border-radius:4px;"></iframe>',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════════
# RIGHT COLUMN — summary + chat
# ════════════════════════════════════════════════════════════════════
with col_content:
    ap = active_paper()

    if not ap:
        st.markdown("#### 📄 Summary / 💬 Chat")
        st.info("Add a paper from the Papers panel to get started.")
    else:
        doc = ap["doc"]

        # ── summary ───────────────────────────────────────────────────
        if needs_summary:
            summary = doc.holistic_summary
            if not summary:
                st.info("Summary not generated yet.")
            else:
                st.info(summary.get("one_liner", ""))

                with st.expander("📖 Narrative Arcs", expanded=False):
                    ca, cb = st.columns(2)
                    with ca:
                        st.markdown("**Arc 1 — What it is**")
                        st.write(summary.get("arc1", ""))
                    with cb:
                        st.markdown("**Arc 2 — What it means**")
                        st.write(summary.get("arc2", ""))

                with st.expander("❓ 7 Questions", expanded=True):
                    questions = {
                        "Q1_problem":      "❓ What was broken?",
                        "Q2_insight":      "💡 Key insight?",
                        "Q3_mechanism":    "⚙️ How does it work?",
                        "Q4_evidence":     "✅ Does it work?",
                        "Q5_assumptions":  "🔍 Assumptions?",
                        "Q6_implications": "🌐 Implications?",
                        "Q7_limitations":  "⚠️ Limitations?",
                    }
                    for qkey, label in questions.items():
                        answer = summary.get(qkey, "")
                        if answer:
                            st.markdown(f"**{label}**")
                            st.write(answer)
                            st.markdown("")

                chain = doc.mathematical_chain
                if chain and chain.get("chains"):
                    with st.expander("📐 Mathematical Chain", expanded=False):
                        st.write(chain.get("mathematical_story", ""))
                        for ch in chain.get("chains", []):
                            st.markdown(f"**{ch['chain_id']}: {ch['name']}**")
                            st.write(ch["story"])
                            if ch.get("depends_on"):
                                st.caption(f"Depends on: {', '.join(ch['depends_on'])}")
                            for eq in ch.get("equations", []):
                                st.code(eq, language="latex")

        # ── chat ──────────────────────────────────────────────────────
        if needs_chat and st.session_state.chat_ready:
            st.markdown("---")
            n          = len(st.session_state.papers)
            chat_label = "💬 Chat" if n == 1 else f"💬 Chat ({n} papers)"
            with st.expander(chat_label, expanded=True):
                llm_model, llm_api_key = get_llm()

                for msg in st.session_state.chat_messages:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

                user_input = st.chat_input("Ask anything about the paper(s)…")
                if user_input:
                    with st.chat_message("user"):
                        st.markdown(user_input)
                    with st.chat_message("assistant"):
                        with st.spinner("Thinking…"):
                            try:
                                reply = chat_turn(
                                    user_message  = user_input,
                                    messages      = st.session_state.chat_messages,
                                    indices       = [p["rag_index"] for p in st.session_state.papers],
                                    paper_titles  = [p["doc"].title for p in st.session_state.papers],
                                    paper_ids     = [p["paper_id"] for p in st.session_state.papers],
                                    reader_params = reader_params(),
                                    model         = llm_model,
                                    api_key       = llm_api_key,
                                    turn_counter  = st.session_state.chat_turn_counter,
                                )
                                st.markdown(reply)
                            except DailyTokenLimitError:
                                st.error("🚫 Daily token limit reached.")
                            except InvalidAPIKeyError:
                                st.error("🔑 API key rejected.")
                            except Exception as e:
                                st.error(f"Error: {e}")

        elif needs_chat and not st.session_state.chat_ready:
            st.markdown("---")
            st.info("💬 Chat will appear once a paper is added.")
