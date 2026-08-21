# Environment Variables

All settings are defined in `app/core/config.py` (`pydantic-settings`, fails fast on
invalid combinations at startup). Copy `.env.example` to `.env` for local dev.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` or `production` |
| `PORT` | `8000` | Railway overrides this automatically — don't hardcode |
| `OPENAI_API_KEY` | *(empty)* | Set this or `ANTHROPIC_API_KEY` |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `ANTHROPIC_API_KEY` | *(empty)* | Alternative to OpenAI |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | |
| `CHAT_LLM_PROVIDER` | *(auto-detect)* | Force `openai` or `anthropic`; must have the matching key set or startup fails |
| `CHAT_MAX_LLM_CALLS_PER_DAY` | `300` | Daily ceiling on real LLM calls, independent of rate limiting |
| `CHAT_MAX_MESSAGE_LENGTH` | `2000` | Characters |
| `CHAT_MAX_BODY_BYTES` | `8192` | Enforced by `BodySizeLimitMiddleware` before JSON parsing |
| `CHAT_FLOW_TIMEOUT_SECONDS` | `25` | Target for the flow execution timeout (see SECURITY.md known gaps) |
| `RATE_LIMIT_PER_SESSION_PER_10MIN` | `20` | |
| `RATE_LIMIT_PER_IP_PER_10MIN` | `40` | |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated. **Set to the production domain in Railway — no wildcard.** |
| `DATABASE_PATH` | `./data/conversations.db` | Point at a Railway volume mount in production |

## Never set these to real values in `.env.example`

`.env.example` only ever contains empty placeholders for secrets. Real values live in
your local `.env` (gitignored) or Railway's environment variable store — never in git.
