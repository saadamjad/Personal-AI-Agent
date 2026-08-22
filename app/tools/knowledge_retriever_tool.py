from typing import Any

from crewai.tools import tool

from app.knowledge.loader import KnowledgeDocument, load_all_documents
from app.observability.events import (
    PAYLOAD_LIMIT,
    TOOL_CALL,
    TOOL_RESULT,
    USER_TEXT_LIMIT,
    EventCursor,
    bound_text,
)
from app.observability.tracer import AgentTracer

_SEARCH_TOOL_DOC = """Searches the personal/professional knowledge base (profile, career
history, education, projects, skills) and returns the documents relevant
to the query. Always use this before answering a factual question about
the person this agent represents — never answer from memory alone.

Args:
    query: A short description of what the user is asking about,
        e.g. "education", "React Native experience", "contact info".
"""


def query_knowledge_base(query: str) -> tuple[str, list[str], bool]:
    """Return (rendered text, match names, used_all_docs_fallback)."""
    docs = load_all_documents()
    if not docs:
        return "No knowledge base documents are loaded.", [], False

    query_terms = [t for t in query.lower().split() if len(t) > 2]
    used_fallback = False
    if not query_terms:
        matches = docs
    else:
        matches = [d for d in docs if any(t in d.content.lower() for t in query_terms)]
        if not matches:
            # Fall back to everything rather than returning nothing — a missed
            # keyword match must never cause the agent to say "I don't know"
            # about something that's actually in the knowledge base.
            matches = docs
            used_fallback = True

    return _render(matches), [d.name for d in matches], used_fallback


def _render(docs: list[KnowledgeDocument]) -> str:
    return "\n\n".join(f"## {d.name}\n\n{d.content.strip()}" for d in docs)


def search_with_trace(
    query: str,
    tracer: AgentTracer,
    session_id: str,
    cursor: EventCursor,
) -> str:
    logged_query = bound_text(query, USER_TEXT_LIMIT)
    call_id = tracer.log(
        TOOL_CALL,
        {"tool": "search_knowledge_base", "args": {"query": logged_query.value}},
        session_id=session_id,
        parent_id=cursor.event_id,
    )
    cursor.advance(call_id)

    text, names, used_fallback = query_knowledge_base(query)
    logged_result = bound_text(text, PAYLOAD_LIMIT)
    result_id = tracer.log(
        TOOL_RESULT,
        {
            "tool": "search_knowledge_base",
            "matches": names,
            "fallback": used_fallback,
            **logged_result.as_data("result"),
        },
        session_id=session_id,
        parent_id=cursor.event_id,
    )
    cursor.advance(result_id)
    return text


def _plain_search(query: str) -> str:
    text, _names, _fallback = query_knowledge_base(query)
    return text


_plain_search.__doc__ = _SEARCH_TOOL_DOC
search_knowledge_base = tool("search_knowledge_base")(_plain_search)


def build_search_knowledge_base_tool(
    tracer: AgentTracer,
    session_id: str,
    cursor: EventCursor,
) -> Any:
    def _instrumented(query: str) -> str:
        return search_with_trace(query, tracer, session_id, cursor)

    _instrumented.__doc__ = _SEARCH_TOOL_DOC
    return tool("search_knowledge_base")(_instrumented)
