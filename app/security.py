from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from app.config import settings
from app.repositories.user_repository import get_user_by_id


password_hash = PasswordHash.recommended()

SECRET_KEY = settings.jwt_secret_key
ALGORITHM = "HS256"

bearer_scheme = HTTPBearer()


def hash_password(password: str):
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str):
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int):
    expires = datetime.now(timezone.utc) + timedelta(minutes=60)

    payload = {
        "sub": str(user_id),
        "exp": expires
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = int(payload["sub"])

    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    user = get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    if payload.get("guest") is True:
        from app.services.guest_demo import authorize_guest
        user.guest_document_id = authorize_guest(payload, request.method, request.url.path)

    return user

def create_guest_token(document):
    return jwt.encode({
        "sub": str(document.owner_id), "guest": True,
        "guest_document_id": document.id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=20),
    }, SECRET_KEY, algorithm=ALGORITHM)
