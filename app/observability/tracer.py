from typing import Any, Protocol

from app.core.logging import get_logger

logger = get_logger(__name__)


class AgentTracer(Protocol):
    """Best-effort turn recorder. Implementations must not raise to callers."""

    def log(
        self,
        event: str,
        data: dict[str, Any],
        *,
        session_id: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None: ...

    def log_crew_followup(
        self,
        *,
        session_id: str,
        parent_id: str | None,
        task_outputs: list[tuple[str, str]],
        final_output: str,
    ) -> str | None: ...


class NullAgentTracer:
    def log(
        self,
        event: str,
        data: dict[str, Any],
        *,
        session_id: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        return None

    def log_crew_followup(
        self,
        *,
        session_id: str,
        parent_id: str | None,
        task_outputs: list[tuple[str, str]],
        final_output: str,
    ) -> str | None:
        return None


class SafeAgentTracer:
    """Guarantees a misbehaving tracer cannot break a chat turn."""

    def __init__(self, inner: AgentTracer) -> None:
        self._inner = inner

    def log(
        self,
        event: str,
        data: dict[str, Any],
        *,
        session_id: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        try:
            return self._inner.log(
                event,
                data,
                session_id=session_id,
                parent_id=parent_id,
                metadata=metadata,
            )
        except Exception:
            logger.warning(
                "tracer_log_failed",
                extra={"event": event, "session_id": session_id},
                exc_info=True,
            )
            return None

    def log_crew_followup(
        self,
        *,
        session_id: str,
        parent_id: str | None,
        task_outputs: list[tuple[str, str]],
        final_output: str,
    ) -> str | None:
        try:
            return self._inner.log_crew_followup(
                session_id=session_id,
                parent_id=parent_id,
                task_outputs=task_outputs,
                final_output=final_output,
            )
        except Exception:
            logger.warning(
                "tracer_crew_followup_failed", extra={"session_id": session_id}, exc_info=True
            )
            return None


def ensure_safe_tracer(tracer: AgentTracer | None) -> AgentTracer:
    """Idempotent wrap — Null never raises; Safe is not wrapped again."""
    if tracer is None or isinstance(tracer, NullAgentTracer):
        return tracer if tracer is not None else NullAgentTracer()
    if isinstance(tracer, SafeAgentTracer):
        return tracer
    return SafeAgentTracer(tracer)
