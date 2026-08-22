from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings
from app.observability import build_tracer
from app.services.chat_service import ChatService
from app.storage.conversation_store import ConversationStore


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    store = ConversationStore(settings)
    return ChatService(settings, store, build_tracer(settings))


def get_client_ip(request: Request) -> str:
    # X-Forwarded-For is a comma-separated hop chain; a client can prepend
    # arbitrary fake entries before it ever reaches our trusted edge proxy
    # (Railway), which appends the real client IP as the LAST entry. Taking
    # the first entry would let a client spoof its way around IP rate
    # limiting — take the last one instead.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
