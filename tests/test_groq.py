import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import get_current_user
from app.services.llm.groq import GroqProvider
import app.routers.documents as documents


@pytest.fixture
def groq(monkeypatch):
    monkeypatch.setattr(settings, 'groq_api_key', 'test-secret')
    return GroqProvider()


@pytest.mark.parametrize('method', ['generate', 'stream'])
@pytest.mark.parametrize('failure', ['timeout', 'status', 'invalid'])
def test_provider_failures_are_safe(groq, monkeypatch, method, failure):
    def handle(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('test-secret raw response', request=request)
        if failure == 'status':
            return httpx.Response(429, text='test-secret raw response')
        return httpx.Response(200, text='data: broken-json\n\n' if method == 'stream' else '{}')

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(httpx, 'post', client.post)
        monkeypatch.setattr(httpx, 'stream', client.stream)
        with pytest.raises(RuntimeError) as caught:
            result = getattr(groq, method)('question')
            if method == 'stream':
                list(result)
        assert 'test-secret' not in str(caught.value)
        assert 'raw response' not in str(caught.value)


def test_stream_success_without_raw_logging(groq, monkeypatch, capsys):
    def handle(request):
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n')
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(httpx, 'stream', client.stream)
        assert list(groq.stream('question')) == ['hello']
    assert 'hello' not in capsys.readouterr().out
    assert groq.TIMEOUT.read == 60.0


def test_truncated_stream_fails(groq, monkeypatch):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=''))) as client:
        monkeypatch.setattr(httpx, 'stream', client.stream)
        with pytest.raises(RuntimeError, match='before completing'):
            list(groq.stream('question'))


@pytest.mark.parametrize('after_first_token', [False, True])
def test_stream_route_handles_provider_failure(monkeypatch, after_first_token):
    class User:
        id = 123
    monkeypatch.setattr(documents, 'get_document_by_id', lambda *args: object())
    monkeypatch.setattr(documents, 'check_rate_limit', lambda *args: True)
    closed = []
    def failing_stream(**kwargs):
        try:
            if after_first_token:
                yield 'partial answer'
            raise RuntimeError('Groq is unavailable. Please try again later.')
        finally:
            closed.append(True)
    monkeypatch.setattr(documents, 'stream_document_rag', failing_stream)
    app.dependency_overrides[get_current_user] = lambda: User()
    try:
        with TestClient(app) as client:
            response = client.post('/files/1/ask/stream', json={'question': 'What is this about?'})
        if after_first_token:
            assert response.status_code == 200
            assert response.text.startswith('partial answer')
            assert 'Generation interrupted' in response.text
        else:
            assert response.status_code == 503
        assert closed == [True]
    finally:
        app.dependency_overrides.clear()
