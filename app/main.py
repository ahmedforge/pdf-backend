from fastapi import FastAPI
from app.routers.documents import router as documents_router


app = FastAPI()

app.include_router(documents_router)


@app.get("/")
def home():
    return {"message": "Backend is running"}


@app.get("/about")
def about():
    return {"project": "PDF BACKEND stuff"}