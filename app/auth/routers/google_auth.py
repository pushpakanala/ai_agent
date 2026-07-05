"""
google_auth.py
--------------
Google OAuth router.

FIXES:
  1. Checks granted scopes after callback — if Gmail scope missing,
     redirects user back to login with a clear error message instead
     of silently creating a broken account.
  2. Handles the `error` query param Google sends when user denies access.
  3. Removed all print() statements — replaced with logger.
"""

import httpx
import requests

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

from app.auth.repositories.user_repository import save_user
from app.auth.services.google_oauth_service import get_google_login_url
from app.auth.services.jwt_service import create_access_token
from app.common.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    FRONTEND_URL,
)
from app.common.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/auth/google",
    tags=["Google Auth"],
)

# Gmail scope required for the job tracker to work
REQUIRED_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@router.get("/login")
async def login():
    return RedirectResponse(get_google_login_url())


@router.get("/callback")
async def callback(code: str = None, error: str = None, scope: str = None):
    """
    Google OAuth callback.

    Handles three cases:
    1. User denied access entirely  → error param is set
    2. User granted partial access  → check granted scopes
    3. User granted full access     → normal login flow
    """

    # ── Case 1: User clicked "Deny" or cancelled ──────────────────────────
    if error:
        logger.warning(f"Google OAuth denied by user: {error}")
        params = urlencode({
            "error": "access_denied",
            "message": "You need to grant Gmail access for JobIQ to track your job applications. Please try again and allow all requested permissions.",
        })
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/error?{params}",
            status_code=302,
        )

    if not code:
        params = urlencode({
            "error": "no_code",
            "message": "Authentication failed. Please try again.",
        })
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/error?{params}",
            status_code=302,
        )

    # ── Exchange code for tokens ───────────────────────────────────────────
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code":          code,
        "client_id":     GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "grant_type":    "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)

    token_data = response.json()
    access_token  = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token:
        logger.error(f"Failed to get access token: {token_data}")
        params = urlencode({
            "error": "token_failed",
            "message": "Failed to authenticate with Google. Please try again.",
        })
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/error?{params}",
            status_code=302,
        )

    # ── Case 2: Check granted scopes ──────────────────────────────────────
    # Google returns granted scopes in the token response
    granted_scopes = token_data.get("scope", "") or scope or ""

    if REQUIRED_GMAIL_SCOPE not in granted_scopes:
        logger.warning(f"User did not grant Gmail scope. Granted: {granted_scopes}")
        params = urlencode({
            "error": "missing_gmail_scope",
            "message": (
                "JobIQ needs access to your Gmail to automatically track job applications. "
                "Please sign in again and check the box next to "
                "'View your email messages and settings'."
            ),
        })
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/error?{params}",
            status_code=302,
        )

    # ── Case 3: Full access granted — normal login flow ───────────────────
    user_info = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    if not user_info.get("email"):
        params = urlencode({
            "error": "no_email",
            "message": "Could not retrieve your Google account details. Please try again.",
        })
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/error?{params}",
            status_code=302,
        )

    await save_user(
        email=user_info["email"],
        name=user_info.get("name", ""),
        access_token=access_token,
        refresh_token=refresh_token,
    )

    logger.info(f"User logged in: {user_info['email']}")

    jwt_token = create_access_token(user_info["email"])

    params = urlencode({
        "token":   jwt_token,
        "email":   user_info["email"],
        "name":    user_info.get("name", ""),
        "picture": user_info.get("picture", ""),
    })

    return RedirectResponse(
        url=f"{FRONTEND_URL}/auth/success?{params}",
        status_code=302,
    )