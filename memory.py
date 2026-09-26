import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).with_name("memory.db")


class Memory:
    def __init__(self, limit=30):
        self.limit = limit
        self.lock = threading.Lock()
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self.db.commit()

    def add(self, chat_id, username, text):
        with self.lock:
            self.db.execute(
                "INSERT INTO messages(chat_id, username, text) VALUES (?, ?, ?)",
                (chat_id, username[:100], text[:4000]),
            )
            self.db.execute(
                """DELETE FROM messages
                   WHERE chat_id = ?
                   AND id NOT IN (
                       SELECT id FROM messages WHERE chat_id = ?
                       ORDER BY id DESC LIMIT ?
                   )""",
                (chat_id, chat_id, self.limit),
            )
            self.db.commit()

    def context(self, chat_id):
        with self.lock:
            rows = self.db.execute(
                """SELECT username, text FROM messages
                   WHERE chat_id = ? ORDER BY id DESC LIMIT ?""",
                (chat_id, self.limit),
            ).fetchall()
        rows.reverse()
        return "\n".join(f"{u}: {t}" for u, t in rows)
