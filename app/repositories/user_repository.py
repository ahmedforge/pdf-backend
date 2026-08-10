from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import User


def get_user_by_email(email: str):
    with SessionLocal() as db:
        return db.scalar(
            select(User).where(User.email == email)
        )


def create_user(email: str, hashed_password: str):
    with SessionLocal() as db:
        user = User(
            email=email,
            hashed_password=hashed_password
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user
def get_user_by_id(user_id: int):
    with SessionLocal() as db:
        return db.get(User, user_id)