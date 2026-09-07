from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

@app.get("/healthcheck")
async def healthcheck():
    return {"status": "ok", "project": settings.PROJECT_NAME}
