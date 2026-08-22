from app.tasks.qa_task import TASK_DESCRIPTION_TEMPLATE


def test_task_description_uses_the_given_owner_name() -> None:
    description = TASK_DESCRIPTION_TEMPLATE.format(owner_name="Alex")
    assert "Alex" in description
    assert "Saad" not in description


def test_task_description_still_has_runtime_placeholders_for_crewai() -> None:
    """{history} and {message} must survive owner_name templating unescaped,
    since CrewAI fills those in per-request via kickoff(inputs=...)."""
    description = TASK_DESCRIPTION_TEMPLATE.format(owner_name="Saad")
    assert "{history}" in description
    assert "{message}" in description
