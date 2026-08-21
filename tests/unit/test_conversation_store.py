from app.core.config import Settings
from app.storage.conversation_store import ConversationStore


def _settings(db_path: str) -> Settings:
    return Settings(database_path=db_path, openai_api_key="sk-test")


def test_save_and_get_recent_messages(tmp_path) -> None:
    store = ConversationStore(_settings(str(tmp_path / "test.db")))
    store.save_message("session-1", "user", "hello")
    store.save_message("session-1", "assistant", "hi there")

    messages = store.get_recent_messages("session-1", limit=10)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert [m.seq for m in messages] == [1, 2]


def test_messages_are_scoped_by_session(tmp_path) -> None:
    store = ConversationStore(_settings(str(tmp_path / "test.db")))
    store.save_message("session-a", "user", "a message")
    store.save_message("session-b", "user", "b message")

    a_messages = store.get_recent_messages("session-a")
    assert len(a_messages) == 1
    assert a_messages[0].content == "a message"


def test_llm_call_budget_counter(tmp_path) -> None:
    store = ConversationStore(_settings(str(tmp_path / "test.db")))
    store.record_llm_call()
    store.record_llm_call()
    assert store.count_llm_calls_since(seconds_ago=3600) == 2
