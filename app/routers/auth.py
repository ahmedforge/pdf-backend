from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.repositories.user_repository import (
    create_user,
    get_user_by_email
)

from app.security import (
    hash_password,
    verify_password,
    create_access_token
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
def register(data: RegisterRequest):
    email = data.email.lower()

    existing_user = get_user_by_email(email)

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    hashed_password = hash_password(data.password)

    user = create_user(
        email=email,
        hashed_password=hashed_password
    )
    logger.info("User registered: %s", user.email)

    return {
        "message": "User registered successfully",
        "id": user.id,
        "email": user.email
    }
@router.post("/login")
def login(data: LoginRequest):
    user = get_user_by_email(data.email.lower())

    if not user or not verify_password(
        data.password,
        user.hashed_password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    access_token = create_access_token(user.id)
    logger.info("User logged in: %s", user.email)
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }