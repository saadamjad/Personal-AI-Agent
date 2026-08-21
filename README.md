# portfolio-agent

[![CI](https://github.com/saadamjad/Personal-AI-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/saadamjad/Personal-AI-Agent/actions/workflows/ci.yml)

A personal AI representative for [saadstack.com](https://saadstack.com) — answers
questions from recruiters, hiring managers, and clients about Saad's professional
background, using a CrewAI agent grounded in a plain-text knowledge base.

Independent from the portfolio website's codebase: FastAPI + CrewAI, deployed on
Railway, talked to over HTTPS by the site's existing chat widget.

## Quick start (local dev)

```bash
cp .env.example .env        # fill in OPENAI_API_KEY or ANTHROPIC_API_KEY
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Then:

```bash
curl http://localhost:8000/healthz
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "'$(python3 -c 'import uuid;print(uuid.uuid4())')'", "message": "What is Saad'\''s experience?"}'
```

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — how the pieces fit together
- [SECURITY.md](SECURITY.md) — the security model
- [DEPLOYMENT.md](DEPLOYMENT.md) — Railway deployment
- [ENVIRONMENT.md](ENVIRONMENT.md) — every env var, what it does
- [CONTRIBUTING.md](CONTRIBUTING.md) — updating knowledge, adding tools/agents, running tests

## Testing

```bash
ruff check .
mypy app
pytest
```
