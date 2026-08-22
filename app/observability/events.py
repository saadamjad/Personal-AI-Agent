from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EventName(StrEnum):
    USER_MESSAGE = "user_message"
    ASSISTANT_RESPONSE = "assistant_response"
    DECISION = "decision"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CREW_KICKOFF = "crew_kickoff"


# Stable aliases so call sites can `from app.observability.events import USER_MESSAGE`.
USER_MESSAGE = EventName.USER_MESSAGE
ASSISTANT_RESPONSE = EventName.ASSISTANT_RESPONSE
DECISION = EventName.DECISION
ERROR = EventName.ERROR
TOOL_CALL = EventName.TOOL_CALL
TOOL_RESULT = EventName.TOOL_RESULT
CREW_KICKOFF = EventName.CREW_KICKOFF

USER_TEXT_LIMIT = 2_000
PAYLOAD_LIMIT = 8_000
TOOL_OUTPUT_LIMIT = 2_000


@dataclass
class EventCursor:
    """Mutable last-event pointer so mid-turn steps can chain parent_id."""

    event_id: str | None = None

    def advance(self, event_id: str | None) -> None:
        if event_id:
            self.event_id = event_id


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


@dataclass(frozen=True)
class BoundText:
    value: str
    truncated: bool
    original_length: int

    def as_data(self, key: str = "text") -> dict[str, Any]:
        payload: dict[str, Any] = {key: self.value}
        if self.truncated:
            payload["truncated"] = True
            payload["original_length"] = self.original_length
        return payload


def bound_text(text: str, limit: int) -> BoundText:
    original = len(text)
    if original <= limit:
        return BoundText(text, False, original)
    return BoundText(text[:limit], True, original)
