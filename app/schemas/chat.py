from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CAMEL_CONFIG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChatRequest(BaseModel):
    model_config = _CAMEL_CONFIG

    session_id: UUID
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    model_config = _CAMEL_CONFIG

    reply: str
    session_id: UUID
    message_id: str
    created_at: datetime
    simulated: bool = False


class ChatMessage(BaseModel):
    model_config = _CAMEL_CONFIG

    id: str
    role: str
    content: str
    timestamp: datetime
    seq: int


class ChatHistoryResponse(BaseModel):
    model_config = _CAMEL_CONFIG

    session_id: UUID
    messages: list[ChatMessage]
