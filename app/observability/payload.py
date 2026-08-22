"""Validate and normalize events before they are written to ZizkaDB.

Rejected events are not sent — a bad record is worse than a missing one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.core.logging import get_logger
from app.observability.events import (
    ASSISTANT_RESPONSE,
    CREW_KICKOFF,
    DECISION,
    ERROR,
    TOOL_CALL,
    TOOL_RESULT,
    USER_MESSAGE,
)

logger = get_logger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

MODERATION_CATEGORIES = frozenset(
    {"jailbreak", "abuse", "greeting", "thanks", "gibberish", "clean"}
)


class _UserData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    truncated: bool = False
    original_length: int | None = Field(default=None, ge=1)

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text is blank")
        return value


class _AssistantData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    truncated: bool = False
    original_length: int | None = Field(default=None, ge=1)


class _DecisionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: Literal["moderation", "budget", "unconfigured", "llm"]
    category: str | None = None

    @model_validator(mode="after")
    def _category_matches_route(self) -> _DecisionData:
        if self.route == "moderation":
            if self.category not in MODERATION_CATEGORIES:
                raise ValueError("moderation decision requires a known category")
        elif self.category is not None:
            raise ValueError("category is only valid on moderation decisions")
        return self


class _ErrorData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["validation", "rate_limited", "timeout", "crew_failed"]
    message: str | None = None

    @field_validator("message", mode="before")
    @classmethod
    def _blank_message_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class _ToolCallData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(..., min_length=1)
    args: dict[str, Any]


class _ToolResultData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(..., min_length=1)
    matches: list[str]
    fallback: bool
    result: str
    truncated: bool = False
    original_length: int | None = Field(default=None, ge=1)


class _CrewKickoffData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=1)
    truncated: bool = False
    original_length: int | None = Field(default=None, ge=1)

    @field_validator("goal")
    @classmethod
    def _goal_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("goal is blank")
        return value


class _AssistantMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulated: bool
    moderation_category: str | None = None

    @field_validator("moderation_category")
    @classmethod
    def _known_category(cls, value: str | None) -> str | None:
        if value is not None and value not in MODERATION_CATEGORIES:
            raise ValueError("unknown moderation_category")
        return value


_DATA_MODELS: dict[str, type[BaseModel]] = {
    USER_MESSAGE: _UserData,
    ASSISTANT_RESPONSE: _AssistantData,
    DECISION: _DecisionData,
    ERROR: _ErrorData,
    TOOL_CALL: _ToolCallData,
    TOOL_RESULT: _ToolResultData,
    CREW_KICKOFF: _CrewKickoffData,
}


@dataclass(frozen=True)
class ValidatedEvent:
    event: str
    data: dict[str, Any]
    session_id: str
    parent_id: str | None
    metadata: dict[str, Any] | None


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def normalize_optional_id(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if not is_uuid(stripped):
        return None
    return stripped


def validate_outbound_event(
    event: str,
    data: dict[str, Any],
    *,
    session_id: str,
    parent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ValidatedEvent | None:
    """Return a normalized event, or None if it must not be written."""
    try:
        return _validate(event, data, session_id=session_id, parent_id=parent_id, metadata=metadata)
    except (ValidationError, ValueError) as exc:
        logger.warning(
            "zizkadb_event_rejected",
            extra={"event": event, "session_id": session_id, "reason": str(exc)},
        )
        return None


def _validate(
    event: str,
    data: dict[str, Any],
    *,
    session_id: str,
    parent_id: str | None,
    metadata: dict[str, Any] | None,
) -> ValidatedEvent:
    session = session_id.strip()
    if not session:
        raise ValueError("session_id is required")

    schema = _DATA_MODELS.get(event)
    if schema is None:
        raise ValueError(f"unknown event type: {event}")

    clean_data = schema.model_validate(data).model_dump(exclude_none=True)
    if clean_data.get("truncated") is False:
        clean_data.pop("truncated")
    clean_meta = _validate_metadata(event, metadata)
    clean_parent = normalize_optional_id(parent_id)
    provided_parent = (parent_id or "").strip()
    if provided_parent and clean_parent is None:
        logger.warning(
            "zizkadb_parent_id_dropped",
            extra={"event": event, "session_id": session},
        )

    return ValidatedEvent(
        event=event,
        data=clean_data,
        session_id=session,
        parent_id=clean_parent,
        metadata=clean_meta,
    )


def _validate_metadata(event: str, metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if event == ASSISTANT_RESPONSE:
        return _AssistantMetadata.model_validate(metadata or {}).model_dump(exclude_none=True)
    if not metadata:
        return None
    if event == DECISION:
        category = metadata.get("moderation_category")
        if category is None or category == "":
            return None
        if category not in MODERATION_CATEGORIES:
            raise ValueError("unknown moderation_category")
        return {"moderation_category": category}
    return None
