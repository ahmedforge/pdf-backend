from fastapi import FastAPI, UploadFile, File, HTTPException
from app.routers.documents import router as documents_router
from fastapi.responses import FileResponse
from pypdf import PdfReader
from datetime import datetime
from app.routers.auth import router as auth_router

app = FastAPI()
app.include_router(documents_router)
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




