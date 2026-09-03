from fastapi import FastAPI, UploadFile, File, HTTPException
from app.routers.documents import router as documents_router
from fastapi.responses import FileResponse
from pypdf import PdfReader
from datetime import datetime
from app.routers.auth import router as auth_router
import app.logging_config
from contextlib import asynccontextmanager
from app.routers import health
from fastapi.middleware.cors import CORSMiddleware

from app.services.embedding_service import get_embedding_model
from app.services.llm.factory import get_llm_provider
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm embedding model
    get_embedding_model()

    # Warm LLM
    llm = get_llm_provider()
    try:
        llm.generate("Reply with OK.")
    except RuntimeError as exc:
        print(f"[STARTUP] LLM warmup skipped: {exc}")

    yield
app = FastAPI(
    title="PDF Backend",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents_router)
app.include_router(health.router)
app.include_router(auth_router)

def extract_text_from_pdf(file_path: str):
    reader = PdfReader(file_path)

    text = ""

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return reader, text


@app.get("/")
def home():
    return {"message": "Backend is running"}


@app.get("/about")
def about():
    return {"project": "PDF BACKEND stuff"}




