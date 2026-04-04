import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def _default_db_path() -> str:
    """
    Store the database in the top-level /database folder (per project requirements).
    """
    backend_dir = Path(__file__).resolve().parent
    project_root = backend_dir.parent
    db_dir = project_root / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "study_assistant.db")


DB_PATH = os.environ.get("STUDY_ASSISTANT_DB_PATH", _default_db_path())


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """
    Create tables if they don't exist.
    """
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS notes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              filename TEXT,
              original_text TEXT NOT NULL,
              summary TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS flashcards (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              note_id INTEGER NOT NULL,
              question TEXT NOT NULL,
              answer TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS quiz (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              note_id INTEGER NOT NULL,
              question TEXT NOT NULL,
              options_json TEXT NOT NULL,
              correct_index INTEGER NOT NULL,
              answer_text TEXT,
              explanation TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
            );
            """
        )

        # Lightweight migrations for older DBs (if table existed before new columns).
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(quiz);").fetchall()}
        if "answer_text" not in cols:
            conn.execute("ALTER TABLE quiz ADD COLUMN answer_text TEXT;")
        if "explanation" not in cols:
            conn.execute("ALTER TABLE quiz ADD COLUMN explanation TEXT;")


def query_one(sql: str, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone()


def query_all(sql: str, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall()


def execute(sql: str, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid

