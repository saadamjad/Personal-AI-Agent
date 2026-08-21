from crewai import LLM, Agent

from app.core.config import Settings
from app.prompts.system_prompt import QA_AGENT_BACKSTORY, QA_AGENT_GOAL
from app.tools.knowledge_retriever_tool import search_knowledge_base


def build_llm(settings: Settings) -> LLM:
    provider = settings.resolved_provider
    if provider == "openai":
        return LLM(model=f"openai/{settings.openai_model}", api_key=settings.openai_api_key)
    if provider == "anthropic":
        return LLM(
            model=f"anthropic/{settings.anthropic_model}", api_key=settings.anthropic_api_key
        )
    raise ValueError("No LLM provider configured — set OPENAI_API_KEY or ANTHROPIC_API_KEY")


def build_qa_agent(settings: Settings) -> Agent:
    return Agent(
        role="Saad's Personal Representative",
        goal=QA_AGENT_GOAL,
        backstory=QA_AGENT_BACKSTORY,
        tools=[search_knowledge_base],
        llm=build_llm(settings),
        verbose=False,
        max_iter=6,
    )
