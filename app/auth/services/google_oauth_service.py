from urllib.parse import urlencode

from app.common.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
)

REDIRECT_URI = "http://localhost:8000/auth/google/callback"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly", 
]


def get_google_login_url():

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }

    return (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(params)
    )