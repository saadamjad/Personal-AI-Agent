from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from app.core.config import Settings
from app.core.errors import FlowExecutionError, ValidationAppError
from app.flows.chat_flow import ChatFlowResult
from app.services.chat_service import ChatService
from app.storage.conversation_store import ConversationStore


@dataclass
class RecordingTracer:
    events: list[dict[str, Any]] = field(default_factory=list)
    _n: int = 0

    def log(
        self,
        event: str,
        data: dict[str, Any],
        *,
        session_id: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self._n += 1
        event_id = f"evt-{self._n}"
        self.events.append(
            {
                "event_id": event_id,
                "event": event,
                "data": data,
                "session_id": session_id,
                "parent_id": parent_id,
                "metadata": metadata,
            }
        )
        return event_id

    def log_crew_followup(
        self,
        *,
        session_id: str,
        parent_id: str | None,
        task_outputs: list[tuple[str, str]],
        final_output: str,
    ) -> str | None:
        last = parent_id
        for description, output in task_outputs:
            last = self.log(
                "crew_task",
                {"description": description, "output": output},
                session_id=session_id,
                parent_id=last,
            )
        return self.log(
            "crew_output",
            {"output": final_output},
            session_id=session_id,
            parent_id=last,
        )


class ExplodingTracer:
    def log(self, *args: object, **kwargs: object) -> str | None:
        raise RuntimeError("zizka down")

    def log_crew_followup(self, **kwargs: object) -> str | None:
        raise RuntimeError("zizka down")


def _service(tmp_path, tracer=None, **overrides) -> ChatService:
    settings = Settings(
        database_path=str(tmp_path / "test.db"),
        openai_api_key="sk-test",
        chat_max_llm_calls_per_day=overrides.pop("chat_max_llm_calls_per_day", 300),
        **overrides,
    )
    store = ConversationStore(settings)
    return ChatService(settings, store, tracer)


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
        "app.services.chat_service.run_chat_flow",
        return_value=ChatFlowResult(reply="Saad has 7 years of experience."),
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
    service = _service(tmp_path)
    with patch("app.services.chat_service.run_chat_flow", side_effect=RuntimeError("boom")):
        try:
            service.handle_turn("session-1", "What's his experience?")
            raise AssertionError("expected FlowExecutionError")
        except FlowExecutionError:
            pass


def test_empty_message_raises_validation_error(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        service.handle_turn("session-1", "   ")
        raise AssertionError("expected ValidationAppError")
    except ValidationAppError:
        pass


def test_moderation_emits_simulated_chain(tmp_path) -> None:
    tracer = RecordingTracer()
    service = _service(tmp_path, tracer=tracer)
    with patch("app.services.chat_service.run_chat_flow") as mock_flow:
        service.handle_turn("session-1", "hello!")
    mock_flow.assert_not_called()
    assert [e["event"] for e in tracer.events] == [
        "user_message",
        "decision",
        "assistant_response",
    ]
    assert tracer.events[1]["data"]["route"] == "moderation"
    assert tracer.events[2]["metadata"]["simulated"] is True
    assert all(e["session_id"] == "session-1" for e in tracer.events)
    assert tracer.events[1]["parent_id"] == tracer.events[0]["event_id"]
    assert tracer.events[2]["parent_id"] == tracer.events[1]["event_id"]


def test_budget_emits_decision_without_flow(tmp_path) -> None:
    tracer = RecordingTracer()
    service = _service(tmp_path, tracer=tracer, chat_max_llm_calls_per_day=0)
    with patch("app.services.chat_service.run_chat_flow") as mock_flow:
        service.handle_turn("session-1", "What's his experience?")
    mock_flow.assert_not_called()
    assert [e["event"] for e in tracer.events] == [
        "user_message",
        "decision",
        "assistant_response",
    ]
    assert tracer.events[1]["data"]["route"] == "budget"
    assert tracer.events[2]["metadata"]["simulated"] is True


def test_clean_message_forwards_session_and_parent_to_flow(tmp_path) -> None:
    tracer = RecordingTracer()
    service = _service(tmp_path, tracer=tracer)
    with patch(
        "app.services.chat_service.run_chat_flow",
        return_value=ChatFlowResult(reply="ok", last_event_id="crew-out"),
    ) as mock_flow:
        service.handle_turn("session-1", "What's his experience?")

    args = mock_flow.call_args.args
    assert args[1] == "session-1"
    assert args[5] == tracer.events[1]["event_id"]
    assert tracer.events[-1]["event"] == "assistant_response"
    assert tracer.events[-1]["parent_id"] == "crew-out"
    assert tracer.events[-1]["metadata"]["simulated"] is False


def test_flow_failure_emits_error(tmp_path) -> None:
    tracer = RecordingTracer()
    service = _service(tmp_path, tracer=tracer)
    with patch("app.services.chat_service.run_chat_flow", side_effect=RuntimeError("boom")):
        try:
            service.handle_turn("session-1", "What's his experience?")
        except FlowExecutionError:
            pass
    assert [e["event"] for e in tracer.events] == ["user_message", "decision", "error"]
    assert tracer.events[-1]["data"]["code"] == "crew_failed"


def test_validation_emits_error_without_user_message(tmp_path) -> None:
    tracer = RecordingTracer()
    service = _service(tmp_path, tracer=tracer)
    try:
        service.handle_turn("session-1", "   ")
    except ValidationAppError:
        pass
    assert [e["event"] for e in tracer.events] == ["error"]
    assert tracer.events[0]["data"]["code"] == "validation"


def test_rate_limit_trace_emits_error(tmp_path) -> None:
    from app.core.errors import RateLimitError

    tracer = RecordingTracer()
    service = _service(tmp_path, tracer=tracer, rate_limit_per_session_per_10min=0)
    try:
        service.check_rate_limits("session-1", "1.1.1.1")
        raise AssertionError("expected RateLimitError")
    except RateLimitError:
        pass
    assert tracer.events[0]["event"] == "error"
    assert tracer.events[0]["data"]["code"] == "rate_limited"
    assert "ip" not in tracer.events[0]["data"]


def test_exploding_tracer_does_not_break_chat(tmp_path) -> None:
    service = _service(tmp_path, tracer=ExplodingTracer())
    with patch(
        "app.services.chat_service.run_chat_flow",
        return_value=ChatFlowResult(reply="still works"),
    ):
        result = service.handle_turn("session-1", "What's his experience?")
    assert result.reply == "still works"
    assert result.simulated is False
