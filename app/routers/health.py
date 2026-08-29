import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.config import settings
from app.database import engine

router = APIRouter()


@router.get("/health/live")
def health_live():
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready():
    checks = {
        "database": False,
        "llm": False,
    }

    # Database check
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    # LLM check
    try:
        if settings.llm_provider == "ollama":
            response = httpx.get(
                "http://127.0.0.1:11434/api/tags",
                timeout=5.0,
            )
            response.raise_for_status()
            checks["llm"] = True

        elif settings.llm_provider == "groq":
            if not settings.groq_api_key:
                raise RuntimeError("GROQ_API_KEY is not configured")

            response = httpx.get(
                "https://api.groq.com/openai/v1/models",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                },
                timeout=10.0,
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