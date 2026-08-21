from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    session_id: UUID
    message_id: str
    created_at: datetime
    simulated: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str
    created_at: datetime
    seq: int


class ChatHistoryResponse(BaseModel):
    session_id: UUID
    messages: list[ChatMessage]
