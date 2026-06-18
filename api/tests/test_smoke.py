import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_books(client: TestClient) -> None:
    r = client.get("/api/books")
    assert r.status_code == 200
    books = r.json()
    assert len(books) >= 1
    assert "bookId" in books[0]
    assert "pageCount" in books[0]


def test_query_streams_events(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/api/query",
        json={"question": "Why did Rome fall?"},
    ) as response:
        assert response.status_code == 200
        event_types: list[str] = []
        for raw_line in response.iter_lines():
            if not raw_line or not raw_line.startswith("data:"):
                continue
            payload = json.loads(raw_line.removeprefix("data:").strip())
            event_types.append(payload["type"])
            if payload["type"] == "done":
                break

    assert "citations" in event_types
    assert "token" in event_types
    assert event_types[-1] == "done"
