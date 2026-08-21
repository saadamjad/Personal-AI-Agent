import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("CHAT_LLM_PROVIDER", "openai")


@pytest.fixture
def tmp_db_path(tmp_path, monkeypatch) -> Iterator[str]:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()
