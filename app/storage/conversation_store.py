import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import Settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_seq
    ON chat_messages (session_id, seq);

CREATE TABLE IF NOT EXISTS llm_call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class StoredMessage:
    id: str
    session_id: str
    role: str
    content: str
    seq: int
    created_at: datetime


class ConversationStore:
    def __init__(self, settings: Settings) -> None:
        db_path = Path(settings.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def next_seq(self, conn: sqlite3.Connection, session_id: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM chat_messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row[0]) + 1

    def save_message(self, session_id: str, role: str, content: str) -> StoredMessage:
        with self._connect() as conn:
            seq = self.next_seq(conn, session_id)
            now = datetime.now(UTC)
            msg = StoredMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role=role,
                content=content,
                seq=seq,
                created_at=now,
            )
            conn.execute(
                "INSERT INTO chat_messages (id, session_id, role, content, seq, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (msg.id, msg.session_id, msg.role, msg.content, msg.seq, now.isoformat()),
            )
            return msg

    def get_recent_messages(self, session_id: str, limit: int = 12) -> list[StoredMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, session_id, role, content, seq, created_at FROM chat_messages "
                "WHERE session_id = ? ORDER BY seq DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        messages = [
            StoredMessage(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                seq=row[4],
                created_at=datetime.fromisoformat(row[5]),
            )
            for row in rows
        ]
        return list(reversed(messages))

    def record_llm_call(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO llm_call_log (called_at) VALUES (?)",
                (datetime.now(UTC).isoformat(),),
            )

    def count_llm_calls_since(self, seconds_ago: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM llm_call_log WHERE called_at >= ?", (cutoff,)
            ).fetchone()
        return int(row[0])
