from crewai import Agent, Task

TASK_DESCRIPTION = """\
Conversation history (most recent last, may be empty for a new session):
{history}

The visitor just said:
{message}

Respond to the visitor's message following your role, scope, and accuracy rules.
Use the search_knowledge_base tool to ground any factual claim about Saad.
"""


def build_qa_task(agent: Agent) -> Task:
    return Task(
        description=TASK_DESCRIPTION,
        expected_output=(
            "A warm, concise, accurate reply to the visitor — grounded in the knowledge "
            "base, staying within scope, 1-3 sentences unless a full summary was requested."
        ),
        agent=agent,
    )
