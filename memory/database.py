"""
JARVIS — memory/database.py
SQLite database setup and management for JARVIS memory.

Thread-safe: each call to get_connection() returns a fresh connection.
Uses WAL mode for concurrent read/write from multiple threads.
"""

import sqlite3
import os
import threading
from pathlib import Path
from utils.logger import log


# Database file location
DB_PATH = Path(__file__).parent.parent / "jarvis_memory.db"

# ─── Backward-compat lock (kept for imports in other modules) ─
_conn_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    """
    Get a NEW database connection (thread-safe).

    Each call creates a fresh sqlite3.Connection bound to the
    calling thread. Callers MUST use it with a context manager:

        with get_connection() as conn:
            conn.execute(...)
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row  # Enable dict-like row access

        # Enable WAL mode for better concurrency
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass

        return conn
    except Exception as e:
        log.error(f"Failed to create database connection: {e}")
        raise


def close_connection():
    """
    Shutdown hook — kept for backward compatibility.
    With per-call connections, there is no singleton to close.
    WAL checkpoint ensures all writes are flushed.
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        log.info("Database WAL checkpoint completed")
    except Exception as e:
        log.error(f"Error during database shutdown: {e}")


def initialize_db():
    """Create all tables if they don't exist."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # ── Conversation History ──────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    user_input  TEXT     NOT NULL,
                    jarvis_reply TEXT    NOT NULL,
                    intent      TEXT     DEFAULT 'chat',
                    session_id  TEXT     DEFAULT 'default'
                )
            """)

            # ── User Preferences ─────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── Reminders ────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                    message     TEXT     NOT NULL,
                    remind_at   DATETIME NOT NULL,
                    is_done     INTEGER  DEFAULT 0,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recurring_reminders (
                    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                    message     TEXT     NOT NULL,
                    frequency   TEXT     NOT NULL,
                    at_time     TEXT     NOT NULL,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS whatsapp_drafts (
                    id               INTEGER  PRIMARY KEY AUTOINCREMENT,
                    contact          TEXT     NOT NULL,
                    incoming_message TEXT     NOT NULL,
                    generated_reply  TEXT     NOT NULL,
                    status           TEXT     DEFAULT 'pending',
                    timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS assistant_alerts (
                    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                    alert_type  TEXT     NOT NULL,
                    message     TEXT     NOT NULL,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    delivered_at DATETIME
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
                    goal         TEXT     NOT NULL,
                    plan_json    TEXT     NOT NULL,
                    current_step INTEGER  DEFAULT 0,
                    status       TEXT     DEFAULT 'pending',
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_alerts (
                    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
                    entity_id     TEXT     NOT NULL,
                    entity_type   TEXT     NOT NULL,
                    alert_window  TEXT     NOT NULL,
                    target_time   DATETIME NOT NULL,
                    delivered_at  DATETIME,
                    UNIQUE(entity_id, entity_type, alert_window)
                )
            """)

            # ── Skills Log ───────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skill_log (
                    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    skill       TEXT     NOT NULL,
                    input       TEXT,
                    result      TEXT
                )
            """)

            conn.commit()
            log.info(f"Database initialized at: {DB_PATH} ✅")

    except Exception as e:
        log.error(f"Database init error: {e}")


def log_skill_use(skill: str, input_text: str, result: str):
    """Log a skill execution to the database."""
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO skill_log (skill, input, result) VALUES (?, ?, ?)",
                (skill, input_text[:200], result[:500])
            )
            conn.commit()
    except Exception as e:
        log.error(f"Skill log error: {e}")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    initialize_db()
    print(f"Database ready at: {DB_PATH}")

