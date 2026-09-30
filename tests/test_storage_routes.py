import io
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app.main import app
from app.security import get_current_user
import app.routers.documents as routes
import app.services.storage_service as storage


def pdf_bytes():
    writer = PdfWriter(); page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    contents = DecodedStreamObject(); contents.set_data(b'BT /F1 12 Tf 72 720 Td (Persistent PDF verification) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(contents)
    output = io.BytesIO(); writer.write(output); return output.getvalue()


@pytest.fixture
def api(monkeypatch, tmp_path):
    objects = {}; documents = {}; temporary = []; operations = []; failures = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(storage.storage_settings, 'file_storage_backend', 'supabase')
    monkeypatch.setattr(storage.storage_settings, 'supabase_url', 'https://project.supabase.co')
    monkeypatch.setattr(storage.storage_settings, 'supabase_service_role_key', SecretStr('test-only-key'))
    def handle(request):
        operations.append(request.method)
        if request.method in failures:
            return httpx.Response(failures[request.method], json={'message': 'private upstream detail'})
        filename = request.url.path.rsplit('/', 1)[-1]
        if request.method == 'POST':
            if filename in objects:
                return httpx.Response(409)
            objects[filename] = request.read()
            return httpx.Response(200, json={})
        if request.method == 'GET':
            return httpx.Response(200, content=objects[filename]) if filename in objects else httpx.Response(404)
        for filename in json.loads(request.read())['prefixes']:
            objects.pop(filename, None)
        return httpx.Response(200, json=[])
    real_client = httpx.Client
    monkeypatch.setattr(storage.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    real_temp = storage.NamedTemporaryFile
    def tempfile(**kwargs):
        target = real_temp(**kwargs); temporary.append(target.name); return target
    monkeypatch.setattr(storage, 'NamedTemporaryFile', tempfile)
    real_mkstemp = routes.mkstemp
    def stage(**kwargs):
        fd, name = real_mkstemp(**kwargs); temporary.append(name); return fd, name
    monkeypatch.setattr(routes, 'mkstemp', stage)
    def insert(filename, size, uploaded_at, owner):
        document = SimpleNamespace(id=len(documents)+1, filename=filename, owner_id=owner)
        documents[document.id] = document; return document
    monkeypatch.setattr(routes, 'insert_document', insert)
    monkeypatch.setattr(routes, 'save_document_chunks', lambda *args: None)
    monkeypatch.setattr(routes, 'get_document_by_id', lambda id, owner: documents.get(id) if id in documents and documents[id].owner_id == owner else None)
    monkeypatch.setattr(routes, 'delete_document', lambda id, owner: documents.pop(id, None))
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, objects=objects, documents=documents, temporary=temporary, operations=operations, failures=failures)
    finally:
        app.dependency_overrides.clear()
    assert all(not Path(path).exists() for path in temporary)


def upload(api):
    return api.client.post('/upload', files={'file': ('report.pdf', pdf_bytes(), 'application/pdf')})


def test_upload_read_and_delete_without_local_persistent_files(api):
    response = upload(api); assert response.status_code == 200
    assert not Path('uploads').exists()
    assert all(not Path(path).exists() for path in api.temporary)
    downloaded = api.client.get('/download/1')
    assert downloaded.status_code == 200 and downloaded.content == pdf_bytes()
    assert api.client.get('/extract/1').json()['text'].strip() == 'Persistent PDF verification'
    assert api.client.get('/info/1').status_code == 200
    assert api.client.get('/search/1', params={'query': 'persistent'}).json()['found'] is True
    assert all(not Path(path).exists() for path in api.temporary)
    assert api.client.delete('/files/1').status_code == 200
    assert api.objects == {} and api.documents == {}


def test_duplicate_upload_keeps_existing_pdf(api):
    assert upload(api).status_code == 200
    original = dict(api.objects)
    assert upload(api).status_code == 409
    assert api.objects == original and len(api.documents) == 1


def test_storage_failure_does_not_create_document(api):
    api.failures['POST'] = 503
    response = upload(api)
    assert response.status_code == 503
    assert api.documents == {} and api.objects == {}
    assert 'private upstream detail' not in response.text


def test_embedding_failure_removes_new_pdf_and_record(api, monkeypatch):
    def fail(*args):
        raise RuntimeError('Embedding failed')
    monkeypatch.setattr(routes, 'save_document_chunks', fail)
    assert upload(api).status_code == 500
    assert api.documents == {} and api.objects == {}


def test_delete_failure_keeps_document(api):
    assert upload(api).status_code == 200
    api.failures['DELETE'] = 503
    assert api.client.delete('/files/1').status_code == 503
    assert len(api.documents) == 1 and 'report.pdf' in api.objects


def test_other_user_cannot_fetch_pdf(api):
    assert upload(api).status_code == 200
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2)
    before = len(api.operations)
    assert api.client.get('/download/1').status_code == 404
    assert len(api.operations) == before


def test_local_upload_conflict_keeps_existing_file(api, monkeypatch):
    monkeypatch.setattr(storage.storage_settings, 'file_storage_backend', 'local')
    assert upload(api).status_code == 200
    original = Path('uploads/report.pdf').read_bytes()
    assert upload(api).status_code == 409
    assert Path('uploads/report.pdf').read_bytes() == original


def test_invalid_storage_configuration_does_not_print_key():
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as caught:
        storage.StorageSettings(
            _env_file=None, file_storage_backend='supabase',
            supabase_url='invalid-url', supabase_service_role_key='private-secret-value',
        )
    assert 'private-secret-value' not in str(caught.value)
