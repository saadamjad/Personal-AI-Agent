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
- **`knowledge/` is plain markdown/YAML, not Python.** Updating the bio, adding a
  new project, or correcting a job title is a content edit + redeploy, never a code
  change.
- **No vector database.** The knowledge base is small (a handful of short files), so
  `knowledge/loader.py` loads everything into memory and the retriever tool does simple
  keyword filtering with a safe fallback to "return everything" rather than risking a
  missed embedding match causing a false "I don't know."

## Request lifecycle

Middleware wraps outside-in as: CORS → SecurityHeaders → RequestId → BodySizeLimit →
routes. Added in the reverse order in `main.py` (`BodySizeLimit`, `RequestId`,
`SecurityHeaders`, then `CORS` last) since Starlette makes the last-added middleware
outermost — CORS has to wrap everything, including BodySizeLimit's early rejections,
or the browser discards those error responses as cross-origin failures instead of
showing the 413.

1. `CORSMiddleware` adds CORS headers to whatever comes back, whichever layer produced it.
2. `SecurityHeadersMiddleware` (`core/middleware.py`) adds baseline headers
   (`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer-when-downgrade`)
   to every response — low-stakes for a pure JSON API, but free defense-in-depth.
3. `RequestIdMiddleware` stamps every request with a UUID (returned as `X-Request-ID`,
   used to correlate logs).
4. `BodySizeLimitMiddleware` rejects oversized bodies before they're parsed.
5. `ChatService.check_rate_limits` enforces per-session and per-IP sliding-window limits.
6. `ChatService.handle_turn` (route handlers are plain `def`, not `async def`, so
   FastAPI runs them in its threadpool — the blocking CrewAI call doesn't stall the
   event loop for other requests, including health checks):
   - validates message length
   - runs `services/moderation.py` — jailbreak/abuse/greeting/thanks/gibberish are
     short-circuited with a canned reply *before* any LLM call
   - checks the daily LLM call budget (`storage/conversation_store.py`'s
     `check_and_record_llm_call`, persisted in SQLite so it survives redeploys)
   - calls `ChatFlow` if configured and under budget, bounded by
     `CHAT_FLOW_TIMEOUT_SECONDS` via a `ThreadPoolExecutor` future — otherwise returns
     a fallback reply
   - persists both turns to `storage/conversation_store.py` (SQLite)
7. Any unhandled exception is caught by `core/errors.py`'s global handler and turned
   into a generic `{"error": "<message>"}` body — no stack traces ever reach the client.

## API wire format

Request/response JSON is camelCase (`sessionId`, `messageId`, …) to match the
website's existing `chatApi.js`/`useChatMessages.js` — the schemas in
`app/schemas/chat.py` use `alias_generator=to_camel` so Python stays snake_case
internally while the wire format doesn't change the frontend at all.

## Storage

SQLite via a single file (`DATABASE_PATH`, mounted on a Railway volume in production).
Chosen over Postgres/Redis because this is single-instance, low-QPS, personal-scale
traffic — SQLite gives durability across redeploys with zero extra infrastructure.
`ConversationStore`'s interface (`save_message`, `get_recent_messages`,
`check_and_record_llm_call`) can be swapped to a different backend later without
touching callers. A per-instance write lock keeps sequence-numbering and budget
check-then-record atomic across concurrent request-handling threads.

## Deliberately out of scope for v1

- Multi-agent crew (router / knowledge / lead-qualification agents) — `chat_flow.py`
  is structured so this is additive later.
- Meeting scheduling (Google Meet/Zoom).
- ZizkaDB analytics/event logging.

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to extend the agent/knowledge base.
