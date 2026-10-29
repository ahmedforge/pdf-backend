from sqlalchemy import select, or_

from app.database import SessionLocal
from app.models.document import Document
from app.models.pending_upload import PendingUpload


def insert_document(filename, size_bytes, uploaded_at, owner_id):
    with SessionLocal() as db:
        document = Document(
            filename=filename,
            size_bytes=size_bytes,
            uploaded_at=uploaded_at,
            owner_id=owner_id
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        return document


def get_all_documents(owner_id: int):
    with SessionLocal() as db:
        documents = db.scalars(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.id.desc())
        ).all()

        return [
            {
                "id": document.id,
                "filename": document.filename,
                "display_name": document.display_name or document.filename,
                "size_bytes": document.size_bytes,
                "uploaded_at": document.uploaded_at
            }
            for document in documents
        ]


def get_document_by_id(document_id: int, owner_id: int):
    with SessionLocal() as db:
        return db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.owner_id == owner_id
            )
        )


def local_storage_key_in_use(key):
    # Never reuse a legacy path, a live key, or an outstanding deletion key.
    with SessionLocal() as db:
        return db.scalar(select(Document.id).where(or_(
            Document.storage_key == key,
            (Document.storage_key.is_(None)) & (Document.filename == key),
        )).limit(1)) is not None or db.get(PendingUpload, key) is not None


def rename_document(document_id, owner_id, display_name):
    with SessionLocal.begin() as db:
        document = db.scalar(select(Document).where(
            Document.id == document_id, Document.owner_id == owner_id,
        ).with_for_update())
        if document is None:
            return None
        document.display_name = display_name
    return document


def delete_document(document_id: int, owner_id: int):
    # Storage deletion follows commit; the row and its retry marker are atomic.
    with SessionLocal.begin() as db:
        document = db.scalar(select(Document).where(
            Document.id == document_id, Document.owner_id == owner_id,
        ).with_for_update())
        if document is None:
            return None
        key = document.storage_key or document.filename
        marker = db.scalar(select(PendingUpload).where(
            PendingUpload.storage_key == key,
        ).with_for_update())
        if marker is None:
            db.add(PendingUpload(storage_key=key))
        db.delete(document)
    return document
