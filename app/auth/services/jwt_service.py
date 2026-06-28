import jwt
from datetime import datetime, timedelta

from app.common.config import SECRET_KEY


def create_access_token(email: str):

    payload = {
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=7),
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm="HS256",
    )


def verify_token(token: str):

    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=["HS256"],
    )