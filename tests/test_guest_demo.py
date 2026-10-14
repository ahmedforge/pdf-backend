from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.security import create_guest_token, SECRET_KEY, ALGORITHM, get_current_user
from app.services import guest_demo
import app.security as security
import app.routers.documents as documents


@pytest.fixture
def demo(monkeypatch):
    document=SimpleNamespace(id=41,owner_id=200)
    monkeypatch.setattr(guest_demo,'get_demo_document',lambda: document)
    monkeypatch.setattr(security,'get_user_by_id',lambda owner: SimpleNamespace(id=owner))
    return document


def headers(document):
    return {'Authorization': 'Bearer '+create_guest_token(document)}


def test_guest_entry_issues_only_short_lived_scoped_token(demo):
    response=TestClient(app).post('/auth/guest')
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    payload=jwt.decode(response.json()['access_token'],SECRET_KEY,algorithms=[ALGORITHM])
    assert payload['guest'] is True and payload['sub']=='200' and payload['guest_document_id']==41
    seconds=payload['exp']-datetime.now(timezone.utc).timestamp()
    assert 1190<seconds<=1200


def test_guest_lists_only_sample_even_if_owner_has_other_documents(demo,monkeypatch):
    monkeypatch.setattr(documents,'get_all_documents',lambda owner:[{'id':41},{'id':42}])
    assert TestClient(app).get('/files',headers=headers(demo)).json()=={'files':[{'id':41}]}


@pytest.mark.parametrize('method,path', [('POST','/upload'),('PATCH','/files/41'),('DELETE','/files/41'),('GET','/download/42'),('POST','/files/42/ask/stream'),('GET','/files/41/semantic-search'),('GET','/extract/41')])
def test_guest_cannot_write_or_access_other_routes(demo,method,path):
    response=TestClient(app).request(method,path,headers=headers(demo))
    assert response.status_code==403


def test_guest_claims_must_match_current_configured_sample(demo):
    forged=SimpleNamespace(id=42,owner_id=200)
    assert TestClient(app).get('/files',headers=headers(forged)).status_code==401
    forged=SimpleNamespace(id=41,owner_id=201)
    assert TestClient(app).get('/files',headers=headers(forged)).status_code==401


def test_expired_guest_and_modified_signature_are_rejected(demo):
    token=jwt.encode({'sub':'200','guest':True,'guest_document_id':41,'exp':datetime.now(timezone.utc)-timedelta(seconds=1)},SECRET_KEY,algorithm=ALGORITHM)
    assert TestClient(app).get('/files',headers={'Authorization':'Bearer '+token}).status_code==401
    token=jwt.encode({'sub':'200','guest':True,'guest_document_id':41},'different-secret-for-test-only-32bytes',algorithm=ALGORITHM)
    assert TestClient(app).get('/files',headers={'Authorization':'Bearer '+token}).status_code==401


def test_guest_disabled_is_user_safe(monkeypatch):
    monkeypatch.setattr(settings,'guest_demo_document_id',None)
    response=TestClient(app).post('/auth/guest')
    assert response.status_code==503
    assert 'temporarily unavailable' in response.json()['detail']


@pytest.mark.parametrize('method,path',[('GET','/files'),('GET','/download/41'),('POST','/files/41/ask'),('POST','/files/41/ask/stream')])
def test_allowed_sample_routes(demo,method,path):
    assert guest_demo.authorize_guest({'sub':'200','guest_document_id':41},method,path)==41


def test_guest_stream_uses_normal_sse_and_shared_owner_rate_limit(demo,monkeypatch):
    checked=[]
    monkeypatch.setattr(documents,'get_document_by_id',lambda *args: demo)
    monkeypatch.setattr(documents,'check_rate_limit',lambda owner: checked.append(owner) or True)
    monkeypatch.setattr(documents,'stream_document_events',lambda *args: iter(['event: sources\ndata: {"sources": []}\n\n','event: token\ndata: {"text":"Sample answer"}\n\n','event: done\ndata: {"complete":true}\n\n']))
    client=TestClient(app)
    for _ in range(2):
        response=client.post('/files/41/ask/stream?format=sse',headers=headers(demo),json={'question':'Test'})
        assert response.status_code==200 and 'event: done' in response.text
    assert checked==[200,200]
    monkeypatch.setattr(documents,'check_rate_limit',lambda owner: False)
    assert client.post('/files/41/ask/stream?format=sse',headers=headers(demo),json={'question':'Test'}).status_code==429


def test_regular_sessions_are_unchanged(monkeypatch):
    monkeypatch.setattr(documents,'get_all_documents',lambda owner:[{'id':41},{'id':42}])
    monkeypatch.setattr(security,'get_user_by_id',lambda owner: SimpleNamespace(id=owner))
    token=security.create_access_token(200)
    assert TestClient(app).get('/files',headers={'Authorization':'Bearer '+token}).json()=={'files':[{'id':41},{'id':42}]}
