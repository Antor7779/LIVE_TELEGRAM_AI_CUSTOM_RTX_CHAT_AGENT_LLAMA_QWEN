from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "chat.db"


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'New Chat',
            model TEXT NOT NULL,
            persona TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('system','user','assistant')),
            content TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, id);

        CREATE INDEX IF NOT EXISTS idx_conversations_updated
            ON conversations(updated_at DESC);

        CREATE TABLE IF NOT EXISTS channel_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            conversation_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(channel, sender_id),
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        """)


def create_conversation(title="New Chat", model="llama3.1:8b", persona="general"):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO conversations(title, model, persona) VALUES (?, ?, ?)",
            (title, model, persona),
        )
        return cur.lastrowid


def get_conversation(conversation_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return dict(row) if row else None


def get_conversations():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_messages(conversation_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_message(conversation_id, role, content, model=None):
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO messages(conversation_id, role, content, model)
               VALUES (?, ?, ?, ?)""",
            (conversation_id, role, content, model),
        )
        return cur.lastrowid


def touch_conversation(conversation_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )


def update_conversation(conversation_id, title=None, model=None, persona=None):
    current = get_conversation(conversation_id)
    if not current:
        return

    title = current["title"] if title is None else title
    model = current["model"] if model is None else model
    persona = current["persona"] if persona is None else persona

    with get_connection() as conn:
        conn.execute(
            """UPDATE conversations
               SET title=?, model=?, persona=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (title, model, persona, conversation_id),
        )


def delete_conversation(conversation_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
