from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, String, Integer, DateTime, JSON, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
import app.services.ingestion_service as ingest


@pytest.fixture
def state(monkeypatch, tmp_path):
    # Real transactions and uniqueness constraints, with JSON replacing vector
    # for focused failure-injection tests that need no external database/model.
    class Base(DeclarativeBase): pass
    class Document(Base):
        __tablename__ = "documents"
        id: Mapped[int] = mapped_column(primary_key=True)
        filename: Mapped[str] = mapped_column(String, unique=True)
        storage_key: Mapped[str | None] = mapped_column(String)
        size_bytes: Mapped[int] = mapped_column(Integer)
        owner_id: Mapped[int] = mapped_column(Integer)
        uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    class Chunk(Base):
        __tablename__ = "chunks"
        id: Mapped[int] = mapped_column(primary_key=True)
        document_id: Mapped[int] = mapped_column(Integer)
        chunk_index: Mapped[int] = mapped_column(Integer)
        page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
        chunk_text: Mapped[str] = mapped_column(String)
        embedding: Mapped[list] = mapped_column(JSON)
    class PendingUpload(Base):
        __tablename__ = "pending_uploads"
        storage_key: Mapped[str] = mapped_column(String, primary_key=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    for name, value in [("SessionLocal", sessions), ("Document", Document), ("Chunk", Chunk), ("PendingUpload", PendingUpload)]:
        monkeypatch.setattr(ingest, name, value)
    monkeypatch.setattr(ingest.storage_settings, "file_storage_backend", "supabase")
    monkeypatch.setattr(ingest, "generate_embeddings", lambda texts: [[0.0]*384 for _ in texts])
    objects = {}
    monkeypatch.setattr(ingest, "persist_pdf", lambda key, path: objects.update({key: Path(path).read_bytes()}))
    monkeypatch.setattr(ingest, "delete_pdf", lambda key: objects.pop(key, None))
    path = tmp_path / "example.pdf"; path.write_bytes(b"%PDF-test")
    def upload():
        return ingest.ingest_document("example.pdf", 9, datetime.now(timezone.utc), 1, ["example text"], str(path))
    def count(model):
        with sessions() as db: return len(db.scalars(select(model)).all())
    yield SimpleNamespace(upload=upload, objects=objects, sessions=sessions, Document=Document,
                          Chunk=Chunk, PendingUpload=PendingUpload, count=count)
    engine.dispose()


def test_document_and_chunks_commit_together(state):
    doc = state.upload()
    assert doc.storage_key in state.objects
    assert state.count(state.Document) == state.count(state.Chunk) == 1
    assert state.count(state.PendingUpload) == 0


def test_duplicate_preserves_original_object(state):
    state.upload(); original = dict(state.objects)
    with pytest.raises(HTTPException) as caught: state.upload()
    assert caught.value.status_code == 409
    assert state.objects == original
    assert state.count(state.Document) == state.count(state.Chunk) == 1
    assert state.count(state.PendingUpload) == 0


def test_embedding_failure_precedes_any_writes(state, monkeypatch):
    def fail(texts): raise RuntimeError("embedding failed")
    monkeypatch.setattr(ingest, "generate_embeddings", fail)
    with pytest.raises(RuntimeError): state.upload()
    assert state.count(state.Document) == state.count(state.Chunk) == state.count(state.PendingUpload) == 0
    assert state.objects == {}


def test_upload_timeout_after_object_created_rolls_back(state, monkeypatch):
    def fail(key, path):
        state.objects[key] = b"uploaded before timeout"
        raise HTTPException(503, "timeout")
    monkeypatch.setattr(ingest, "persist_pdf", fail)
    with pytest.raises(HTTPException): state.upload()
    assert state.objects == {}
    assert state.count(state.Document) == state.count(state.Chunk) == 0
    assert state.count(state.PendingUpload) == 1
    # Even if an upload finishes after the immediate delete, delayed recovery
    # still owns that key and removes the late object.
    with state.sessions.begin() as db:
        item = db.scalar(select(state.PendingUpload))
        state.objects[item.storage_key] = b"late storage completion"
        item.created_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    ingest.cleanup_pending_uploads()
    assert state.objects == {} and state.count(state.PendingUpload) == 0


def test_cleanup_outage_is_durable_then_retried(state, monkeypatch):
    def upload_fail(key, path):
        state.objects[key] = b"partial upload"
        raise HTTPException(503, "timeout")
    def delete_fail(key): raise HTTPException(503, "storage offline")
    monkeypatch.setattr(ingest, "persist_pdf", upload_fail)
    monkeypatch.setattr(ingest, "delete_pdf", delete_fail)
    with pytest.raises(HTTPException): state.upload()
    assert state.count(state.Document) == state.count(state.Chunk) == 0
    assert state.count(state.PendingUpload) == 1 and len(state.objects) == 1
    with state.sessions.begin() as db:
        item = db.scalar(select(state.PendingUpload))
        item.created_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    monkeypatch.setattr(ingest, "delete_pdf", lambda key: state.objects.pop(key, None))
    ingest.cleanup_pending_uploads()
    assert state.objects == {} and state.count(state.PendingUpload) == 0


def test_recovery_cannot_delete_a_committed_object(state):
    doc = state.upload()
    ingest.cleanup_pending_uploads(doc.storage_key)
    assert doc.storage_key in state.objects
    assert state.count(state.Document) == 1


def test_interrupted_process_leaves_recoverable_marker(state, monkeypatch):
    def interrupt(key, path):
        state.objects[key] = b"uploaded before process stopped"
        raise SystemExit("simulate worker termination")
    monkeypatch.setattr(ingest, "persist_pdf", interrupt)
    with pytest.raises(SystemExit): state.upload()
    assert state.count(state.Document) == state.count(state.Chunk) == 0
    assert state.count(state.PendingUpload) == 1
    with state.sessions.begin() as db:
        db.scalar(select(state.PendingUpload)).created_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    ingest.cleanup_pending_uploads()
    assert state.objects == {} and state.count(state.PendingUpload) == 0


def test_page_metadata_commits_with_sequential_document_indexes(state):
    from app.services.ingestion_service import ingest_document
    # Existing fixture stages its sample PDF in pytest's temporary directory.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.pdf') as original:
        original.write(b'%PDF-test'); original.flush()
        doc = ingest_document('pages.pdf', 9, datetime.now(timezone.utc), 1,
            [{'chunk_text': 'first passage', 'page_number': 1}, {'chunk_text': 'second passage', 'page_number': 4}], original.name)
    with state.sessions() as db:
        chunks = db.scalars(select(state.Chunk).where(state.Chunk.document_id == doc.id).order_by(state.Chunk.chunk_index)).all()
        assert [(chunk.chunk_index, chunk.page_number) for chunk in chunks] == [(0, 1), (1, 4)]
