from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings
from app.services.chat_service import ChatService
from app.storage.conversation_store import ConversationStore


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    store = ConversationStore(settings)
    return ChatService(settings, store)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
