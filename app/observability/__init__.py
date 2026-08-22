from app.core.config import Settings
from app.core.logging import get_logger
from app.observability.tracer import (
    AgentTracer,
    NullAgentTracer,
    SafeAgentTracer,
    ensure_safe_tracer,
)

logger = get_logger(__name__)


def build_tracer(settings: Settings) -> AgentTracer:
    if not settings.zizkadb_ready:
        if settings.zizkadb_enabled:
            logger.warning("zizkadb_enabled_but_not_configured")
        return NullAgentTracer()
    from app.observability.zizka import ZizkaAgentTracer

    return ZizkaAgentTracer(settings)


__all__ = [
    "AgentTracer",
    "NullAgentTracer",
    "SafeAgentTracer",
    "build_tracer",
    "ensure_safe_tracer",
]
