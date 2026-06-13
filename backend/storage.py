"""
PDF storage layer.

  ADMIN_MODE=true  →  local filesystem  (uploads/)
  deployed         →  Supabase Storage  (bucket: "papers")

Public API:
  save_pdf(user_id, paper_id, content)  →  local_path
  get_signed_url(user_id, paper_id)     →  str | None
  ensure_local(user_id, paper_id)       →  local_path | None
  delete_pdf(user_id, paper_id)
  exists_locally(paper_id)              →  bool
"""

import os

_IS_LOCAL   = os.environ.get("ADMIN_MODE", "").lower() == "true"
BUCKET      = "papers"
_UPLOAD_DIR = "uploads"


def _client():
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def save_pdf(user_id: str, paper_id: str, content: bytes) -> str:
    """Save PDF content. Always writes a local temp copy for the pipeline."""
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    local_path = f"{_UPLOAD_DIR}/{paper_id}.pdf"
    with open(local_path, "wb") as f:
        f.write(content)

    if not _IS_LOCAL:
        remote_path = f"{user_id}/{paper_id}.pdf"
        try:
            _client().storage.from_(BUCKET).upload(
                remote_path, content,
                {"content-type": "application/pdf", "upsert": "true"},
            )
        except Exception as e:
            print(f"[storage] upload failed: {e}")

    return local_path


def get_signed_url(user_id: str, paper_id: str, expires_in: int = 3600) -> str | None:
    """Return a short-lived signed URL (deployed only). None in local mode."""
    if _IS_LOCAL:
        return None
    remote_path = f"{user_id}/{paper_id}.pdf"
    try:
        resp = _client().storage.from_(BUCKET).create_signed_url(remote_path, expires_in)
        return resp.get("signedURL") or resp.get("signed_url")
    except Exception as e:
        print(f"[storage] get_signed_url failed: {e}")
        return None


def ensure_local(user_id: str, paper_id: str) -> str | None:
    """Ensure PDF exists locally, downloading from Supabase if necessary."""
    local_path = f"{_UPLOAD_DIR}/{paper_id}.pdf"
    if os.path.exists(local_path):
        return local_path
    if _IS_LOCAL:
        return None
    remote_path = f"{user_id}/{paper_id}.pdf"
    try:
        data = _client().storage.from_(BUCKET).download(remote_path)
        os.makedirs(_UPLOAD_DIR, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
        return local_path
    except Exception as e:
        print(f"[storage] download failed: {e}")
        return None


def delete_pdf(user_id: str, paper_id: str):
    """Delete PDF from local disk and (deployed) Supabase Storage."""
    local_path = f"{_UPLOAD_DIR}/{paper_id}.pdf"
    if os.path.exists(local_path):
        try:
            os.remove(local_path)
        except OSError:
            pass
    if not _IS_LOCAL:
        remote_path = f"{user_id}/{paper_id}.pdf"
        try:
            _client().storage.from_(BUCKET).remove([remote_path])
        except Exception as e:
            print(f"[storage] delete failed: {e}")


def exists_locally(paper_id: str) -> bool:
    return os.path.exists(f"{_UPLOAD_DIR}/{paper_id}.pdf")
