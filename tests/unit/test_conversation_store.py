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


def test_llm_call_budget_blocks_after_max(tmp_path) -> None:
    store = ConversationStore(_settings(str(tmp_path / "test.db")))
    assert store.check_and_record_llm_call(max_calls_per_day=2) is True
    assert store.check_and_record_llm_call(max_calls_per_day=2) is True
    assert store.check_and_record_llm_call(max_calls_per_day=2) is False


def test_llm_call_budget_persists_across_store_instances(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    store_a = ConversationStore(_settings(db_path))
    store_a.check_and_record_llm_call(max_calls_per_day=1)

    # A fresh ConversationStore instance (simulating a process restart) must
    # still see the recorded call — this is the whole point of persisting the
    # budget in SQLite instead of an in-memory counter.
    store_b = ConversationStore(_settings(db_path))
    assert store_b.check_and_record_llm_call(max_calls_per_day=1) is False


def test_concurrent_saves_do_not_produce_duplicate_seq(tmp_path) -> None:
    import threading

    store = ConversationStore(_settings(str(tmp_path / "test.db")))
    threads = [
        threading.Thread(target=store.save_message, args=("session-1", "user", f"msg {i}"))
        for i in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    messages = store.get_recent_messages("session-1", limit=100)
    seqs = [m.seq for m in messages]
    assert len(seqs) == len(set(seqs)), "duplicate seq values from a write race"
    assert sorted(seqs) == list(range(1, 21))
