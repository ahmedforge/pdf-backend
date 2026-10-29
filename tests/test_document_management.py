"""Document management uses actual transactions, cascade constraints and local PDFs."""
import asyncio
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select, event

from app.main import app
from app.security import get_current_user
import app.repositories.document_repository as repository
import app.routers.documents as routes
import app.services.ingestion_service as ingest
import app.services.storage_service as storage
import app.services.upload_recovery as recovery
from tests.test_ingestion import state
from tests.test_storage_routes import pdf_bytes


@pytest.fixture
def api(state, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name, value in [("SessionLocal", state.sessions), ("Document", state.Document), ("PendingUpload", state.PendingUpload)]:
        monkeypatch.setattr(repository, name, value)
    monkeypatch.setattr(storage.storage_settings, 'file_storage_backend', 'local')
    monkeypatch.setattr(ingest, 'persist_pdf', storage.persist_pdf)
    monkeypatch.setattr(ingest, 'delete_pdf', storage.delete_pdf)
    owner = SimpleNamespace(id=1)
    app.dependency_overrides[get_current_user] = lambda: owner
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, owner=owner, state=state, root=tmp_path)
    finally:
        app.dependency_overrides.clear()


def upload(api, name='report.pdf', contents=None):
    return api.client.post('/upload', files={'file': (name, contents if contents is not None else pdf_bytes(), 'application/pdf')})


def document(api, id):
    with api.state.sessions() as db:
        return db.get(api.state.Document, id)


def age_markers(api):
    with api.state.sessions.begin() as db:
        for marker in db.scalars(select(api.state.PendingUpload)):
            marker.created_at = datetime.now(timezone.utc) - timedelta(minutes=6)


def test_per_owner_uniqueness_distinct_files_download_and_delete(api):
    first = upload(api); assert first.status_code == 200
    first_id = first.json()['id']; first_doc = document(api, first_id)
    first_path = Path('uploads') / first_doc.storage_key
    assert first_doc.storage_key != first_doc.filename
    assert len(first_doc.storage_key) == 36  # uuid4 hex + .pdf
    assert first.json()['document_id'] == first_id
    assert first.json()['display_name'] == 'report.pdf'
    assert first.json()['size_bytes'] == len(pdf_bytes())
    assert upload(api).status_code == 409
    assert first_path.read_bytes() == pdf_bytes()
    assert len(list(Path('uploads').iterdir())) == 1
    api.owner.id = 2
    second = upload(api); assert second.status_code == 200
    second_id = second.json()['id']; second_doc = document(api, second_id)
    second_path = Path('uploads') / second_doc.storage_key
    assert second_path != first_path and second_path.exists()
    assert api.client.get(f'/download/{second_id}').content == pdf_bytes()
    assert api.client.delete(f'/files/{first_id}').status_code == 404
    assert first_path.exists()
    assert api.client.patch(f'/files/{first_id}', json={'display_name': 'Foreign'}).status_code == 404
    api.owner.id = 1
    assert api.client.get(f'/download/{first_id}').content == pdf_bytes()
    assert api.client.delete(f'/files/{first_id}').status_code == 200
    assert not first_path.exists() and second_path.read_bytes() == pdf_bytes()
    assert document(api, first_id) is None
    with api.state.sessions() as db:
        assert not db.scalars(select(api.state.Chunk).where(api.state.Chunk.document_id == first_id)).all()
    assert api.state.count(api.state.PendingUpload) == 0
    assert api.client.delete(f'/files/{first_id}').status_code == 404


def test_rename_keeps_storage_and_original_name_and_list_fields(api):
    id = upload(api).json()['id']; before = document(api, id)
    response = api.client.patch(f'/files/{id}', json={'display_name': '  Annual\x00\n report\u200b  '})
    assert response.status_code == 200
    assert response.json()['display_name'] == 'Annual report'
    after = document(api, id)
    assert (after.filename, after.storage_key) == (before.filename, before.storage_key)
    listing = api.client.get('/files').json()['files'][0]
    assert set(listing) == {'id', 'filename', 'display_name', 'size_bytes', 'uploaded_at'}
    assert listing['display_name'] == 'Annual report'
    assert api.client.get(f'/download/{id}').content == pdf_bytes()
    assert api.client.patch('/files/999', json={'display_name': 'Missing'}).status_code == 404


@pytest.mark.parametrize('value', ['', '   ', '\x00\n\t', 'x'*121, None, 123])
def test_rename_validation(api, value):
    id = upload(api).json()['id']
    assert api.client.patch(f'/files/{id}', json={'display_name': value}).status_code == 422
    assert document(api, id).display_name is None


def test_delete_outage_is_durable_and_stale_key_cannot_touch_new_upload(api, monkeypatch, caplog):
    id = upload(api).json()['id']; old_key = document(api, id).storage_key
    real_delete = ingest.delete_pdf
    with monkeypatch.context() as patch:
        def unavailable(key): raise HTTPException(503, 'secret-do-not-log')
        patch.setattr(ingest, 'delete_pdf', unavailable)
        assert api.client.delete(f'/files/{id}').status_code == 200
    assert document(api, id) is None and api.state.count(api.state.Chunk) == 0
    assert api.state.count(api.state.PendingUpload) == 1
    assert 'secret-do-not-log' not in caplog.text
    new_id = upload(api).json()['id']; new_key = document(api, new_id).storage_key
    assert old_key != new_key
    age_markers(api); ingest.cleanup_pending_uploads()
    assert not (Path('uploads') / old_key).exists()
    assert (Path('uploads') / new_key).read_bytes() == pdf_bytes()
    assert api.state.count(api.state.PendingUpload) == 0
    real_delete(old_key)  # Already missing: success.
    ingest.cleanup_pending_uploads()


def test_file_deleted_but_marker_commit_fails_then_recovery_is_safe(api, monkeypatch):
    id = upload(api).json()['id']; old_key = document(api, id).storage_key
    with monkeypatch.context() as patch:
        def remove_then_fail(key):
            storage.delete_pdf(key)
            raise RuntimeError('simulated retirement failure')
        patch.setattr(ingest, 'delete_pdf', remove_then_fail)
        assert api.client.delete(f'/files/{id}').status_code == 200
    assert not (Path('uploads') / old_key).exists()
    new_id = upload(api).json()['id']; new_key = document(api, new_id).storage_key
    age_markers(api); ingest.cleanup_pending_uploads()
    assert api.state.count(api.state.PendingUpload) == 0
    assert (Path('uploads') / new_key).exists()


def test_delete_transaction_rolls_back_if_journal_cannot_be_inserted(api):
    id = upload(api).json()['id']; key = document(api, id).storage_key
    engine = api.state.sessions.kw['bind']
    def reject_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO pending_uploads'):
            raise RuntimeError('journal unavailable')
    event.listen(engine, 'before_cursor_execute', reject_insert)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.delete(f'/files/{id}').status_code == 500
    finally:
        event.remove(engine, 'before_cursor_execute', reject_insert)
    assert document(api, id) is not None
    assert api.state.count(api.state.Chunk) > 0
    assert (Path('uploads') / key).exists()
    assert api.state.count(api.state.PendingUpload) == 0


def test_legacy_download_delete_and_delayed_missing_recovery(api):
    Path('uploads').mkdir()
    path = Path('uploads/legacy.pdf'); path.write_bytes(pdf_bytes())
    with api.state.sessions.begin() as db:
        legacy = api.state.Document(filename='legacy.pdf', owner_id=1, size_bytes=path.stat().st_size,
                                    uploaded_at=datetime.now(timezone.utc), storage_key=None)
        db.add(legacy); db.flush(); id = legacy.id
    assert document(api, id).storage_key is None
    assert api.client.get(f'/download/{id}').content == pdf_bytes()
    assert api.client.delete(f'/files/{id}').status_code == 200
    assert not path.exists()
    with api.state.sessions.begin() as db:
        db.add(api.state.PendingUpload(storage_key='legacy.pdf', created_at=datetime.now(timezone.utc)-timedelta(minutes=6)))
    new_id = upload(api, 'legacy.pdf').json()['id']
    new_key = document(api, new_id).storage_key
    assert new_key != 'legacy.pdf'
    ingest.cleanup_pending_uploads()
    assert api.state.count(api.state.PendingUpload) == 0
    assert (Path('uploads') / new_key).exists()


@pytest.mark.parametrize('key', ['../outside.pdf', '/tmp/outside.pdf', 'a/b.pdf', '..', 'a\\b.pdf', ''])
def test_traversal_keys_are_rejected(api, key):
    with pytest.raises(HTTPException) as caught: storage.delete_pdf(key)
    assert caught.value.status_code == 400


def test_symlink_escape_and_upload_root_symlink_are_rejected(api):
    outside = Path('outside.pdf'); outside.write_bytes(b'keep')
    Path('uploads').mkdir(); Path('uploads/link.pdf').symlink_to(outside.absolute())
    with pytest.raises(HTTPException): storage.delete_pdf('link.pdf')
    assert outside.read_bytes() == b'keep'
    Path('uploads/link.pdf').unlink(); Path('uploads').rmdir()
    Path('elsewhere').mkdir(); Path('uploads').symlink_to(Path('elsewhere').absolute(), target_is_directory=True)
    with pytest.raises(HTTPException): storage.delete_pdf('missing.pdf')


def test_bad_journal_entry_does_not_block_valid_missing_key(api, caplog):
    with api.state.sessions.begin() as db:
        for key in ['../private-secret-key.pdf', 'missing.pdf']:
            db.add(api.state.PendingUpload(storage_key=key, created_at=datetime.now(timezone.utc)-timedelta(minutes=6)))
    ingest.cleanup_pending_uploads()
    with api.state.sessions() as db:
        assert db.get(api.state.PendingUpload, 'missing.pdf') is None
        assert db.get(api.state.PendingUpload, '../private-secret-key.pdf') is not None
    assert 'private-secret-key' not in caplog.text


def test_corrupt_and_encrypted_pdfs_are_422_and_cleaned(api):
    corrupt = upload(api, contents=b'%PDF-1.7\nnot a valid PDF')
    assert corrupt.status_code == 422
    writer = PdfWriter(); writer.add_blank_page(width=612, height=792); writer.encrypt('password')
    data = io.BytesIO(); writer.write(data)
    encrypted = upload(api, contents=data.getvalue())
    assert encrypted.status_code == 422
    for response in [corrupt, encrypted]:
        assert 'unencrypted, readable PDF' in response.json()['detail']
    assert api.state.count(api.state.Document) == 0
    assert not list(Path('uploads').iterdir())


def test_unexpected_parser_error_stays_500(api, monkeypatch):
    def fail(path): raise RuntimeError('private details')
    monkeypatch.setattr(routes, 'extract_page_chunks', fail)
    response = upload(api)
    assert response.status_code == 500 and response.json() == {'detail': 'PDF upload processing failed.'}
    assert not list(Path('uploads').iterdir())


def test_periodic_recovery_runs_in_local_mode_and_stops_cleanly(api, monkeypatch):
    with api.state.sessions.begin() as db:
        db.add(api.state.PendingUpload(storage_key='missing.pdf', created_at=datetime.now(timezone.utc)-timedelta(minutes=6)))
    sleeps = []
    async def tick(delay):
        sleeps.append(delay)
        if len(sleeps) > 1: raise asyncio.CancelledError
    monkeypatch.setattr(recovery.asyncio, 'sleep', tick)
    with pytest.raises(asyncio.CancelledError): asyncio.run(recovery.recover_uploads())
    assert sleeps == [60, 60]
    assert api.state.count(api.state.PendingUpload) == 0


def test_generated_key_skips_legacy_and_pending_paths_and_never_overwrites(api, monkeypatch):
    keys = iter([SimpleNamespace(hex='a'*32), SimpleNamespace(hex='b'*32), SimpleNamespace(hex='c'*32)])
    Path('uploads').mkdir()
    with api.state.sessions.begin() as db:
        db.add(api.state.Document(filename='a'*32+'.pdf', owner_id=1, size_bytes=1,
                                 uploaded_at=datetime.now(timezone.utc), storage_key=None))
        db.add(api.state.PendingUpload(storage_key='b'*32+'.pdf'))
    monkeypatch.setattr(routes, 'uuid4', lambda: next(keys))
    response = upload(api, 'anything.pdf')
    assert response.status_code == 200
    assert document(api, response.json()['id']).storage_key == 'c'*32+'.pdf'
    # Disk-only collision also cannot overwrite a path, even with a mocked UUID.
    path = Path('uploads') / ('d'*32+'.pdf'); path.write_bytes(b'original')
    monkeypatch.setattr(routes, 'uuid4', lambda: SimpleNamespace(hex='d'*32))
    assert upload(api, 'another.pdf').status_code == 409
    assert path.read_bytes() == b'original'


def test_oversize_and_empty_text_keep_existing_error_shapes(api):
    response = upload(api, contents=b'%PDF-'+b'x'*(10*1024*1024))
    assert response.status_code == 413
    assert response.json() == {'detail': 'File is too large. Maximum size is 10 MiB (10485760 bytes)'}
    writer = PdfWriter(); writer.add_blank_page(width=612, height=792)
    data = io.BytesIO(); writer.write(data)
    assert upload(api, contents=data.getvalue()).status_code == 422
    assert upload(api, contents=b'not pdf').status_code == 400
    assert upload(api, name='text.txt').status_code == 400
    assert not list(Path('uploads').iterdir())


def test_legacy_helper_uses_safe_path_resolution(api):
    from app.services.file_service import get_existing_file
    Path('uploads').mkdir(); Path('uploads/legacy.pdf').write_bytes(pdf_bytes())
    name, path = get_existing_file('legacy.pdf')
    assert name == 'legacy.pdf' and Path(path).read_bytes() == pdf_bytes()
    outside = Path('outside.pdf'); outside.write_bytes(b'keep')
    Path('uploads/link.pdf').symlink_to(outside.absolute())
    with pytest.raises(HTTPException): get_existing_file('link.pdf')


def test_partial_journal_failure_does_not_starve_later_keys(api, monkeypatch):
    with api.state.sessions.begin() as db:
        for i in range(12):
            db.add(api.state.PendingUpload(storage_key=f'key-{i}.pdf', created_at=datetime.now(timezone.utc)-timedelta(minutes=6)))
    def fail(key):
        if int(key.removeprefix('key-').removesuffix('.pdf')) < 10:
            raise HTTPException(503, 'no details')
        storage.delete_pdf(key)
    monkeypatch.setattr(ingest, 'delete_pdf', fail)
    ingest.cleanup_pending_uploads()
    assert api.state.count(api.state.PendingUpload) == 12
    ingest.cleanup_pending_uploads()
    assert api.state.count(api.state.PendingUpload) == 10
    monkeypatch.setattr(ingest, 'delete_pdf', storage.delete_pdf)
    age_markers(api); ingest.cleanup_pending_uploads()
    assert api.state.count(api.state.PendingUpload) == 0


@pytest.mark.parametrize('key', ['../outside.pdf', '/tmp/outside.pdf', 'nested/key.pdf', 'a\\b.pdf', '\x00.pdf'])
def test_reader_and_path_resolver_also_reject_invalid_keys(api, key):
    with pytest.raises(HTTPException): storage.local_pdf_path(key)
    with pytest.raises(HTTPException):
        with storage.open_pdf(key):
            pytest.fail('Invalid original was exposed')


def test_viewer_cross_owner_and_symlink_never_serves_foreign_bytes(api):
    id = upload(api).json()['id']
    api.owner.id = 2
    assert api.client.get(f'/download/{id}').status_code == 404
    api.owner.id = 1
    key = document(api, id).storage_key
    path = Path('uploads')/key; path.unlink()
    outside=Path('outside.pdf'); outside.write_bytes(b'foreign-secret')
    path.symlink_to(outside.absolute())
    response=api.client.get(f'/download/{id}')
    assert response.status_code == 400
    assert b'foreign-secret' not in response.content
