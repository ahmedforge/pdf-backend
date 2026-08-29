from fastapi import APIRouter, HTTPException
from sqlalchemy import text
import httpx
from app.config import settings

from app.database import SessionLocal



router = APIRouter(
    prefix="/health",
    tags=["health"],
)


@router.get("/live")
def health_live():
    return {
        "status": "ok",
    }


@router.get("/ready")
def health_ready():
    checks = {
        "database": False,
        "llm": False,
    }

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))

        checks["database"] = True

    except Exception:
        pass

    try:
        response = httpx.get(
            "http://127.0.0.1:11434/api/tags",
            timeout=3.0,
        )
        response.raise_for_status()

        checks["llm"] = True

    except Exception:
        pass

    if not all(checks.values()):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "checks": checks,
            },
        )

    return {
        "status": "ready",
        "checks": checks,
    }