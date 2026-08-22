from typing import Any

from crewai import LLM, Agent

from app.core.config import Settings
from app.prompts.system_prompt import build_qa_agent_backstory, build_qa_agent_goal
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


def build_qa_agent(settings: Settings, tools: list[Any] | None = None) -> Agent:
    return Agent(
        role=f"{settings.agent_owner_name}'s Personal Assistant",
        goal=build_qa_agent_goal(settings.agent_owner_name),
        backstory=build_qa_agent_backstory(settings.agent_owner_name),
        tools=tools if tools is not None else [search_knowledge_base],
        llm=build_llm(settings),
        verbose=False,
        max_iter=6,
    )
