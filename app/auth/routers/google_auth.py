"""
google_auth.py
--------------
Added two new endpoints:

  POST /auth/google/refresh
    - Frontend calls this when it receives a 401 (access token expired)
    - Backend reads the Google refresh token from MongoDB
    - Calls Google to get a new Google access token
    - Issues a new 15-minute JWT
    - Frontend retries the original request silently
    - User never sees any interruption

  POST /auth/google/logout
    - Clears the user session
    - Frontend redirects to landing page
"""

import httpx
import requests

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from urllib.parse import urlencode

from app.auth.dependencies import get_current_user
from app.auth.repositories.user_repository import save_user, get_user
from app.auth.services.google_oauth_service import get_google_login_url
from app.auth.services.jwt_service import create_access_token
from app.common.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    FRONTEND_URL,
)
from app.common.db import db
from app.common.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/auth/google",
    tags=["Google Auth"],
)

REQUIRED_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


# ── Login ─────────────────────────────────────────────────────────────────────

@router.get("/login")
async def login():
    return RedirectResponse(get_google_login_url())


# ── OAuth Callback ────────────────────────────────────────────────────────────

@router.get("/callback")
async def callback(code: str = None, error: str = None, scope: str = None):

    if error:
        logger.warning(f"Google OAuth denied by user: {error}")
        params = urlencode({
            "error":   "access_denied",
            "message": "You need to grant Gmail access for JobIQ to track your job applications. Please try again and allow all requested permissions.",
        })
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/error?{params}", status_code=302)

    if not code:
        params = urlencode({
            "error":   "no_code",
            "message": "Authentication failed. Please try again.",
        })
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/error?{params}", status_code=302)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  GOOGLE_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )

    token_data    = response.json()
    access_token  = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token:
        logger.error(f"Failed to get access token: {token_data}")
        params = urlencode({
            "error":   "token_failed",
            "message": "Failed to authenticate with Google. Please try again.",
        })
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/error?{params}", status_code=302)

    granted_scopes = token_data.get("scope", "") or scope or ""
    if REQUIRED_GMAIL_SCOPE not in granted_scopes:
        logger.warning(f"User did not grant Gmail scope. Granted: {granted_scopes}")
        params = urlencode({
            "error":   "missing_gmail_scope",
            "message": (
                "JobIQ needs access to your Gmail to automatically track job applications. "
                "Please sign in again and check the box next to "
                "'View your email messages and settings'."
            ),
        })
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/error?{params}", status_code=302)

    user_info = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    if not user_info.get("email"):
        params = urlencode({
            "error":   "no_email",
            "message": "Could not retrieve your Google account details. Please try again.",
        })
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/error?{params}", status_code=302)

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

    return RedirectResponse(url=f"{FRONTEND_URL}/auth/success?{params}", status_code=302)


# ── Refresh Token ─────────────────────────────────────────────────────────────

class RefreshRequest(BaseModel):
    email: str


@router.post("/refresh")
async def refresh_token(payload: RefreshRequest):
    """
    Called by the frontend when a 401 is received (JWT expired).

    Flow:
      1. Frontend receives 401 on any API call
      2. Frontend calls POST /auth/google/refresh with { email }
      3. Backend reads Google refresh token from MongoDB
      4. Backend calls Google token endpoint to get new access token
      5. Backend issues new 15-minute JWT
      6. Frontend stores new JWT, retries original request
      7. User never sees any interruption

    If Google refresh fails (user revoked access):
      → Returns 401 → frontend redirects to login
    """
    user = db.db["users"].find_one({"email": payload.email})

    if not user:
        raise HTTPException(status_code=401, detail="User not found. Please sign in again.")

    google_refresh_token = user.get("refresh_token")

    if not google_refresh_token:
        raise HTTPException(
            status_code=401,
            detail="No refresh token available. Please sign in again.",
        )

    # Call Google to get a new access token using the stored refresh token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": google_refresh_token,
                "grant_type":    "refresh_token",
            },
        )

    token_data = response.json()

    if "error" in token_data:
        logger.warning(f"Google refresh failed for {payload.email}: {token_data}")
        raise HTTPException(
            status_code=401,
            detail="Session expired. Please sign in again.",
        )

    new_google_access_token = token_data.get("access_token")

    # Update the stored Google access token
    db.db["users"].update_one(
        {"email": payload.email},
        {"$set": {"access_token": new_google_access_token}},
    )

    # Issue a new short-lived JWT
    new_jwt = create_access_token(payload.email)

    logger.info(f"Token refreshed for {payload.email}")

    return {
        "token": new_jwt,
        "email": payload.email,
    }


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(current_user: str = Depends(get_current_user)):
    """
    Logs the user out. Frontend should clear the token from memory
    and redirect to the landing page.
    """
    logger.info(f"User logged out: {current_user}")
    return {"message": "Logged out successfully."}