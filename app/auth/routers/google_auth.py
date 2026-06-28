import httpx
import requests

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.auth.repositories.user_repository import save_user
from app.auth.services.google_oauth_service import (
    get_google_login_url,
)
from app.auth.services.jwt_service import (
    create_access_token,
)
from app.common.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
)


router = APIRouter(
    prefix="/auth/google",
    tags=["Google Auth"],
)


@router.get("/login")
async def login():

    return RedirectResponse(
        get_google_login_url()
    )


@router.get("/callback")
async def callback(code: str):

    print("STEP 1: Google callback reached")

    token_url = "https://oauth2.googleapis.com/token"

    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": "http://localhost:8000/auth/google/callback",
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:

        response = await client.post(
            token_url,
            data=data,
        )

    token_data = response.json()

    print("TOKEN DATA:", token_data)

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    print("ACCESS TOKEN EXISTS:", access_token is not None)
    print("REFRESH TOKEN EXISTS:", refresh_token is not None)

    if not access_token:
        return {
            "status": "error",
            "message": "Failed to get access token",
            "google_response": token_data,
        }

    # Get Google user details
    user_info = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
    ).json()

    print("USER INFO:", user_info)

    # Save into MongoDB
    await save_user(
        email=user_info["email"],
        name=user_info.get("name", ""),
        access_token=access_token,
        refresh_token=refresh_token,
    )

    print("USER SAVED TO MONGO")

    # Create JWT token for frontend
    jwt_token = create_access_token(
        user_info["email"]
    )

    return {
        "status": "success",
        "token": jwt_token,
        "user": {
            "email": user_info["email"],
            "name": user_info.get("name", ""),
            "picture": user_info.get("picture"),
        }
    }