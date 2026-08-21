from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse()


@router.get("/readyz", response_model=ReadinessResponse)
async def readyz() -> ReadinessResponse:
    settings = get_settings()
    try:
        from app.knowledge.loader import knowledge_loaded

        loaded = knowledge_loaded()
    except Exception:
        loaded = False

    ready = loaded and settings.llm_configured
    return ReadinessResponse(
        status="ready" if ready else "degraded",
        knowledge_loaded=loaded,
        llm_configured=settings.llm_configured,
    )
