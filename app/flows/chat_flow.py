from typing import cast

from crewai import Crew, Process
from crewai.crews.crew_output import CrewOutput
from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel

from app.agents.qa_agent import build_qa_agent
from app.core.config import Settings
from app.tasks.qa_task import build_qa_task


class ChatFlowState(BaseModel):
    session_id: str = ""
    message: str = ""
    history_text: str = ""
    reply: str = ""


class ChatFlow(Flow[ChatFlowState]):
    """Single orchestration entry point for a chat turn.

    Currently wraps one agent/one task. Adding a router, a knowledge
    specialist, or a lead-qualification agent later is a change confined to
    this file — the service layer and API contract don't change.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    @start()
    def answer(self) -> str:
        agent = build_qa_agent(self._settings)
        task = build_qa_task(agent, self._settings.agent_owner_name)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = cast(
            CrewOutput,
            crew.kickoff(
                inputs={"message": self.state.message, "history": self.state.history_text}
            ),
        )
        self.state.reply = str(result.raw)
        return cast(str, self.state.reply)

    @listen(answer)
    def finalize(self, reply: str) -> str:
        return reply


def run_chat_flow(settings: Settings, session_id: str, message: str, history_text: str) -> str:
    flow = ChatFlow(settings)
    flow.state.session_id = session_id
    flow.state.message = message
    flow.state.history_text = history_text
    return cast(str, flow.kickoff())
