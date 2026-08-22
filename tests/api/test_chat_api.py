import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.flows.chat_flow import ChatFlowResult


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://saadstack.com")

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


async def test_chat_happy_path_uses_camelcase_wire_format(app_client) -> None:
    """The website's chatApi.js sends {sessionId, message} and reads
    {reply, messageId, simulated} back — the wire format must match that
    exactly, not Python's snake_case, or the chat widget breaks entirely."""
    session_id = str(uuid.uuid4())
    with patch(
        "app.services.chat_service.run_chat_flow",
        return_value=ChatFlowResult(reply="Saad is a great engineer."),
    ):
        async with app_client as client:
            resp = await client.post(
                "/api/v1/chat", json={"sessionId": session_id, "message": "Tell me about Saad"}
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Saad is a great engineer."
    assert body["sessionId"] == session_id
    assert "messageId" in body and body["messageId"]
    assert body["simulated"] is False
    # snake_case must NOT appear — that would mean the alias config regressed
    assert "session_id" not in body
    assert "message_id" not in body


async def test_chat_history_uses_camelcase_and_id_timestamp_fields(app_client) -> None:
    session_id = str(uuid.uuid4())
    with patch(
        "app.services.chat_service.run_chat_flow",
        return_value=ChatFlowResult(reply="reply text"),
    ):
        async with app_client as client:
            await client.post(
                "/api/v1/chat", json={"sessionId": session_id, "message": "hello there question"}
            )
            resp = await client.get(
                "/api/v1/chat/history", params={"sessionId": session_id, "limit": 20}
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessionId"] == session_id
    assert len(body["messages"]) == 2
    for msg in body["messages"]:
        assert "id" in msg and msg["id"]
        assert "timestamp" in msg
        assert "role" in msg and "content" in msg


async def test_chat_invalid_session_id(app_client) -> None:
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat", json={"sessionId": "not-a-uuid", "message": "hi"}
        )
    assert resp.status_code == 422


async def test_chat_oversized_message_rejected_by_schema(app_client) -> None:
    session_id = str(uuid.uuid4())
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat", json={"sessionId": session_id, "message": "x" * 2001}
        )
    assert resp.status_code == 422


async def test_chat_oversized_body_rejected_by_middleware(app_client) -> None:
    session_id = str(uuid.uuid4())
    huge_message = "x" * 9000
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat",
            content=f'{{"sessionId": "{session_id}", "message": "{huge_message}"}}'.encode(),
            headers={"Content-Type": "application/json", "Origin": "https://saadstack.com"},
        )
    assert resp.status_code == 413
    assert resp.json() == {"error": "Request body exceeds the allowed size."}


async def test_oversized_body_rejection_still_carries_cors_headers(app_client) -> None:
    """Regression test: CORS must wrap BodySizeLimitMiddleware, or the browser
    discards this 413 as an opaque cross-origin failure instead of showing it."""
    session_id = str(uuid.uuid4())
    huge_message = "x" * 9000
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat",
            content=f'{{"sessionId": "{session_id}", "message": "{huge_message}"}}'.encode(),
            headers={"Content-Type": "application/json", "Origin": "https://saadstack.com"},
        )
    assert resp.status_code == 413
    assert resp.headers.get("access-control-allow-origin") == "https://saadstack.com"


async def test_malformed_json_does_not_leak_stack_trace(app_client) -> None:
    async with app_client as client:
        resp = await client.post(
            "/api/v1/chat", content=b"{not valid json", headers={"Content-Type": "application/json"}
        )
    assert resp.status_code == 422
    assert "Traceback" not in resp.text


async def test_rate_limit_error_uses_flat_error_string(app_client, monkeypatch) -> None:
    """The frontend's formatApiError only recognizes a flat {"error": "..."}
    string body — a nested {"error": {"message": ...}} shape is silently
    discarded and replaced with a generic fallback message client-side."""
    monkeypatch.setenv("RATE_LIMIT_PER_SESSION_PER_10MIN", "1")

    from app.api import deps
    from app.core.config import get_settings

    get_settings.cache_clear()
    deps.get_chat_service.cache_clear()

    session_id = str(uuid.uuid4())
    with patch(
        "app.services.chat_service.run_chat_flow",
        return_value=ChatFlowResult(reply="ok"),
    ):
        async with app_client as client:
            resp = await client.post(
                "/api/v1/chat", json={"sessionId": session_id, "message": "hi there"}
            )
            assert resp.status_code == 200
            resp = await client.post(
                "/api/v1/chat", json={"sessionId": session_id, "message": "hi again"}
            )
    assert resp.status_code == 429
    body = resp.json()
    assert isinstance(body["error"], str)
    assert "slow down" in body["error"]
