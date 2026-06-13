"""
Session + feedback parameter manager.

  ADMIN_MODE=true  →  SQLAlchemy + SQLite  (data/papers.db)
  deployed         →  Supabase             (existing project)
"""

import os
import uuid

_IS_LOCAL = os.environ.get("ADMIN_MODE", "").lower() == "true"

FEEDBACK_SHIFT = 0.15
THRESHOLD = 3


# ── LOCAL (SQLite) ────────────────────────────────────────────────────

if _IS_LOCAL:
    from datetime import datetime, timezone
    from sqlalchemy import (
        Column, DateTime, Float, Integer, String,
        create_engine, text,
    )
    from sqlalchemy.orm import DeclarativeBase, Session

    os.makedirs("data", exist_ok=True)
    _engine = create_engine("sqlite:///data/papers.db", echo=False)

    class _Base(DeclarativeBase):
        pass

    class _Session(_Base):
        __tablename__ = "sessions"
        id                   = Column(String, primary_key=True,
                                      default=lambda: str(uuid.uuid4()))
        paper_id             = Column(String, nullable=False)
        user_id              = Column(String)
        reader_expertise     = Column(Float, default=0.0)
        scientific_knowledge = Column(Float, default=0.0)
        language_complexity  = Column(Float, default=0.0)
        created_at           = Column(DateTime(timezone=True),
                                      default=lambda: datetime.now(timezone.utc))
        updated_at           = Column(DateTime(timezone=True),
                                      default=lambda: datetime.now(timezone.utc),
                                      onupdate=lambda: datetime.now(timezone.utc))

    class _Feedback(_Base):
        __tablename__ = "feedback"
        id               = Column(Integer, primary_key=True, autoincrement=True)
        session_id       = Column(String, nullable=False)
        paper_id         = Column(String, nullable=False)
        question         = Column(String)
        direction        = Column(String)
        reason           = Column(String)
        expertise_before = Column(Float)
        expertise_after  = Column(Float)
        user_id          = Column(String)
        created_at       = Column(DateTime(timezone=True),
                                  default=lambda: datetime.now(timezone.utc))

    class _ParamDefaults(_Base):
        __tablename__ = "parameter_defaults"
        id                   = Column(Integer, primary_key=True, autoincrement=True)
        reader_expertise     = Column(Float, default=0.0)
        scientific_knowledge = Column(Float, default=0.0)
        language_complexity  = Column(Float, default=0.0)
        sample_count         = Column(Integer, default=0)
        updated_at           = Column(DateTime(timezone=True),
                                      default=lambda: datetime.now(timezone.utc))

    _Base.metadata.create_all(_engine)

    # Seed defaults row if absent
    with Session(_engine) as _s:
        if not _s.query(_ParamDefaults).first():
            _s.add(_ParamDefaults())
            _s.commit()

    # ── public API ────────────────────────────────────────────────────

    def create_session(paper_id: str, user_id: str | None = None) -> dict:
        defaults = get_global_defaults()
        sid = str(uuid.uuid4())
        row = _Session(
            id=sid, paper_id=paper_id, user_id=user_id,
            reader_expertise=defaults["reader_expertise"],
            scientific_knowledge=defaults["scientific_knowledge"],
            language_complexity=defaults["language_complexity"],
        )
        with Session(_engine) as s:
            s.add(row)
            s.commit()
        return {"id": sid, "paper_id": paper_id, **defaults}

    def get_session(session_id: str) -> dict | None:
        with Session(_engine) as s:
            row = s.get(_Session, session_id)
            if not row:
                return None
            return {
                "id": row.id, "paper_id": row.paper_id,
                "reader_expertise": row.reader_expertise,
                "scientific_knowledge": row.scientific_knowledge,
                "language_complexity": row.language_complexity,
            }

    def update_session_parameters(session_id: str, reader_expertise: float,
                                   scientific_knowledge: float | None = None,
                                   language_complexity: float | None = None) -> dict:
        if scientific_knowledge is None:
            scientific_knowledge = reader_expertise
        if language_complexity is None:
            language_complexity = reader_expertise
        reader_expertise     = max(0.0, min(1.0, reader_expertise))
        scientific_knowledge = max(0.0, min(1.0, scientific_knowledge))
        language_complexity  = max(0.0, min(1.0, language_complexity))

        with Session(_engine) as s:
            row = s.get(_Session, session_id)
            if row:
                row.reader_expertise     = reader_expertise
                row.scientific_knowledge = scientific_knowledge
                row.language_complexity  = language_complexity
                row.updated_at           = datetime.now(timezone.utc)
                s.commit()
        return get_session(session_id) or {}

    def record_feedback(session_id: str, paper_id: str, question: str,
                        direction: str, reason: str, expertise_before: float,
                        expertise_after: float, user_id: str | None = None):
        with Session(_engine) as s:
            s.add(_Feedback(
                session_id=session_id, paper_id=paper_id, question=question,
                direction=direction, reason=reason,
                expertise_before=expertise_before, expertise_after=expertise_after,
                user_id=user_id,
            ))
            s.commit()
        _check_and_update_defaults(question, direction)

    def apply_feedback(session: dict, direction: str) -> dict:
        expertise = session["reader_expertise"]
        sci       = session["scientific_knowledge"]
        lang      = session["language_complexity"]
        if direction == "too_technical":
            expertise = sci = lang = expertise - FEEDBACK_SHIFT
        elif direction == "too_simple":
            expertise = sci = lang = expertise + FEEDBACK_SHIFT
        elif direction == "language_too_hard":
            lang = lang - FEEDBACK_SHIFT
        elif direction == "more_math":
            sci = sci + FEEDBACK_SHIFT
        return update_session_parameters(session["id"], expertise, sci, lang)

    def get_global_defaults() -> dict:
        with Session(_engine) as s:
            row = s.query(_ParamDefaults).first()
            return {
                "reader_expertise":     row.reader_expertise     if row else 0.0,
                "scientific_knowledge": row.scientific_knowledge if row else 0.0,
                "language_complexity":  row.language_complexity  if row else 0.0,
            }

    def _check_and_update_defaults(question: str, direction: str):
        with Session(_engine) as s:
            count = s.query(_Feedback).filter_by(direction=direction).count()
        if count >= THRESHOLD and count % THRESHOLD == 0:
            defaults = get_global_defaults()
            shift = FEEDBACK_SHIFT if "simple" in direction or "math" in direction else -FEEDBACK_SHIFT
            new_val = max(0.0, min(1.0, defaults["reader_expertise"] + shift))
            with Session(_engine) as s:
                row = s.query(_ParamDefaults).first()
                if row:
                    row.reader_expertise     = new_val
                    row.scientific_knowledge = new_val
                    row.language_complexity  = new_val
                    row.sample_count         = count
                    row.updated_at           = datetime.now(timezone.utc)
                    s.commit()
            print(f"Global defaults updated: reader_expertise → {new_val}")


# ── DEPLOYED (Supabase) ───────────────────────────────────────────────

else:
    from supabase import create_client as _create_client

    _sb = _create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )

    def create_session(paper_id: str, user_id: str | None = None) -> dict:
        defaults = get_global_defaults()
        row = {"paper_id": paper_id,
               "reader_expertise":     defaults["reader_expertise"],
               "scientific_knowledge": defaults["scientific_knowledge"],
               "language_complexity":  defaults["language_complexity"]}
        if user_id:
            row["user_id"] = user_id
        result = _sb.table("sessions").insert(row).execute()
        return result.data[0]

    def get_session(session_id: str) -> dict | None:
        result = _sb.table("sessions").select("*").eq("id", session_id).execute()
        return result.data[0] if result.data else None

    def update_session_parameters(session_id: str, reader_expertise: float,
                                   scientific_knowledge: float | None = None,
                                   language_complexity: float | None = None) -> dict:
        if scientific_knowledge is None:
            scientific_knowledge = reader_expertise
        if language_complexity is None:
            language_complexity = reader_expertise
        reader_expertise     = max(0.0, min(1.0, reader_expertise))
        scientific_knowledge = max(0.0, min(1.0, scientific_knowledge))
        language_complexity  = max(0.0, min(1.0, language_complexity))
        result = _sb.table("sessions").update({
            "reader_expertise":     reader_expertise,
            "scientific_knowledge": scientific_knowledge,
            "language_complexity":  language_complexity,
            "updated_at":           "now()",
        }).eq("id", session_id).execute()
        return result.data[0]

    def record_feedback(session_id: str, paper_id: str, question: str,
                        direction: str, reason: str, expertise_before: float,
                        expertise_after: float, user_id: str | None = None):
        row = {"session_id": session_id, "paper_id": paper_id,
               "question": question, "direction": direction, "reason": reason,
               "expertise_before": expertise_before, "expertise_after": expertise_after}
        if user_id:
            row["user_id"] = user_id
        _sb.table("feedback").insert(row).execute()
        _check_and_update_defaults(question, direction)

    def apply_feedback(session: dict, direction: str) -> dict:
        expertise = session["reader_expertise"]
        sci       = session["scientific_knowledge"]
        lang      = session["language_complexity"]
        if direction == "too_technical":
            expertise = sci = lang = expertise - FEEDBACK_SHIFT
        elif direction == "too_simple":
            expertise = sci = lang = expertise + FEEDBACK_SHIFT
        elif direction == "language_too_hard":
            lang = lang - FEEDBACK_SHIFT
        elif direction == "more_math":
            sci = sci + FEEDBACK_SHIFT
        return update_session_parameters(session["id"], expertise, sci, lang)

    def get_global_defaults() -> dict:
        result = _sb.table("parameter_defaults").select("*").limit(1).execute()
        if result.data:
            return result.data[0]
        return {"reader_expertise": 0.0, "scientific_knowledge": 0.0,
                "language_complexity": 0.0}

    def _check_and_update_defaults(question: str, direction: str):
        result = _sb.table("feedback").select("id").eq("direction", direction).execute()
        count = len(result.data)
        if count >= THRESHOLD and count % THRESHOLD == 0:
            defaults = get_global_defaults()
            shift = FEEDBACK_SHIFT if "simple" in direction or "math" in direction else -FEEDBACK_SHIFT
            new_val = max(0.0, min(1.0, defaults["reader_expertise"] + shift))
            _sb.table("parameter_defaults").update({
                "reader_expertise":     new_val,
                "scientific_knowledge": new_val,
                "language_complexity":  new_val,
                "sample_count":         count,
                "updated_at":           "now()",
            }).eq("id", defaults["id"]).execute()
            print(f"Global defaults updated: reader_expertise → {new_val}")
