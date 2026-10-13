from contextlib import contextmanager
from sqlalchemy import select
import pytest
import scripts.reingest_page_chunks as reingest
from tests.test_ingestion import state  # Reuse isolated real-transaction fixture.


@pytest.fixture
def setup(state, monkeypatch):
    doc = state.upload()
    monkeypatch.setattr(reingest, 'SessionLocal', state.sessions)
    monkeypatch.setattr(reingest, 'Document', state.Document)
    monkeypatch.setattr(reingest, 'Chunk', state.Chunk)
    @contextmanager
    def original(key): yield 'unused.pdf'
    monkeypatch.setattr(reingest, 'open_pdf', original)
    monkeypatch.setattr(reingest, 'extract_page_chunks', lambda path: [{'chunk_text': 'New first passage', 'page_number': 2}, {'chunk_text': 'New second passage', 'page_number': 5}])
    monkeypatch.setattr(reingest, 'generate_embeddings', lambda chunks: [[0.0]*384 for _ in chunks])
    return state, doc


def test_dry_run_apply_and_rerun_are_safe(setup):
    state, doc = setup
    assert reingest.rebuild_document(doc.id) == 'dry-run: 2 page-aware chunks'
    with state.sessions() as db:
        assert db.scalar(select(state.Chunk)).page_number is None
    assert reingest.rebuild_document(doc.id, apply=True) == 'rebuilt: 2 chunks'
    with state.sessions() as db:
        chunks = db.scalars(select(state.Chunk).order_by(state.Chunk.chunk_index)).all()
        assert [(chunk.chunk_index, chunk.page_number) for chunk in chunks] == [(0, 2), (1, 5)]
        assert db.get(state.Document, doc.id).storage_key == doc.storage_key
    assert reingest.rebuild_document(doc.id, apply=True) == 'already page-aware'


def test_missing_original_or_failed_replacement_preserves_old_chunks(setup, monkeypatch):
    state, doc = setup
    @contextmanager
    def missing(key): raise FileNotFoundError('missing'); yield
    with monkeypatch.context() as patch:
        patch.setattr(reingest, 'open_pdf', missing)
        with pytest.raises(FileNotFoundError): reingest.rebuild_document(doc.id, apply=True)
    monkeypatch.setattr(reingest, 'extract_page_chunks', lambda path: [{'chunk_text': None, 'page_number': 1}])
    with pytest.raises(Exception): reingest.rebuild_document(doc.id, apply=True)
    with state.sessions() as db:
        chunk = db.scalar(select(state.Chunk))
        assert chunk.chunk_text == 'example text' and chunk.page_number is None
