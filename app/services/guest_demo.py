"""Public sample access: no accounts per visitor, no uploaded private documents."""
from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.document import Document


def get_demo_document():
    document_id = settings.guest_demo_document_id
    if not document_id:
        raise HTTPException(503, "The guest demo is temporarily unavailable. Please sign in or try again later.")
    with SessionLocal() as db:
        document = db.scalar(select(Document).where(Document.id == document_id))
    if document is None or document.owner_id is None:
        raise HTTPException(503, "The guest demo is temporarily unavailable. Please sign in or try again later.")
    return document


def authorize_guest(payload, method, path):
    document = get_demo_document()
    if payload.get('guest_document_id') != document.id or payload.get('sub') != str(document.owner_id):
        raise HTTPException(401, "This demo session expired. Please start the demo again.")
    allowed = {
        ('GET', '/files'),
        ('GET', f'/download/{document.id}'),
        ('POST', f'/files/{document.id}/ask'),
        ('POST', f'/files/{document.id}/ask/stream'),
    }
    if (method, path) not in allowed:
        raise HTTPException(403, "Guest access is limited to reading and asking about the sample PDF. Sign in to use your own documents.")
    return document.id
