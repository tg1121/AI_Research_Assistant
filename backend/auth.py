import os
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_IS_LOCAL = os.environ.get("ADMIN_MODE", "").lower() == "true"

# auto_error=False so we can skip auth entirely in ADMIN_MODE without a 403
security = HTTPBearer(auto_error=not _IS_LOCAL)

ADMIN_USER_ID = "00000000-0000-0000-0000-000000000000"


class _AdminUser:
    id    = ADMIN_USER_ID
    email = "admin@local"


def _supabase():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY not set")
    return create_client(url, key)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if _IS_LOCAL:
        return _AdminUser()
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing token")
    token = credentials.credentials
    try:
        response = _supabase().auth.get_user(token)
        if not response.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return response.user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
