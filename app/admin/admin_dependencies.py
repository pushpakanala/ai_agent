"""
admin_dependencies.py
---------------------
Admin auth guard — extends the existing get_current_user dependency.

Set ADMIN_EMAILS env var on Render (comma-separated):
    ADMIN_EMAILS=pushpakpraneeth.anala@gmail.com,jobiqservices@gmail.com

Only those emails can access /admin/* endpoints.
Everyone else gets 403 immediately.
"""

import os
from fastapi import Depends, HTTPException
from app.auth.dependencies import get_current_user

_raw = os.getenv("ADMIN_EMAILS", "")
ADMIN_EMAILS = {e.strip().lower() for e in _raw.split(",") if e.strip()}


async def require_admin(
    current_user: str = Depends(get_current_user),
) -> str:
    if not ADMIN_EMAILS:
        raise HTTPException(
            status_code=503,
            detail="Admin access not configured. Set ADMIN_EMAILS env var.",
        )
    if current_user.lower() not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=403,
            detail="Admin access required.",
        )
    return current_user