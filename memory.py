import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).with_name("memory.db")


class Memory:
    def __init__(self, limit=120):
        self.limit = limit
        self.lock = threading.Lock()
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                fact TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, username, fact)
            )
        """)
        self.db.commit()

    def add(self, chat_id, username, text):
        with self.lock:
            self.db.execute(
                "INSERT INTO messages(chat_id, username, text) VALUES (?, ?, ?)",
                (chat_id, username[:100], text[:4000]),
            )
            self.db.execute(
                """DELETE FROM messages
                   WHERE chat_id = ? AND id NOT IN (
                       SELECT id FROM messages
                       WHERE chat_id = ?
                       ORDER BY id DESC LIMIT ?
                   )""",
                (chat_id, chat_id, self.limit),
            )
            self.db.commit()
            return self.db.execute(
                "SELECT COUNT(*) FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()[0]

    def context(self, chat_id):
        with self.lock:
            facts = self.db.execute(
                """SELECT username, fact FROM facts
                   WHERE chat_id = ?
                   ORDER BY id DESC LIMIT 80""",
                (chat_id,),
            ).fetchall()
            rows = self.db.execute(
                """SELECT username, text FROM messages
                   WHERE chat_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (chat_id, self.limit),
            ).fetchall()

        rows.reverse()
        parts = []

        if facts:
            parts.append(
                "ДОЛГОСРОЧНАЯ ПАМЯТЬ "
                "(только ранее явно сказанные факты):"
            )
            parts.extend(f"{u}: {f}" for u, f in reversed(facts))

        parts.append("ПОСЛЕДНИЕ СООБЩЕНИЯ:")
        parts.extend(f"{u}: {t}" for u, t in rows)
        return "\n".join(parts)

    def add_fact(self, chat_id, username, fact):
        fact = (fact or "").strip()[:500]
        if not fact:
            return

        with self.lock:
            self.db.execute(
                """INSERT OR IGNORE INTO facts(chat_id, username, fact)
                   VALUES (?, ?, ?)""",
                (chat_id, username[:100], fact),
            )
            self.db.execute(
                """DELETE FROM facts
                   WHERE chat_id = ? AND id NOT IN (
                       SELECT id FROM facts
                       WHERE chat_id = ?
                       ORDER BY id DESC LIMIT 200
                   )""",
                (chat_id, chat_id),
            )
            self.db.commit()
