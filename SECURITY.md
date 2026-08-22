# Security Model

This is a public-facing service — anyone visiting the owner's site can talk to it.
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
- A separate daily LLM call budget (`ConversationStore.check_and_record_llm_call`,
  default 300/day) is a cost backstop independent of per-key rate limiting —
  persisted in SQLite so it survives redeploys, not just an in-memory counter.
- Client IP for per-IP limiting comes from `X-Forwarded-For`'s *last* hop (the value
  Railway's edge proxy appends), not the first — the first entry is client-controlled
  and trivially spoofable.

## Request limits

- Max body size: 8KB (`BodySizeLimitMiddleware`, checked before JSON parsing)
- Max message length: 2000 characters (enforced both in the Pydantic schema and in
  `ChatService.handle_turn`)
- Flow execution timeout: `CHAT_FLOW_TIMEOUT_SECONDS` (default 25) is enforced via a
  bounded `ThreadPoolExecutor` future in `ChatService._run_flow_with_timeout` — a slow
  or hung LLM call returns a fallback reply to the caller within that bound, on top of
  CrewAI's own `max_iter` cap (6) bounding tool-calling loops. Note this bounds the
  *response*, not the underlying thread — a timed-out call keeps running in the
  background until it naturally completes/errors; there's no true cancellation.

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
`{"error": "<message>"}` — no stack traces, no internal paths, no library error
messages. The request ID isn't in the body (kept minimal to match the frontend's
error-parsing contract) but travels in the `X-Request-ID` response header, and the
error `code` is always in the server-side log line for cross-referencing.

## CORS

Locked to explicit origins via `CORS_ALLOWED_ORIGINS` (comma-separated) — no wildcard.
Set this to the production website domain in Railway; keep `localhost` origins out
of the production env var.

**CORS is not authentication.** It only stops a *browser* from letting JavaScript on
another origin read the response — it does nothing to stop a direct `curl`/script call,
which never goes through browser-enforced CORS at all. Anyone who learns this service's
URL can call `/api/v1/chat` directly, bypassing the website entirely. This is an accepted
tradeoff, not an oversight: there's no per-caller API key because a browser-held secret
is extractable from the frontend anyway (see "Website → Agent API" below), so it wouldn't
add real protection. What actually bounds abuse from a direct caller is the per-session/
per-IP rate limiter and the daily LLM-call budget above — both apply regardless of
whether the request came through the website or a raw HTTP client.

### Website → Agent API

The website sends no credential to this service — it relies entirely on the protections
above (rate limiting, daily budget, moderation) rather than an API key, because any key
embedded in frontend JavaScript could be extracted and reused by anyone anyway. If you
need to guarantee requests only originate from your own website, put a reverse proxy or
edge function in front of this service that injects a server-held secret — don't put that
secret in browser code.

## Response headers

`SecurityHeadersMiddleware` (`app/core/middleware.py`) adds `X-Content-Type-Options:
nosniff` and `Referrer-Policy: no-referrer-when-downgrade` to every response. This is a
pure JSON API with no HTML responses, so the actual risk these mitigate is low — added
as free, standard-practice defense-in-depth rather than in response to a specific
threat.

## CrewAI telemetry

CrewAI phones home to `telemetry.crewai.com` at import/execution time by default.
Disabled two ways for defense-in-depth: `CREWAI_DISABLE_TELEMETRY=true` and
`OTEL_SDK_DISABLED=true` are set programmatically at the top of `app/main.py`
(before crewai is ever imported) and also in the Dockerfile/`.env.example`. This
avoids an unnecessary external dependency on every request and avoids sending
conversation-adjacent data to a third party without explicit opt-in.

## Known gaps / near-term hardening

- Per-session rate limiting is bypassable: `session_id` is a client-supplied UUID with
  no server-side issuance, so a client can mint a fresh one per request for a fresh
  20-message budget. This is an accepted tradeoff, not an oversight — real damage is
  still bounded by the per-IP limiter and, more importantly, the global daily LLM-call
  budget (300/day), which applies regardless of how many session IDs are cycled. A real
  fix would need session issuance/auth, which is disproportionate to this service's
  threat model at personal-assistant scale.
- No WAF/bot-detection layer in front of the service (relies on rate limiting alone).
- No authenticated admin surface exists (`CHAT_ADMIN_SECRET` and the old "teach" flow
  were deliberately dropped, not ported — see git history of the old repo).
- A timed-out flow execution (see Request limits above) can't be truly cancelled —
  the background thread keeps running until the LLM call itself resolves.
