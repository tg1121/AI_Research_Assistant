"""
Unified database layer.

  ADMIN_MODE=true  →  SQLAlchemy + SQLite  (data/papers.db)
  deployed         →  Supabase             (existing project)

Public API (same signatures both modes):
  save_paper(user_id, paper_id, title, detected_domain, pdf_size_bytes=0)
  get_papers(user_id)  →  list[dict]
  delete_paper(user_id, paper_id)
  check_storage_limit(user_id, new_bytes)   # raises StorageLimitError if over 100 MB (deployed only)
  get_user_storage_bytes(user_id)  →  int
"""

import os

_IS_LOCAL = os.environ.get("ADMIN_MODE", "").lower() == "true"
STORAGE_LIMIT_BYTES = 100 * 1024 * 1024  # 100 MB (deployed only)


class StorageLimitError(Exception):
    pass


# ── LOCAL (SQLite) ────────────────────────────────────────────────────

if _IS_LOCAL:
    from datetime import datetime, timezone
    from sqlalchemy import (
        Column, DateTime, Integer, String, UniqueConstraint,
        create_engine, func, text,
    )
    from sqlalchemy.orm import DeclarativeBase, Session

    os.makedirs("data", exist_ok=True)
    _engine = create_engine("sqlite:///data/papers.db", echo=False)

    class _Base(DeclarativeBase):
        pass

    class _Paper(_Base):
        __tablename__ = "papers"
        __table_args__ = (UniqueConstraint("paper_id", "user_id"),)
        id             = Column(Integer, primary_key=True, autoincrement=True)
        paper_id       = Column(String, nullable=False)
        user_id        = Column(String, nullable=False)
        title          = Column(String)
        uploaded_at    = Column(DateTime(timezone=True),
                                default=lambda: datetime.now(timezone.utc))
        detected_domain = Column(String)
        pdf_size_bytes = Column(Integer, default=0)

    _Base.metadata.create_all(_engine)

    def save_paper(user_id: str, paper_id: str, title: str,
                   detected_domain: str | None, pdf_size_bytes: int = 0):
        with Session(_engine) as s:
            row = s.query(_Paper).filter_by(
                user_id=user_id, paper_id=paper_id).first()
            if row:
                row.title           = title
                row.detected_domain = detected_domain
            else:
                s.add(_Paper(
                    paper_id=paper_id, user_id=user_id, title=title,
                    detected_domain=detected_domain,
                    pdf_size_bytes=pdf_size_bytes,
                    uploaded_at=datetime.now(timezone.utc),
                ))
            s.commit()

    def get_papers(user_id: str) -> list[dict]:
        with Session(_engine) as s:
            rows = (
                s.query(_Paper)
                .filter_by(user_id=user_id)
                .order_by(_Paper.uploaded_at.desc())
                .all()
            )
            return [
                {
                    "paper_id":        r.paper_id,
                    "title":           r.title or r.paper_id,
                    "uploaded_at":     r.uploaded_at.isoformat() if r.uploaded_at else None,
                    "detected_domain": r.detected_domain,
                    "pdf_size_bytes":  r.pdf_size_bytes or 0,
                }
                for r in rows
            ]

    def delete_paper(user_id: str, paper_id: str):
        with Session(_engine) as s:
            s.query(_Paper).filter_by(
                user_id=user_id, paper_id=paper_id).delete()
            s.commit()

    def get_user_storage_bytes(user_id: str) -> int:
        with Session(_engine) as s:
            total = s.query(
                func.sum(_Paper.pdf_size_bytes)
            ).filter_by(user_id=user_id).scalar()
            return total or 0

    def check_storage_limit(user_id: str, new_bytes: int):
        pass  # no limit for local admin


# ── DEPLOYED (Supabase) ───────────────────────────────────────────────

else:
    _sb = None

    def _client():
        global _sb
        if _sb is None:
            from supabase import create_client
            _sb = create_client(
                os.environ["SUPABASE_URL"],
                os.environ["SUPABASE_KEY"],
            )
        return _sb

    def save_paper(user_id: str, paper_id: str, title: str,
                   detected_domain: str | None, pdf_size_bytes: int = 0):
        _client().table("papers").upsert({
            "paper_id":        paper_id,
            "user_id":         user_id,
            "title":           title,
            "detected_domain": detected_domain,
            "pdf_size_bytes":  pdf_size_bytes,
        }).execute()

    def get_papers(user_id: str) -> list[dict]:
        result = (
            _client().table("papers")
            .select("paper_id,title,uploaded_at,detected_domain,pdf_size_bytes")
            .eq("user_id", user_id)
            .order("uploaded_at", desc=True)
            .execute()
        )
        return result.data or []

    def delete_paper(user_id: str, paper_id: str):
        _client().table("papers") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("paper_id", paper_id) \
            .execute()

    def get_user_storage_bytes(user_id: str) -> int:
        result = (
            _client().table("papers")
            .select("pdf_size_bytes")
            .eq("user_id", user_id)
            .execute()
        )
        return sum((r.get("pdf_size_bytes") or 0) for r in (result.data or []))

    def check_storage_limit(user_id: str, new_bytes: int):
        used = get_user_storage_bytes(user_id)
        if used + new_bytes > STORAGE_LIMIT_BYTES:
            used_mb = used / 1024 / 1024
            raise StorageLimitError(
                f"Storage limit reached ({used_mb:.1f} MB / 100 MB). "
                "Delete a paper to upload a new one."
            )
