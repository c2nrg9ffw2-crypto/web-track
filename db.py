"""Database layer.

Uses Supabase / Postgres when the ``DATABASE_URL`` environment variable is set
(Render in the cloud, or your Mac when you export it), and falls back to a local
SQLite file otherwise. The rest of the app talks to this module through
``get_db()`` and writes plain ``?``-style SQL; placeholders are translated to
``%s`` automatically for Postgres.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL")
IS_PG = bool(DATABASE_URL)

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row

DB_PATH = Path.home() / ".local" / "share" / "taskboard" / "data.db"


def _translate(sql: str) -> str:
    """SQLite uses ``?`` placeholders, Postgres uses ``%s``."""
    return sql.replace("?", "%s") if IS_PG else sql


class Conn:
    """Thin wrapper giving SQLite and Postgres a uniform execute interface."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        sql = _translate(sql)
        if IS_PG:
            return self.raw.execute(sql, params or None)
        return self.raw.execute(sql, params)

    def executemany(self, sql, seq):
        sql = _translate(sql)
        seq = list(seq)
        if IS_PG:
            cur = self.raw.cursor()
            if seq:
                cur.executemany(sql, seq)
            return cur
        return self.raw.executemany(sql, seq)


@contextmanager
def get_db():
    if IS_PG:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=None)
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    wrapper = Conn(conn)
    try:
        yield wrapper
        conn.commit()
    finally:
        conn.close()


def init_db():
    pk = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    msg_pk = "BIGINT PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY"
    statements = [
        f"""
        CREATE TABLE IF NOT EXISTS tasks (
            id {pk},
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            priority TEXT DEFAULT 'medium',
            done INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            webuntis_id TEXT,
            reminders_id TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS notes (
            id {pk},
            title TEXT NOT NULL,
            content TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            apple_notes_id TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS schedule_lessons (
            id {pk},
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            subject TEXT,
            teacher TEXT,
            room TEXT,
            cancelled INTEGER DEFAULT 0,
            lesson_code TEXT DEFAULT 'REGULAR',
            synced_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS messages (
            id {msg_pk},
            subject TEXT,
            body TEXT,
            sender TEXT,
            sent_at TEXT,
            is_read INTEGER DEFAULT 0,
            synced_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mudo_bookings (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            duration_min INTEGER,
            title TEXT NOT NULL,
            instructors TEXT,
            room TEXT,
            status TEXT NOT NULL,
            synced_at TEXT NOT NULL
        )
        """,
    ]
    with get_db() as conn:
        for stmt in statements:
            conn.execute(stmt)


def migrate_db():
    statements = [
        "ALTER TABLE schedule_lessons ADD COLUMN lesson_code TEXT DEFAULT 'REGULAR'",
        "ALTER TABLE tasks ADD COLUMN webuntis_id TEXT",
        "ALTER TABLE tasks ADD COLUMN reminders_id TEXT",
        "ALTER TABLE notes ADD COLUMN apple_notes_id TEXT",
    ]
    for stmt in statements:
        if IS_PG:
            stmt = stmt.replace("ADD COLUMN", "ADD COLUMN IF NOT EXISTS")
        # Each in its own connection so a failure (column already exists on
        # SQLite) cannot poison a shared Postgres transaction.
        with get_db() as conn:
            try:
                conn.execute(stmt)
            except Exception:
                pass
