from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_receive_text() -> None:
    response = client.post("/api/v1/text", json={"text": "Hello FastAPI"})

    assert response.status_code == 200
    assert response.json() == {"text": "Hello FastAPI"}


def test_receive_text_rejects_form_data() -> None:
    response = client.post(
        "/api/v1/text",
        files={"text": (None, "Hello FastAPI")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"