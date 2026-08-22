from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from zizkadb import ZizkaDB
from zizkadb_crewai import ZizkaDBCrewLogger

from app.core.config import Settings
from app.core.logging import get_logger
from app.observability.events import PAYLOAD_LIMIT, TOOL_OUTPUT_LIMIT, truncate
from app.observability.payload import normalize_optional_id, validate_outbound_event

T = TypeVar("T")

logger = get_logger(__name__)


class ZizkaAgentTracer:
    """Sync facade over the async zizkadb-sdk / zizkadb-crewai clients.

    Each call opens a fresh ZizkaDB client inside a dedicated event loop so we
    never reuse an ``httpx.AsyncClient`` across loops.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._agent = settings.zizkadb_agent

    def log(
        self,
        event: str,
        data: dict[str, Any],
        *,
        session_id: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        validated = validate_outbound_event(
            event,
            data,
            session_id=session_id,
            parent_id=parent_id,
            metadata=metadata,
        )
        if validated is None:
            return None
        kwargs: dict[str, Any] = {
            "agent": self._agent,
            "event": validated.event,
            "data": validated.data,
            "session_id": validated.session_id,
        }
        if validated.parent_id is not None:
            kwargs["parent_id"] = validated.parent_id
        if validated.metadata:
            kwargs["metadata"] = validated.metadata
        result = self._run(lambda db: db.log(**kwargs))
        return result.event_id if result is not None else None

    def log_crew_followup(
        self,
        *,
        session_id: str,
        parent_id: str | None,
        task_outputs: list[tuple[str, str]],
        final_output: str,
    ) -> str | None:
        session = session_id.strip()
        if not session:
            logger.warning("zizkadb_event_rejected", extra={"event": "crew_followup"})
            return None
        parent = normalize_optional_id(parent_id)

        async def _write(db: ZizkaDB) -> str | None:
            crew_logger = ZizkaDBCrewLogger(db, agent=self._agent, session_id=session)
            crew_logger.last_event_id = parent
            for description, output in task_outputs:
                desc = description.strip()
                if not desc and not output:
                    continue
                await crew_logger.log_task(
                    description=truncate(desc, PAYLOAD_LIMIT),
                    output=truncate(output, TOOL_OUTPUT_LIMIT),
                )
            await crew_logger.log_output(truncate(final_output, PAYLOAD_LIMIT))
            last_id: str | None = crew_logger.last_event_id
            return last_id

        return self._run(_write)

    def _connect(self) -> ZizkaDB:
        host = self._settings.zizkadb_host
        api_key = self._settings.zizkadb_api_key
        kwargs: dict[str, Any] = {"timeout": self._settings.zizkadb_timeout_seconds}
        if api_key:
            kwargs["api_key"] = api_key
        if host:
            kwargs["host"] = host
        if "api_key" not in kwargs and "host" not in kwargs:
            raise RuntimeError("ZizkaDB tracer constructed without host or api_key")
        return ZizkaDB(**kwargs)

    def _run(self, factory: Callable[[ZizkaDB], Awaitable[T]]) -> T | None:
        def _start() -> T:
            async def _inner() -> T:
                async with self._connect() as db:
                    return await factory(db)

            return asyncio.run(_inner())

        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return _start()
            return self._run_in_thread(_start)
        except Exception:
            logger.warning("zizkadb_request_failed", extra={"agent": self._agent}, exc_info=True)
            return None

    def _run_in_thread(self, start: Callable[[], T]) -> T:
        # Do not use `with ThreadPoolExecutor(...)`: on timeout its __exit__
        # waits for the worker, which would block the chat turn until the hung
        # ingest finishes. CrewAI may already have a running loop when tools
        # fire, so this path is the production one for tool_* events.
        timeout = self._settings.zizkadb_timeout_seconds + 1
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zizka-loop")
        try:
            return pool.submit(start).result(timeout=timeout)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
