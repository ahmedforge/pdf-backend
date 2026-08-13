from fastapi.testclient import TestClient

from app.main import app


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