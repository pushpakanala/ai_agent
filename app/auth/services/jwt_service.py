import jwt
from datetime import datetime, timedelta
from app.common.config import SECRET_KEY


def create_access_token(email: str) -> str:
    """
    Short-lived access token — 15 minutes.
    When this expires the frontend calls /auth/refresh to get a new one
    using the Google refresh token stored in MongoDB.
    User never has to log in again unless they revoke Google access.
    """
    payload = {
        "email": email,
        "exp":   datetime.utcnow() + timedelta(minutes=15),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])