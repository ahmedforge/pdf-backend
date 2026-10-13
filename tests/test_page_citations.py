import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.security import get_current_user
import app.services.pdf_service as pdf
import app.services.rag_service as rag
import app.routers.documents as routes


def events(stream):
    return [(block.splitlines()[0][7:], json.loads(block.splitlines()[1][6:]))
            for block in ''.join(stream).strip().split('\n\n')]


def test_page_chunks_use_physical_pages_and_skip_empty_short_text(monkeypatch):
    texts = ['', 'Tiny', 'First searchable physical page sentence. '*20,
             'Second searchable physical page sentence. '*20]
    monkeypatch.setattr(pdf, 'PdfReader', lambda path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda text=text: text) for text in texts]))
    chunks = pdf.extract_page_chunks('unused.pdf')
    assert {chunk['page_number'] for chunk in chunks} == {3, 4}
    assert all(not ('First' in chunk['chunk_text'] and 'Second' in chunk['chunk_text']) for chunk in chunks)


@pytest.fixture
def context(monkeypatch):
    chunks = [{'chunk_index': 25, 'page_number': 7, 'chunk_text': 'Stored passage.', 'similarity': .8}]
    monkeypatch.setattr(rag, 'semantic_search_chunks', lambda **kwargs: chunks)
    class LLM:
        def generate(self, prompt): return 'Valid [Chunk 25] invalid [Chunk 99].'
        def stream(self, prompt): yield from self.generate(prompt)
    monkeypatch.setattr(rag, 'llm', LLM())
    return chunks


def test_json_sources_preserve_existing_fields_and_strip_invalid_markers(context):
    result = rag.ask_document_rag(1, 'question')
    assert '[Chunk 99]' not in result['answer']
    assert result['sources'] == [{'chunk_index': 25, 'page': 7, 'text': 'Stored passage.', 'similarity': .8, 'preview': 'Stored passage.'}]
    context[0]['page_number'] = None
    assert rag.ask_document_rag(1, 'question')['sources'][0]['page'] is None


def test_sse_sources_first_done_last_and_split_marker_validation(context):
    result = events(rag.stream_document_events(1, 'question'))
    assert result[0][0] == 'sources'
    assert result[0][1]['sources'][0]['page'] == 7
    assert result[-1] == ('done', {'complete': True})
    assert ''.join(data['text'] for name, data in result if name == 'token') == 'Valid [Chunk 25] invalid .'
    assert '[Chunk 99]' in ''.join(rag.stream_document_rag(1, 'question'))  # Legacy stream unchanged.


def test_sse_failure_and_no_context_are_explicit(context, monkeypatch):
    class Failing:
        def stream(self, prompt):
            yield 'Partial answer'
            raise RuntimeError('provider failure')
    monkeypatch.setattr(rag, 'llm', Failing())
    result = events(rag.stream_document_events(1, 'question'))
    assert result[-2][0] == 'error'
    assert result[-1] == ('done', {'complete': False})
    monkeypatch.setattr(rag, 'semantic_search_chunks', lambda **kwargs: [])
    result = events(rag.stream_document_events(1, 'question'))
    assert result[0] == ('sources', {'sources': []})
    assert result[-1] == ('done', {'complete': True})


def test_route_opt_in_preserves_default_plain_stream_and_auth(context, monkeypatch):
    monkeypatch.setattr(routes, 'get_document_by_id', lambda *args: object())
    monkeypatch.setattr(routes, 'check_rate_limit', lambda *args: True)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    try:
        client = TestClient(app)
        plain = client.post('/files/1/ask/stream', json={'question': 'question'})
        structured = client.post('/files/1/ask/stream?format=sse', json={'question': 'question'})
        assert plain.status_code == structured.status_code == 200
        assert plain.headers['content-type'].startswith('text/plain')
        assert structured.headers['content-type'].startswith('text/event-stream')
        assert structured.text.startswith('event: sources\n')
        assert client.post('/files/1/ask/stream?format=invalid', json={'question': 'question'}).status_code == 422
    finally:
        app.dependency_overrides.clear()
    assert TestClient(app).post('/files/1/ask/stream?format=sse', json={'question': 'question'}).status_code in (401, 403)
