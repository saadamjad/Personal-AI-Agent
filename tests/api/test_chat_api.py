import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")

    from app.api import deps
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    deps.get_chat_service.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_healthz(app_client) -> None:
    async with app_client as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_chat_happy_path(app_client) -> None:
    session_id = str(uuid.uuid4())
    with patch("app.services.chat_service.run_chat_flow", return_value="Saad is a great engineer."):
        async with app_client as client:
            resp = await client.post(
                "/api/v1/chat", json={"session_id": session_id, "message": "Tell me about Saad"}
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Saad is a great engineer."
    assert body["session_id"] == session_id


async def test_chat_invalid_session_id(app_client) -> None:
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat", json={"session_id": "not-a-uuid", "message": "hi"}
        )
    assert resp.status_code == 422


async def test_chat_oversized_message_rejected_by_schema(app_client) -> None:
    session_id = str(uuid.uuid4())
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat", json={"session_id": session_id, "message": "x" * 2001}
        )
    assert resp.status_code == 422


async def test_chat_oversized_body_rejected_by_middleware(app_client) -> None:
    session_id = str(uuid.uuid4())
    huge_message = "x" * 9000
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat",
            content=f'{{"session_id": "{session_id}", "message": "{huge_message}"}}'.encode(),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 413


async def test_malformed_json_does_not_leak_stack_trace(app_client) -> None:
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat", content=b"{not valid json", headers={"Content-Type": "application/json"}
        )
    assert resp.status_code == 422
    assert "Traceback" not in resp.text


async def test_rate_limit_trips_after_max_requests(app_client, monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_SESSION_PER_10MIN", "2")

    from app.api import deps
    from app.core.config import get_settings

    get_settings.cache_clear()
    deps.get_chat_service.cache_clear()

    session_id = str(uuid.uuid4())
    with patch("app.services.chat_service.run_chat_flow", return_value="ok"):
        async with app_client as client:
            for _ in range(2):
                resp = await client.post(
                    "/api/v1/chat", json={"session_id": session_id, "message": "hi there"}
                )
                assert resp.status_code == 200
            resp = await client.post(
                "/api/v1/chat", json={"session_id": session_id, "message": "hi again"}
            )
    assert resp.status_code == 429
