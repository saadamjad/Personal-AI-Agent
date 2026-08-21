from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_chat_service, get_client_ip
from app.schemas.chat import ChatHistoryResponse, ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    client_ip: str = Depends(get_client_ip),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    session_id_str = str(body.session_id)
    service.check_rate_limits(session_id_str, client_ip)
    result = service.handle_turn(session_id_str, body.message)
    return ChatResponse(
        reply=result.reply,
        session_id=body.session_id,
        message_id=result.message_id,
        created_at=result.created_at,
        simulated=result.simulated,
    )


@router.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    service: ChatService = Depends(get_chat_service),
) -> ChatHistoryResponse:
    messages = service.get_history(str(session_id), limit)
    return ChatHistoryResponse(session_id=session_id, messages=messages)
