from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    status: str
    knowledge_loaded: bool
    llm_configured: bool
