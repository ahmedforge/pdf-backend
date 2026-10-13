"""Rebuild legacy chunks from stored PDFs, preserving document identity/storage.

Default is dry-run. Use --apply to write. Missing PDFs/unusable text leave chunks
untouched; a migration alone leaves historical page_number values NULL.
"""
import argparse
from pathlib import Path
import sys
from sqlalchemy import delete, exists, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.services.embedding_service import generate_embeddings
from app.services.pdf_service import extract_page_chunks
from app.services.storage_service import open_pdf


def rebuild_document(document_id, apply=False, force=False):
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            return "missing document"
        key = document.storage_key or document.filename
        filename = document.filename
        legacy = db.scalar(select(exists().where(Chunk.document_id == document_id, Chunk.page_number.is_(None))))
        has_chunks = db.scalar(select(exists().where(Chunk.document_id == document_id)))
        if has_chunks and not legacy and not force:
            return "already page-aware"
    # Download and expensive embedding work occur before the replacement transaction.
    with open_pdf(key) as path:
        chunks = extract_page_chunks(path)
    if not chunks:
        return "no searchable text; unchanged"
    if not apply:
        return f"dry-run: {len(chunks)} page-aware chunks"
    embeddings = generate_embeddings([chunk["chunk_text"] for chunk in chunks])
    if len(embeddings) != len(chunks):
        raise RuntimeError("Embedding count mismatch; old chunks preserved")
    with SessionLocal.begin() as db:
        document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
        if document is None:
            return "deleted during re-ingestion; unchanged"
        if (document.storage_key or document.filename) != key or document.filename != filename:
            raise RuntimeError("Original changed; old chunks preserved")
        legacy = db.scalar(select(exists().where(Chunk.document_id == document_id, Chunk.page_number.is_(None))))
        has_chunks = db.scalar(select(exists().where(Chunk.document_id == document_id)))
        if has_chunks and not legacy and not force:
            return "already page-aware"
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.add_all([Chunk(document_id=document_id, chunk_index=index,
                          chunk_text=chunk["chunk_text"], page_number=chunk["page_number"], embedding=embedding)
                    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))])
    return f"rebuilt: {len(chunks)} chunks"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", action="append", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true", help="Also rebuild page-aware documents")
    args = parser.parse_args()
    failures = 0
    if args.document_id:
        ids = args.document_id
    else:
        with SessionLocal() as db:
            ids = db.scalars(select(Document.id).order_by(Document.id)).all()
    for document_id in ids:
        try:
            print(f"Document {document_id}: {rebuild_document(document_id, args.apply, args.force)}")
        except Exception as exc:
            # No credential-bearing exception details or file contents in logs.
            print(f"Document {document_id}: {type(exc).__name__}; unchanged")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
