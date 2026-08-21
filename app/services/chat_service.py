from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings
from app.core.errors import FlowExecutionError, RateLimitError, ValidationAppError
from app.core.logging import get_logger
from app.flows.chat_flow import run_chat_flow
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

_FALLBACK_REPLY = (
    "I'm having trouble reaching my knowledge system right now. In the meantime, you can "
    "reach Saad directly at saad.amjad434@gmail.com or find him on LinkedIn."
)


class ChatService:
    def __init__(self, settings: Settings, store: ConversationStore) -> None:
        self._settings = settings
        self._store = store
        self._session_limiter = SlidingWindowRateLimiter(
            settings.rate_limit_per_session_per_10min
        )
        self._ip_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_ip_per_10min)
        # Single-worker executor so a slow/hung LLM call can be bounded by
        # chat_flow_timeout_seconds without blocking the caller's thread
        # indefinitely (CrewAI's flow.kickoff() is a blocking call).
        self._flow_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat-flow")

    def check_rate_limits(self, session_id: str, client_ip: str) -> None:
        if not self._session_limiter.check(session_id):
            raise RateLimitError("Too many messages in this session — please slow down.")
        if not self._ip_limiter.check(client_ip):
            raise RateLimitError("Too many requests from this network — please slow down.")

    def handle_turn(self, session_id: str, message: str) -> ChatTurnResult:
        trimmed = message.strip()
        if not trimmed:
            raise ValidationAppError("message cannot be empty")
        if len(trimmed) > self._settings.chat_max_message_length:
            raise ValidationAppError("message exceeds the maximum allowed length")

        moderation = classify_message(trimmed)
        if moderation.short_circuit_reply is not None:
            self._store.save_message(session_id, "user", trimmed)
            assistant_msg = self._store.save_message(
                session_id, "assistant", moderation.short_circuit_reply
            )
            return ChatTurnResult(
                reply=moderation.short_circuit_reply,
                message_id=assistant_msg.id,
                created_at=assistant_msg.created_at,
                simulated=True,
            )

        user_msg = self._store.save_message(session_id, "user", trimmed)
        history = self._store.get_recent_messages(session_id, limit=12)
        history_text = "\n".join(f"{m.role}: {m.content}" for m in history if m.id != user_msg.id)

        budget_ok = self._store.check_and_record_llm_call(self._settings.chat_max_llm_calls_per_day)
        if not self._settings.llm_configured or not budget_ok:
            logger.warning(
                "llm_fallback",
                extra={"llm_configured": self._settings.llm_configured, "session_id": session_id},
            )
            reply = _FALLBACK_REPLY
            simulated = True
        else:
            reply = self._run_flow_with_timeout(session_id, trimmed, history_text)
            simulated = False

        assistant_msg = self._store.save_message(session_id, "assistant", reply)
        return ChatTurnResult(
            reply=reply,
            message_id=assistant_msg.id,
            created_at=assistant_msg.created_at,
            simulated=simulated,
        )

    def _run_flow_with_timeout(self, session_id: str, message: str, history_text: str) -> str:
        future = self._flow_executor.submit(
            run_chat_flow, self._settings, session_id, message, history_text
        )
        try:
            return future.result(timeout=self._settings.chat_flow_timeout_seconds)
        except FutureTimeoutError as exc:
            logger.warning("chat_flow_timeout", extra={"session_id": session_id})
            raise FlowExecutionError("The agent took too long to respond.") from exc
        except Exception as exc:
            logger.exception("chat_flow_failed", extra={"session_id": session_id})
            raise FlowExecutionError("The agent is temporarily unavailable.") from exc

    def get_history(self, session_id: str, limit: int) -> list[ChatMessage]:
        messages = self._store.get_recent_messages(session_id, limit=limit)
        return [
            ChatMessage(id=m.id, role=m.role, content=m.content, timestamp=m.created_at, seq=m.seq)
            for m in messages
        ]
