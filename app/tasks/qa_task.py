from crewai import Agent, Task

# {owner_name} is filled in at build time (below); {{history}}/{{message}} stay
# escaped here so CrewAI's own runtime templating fills those in per-request
# from the Flow's kickoff(inputs=...) call.
TASK_DESCRIPTION_TEMPLATE = """\
Conversation history (most recent last, may be empty for a new session):
{{history}}

The visitor just said:
{{message}}

Respond to the visitor's message following your role, scope, and accuracy rules.
Use the search_knowledge_base tool to ground any factual claim about {owner_name}.
"""


def build_qa_task(agent: Agent, owner_name: str) -> Task:
    return Task(
        description=TASK_DESCRIPTION_TEMPLATE.format(owner_name=owner_name),
        expected_output=(
            "A warm, concise, accurate reply to the visitor — grounded in the knowledge "
            "base, staying within scope, 1-3 sentences unless a full summary or a list "
            "of items was requested. Plain text only: no markdown (no **bold**, no "
            "bullet/dash lists, no headers). For multi-item answers, one plain line "
            "per item, no per-item elaboration."
        ),
        agent=agent,
    )
