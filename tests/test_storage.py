from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

import app.services.storage_service as storage


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(storage.storage_settings, 'file_storage_backend', 'supabase')
    monkeypatch.setattr(storage.storage_settings, 'supabase_url', 'https://project.supabase.co')
    monkeypatch.setattr(storage.storage_settings, 'supabase_service_role_key', SecretStr('private-test-secret'))
    client_type = httpx.Client
    def connect(handler):
        monkeypatch.setattr(storage.httpx, 'Client', lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    return connect


def test_pdf_survives_local_loss_and_download_is_cleaned(remote, tmp_path):
    objects = {}
    def handle(request):
        assert request.headers['authorization'] == 'Bearer private-test-secret'
        if request.method == 'POST':
            assert request.headers['x-upsert'] == 'false'
            objects['report.pdf'] = request.read()
            return httpx.Response(200, json={'Key': 'pdfs/report.pdf'})
        assert request.url.path == '/storage/v1/object/authenticated/pdfs/report.pdf'
        return httpx.Response(200, content=objects['report.pdf'])
    remote(handle)
    path = tmp_path/'report.pdf'; path.write_bytes(b'%PDF-test')
    storage.persist_pdf('report.pdf', str(path)); path.unlink()
    with storage.open_pdf('report.pdf') as downloaded:
        assert Path(downloaded).read_bytes() == b'%PDF-test'
    assert not Path(downloaded).exists()


def test_temporary_download_removed_when_processing_fails(remote):
    remote(lambda request: httpx.Response(200, content=b'%PDF-test'))
    with pytest.raises(RuntimeError):
        with storage.open_pdf('report.pdf') as path:
            raise RuntimeError('parser failed')
    assert not Path(path).exists()


@pytest.mark.parametrize('status,expected', [(403, 503), (404, 404), (500, 503)])
def test_storage_errors_do_not_expose_secrets(remote, status, expected):
    remote(lambda request: httpx.Response(status, json={'message': 'private-test-secret'}))
    with pytest.raises(HTTPException) as caught:
        with storage.open_pdf('report.pdf'):
            pass
    assert caught.value.status_code == expected
    assert 'private-test-secret' not in caught.value.detail


def test_upload_conflict_does_not_overwrite(remote, tmp_path):
    remote(lambda request: httpx.Response(400, json={'statusCode': '409'}))
    path = tmp_path/'report.pdf'; path.write_bytes(b'%PDF-test')
    with pytest.raises(HTTPException) as caught:
        storage.persist_pdf('report.pdf', str(path))
    assert caught.value.status_code == 409


def test_delete_targets_exact_object(remote):
    def handle(request):
        assert request.method == 'DELETE'
        assert request.url.path == '/storage/v1/object/pdfs'
        assert request.read() == b'{"prefixes":["report.pdf"]}'
        return httpx.Response(200, json=[])
    remote(handle)
    storage.delete_pdf('report.pdf')


def test_local_mode_keeps_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(storage.storage_settings, 'file_storage_backend', 'local')
    (tmp_path/'uploads').mkdir(); path = tmp_path/'uploads'/'report.pdf'; path.write_bytes(b'%PDF-test')
    with storage.open_pdf('report.pdf') as opened:
        assert Path(opened).read_bytes() == b'%PDF-test'
    assert path.exists()
