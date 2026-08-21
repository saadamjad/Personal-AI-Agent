# Contributing / Extending

## Updating Saad's knowledge (the common case)

Edit the relevant file in `app/knowledge/` — `profile.md`, `career_timeline.yaml`,
`education.md`, `projects.md`, `skills.md`, `hobbies_and_misc.md` — and redeploy. No
code changes needed. `app/knowledge/loader.py` loads every `.md`/`.yaml` file in that
directory automatically, so a new file is picked up without touching the loader.

## Adding a new tool

1. Create `app/tools/your_tool.py`, decorate a function with `@tool("name")` from
   `crewai.tools` (see `app/tools/knowledge_retriever_tool.py` for the pattern).
2. Register it on the relevant agent's `tools=[...]` list in `app/agents/`.

## Adding a new agent / expanding the crew

The single-agent setup today (`app/agents/qa_agent.py` + `app/tasks/qa_task.py`,
wired together in `app/flows/chat_flow.py`) is deliberately structured so a multi-agent
crew is additive:

1. Add a new agent module in `app/agents/` (e.g. `lead_agent.py`) and a matching task
   in `app/tasks/`.
2. In `app/flows/chat_flow.py`, add the new agent/task to the `Crew(agents=[...],
   tasks=[...])` list, or introduce routing logic if agents should handle different
   message types.
3. The API contract (`app/schemas/chat.py`, `app/api/v1/routes_chat.py`) and the
   service layer (`app/services/chat_service.py`) don't need to change — `ChatFlow` is
   the only orchestration entry point they call into.

## Running tests

```bash
pytest              # all tests
pytest tests/unit   # fast, no I/O
ruff check .
mypy app
```

## What's deliberately not built yet

- Multi-agent crew (router / lead-qualification agents)
- Meeting scheduling (Google Meet/Zoom)
- ZizkaDB analytics integration

These are documented as explicit future phases in the project's original planning —
don't build them speculatively without checking current priorities first.
