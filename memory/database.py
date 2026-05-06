"""
JARVIS — memory/database.py
SQLite database setup and management for JARVIS memory.

Uses a single connection pool with thread-safe access to prevent:
  - Connection limit exhaustion
  - Database lock issues
  - Resource leaks
"""

import sqlite3
import os
import threading
from pathlib import Path
from utils.logger import log


# Database file location
DB_PATH = Path(__file__).parent.parent / "jarvis_memory.db"

# ─── Connection Pooling ──────────────────────────────────────
_conn_lock = threading.Lock()
_connection = None


def get_connection() -> sqlite3.Connection:
    """
    Get the singleton database connection (thread-safe).

    Returns the shared connection instance. SQLite handles concurrent
    access via the database lock, and we use a thread lock for safety.
    """
    global _connection

    # Double-check locking pattern to minimize lock contention
    if _connection is None:
        with _conn_lock:
            if _connection is None:
                _connection = _create_connection()

    return _connection


def _create_connection() -> sqlite3.Connection:
    """Create and configure the SQLite connection."""
    try:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Enable dict-like row access

        # Enable WAL mode for better concurrency (if SQLite version supports it)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass  # WAL not available in this SQLite version

        return conn
    except Exception as e:
        log.error(f"Failed to create database connection: {e}")
        raise


def close_connection():
    """
    Close the database connection gracefully.

    Called during shutdown to ensure all transactions are committed
    and the connection is properly cleaned up.
    """
    global _connection

    if _connection is not None:
        try:
            _connection.commit()
            _connection.close()
            _connection = None
            log.info("Database connection closed")
        except Exception as e:
            log.error(f"Error closing database connection: {e}")


def initialize_db():
    """Create all tables if they don't exist."""
    try:
        conn = get_connection()
        with _conn_lock:
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
        conn = get_connection()
        with _conn_lock:
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

