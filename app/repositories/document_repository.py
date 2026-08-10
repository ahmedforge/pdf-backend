from sqlalchemy import select

from app.database import SessionLocal
from app.models.document import Document


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


def delete_document(document_id: int, owner_id: int):
    with SessionLocal() as db:
        document = db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.owner_id == owner_id
            )
        )

        if document:
            db.delete(document)
            db.commit()