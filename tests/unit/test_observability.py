import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import Settings
from app.observability import build_tracer
from app.observability.events import USER_MESSAGE, EventCursor, bound_text, truncate
from app.observability.payload import validate_outbound_event
from app.observability.tracer import NullAgentTracer, SafeAgentTracer, ensure_safe_tracer
from app.observability.zizka import ZizkaAgentTracer
from app.tools.knowledge_retriever_tool import search_with_trace


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


def _settings(**overrides: object) -> Settings:
    return Settings(openai_api_key="sk-test", **overrides)  # type: ignore[arg-type]


def test_truncate_short_text_unchanged() -> None:
    assert truncate("hello", 10) == "hello"


def test_truncate_long_text() -> None:
    assert truncate("abcdefghij", 4) == "abcd"


def test_bound_text_flags_truncation() -> None:
    short = bound_text("hi", 10)
    assert short.as_data() == {"text": "hi"}
    long = bound_text("abcdefghij", 4)
    assert long.as_data() == {"text": "abcd", "truncated": True, "original_length": 10}


def test_null_tracer_returns_none() -> None:
    tracer = NullAgentTracer()
    assert tracer.log(USER_MESSAGE, {"text": "hi"}, session_id="s1") is None
    assert (
        tracer.log_crew_followup(
            session_id="s1", parent_id=None, task_outputs=[], final_output="ok"
        )
        is None
    )


def test_safe_tracer_swallows_inner_errors() -> None:
    tracer = SafeAgentTracer(ExplodingTracer())
    assert tracer.log(USER_MESSAGE, {"text": "hi"}, session_id="s1") is None
    assert (
        tracer.log_crew_followup(
            session_id="s1", parent_id=None, task_outputs=[], final_output="ok"
        )
        is None
    )


def test_ensure_safe_tracer_is_idempotent() -> None:
    null = NullAgentTracer()
    assert ensure_safe_tracer(None) is not None
    assert ensure_safe_tracer(null) is null
    safe = SafeAgentTracer(ExplodingTracer())
    assert ensure_safe_tracer(safe) is safe
    wrapped = ensure_safe_tracer(ExplodingTracer())
    assert isinstance(wrapped, SafeAgentTracer)


def test_build_tracer_null_when_disabled() -> None:
    assert isinstance(build_tracer(_settings()), NullAgentTracer)


def test_build_tracer_null_when_enabled_without_host_or_key() -> None:
    tracer = build_tracer(_settings(zizkadb_enabled=True))
    assert isinstance(tracer, NullAgentTracer)


def test_build_tracer_zizka_when_ready() -> None:
    tracer = build_tracer(_settings(zizkadb_enabled=True, zizkadb_host="http://localhost:9000"))
    assert isinstance(tracer, ZizkaAgentTracer)


def test_zizka_tracer_omits_optional_parent_and_metadata() -> None:
    tracer = ZizkaAgentTracer(
        _settings(zizkadb_enabled=True, zizkadb_host="http://localhost:9000")
    )
    captured: dict[str, Any] = {}

    class _Result:
        event_id = "803954d5-ed14-4e44-84bc-93b1bd9a9f80"

    async def _fake_log(**kwargs: object) -> _Result:
        captured.update(kwargs)
        return _Result()

    with patch("app.observability.zizka.ZizkaDB") as mock_cls:
        db = MagicMock()
        db.log = _fake_log
        instance = MagicMock()
        instance.__aenter__ = AsyncMock(return_value=db)
        instance.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = instance
        tracer.log(USER_MESSAGE, {"text": "hello"}, session_id="s1")

    assert "parent_id" not in captured
    assert "metadata" not in captured
    assert captured["session_id"] == "s1"
    assert captured["data"] == {"text": "hello"}


def test_zizka_tracer_swallows_sdk_errors() -> None:
    tracer = ZizkaAgentTracer(
        _settings(zizkadb_enabled=True, zizkadb_host="http://localhost:9999")
    )
    with patch("app.observability.zizka.ZizkaDB") as mock_cls:
        mock_cls.return_value.__aenter__ = MagicMock(side_effect=RuntimeError("down"))
        mock_cls.return_value.__aexit__ = MagicMock(return_value=None)
        assert tracer.log(USER_MESSAGE, {"text": "hi"}, session_id="s1") is None


def test_zizka_tracer_thread_timeout_does_not_wait_for_hung_worker() -> None:
    tracer = ZizkaAgentTracer(
        _settings(
            zizkadb_enabled=True,
            zizkadb_host="http://localhost:9000",
            zizkadb_timeout_seconds=0.05,
        )
    )

    def _hang() -> str:
        time.sleep(8)
        return "done"

    started = time.monotonic()
    try:
        tracer._run_in_thread(_hang)
        raise AssertionError("expected TimeoutError")
    except TimeoutError:
        pass
    assert time.monotonic() - started < 2.5


def test_zizka_tracer_swallows_crew_followup_errors() -> None:
    tracer = ZizkaAgentTracer(
        _settings(zizkadb_enabled=True, zizkadb_host="http://localhost:9999")
    )
    with patch("app.observability.zizka.ZizkaDB") as mock_cls:
        mock_cls.return_value.__aenter__ = MagicMock(side_effect=RuntimeError("down"))
        mock_cls.return_value.__aexit__ = MagicMock(return_value=None)
        assert (
            tracer.log_crew_followup(
                session_id="s1",
                parent_id="parent",
                task_outputs=[("task", "out")],
                final_output="done",
            )
            is None
        )


def test_validate_accepts_well_formed_user_message() -> None:
    event = validate_outbound_event(
        USER_MESSAGE,
        {"text": "What is Saad's experience?", "truncated": False},
        session_id="803954d5-ed14-4e44-84bc-93b1bd9a9f80",
    )
    assert event is not None
    assert event.data == {"text": "What is Saad's experience?"}
    assert event.parent_id is None


def test_validate_rejects_blank_user_text() -> None:
    assert (
        validate_outbound_event(USER_MESSAGE, {"text": "   "}, session_id="s1") is None
    )


def test_validate_rejects_unknown_event() -> None:
    assert validate_outbound_event("not_a_real_event", {"text": "x"}, session_id="s1") is None


def test_validate_rejects_unknown_decision_route() -> None:
    assert (
        validate_outbound_event("decision", {"route": "billing"}, session_id="s1") is None
    )


def test_validate_requires_category_on_moderation_decision() -> None:
    assert validate_outbound_event("decision", {"route": "moderation"}, session_id="s1") is None
    ok = validate_outbound_event(
        "decision",
        {"route": "moderation", "category": "greeting"},
        session_id="s1",
    )
    assert ok is not None


def test_validate_requires_simulated_on_assistant() -> None:
    assert (
        validate_outbound_event(
            "assistant_response", {"text": "hello"}, session_id="s1"
        )
        is None
    )
    ok = validate_outbound_event(
        "assistant_response",
        {"text": "hello", "truncated": False},
        session_id="s1",
        metadata={"simulated": True},
    )
    assert ok is not None
    assert ok.metadata == {"simulated": True}


def test_validate_drops_invalid_parent_id() -> None:
    event = validate_outbound_event(
        USER_MESSAGE,
        {"text": "hello"},
        session_id="s1",
        parent_id="not-a-uuid",
    )
    assert event is not None
    assert event.parent_id is None


def test_validate_keeps_uuid_parent_id() -> None:
    parent = "803954d5-ed14-4e44-84bc-93b1bd9a9f80"
    event = validate_outbound_event(
        "error",
        {"code": "timeout", "message": "chat_flow_timeout"},
        session_id="s1",
        parent_id=parent,
    )
    assert event is not None
    assert event.parent_id == parent


def test_validate_omits_optional_error_message() -> None:
    event = validate_outbound_event("error", {"code": "rate_limited"}, session_id="s1")
    assert event is not None
    assert event.data == {"code": "rate_limited"}
    assert event.parent_id is None
    assert event.metadata is None


def test_validate_treats_blank_error_message_as_omitted() -> None:
    event = validate_outbound_event(
        "error", {"code": "validation", "message": "   "}, session_id="s1"
    )
    assert event is not None
    assert "message" not in event.data


def test_validate_llm_decision_omits_optional_category() -> None:
    event = validate_outbound_event("decision", {"route": "llm"}, session_id="s1")
    assert event is not None
    assert event.data == {"route": "llm"}
    assert event.metadata is None


def test_validate_decision_ignores_null_optional_metadata() -> None:
    event = validate_outbound_event(
        "decision",
        {"route": "budget"},
        session_id="s1",
        metadata={"moderation_category": None},
    )
    assert event is not None
    assert event.metadata is None


def test_validate_omits_whitespace_parent_id_without_rejecting() -> None:
    event = validate_outbound_event(
        USER_MESSAGE, {"text": "hello"}, session_id="s1", parent_id="   "
    )
    assert event is not None
    assert event.parent_id is None


def test_validate_assistant_omits_optional_moderation_category() -> None:
    event = validate_outbound_event(
        "assistant_response",
        {"text": "hello"},
        session_id="s1",
        metadata={"simulated": False},
    )
    assert event is not None
    assert event.metadata == {"simulated": False}


def test_validate_strips_unknown_metadata() -> None:
    event = validate_outbound_event(
        "error",
        {"code": "rate_limited"},
        session_id="s1",
        metadata={"ip": "1.1.1.1"},
    )
    assert event is not None
    assert event.metadata is None


def test_search_with_trace_records_tool_call_and_result() -> None:
    tracer = RecordingTracer()
    cursor = EventCursor("kickoff-1")
    text = search_with_trace("education", tracer, "session-1", cursor)
    assert "education" in text.lower() or "saad" in text.lower()
    assert [e["event"] for e in tracer.events] == ["tool_call", "tool_result"]
    assert tracer.events[0]["parent_id"] == "kickoff-1"
    assert tracer.events[1]["parent_id"] == "evt-1"
    assert tracer.events[1]["data"]["tool"] == "search_knowledge_base"
    assert "matches" in tracer.events[1]["data"]
    assert cursor.event_id == "evt-2"
