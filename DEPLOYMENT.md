# Deployment (Railway)

## First-time setup

1. Create a new Railway project, connect it to this repo's GitHub remote.
2. Railway auto-detects the `Dockerfile` (confirmed via `railway.json`'s
   `"builder": "DOCKERFILE"`).
3. Add a **volume** mounted at `/app/data` — this is where the SQLite database
   (`DATABASE_PATH=./data/conversations.db`) lives. Without a volume, conversation
   history is lost on every redeploy.
4. Set environment variables (Railway dashboard → Variables) — see
   [ENVIRONMENT.md](ENVIRONMENT.md) for the full list. At minimum:
   - `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
   - `CORS_ALLOWED_ORIGINS` — the production portfolio domain, e.g.
     `https://saadstack.com`
   - `ENVIRONMENT=production`
5. Railway injects `$PORT` automatically — the Dockerfile's `CMD` already respects it
   (`uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`). Don't hardcode a port.
6. Health check: Railway pings `/healthz` per `railway.json`'s `healthcheckPath`.

## Deploying

Push to `master` — Railway rebuilds and redeploys automatically. There's no staging
environment for this project (confirmed decision — solo project, test locally first).

## Verifying a deploy

```bash
curl https://<your-railway-url>/healthz
curl https://<your-railway-url>/readyz     # confirms knowledge loaded + LLM key present
curl -X POST https://<your-railway-url>/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "'$(python3 -c 'import uuid;print(uuid.uuid4())')'", "message": "What is Saad'\''s experience?"}'
```

## Connecting the website

In `apps/web` (the portfolio site repo), set:

```
VITE_CHAT_API_BASE=https://<your-railway-url>/api/v1/chat
```

No other frontend changes are needed — `apps/web/src/features/chat/*` is pure UI and
already speaks this API shape.
