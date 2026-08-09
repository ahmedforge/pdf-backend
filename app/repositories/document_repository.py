from app.database import SessionLocal
from app.models.document import Document


def insert_document(filename, size_bytes, uploaded_at):
    with SessionLocal() as db:
        document = Document(
            filename=filename,
            size_bytes=size_bytes,
            uploaded_at=uploaded_at
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        return document


def get_all_documents():
    with SessionLocal() as db:
        documents = (
            db.query(Document)
            .order_by(Document.id.desc())
            .all()
        )

        return [
            {
                "id": document.id,
                "filename": document.filename,
                "size_bytes": document.size_bytes,
                "uploaded_at": document.uploaded_at
            }
            for document in documents
        ]


def get_document_by_id(document_id: int):
    with SessionLocal() as db:
        return db.get(Document, document_id)


def delete_document(document_id: int):
    with SessionLocal() as db:
        document = db.get(Document, document_id)

        if document:
            db.delete(document)
            db.commit()