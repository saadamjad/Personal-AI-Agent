from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.core.errors import FlowExecutionError, RateLimitError, ValidationAppError
from app.core.logging import get_logger
from app.flows.chat_flow import ChatFlowResult, run_chat_flow
from app.observability.events import (
    ASSISTANT_RESPONSE,
    DECISION,
    ERROR,
    PAYLOAD_LIMIT,
    USER_MESSAGE,
    USER_TEXT_LIMIT,
    bound_text,
)
from app.observability.tracer import AgentTracer, ensure_safe_tracer
from app.schemas.chat import ChatMessage
from app.services.moderation import classify_message
from app.services.rate_limiter import SlidingWindowRateLimiter
from app.storage.conversation_store import ConversationStore


@dataclass(frozen=True)
class ChatTurnResult:
    reply: str
    message_id: str
    created_at: datetime
    simulated: bool


logger = get_logger(__name__)


def _build_fallback_reply(settings: Settings) -> str:
    contact = (
        f" In the meantime, you can reach {settings.agent_owner_name} directly at "
        f"{settings.agent_contact_email}."
        if settings.agent_contact_email
        else ""
    )
    return f"I'm having trouble reaching my knowledge system right now.{contact}"


class ChatService:
    def __init__(
        self,
        settings: Settings,
        store: ConversationStore,
        tracer: AgentTracer | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._tracer = ensure_safe_tracer(tracer)
        self._fallback_reply = _build_fallback_reply(settings)
        self._session_limiter = SlidingWindowRateLimiter(
            settings.rate_limit_per_session_per_10min
        )
        self._ip_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_ip_per_10min)
        # Bounded worker pool so a slow/hung LLM call can be capped by
        # chat_flow_timeout_seconds without blocking the caller's thread
        # indefinitely (CrewAI's flow.kickoff() is a blocking call). Sized at
        # 4 to give a little headroom under concurrent traffic before calls
        # start queueing behind each other.
        self._flow_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat-flow")

    def check_rate_limits(self, session_id: str, client_ip: str) -> None:
        if not self._session_limiter.check(session_id):
            self._trace_error(session_id, "rate_limited")
            raise RateLimitError("Too many messages in this session — please slow down.")
        if not self._ip_limiter.check(client_ip):
            self._trace_error(session_id, "rate_limited")
            raise RateLimitError("Too many requests from this network — please slow down.")

    def handle_turn(self, session_id: str, message: str) -> ChatTurnResult:
        trimmed = message.strip()
        if not trimmed:
            self._trace_error(session_id, "validation", message="empty")
            raise ValidationAppError("message cannot be empty")
        if len(trimmed) > self._settings.chat_max_message_length:
            self._trace_error(session_id, "validation", message="too_long")
            raise ValidationAppError("message exceeds the maximum allowed length")

        user_event_id = self._tracer.log(
            USER_MESSAGE,
            bound_text(trimmed, USER_TEXT_LIMIT).as_data(),
            session_id=session_id,
        )

        moderation = classify_message(trimmed, self._settings.agent_owner_name)
        if moderation.short_circuit_reply is not None:
            decision_id = self._tracer.log(
                DECISION,
                {"route": "moderation", "category": moderation.category},
                session_id=session_id,
                parent_id=user_event_id,
                metadata={"moderation_category": moderation.category},
            )
            self._store.save_message(session_id, "user", trimmed)
            return self._persist_assistant(
                session_id,
                moderation.short_circuit_reply,
                parent_id=decision_id,
                simulated=True,
                metadata={"moderation_category": moderation.category},
            )

        user_msg = self._store.save_message(session_id, "user", trimmed)
        history = self._store.get_recent_messages(session_id, limit=12)
        history_text = "\n".join(f"{m.role}: {m.content}" for m in history if m.id != user_msg.id)

        budget_ok = self._store.check_and_record_llm_call(self._settings.chat_max_llm_calls_per_day)
        if not self._settings.llm_configured or not budget_ok:
            route = "unconfigured" if not self._settings.llm_configured else "budget"
            logger.warning(
                "llm_fallback",
                extra={"llm_configured": self._settings.llm_configured, "session_id": session_id},
            )
            decision_id = self._tracer.log(
                DECISION, {"route": route}, session_id=session_id, parent_id=user_event_id
            )
            return self._persist_assistant(
                session_id,
                self._fallback_reply,
                parent_id=decision_id,
                simulated=True,
            )

        decision_id = self._tracer.log(
            DECISION, {"route": "llm"}, session_id=session_id, parent_id=user_event_id
        )
        flow_result = self._run_flow_with_timeout(
            session_id, trimmed, history_text, parent_id=decision_id
        )
        return self._persist_assistant(
            session_id,
            flow_result.reply,
            parent_id=flow_result.last_event_id or decision_id,
            simulated=False,
        )

    def _persist_assistant(
        self,
        session_id: str,
        reply: str,
        *,
        parent_id: str | None,
        simulated: bool,
        metadata: dict[str, Any] | None = None,
    ) -> ChatTurnResult:
        assistant_msg = self._store.save_message(session_id, "assistant", reply)
        extra = {"simulated": simulated, **(metadata or {})}
        self._tracer.log(
            ASSISTANT_RESPONSE,
            bound_text(reply, PAYLOAD_LIMIT).as_data(),
            session_id=session_id,
            parent_id=parent_id,
            metadata=extra,
        )
        return ChatTurnResult(
            reply=reply,
            message_id=assistant_msg.id,
            created_at=assistant_msg.created_at,
            simulated=simulated,
        )

    def _trace_error(
        self,
        session_id: str,
        code: str,
        *,
        message: str | None = None,
        parent_id: str | None = None,
    ) -> None:
        data: dict[str, Any] = {"code": code}
        if message is not None:
            data["message"] = message
        self._tracer.log(ERROR, data, session_id=session_id, parent_id=parent_id)

    def _run_flow_with_timeout(
        self,
        session_id: str,
        message: str,
        history_text: str,
        parent_id: str | None,
    ) -> ChatFlowResult:
        future = self._flow_executor.submit(
            run_chat_flow,
            self._settings,
            session_id,
            message,
            history_text,
            self._tracer,
            parent_id,
        )
        try:
            return future.result(timeout=self._settings.chat_flow_timeout_seconds)
        except FutureTimeoutError as exc:
            logger.warning("chat_flow_timeout", extra={"session_id": session_id})
            self._trace_error(
                session_id, "timeout", message="chat_flow_timeout", parent_id=parent_id
            )
            raise FlowExecutionError("The agent took too long to respond.") from exc
        except Exception as exc:
            logger.exception("chat_flow_failed", extra={"session_id": session_id})
            self._trace_error(
                session_id, "crew_failed", message="chat_flow_failed", parent_id=parent_id
            )
            raise FlowExecutionError("The agent is temporarily unavailable.") from exc

    def get_history(self, session_id: str, limit: int) -> list[ChatMessage]:
        messages = self._store.get_recent_messages(session_id, limit=limit)
        return [
            ChatMessage(id=m.id, role=m.role, content=m.content, timestamp=m.created_at, seq=m.seq)
            for m in messages
        ]
