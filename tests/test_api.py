from fastapi.testclient import TestClient
from app.services.rag_service import ask_document_rag
from app.main import app
import app.routers.documents as documents_router
from app.main import app
from app.security import get_current_user


client = TestClient(app)


def test_home():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Backend is running"


def test_invalid_registration():
    response = client.post(
        "/auth/register",
        json={
            "email": "not-an-email",
            "password": "123"
        }
    )

    assert response.status_code == 422


def test_files_requires_authentication():
    response = client.get("/files")

    assert response.status_code in (401, 403)

def test_ask_requires_authentication():
    response = client.post(
        "/files/1/ask",
        params={
            "question": "What is this document about?"
        }
    )

    assert response.status_code in (401, 403)
def test_rag_service_returns_grounded_answer(monkeypatch):
    fake_chunks = [
        {
            "id": 1,
            "chunk_index": 42,
            "chunk_text": "Wheeler is the central character in the story.",
            "similarity": 0.75,
        }
    ]

    def fake_semantic_search(
        document_id: int,
        query: str,
        limit: int = 5,
    ):
        return fake_chunks

    class FakeLLM:
        def generate(self, prompt: str) -> str:
             return "The main character is Wheeler. [Chunk 42]"
    monkeypatch.setattr(
        "app.services.rag_service.llm",
        FakeLLM(),
    )

    monkeypatch.setattr(
        "app.services.rag_service.semantic_search_chunks",
        fake_semantic_search,
    )

    

    result = ask_document_rag(
        document_id=1,
        question="Who is the main character?",
        top_k=5,
        min_similarity=0.28,
    )

    assert result["answer"] == (
        "The main character is Wheeler. [Chunk 42]"
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["chunk_index"] == 42
    assert result["sources"][0]["similarity"] == 0.75
def test_rag_service_rejects_weak_matches(monkeypatch):
    fake_chunks = [
        {
            "id": 1,
            "chunk_index": 10,
            "chunk_text": "This chunk is unrelated.",
            "similarity": 0.12,
        }
    ]

    def fake_semantic_search(
        document_id: int,
        query: str,
        limit: int = 5,
    ):
        return fake_chunks

    monkeypatch.setattr(
        "app.services.rag_service.semantic_search_chunks",
        fake_semantic_search,
    )

    result = ask_document_rag(
        document_id=1,
        question="What is the main topic?",
        top_k=5,
        min_similarity=0.28,
    )

    assert result["answer"] == (
        "I could not find the answer in the document."
    )

    assert result["sources"] == []
def test_rag_service_removes_invalid_citations(monkeypatch):
    fake_chunks = [
        {
            "id": 1,
            "chunk_index": 42,
            "chunk_text": "Wheeler is the central character.",
            "similarity": 0.75,
        }
    ]

    def fake_semantic_search(
        document_id: int,
        query: str,
        limit: int = 5,
    ):
        return fake_chunks

    class FakeLLM:
        def generate(self, prompt: str) -> str:
            return "Wheeler is the main character. [Chunk 42] [Chunk 999]"

    monkeypatch.setattr(
        "app.services.rag_service.semantic_search_chunks",
        fake_semantic_search,
    )

    monkeypatch.setattr(
        "app.services.rag_service.llm",
        FakeLLM(),
    )

    result = ask_document_rag(
        document_id=1,
        question="Who is the main character?",
        top_k=5,
        min_similarity=0.28,
    )

    assert "[Chunk 42]" in result["answer"]
    assert "[Chunk 999]" not in result["answer"]
def test_ask_stream_requires_authentication():
    response = client.post(
        "/files/1/ask/stream",
        json={
            "question": "What is this document about?",
            "top_k": 5,
        },
    )

    assert response.status_code in (401, 403)
def test_ask_rate_limited(monkeypatch):
    monkeypatch.setattr(
        documents_router,
        "check_rate_limit",
        lambda user_id: False,
    )

    response = client.post(
        "/files/1/ask",
        json={
            "question": "What is this document about?",
            "top_k": 3,
        },
    )

    assert response.status_code in (401, 403)
def test_ask_returns_429_when_rate_limited(monkeypatch):
    monkeypatch.setattr(
        "app.routers.documents.check_rate_limit",
        lambda user_id: False,
    )

    monkeypatch.setattr(
        "app.routers.documents.get_document_by_id",
        lambda document_id, user_id: object(),
    )

    class FakeUser:
        id = 123

    app.dependency_overrides[get_current_user] = lambda: FakeUser()

    try:
        response = client.post(
            "/files/1/ask",
            json={
                "question": "What is this document about?",
                "top_k": 3,
            },
        )

        assert response.status_code == 429
        assert response.json()["detail"] == (
            "Too many RAG requests. Please try again later."
        )
    finally:
        app.dependency_overrides.clear()