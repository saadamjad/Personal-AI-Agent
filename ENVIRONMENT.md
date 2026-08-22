# Environment Variables

All settings are defined in `app/core/config.py` (`pydantic-settings`, fails fast on
invalid combinations at startup). Copy `.env.example` to `.env` for local dev.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` or `production` |
| `PORT` | `8000` | Railway overrides this automatically — don't hardcode |
| `AGENT_OWNER_NAME` | `Saad` | Who the agent represents — used in the system prompt and the fallback reply. Change this (and `app/knowledge/*`) to make this your own agent |
| `AGENT_CONTACT_EMAIL` | *(empty)* | Shown in the fallback reply when the LLM is unreachable/unconfigured. Omit to leave that sentence out entirely |
| `CREWAI_DISABLE_TELEMETRY` | `true` | Stops CrewAI's import-time network call to telemetry.crewai.com |
| `OTEL_SDK_DISABLED` | `true` | Same purpose, belt-and-suspenders with the above |
| `OPENAI_API_KEY` | *(empty)* | Set this or `ANTHROPIC_API_KEY` |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `ANTHROPIC_API_KEY` | *(empty)* | Alternative to OpenAI |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | |
| `CHAT_LLM_PROVIDER` | *(auto-detect)* | Force `openai` or `anthropic`; must have the matching key set or startup fails |
| `CHAT_MAX_LLM_CALLS_PER_DAY` | `300` | Daily ceiling on real LLM calls, independent of rate limiting |
| `CHAT_MAX_MESSAGE_LENGTH` | `2000` | Characters |
| `CHAT_MAX_BODY_BYTES` | `8192` | Enforced by `BodySizeLimitMiddleware` before JSON parsing |
| `CHAT_FLOW_TIMEOUT_SECONDS` | `25` | Enforced flow execution timeout — see SECURITY.md |
| `RATE_LIMIT_PER_SESSION_PER_10MIN` | `20` | |
| `RATE_LIMIT_PER_IP_PER_10MIN` | `40` | |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated. **Set to the production domain in Railway — no wildcard.** |
| `DATABASE_PATH` | `./data/conversations.db` | Point at a Railway volume mount in production |
| `ZIZKADB_ENABLED` | `false` | Set `true` to send turn events to ZizkaDB. Requires `ZIZKADB_HOST` or `ZIZKADB_API_KEY` |
| `ZIZKADB_HOST` | *(empty)* | Self-hosted ZizkaDB API URL. This agent is `:8000` — use another port locally (or cloud) |
| `ZIZKADB_API_KEY` | *(empty)* | Cloud / remote key (`zizkadb_live_...`). Localhost can omit (SDK uses the dev key) |
| `ZIZKADB_AGENT` | `personal-assistant` | Must match the agent name in the ZizkaDB dashboard |
| `ZIZKADB_TIMEOUT_SECONDS` | `3` | Per-request timeout for ZizkaDB ingest. Keep well below `CHAT_FLOW_TIMEOUT_SECONDS` |

## Never set these to real values in `.env.example`

`.env.example` only ever contains empty placeholders for secrets. Real values live in
your local `.env` (gitignored) or Railway's environment variable store — never in git.
