# Security Model

This is a public-facing service — anyone visiting the portfolio site can talk to it.
Treat it as production, not a toy.

## Prompt injection

`app/services/moderation.py` runs a regex classifier *before* any agent/LLM call,
short-circuiting jailbreak attempts ("ignore previous instructions", "reveal your
system prompt", "developer mode", etc.) with a canned reply — zero LLM cost, zero
latency, deterministic. This is defense-in-depth #1.

Defense-in-depth #2: the agent's system prompt (`app/prompts/system_prompt.py`) has
an explicit, hard scope boundary instructing it to decline off-topic or
instruction-override requests regardless of phrasing.

Neither is airtight against a sufficiently creative semantic attack — that's an
accepted, documented tradeoff at this scale, not an oversight.

## Rate limiting

- 20 requests / session / 10 minutes
- 40 requests / IP / 10 minutes
- In-memory sliding window (`app/services/rate_limiter.py`). This is fine at
  single-instance Railway scale; a multi-instance deployment would need a shared
  backend (Redis) since each instance currently tracks its own counters.
- A separate daily LLM call budget (`DailyCallBudget`, default 300/day) is a cost
  backstop independent of per-key rate limiting.

## Request limits

- Max body size: 8KB (`BodySizeLimitMiddleware`, checked before JSON parsing)
- Max message length: 2000 characters (enforced both in the Pydantic schema and in
  `ChatService.handle_turn`)
- Flow execution timeout: not yet wall-clock enforced at the asyncio level — CrewAI's
  own `max_iter` cap (6) on the agent bounds tool-calling loops. A hard request timeout
  is a near-term hardening item — track it before increasing traffic expectations.

## Secrets

- All config comes from `pydantic-settings` reading environment variables
  (`app/core/config.py`). `.env` is gitignored; only `.env.example` (placeholders) is
  committed.
- Railway environment variables hold real secrets in production. No staging tier
  exists for this project — verify locally before deploying.
- `app/core/logging.py`'s `_RedactingFormatter` strips known secret-shaped keys
  (`api_key`, `authorization`, `password`, etc.) from structured log output.
- LLM API keys are never sent to the browser — the frontend only ever talks to this
  service's `/api/v1/chat` endpoint, never to OpenAI/Anthropic directly.

## Error handling

`app/core/errors.py` registers a global exception handler: every unhandled exception
is logged in full (with request ID) server-side, and the client only ever sees
`{"error": {"code": ..., "message": ..., "request_id": ...}}` — no stack traces, no
internal paths, no library error messages.

## CORS

Locked to explicit origins via `CORS_ALLOWED_ORIGINS` (comma-separated) — no wildcard.
Set this to the production portfolio domain in Railway; keep `localhost` origins out
of the production env var.

## Known gaps / near-term hardening

- No hard wall-clock timeout wrapping `ChatFlow.kickoff` yet (relies on CrewAI's
  `max_iter` + provider-side timeouts).
- No WAF/bot-detection layer in front of the service (relies on rate limiting alone).
- No authenticated admin surface exists (`CHAT_ADMIN_SECRET` and the old "teach" flow
  were deliberately dropped, not ported — see git history of the old repo).
