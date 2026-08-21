from unittest.mock import patch

from app.core.config import Settings
from app.services.chat_service import ChatService
from app.storage.conversation_store import ConversationStore


def _service(tmp_path, **overrides) -> ChatService:
    settings = Settings(
        database_path=str(tmp_path / "test.db"),
        openai_api_key="sk-test",
        chat_max_llm_calls_per_day=overrides.pop("chat_max_llm_calls_per_day", 300),
        **overrides,
    )
    store = ConversationStore(settings)
    return ChatService(settings, store)


def test_moderation_short_circuits_before_calling_the_flow(tmp_path) -> None:
    service = _service(tmp_path)
    with patch("app.services.chat_service.run_chat_flow") as mock_flow:
        result = service.handle_turn("session-1", "hello!")
    mock_flow.assert_not_called()
    assert result.simulated is True
    assert "Saad" in result.reply


def test_clean_message_calls_the_flow_and_persists(tmp_path) -> None:
    service = _service(tmp_path)
    with patch(
        "app.services.chat_service.run_chat_flow", return_value="Saad has 7 years of experience."
    ) as mock_flow:
        result = service.handle_turn("session-1", "What's his experience?")

    mock_flow.assert_called_once()
    assert result.reply == "Saad has 7 years of experience."
    assert result.simulated is False

    history = service.get_history("session-1", limit=10)
    assert [m.role for m in history] == ["user", "assistant"]


def test_budget_exceeded_falls_back_without_calling_the_flow(tmp_path) -> None:
    service = _service(tmp_path, chat_max_llm_calls_per_day=0)
    with patch("app.services.chat_service.run_chat_flow") as mock_flow:
        result = service.handle_turn("session-1", "What's his experience?")
    mock_flow.assert_not_called()
    assert result.simulated is True


def test_flow_failure_raises_flow_execution_error(tmp_path) -> None:
    from app.core.errors import FlowExecutionError

    service = _service(tmp_path)
    with patch("app.services.chat_service.run_chat_flow", side_effect=RuntimeError("boom")):
        try:
            service.handle_turn("session-1", "What's his experience?")
            raise AssertionError("expected FlowExecutionError")
        except FlowExecutionError:
            pass


def test_empty_message_raises_validation_error(tmp_path) -> None:
    from app.core.errors import ValidationAppError

    service = _service(tmp_path)
    try:
        service.handle_turn("session-1", "   ")
        raise AssertionError("expected ValidationAppError")
    except ValidationAppError:
        pass
