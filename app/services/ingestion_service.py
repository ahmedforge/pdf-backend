"""Commit document/chunks together; recover uncommitted remote objects durably."""
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.database import SessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.pending_upload import PendingUpload
from app.services.chunk_service import normalize_chunks
from app.services.embedding_service import generate_embeddings
from app.services.storage_service import storage_settings, persist_pdf, delete_pdf

logger = logging.getLogger(__name__)


def cleanup_pending_uploads(storage_key=None, *, retire_marker=True):
    # Locks avoid racing a live upload or another recovery worker. Markers stay
    # durable if Storage is unavailable, so a later attempt can retry safely.
    query = select(PendingUpload)
    if storage_key is not None:
        query = query.where(PendingUpload.storage_key == storage_key)
    else:
        query = query.where(PendingUpload.created_at < datetime.now(timezone.utc) - timedelta(minutes=5))
    with SessionLocal.begin() as db:
        pending = db.scalars(query.order_by(PendingUpload.created_at, PendingUpload.storage_key).with_for_update(skip_locked=True).limit(10)).all()
        for item in pending:
            try:
                # Savepoint isolates one unavailable/invalid key from the batch.
                with db.begin_nested():
                    delete_pdf(item.storage_key)
                    if retire_marker:
                        db.delete(item)
            except Exception:
                logger.warning("PDF cleanup pending; will retry")
                if storage_key is not None:
                    raise
                # Retry later so bad keys cannot monopolize every batch.
                item.created_at = datetime.now(timezone.utc)
            # Failed rows remain durable for the next recovery pass.


def ingest_document(filename, size_bytes, uploaded_at, owner_id, chunks, file_path):
    # Expensive work precedes all database/storage writes.
    records = normalize_chunks(chunks)
    embeddings = generate_embeddings([record["chunk_text"] for record in records])
    if len(embeddings) != len(chunks):
        raise RuntimeError("Embedding count does not match document chunks")
    remote = storage_settings.file_storage_backend == "supabase"
    key = "upload-" + uuid4().hex + ".pdf" if remote else Path(file_path).name
    if remote:
        with SessionLocal.begin() as db:
            db.add(PendingUpload(storage_key=key))
    try:
        with SessionLocal.begin() as db:
            if remote:
                # Hold this row lock until commit; recovery skips live uploads.
                marker = db.scalar(select(PendingUpload).where(
                    PendingUpload.storage_key == key,
                ).with_for_update())
                if marker is None:
                    raise RuntimeError("Upload recovery marker is missing")
            document = Document(filename=filename, size_bytes=size_bytes,
                                uploaded_at=uploaded_at, owner_id=owner_id,
                                storage_key=key)
            db.add(document)
            db.flush()  # Detect duplicate filenames before uploading anything.
            db.add_all([Chunk(document_id=document.id, chunk_index=index,
                              chunk_text=value["chunk_text"], page_number=value["page_number"], embedding=embedding)
                        for index, (value, embedding) in enumerate(zip(records, embeddings))])
            db.flush()
            persist_pdf(key, file_path)
            if remote:
                db.delete(marker)
        return document
    except Exception as exc:
        if remote:
            try:
                # An ambiguous successful DB commit removes the marker. In
                # that case recovery cannot delete the committed document's PDF.
                # A timeout can occur before Storage finishes processing the
                # request. Keep the marker for a delayed second cleanup even
                # when an immediate delete succeeds.
                uncertain = isinstance(exc, HTTPException) and exc.status_code == 503
                cleanup_pending_uploads(key, retire_marker=not uncertain)
            except Exception:
                logger.warning("Upload recovery pending; cleanup will retry")
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "A file with this name already exists") from exc
        raise
