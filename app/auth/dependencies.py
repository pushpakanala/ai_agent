from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.services.jwt_service import verify_token


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):

    token = credentials.credentials

    try:
        payload = verify_token(token)
        return payload["email"]

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )