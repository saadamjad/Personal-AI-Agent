# Architecture

```
Vite/React SPA (saadstack.com)
        |  HTTPS POST /api/v1/chat
        v
FastAPI (app/api/v1/routes_chat.py)      -- thin transport layer only
        |
        v
ChatService (app/services/chat_service.py)   -- validate, moderate, budget-check, persist
        |
        v
ChatFlow (app/flows/chat_flow.py)        -- the ONLY orchestration entry point
        |
        v
Crew: [QAAgent + QATask] (app/agents, app/tasks)
        |
        v
search_knowledge_base tool (app/tools/knowledge_retriever_tool.py)
        |
        v
Knowledge files (app/knowledge/*.md, *.yaml)
```

## Why this shape

- **`api/` is a thin transport layer.** Route handlers validate the request shape,
  apply rate limiting, and call `ChatService`. No business logic lives here.
- **`services/` is the only caller of `flows/`.** Routes never touch CrewAI directly —
  this keeps the API contract stable no matter how the agent internals change.
- **`flows/` is the single orchestration entry point**, even though today it wraps
  exactly one agent and one task. Adding a router agent, a knowledge specialist, or a
  lead-qualification agent later means editing `chat_flow.py` — the service layer and
  the API contract don't change.
- **`knowledge/` is plain markdown/YAML, not Python.** Updating Saad's bio, adding a
  new project, or correcting a job title is a content edit + redeploy, never a code
  change.
- **No vector database.** The knowledge base is small (a handful of short files), so
  `knowledge/loader.py` loads everything into memory and the retriever tool does simple
  keyword filtering with a safe fallback to "return everything" rather than risking a
  missed embedding match causing a false "I don't know."

## Request lifecycle

1. `RequestIdMiddleware` stamps every request with a UUID (returned as `X-Request-ID`,
   used to correlate logs).
2. `BodySizeLimitMiddleware` rejects oversized bodies before they're parsed.
3. `ChatService.check_rate_limits` enforces per-session and per-IP sliding-window limits.
4. `ChatService.handle_turn`:
   - validates message length
   - runs `services/moderation.py` — jailbreak/abuse/greeting/thanks/gibberish are
     short-circuited with a canned reply *before* any LLM call
   - checks the daily LLM call budget (`services/rate_limiter.py`'s `DailyCallBudget`)
   - calls `ChatFlow` if configured and under budget, otherwise returns a fallback reply
   - persists both turns to `storage/conversation_store.py` (SQLite)
5. Any unhandled exception is caught by `core/errors.py`'s global handler and turned
   into a generic error body — no stack traces ever reach the client.

## Storage

SQLite via a single file (`DATABASE_PATH`, mounted on a Railway volume in production).
Chosen over Postgres/Redis because this is single-instance, low-QPS, personal-scale
traffic — SQLite gives durability across redeploys with zero extra infrastructure.
`ConversationStore`'s interface (`save_message`, `get_recent_messages`,
`count_llm_calls_since`) can be swapped to a different backend later without touching
callers.

## Deliberately out of scope for v1

- Multi-agent crew (router / knowledge / lead-qualification agents) — `chat_flow.py`
  is structured so this is additive later.
- Meeting scheduling (Google Meet/Zoom).
- ZizkaDB analytics/event logging.

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to extend the agent/knowledge base.
