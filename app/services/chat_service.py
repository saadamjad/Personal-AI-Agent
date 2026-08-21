from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings
from app.core.errors import FlowExecutionError, RateLimitError, ValidationAppError
from app.core.logging import get_logger
from app.flows.chat_flow import run_chat_flow
from app.schemas.chat import ChatMessage
from app.services.moderation import classify_message
from app.services.rate_limiter import DailyCallBudget, SlidingWindowRateLimiter
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
        self._budget = DailyCallBudget(settings.chat_max_llm_calls_per_day)

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

        if not self._settings.llm_configured or not self._budget.check_and_record():
            logger.warning(
                "llm_fallback",
                extra={"llm_configured": self._settings.llm_configured, "session_id": session_id},
            )
            reply = _FALLBACK_REPLY
            simulated = True
        else:
            try:
                reply = run_chat_flow(self._settings, session_id, trimmed, history_text)
                simulated = False
            except Exception as exc:
                logger.exception("chat_flow_failed", extra={"session_id": session_id})
                raise FlowExecutionError("The agent is temporarily unavailable.") from exc

        assistant_msg = self._store.save_message(session_id, "assistant", reply)
        return ChatTurnResult(
            reply=reply,
            message_id=assistant_msg.id,
            created_at=assistant_msg.created_at,
            simulated=simulated,
        )

    def get_history(self, session_id: str, limit: int) -> list[ChatMessage]:
        messages = self._store.get_recent_messages(session_id, limit=limit)
        return [
            ChatMessage(role=m.role, content=m.content, created_at=m.created_at, seq=m.seq)
            for m in messages
        ]
