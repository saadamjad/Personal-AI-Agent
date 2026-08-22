from dataclasses import dataclass
from typing import cast

from crewai import Crew, Process
from crewai.crews.crew_output import CrewOutput
from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel

from app.agents.qa_agent import build_qa_agent
from app.core.config import Settings
from app.observability.events import CREW_KICKOFF, USER_TEXT_LIMIT, EventCursor, bound_text
from app.observability.tracer import AgentTracer, ensure_safe_tracer
from app.tasks.qa_task import build_qa_task
from app.tools.knowledge_retriever_tool import build_search_knowledge_base_tool


@dataclass(frozen=True)
class ChatFlowResult:
    reply: str
    last_event_id: str | None = None


class ChatFlowState(BaseModel):
    session_id: str = ""
    message: str = ""
    history_text: str = ""
    reply: str = ""


class ChatFlow(Flow[ChatFlowState]):
    """Single orchestration entry point for a chat turn.

    Currently wraps one agent/one task. Adding a router, a knowledge
    specialist, or a lead-qualification agent later is a change confined to
    this file — the service layer and the API contract don't change.
    """

    def __init__(
        self,
        settings: Settings,
        tracer: AgentTracer,
        parent_id: str | None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._tracer = tracer
        self._parent_id = parent_id
        self.last_event_id: str | None = parent_id

    @start()
    def answer(self) -> str:
        kickoff_id = self._tracer.log(
            CREW_KICKOFF,
            bound_text(self.state.message, USER_TEXT_LIMIT).as_data("goal"),
            session_id=self.state.session_id,
            parent_id=self._parent_id,
        )
        cursor = EventCursor(kickoff_id or self._parent_id)
        tool = build_search_knowledge_base_tool(self._tracer, self.state.session_id, cursor)
        agent = build_qa_agent(self._settings, tools=[tool])
        task = build_qa_task(agent, self._settings.agent_owner_name)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = cast(
            CrewOutput,
            crew.kickoff(
                inputs={"message": self.state.message, "history": self.state.history_text}
            ),
        )
        followup_id = self._tracer.log_crew_followup(
            session_id=self.state.session_id,
            parent_id=cursor.event_id,
            task_outputs=_task_outputs(result),
            final_output=str(result.raw),
        )
        self.last_event_id = followup_id or cursor.event_id
        self.state.reply = str(result.raw)
        return cast(str, self.state.reply)

    @listen(answer)
    def finalize(self, reply: str) -> str:
        return reply


def _task_outputs(result: CrewOutput) -> list[tuple[str, str]]:
    outputs: list[tuple[str, str]] = []
    for item in getattr(result, "tasks_output", None) or []:
        description = str(getattr(item, "description", "") or "")
        raw = str(getattr(item, "raw", "") or "")
        outputs.append((description, raw))
    return outputs


def run_chat_flow(
    settings: Settings,
    session_id: str,
    message: str,
    history_text: str,
    tracer: AgentTracer | None = None,
    parent_id: str | None = None,
) -> ChatFlowResult:
    flow = ChatFlow(settings, ensure_safe_tracer(tracer), parent_id)
    flow.state.session_id = session_id
    flow.state.message = message
    flow.state.history_text = history_text
    reply = cast(str, flow.kickoff())
    return ChatFlowResult(reply=reply, last_event_id=flow.last_event_id)
