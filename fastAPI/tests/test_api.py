from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from src.db.models.message import Message
from src.db.models.profile import Profile
from src.db.session import get_db_session
from src.main import app

client = TestClient(app)
last_fake_session: FakeSession | None = None


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.profile = Profile(id=1, user_id="user-1", name="Old Name")
        self.message = [Message(id=1, user_id="user-1", text="Hello FastAPI")]

    async def scalar(self, statement: object) -> object | None:
        user_id = next(iter(statement.compile().params.values()))
        if user_id in {"user-1", "user-2"}:
            if user_id == "user-2":
                self.profile = Profile(id=2, user_id="user-2", name="Old Name")
            return self.profile
        return None

    async def scalars(self, statement: object) -> list[Message]:
        user_id = next(iter(statement.compile().params.values()))
        return [message for message in self.message if message.user_id == user_id]

    def add(self, instance: object) -> None:
        self.added.append(instance)


async def fake_get_db_session() -> AsyncIterator[FakeSession]:
    global last_fake_session
    last_fake_session = FakeSession()
    yield last_fake_session


app.dependency_overrides[get_db_session] = fake_get_db_session


def test_receive_message() -> None:
    response = client.post(
        "/api/v1/message",
        json={"user_id": "user-1", "text": "Hello FastAPI"},
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-1", "text": "Hello FastAPI"}
    assert last_fake_session is not None
    assert last_fake_session.profile.user_id == "user-1"
    assert last_fake_session.profile.name == "Old Name"
    assert not any(isinstance(instance, Profile) for instance in last_fake_session.added)
    assert any(isinstance(instance, Message) for instance in last_fake_session.added)


def test_get_profile_message() -> None:
    response = client.get("/api/v1/profile", params={"user_id": "user-1"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-1",
        "name": "Old Name",
        "message": [{"text": "Hello FastAPI"}],
    }


def test_get_profile_message_rejects_extra_query_params() -> None:
    response = client.get("/api/v1/profile", params={"user_id": "user-1", "limit": "1"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_QUERY_PARAMS"


def test_update_profile_name() -> None:
    response = client.post(
        "/api/v1/profile",
        json={"user_id": "user-2", "name": "Bob"},
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-2", "name": "Bob"}
    assert last_fake_session is not None
    assert last_fake_session.profile.user_id == "user-2"
    assert last_fake_session.profile.name == "Bob"
    assert not any(isinstance(instance, Profile) for instance in last_fake_session.added)


def test_update_profile_name_rejects_form_data() -> None:
    response = client.post(
        "/api/v1/profile",
        files={"user_id": (None, "user-2"), "name": (None, "Bob")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_receive_message_rejects_form_data() -> None:
    response = client.post(
        "/api/v1/message",
        files={"text": (None, "Hello FastAPI")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"