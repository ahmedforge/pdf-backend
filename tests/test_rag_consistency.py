import pytest
from app.config import settings
import app.services.rag_service as rag


@pytest.mark.parametrize('similarity,threshold', [(0.12, 0.3), (0.75, 0.3), (0.5, 0.8)])
def test_rag_paths_use_same_prompt_and_configured_threshold(monkeypatch, similarity, threshold):
    chunks = [
        {'chunk_index': 1, 'chunk_text': 'first', 'similarity': similarity},
        {'chunk_index': 2, 'chunk_text': 'second', 'similarity': similarity},
    ]
    monkeypatch.setattr(settings, 'rag_min_similarity', threshold)
    monkeypatch.setattr(rag, 'semantic_search_chunks', lambda **kwargs: chunks)
    prompts = []
    class LLM:
        def generate(self, prompt):
            prompts.append(prompt)
            return 'answer [Chunk 1]'
        def stream(self, prompt):
            prompts.append(prompt)
            yield 'answer [Chunk 1]'
    monkeypatch.setattr(rag, 'llm', LLM())
    answer = rag.ask_document_rag(1, 'question')
    assert ''.join(rag.stream_document_rag(1, 'question')) == answer['answer']
    assert prompts[0] == prompts[1]
    assert len(answer['sources']) == (2 if similarity >= threshold else 1)


def test_both_rag_paths_skip_llm_when_no_chunks(monkeypatch):
    monkeypatch.setattr(rag, 'semantic_search_chunks', lambda **kwargs: [])
    monkeypatch.setattr(rag, 'llm', object())
    answer = rag.ask_document_rag(1, 'question')
    assert answer['sources'] == []
    assert ''.join(rag.stream_document_rag(1, 'question')) == answer['answer']
