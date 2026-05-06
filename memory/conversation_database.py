"""
JARVIS — memory/conversation_database.py
Permanent conversation history — remembers EVERYTHING forever.
SQLite-backed, searchable, context-injectable.

Every single exchange is stored here — across ALL restarts.
Used by MemorySystem to inject context into every AI call.
"""

import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from utils.logger import log

DB_PATH = Path(__file__).parent.parent / "data" / "conversations_full.db"


class ConversationDatabase:
    """
    Stores EVERY conversation FOREVER.
    Searchable, context-aware, preference-tracking.
    Thread-safe (uses threading.Lock).
    """

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(DB_PATH), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_tables()
        log.info("ConversationDatabase ready ✅")

    # ── Schema ───────────────────────────────────────────────────

    def _init_tables(self):
        """Create all tables if they don't exist."""
        with self._lock:
            self._conn.executescript("""
                -- Every conversation exchange, forever
                CREATE TABLE IF NOT EXISTS conversations (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp     TEXT    NOT NULL,
                    user_input    TEXT    NOT NULL,
                    jarvis_reply  TEXT    NOT NULL DEFAULT '',
                    intent        TEXT    DEFAULT 'chat',
                    session_id    TEXT,
                    success       INTEGER DEFAULT 1
                );

                -- Personal facts extracted from conversation
                CREATE TABLE IF NOT EXISTS user_facts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    category    TEXT NOT NULL,
                    fact_key    TEXT NOT NULL,
                    fact_value  TEXT NOT NULL,
                    learned_at  TEXT NOT NULL,
                    UNIQUE(category, fact_key)
                );

                -- Frequency-tracked user preferences
                CREATE TABLE IF NOT EXISTS preferences (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    pref_type   TEXT NOT NULL,
                    pref_value  TEXT NOT NULL,
                    frequency   INTEGER DEFAULT 1,
                    last_used   TEXT NOT NULL,
                    UNIQUE(pref_type, pref_value)
                );

                CREATE INDEX IF NOT EXISTS idx_conv_ts
                    ON conversations(timestamp);
                CREATE INDEX IF NOT EXISTS idx_conv_input
                    ON conversations(user_input);
                CREATE INDEX IF NOT EXISTS idx_facts_cat
                    ON user_facts(category);
            """)

    # ── Save ─────────────────────────────────────────────────────

    def save(
        self,
        user_input: str,
        jarvis_reply: str,
        intent: str = "chat",
        session_id: str | None = None,
        success: bool = True,
    ):
        """Save one conversation exchange permanently."""
        if not user_input or not user_input.strip():
            return
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT INTO conversations
                       (timestamp, user_input, jarvis_reply, intent, session_id, success)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        datetime.now().isoformat(),
                        user_input.strip(),
                        (jarvis_reply or "").strip(),
                        intent,
                        session_id,
                        int(success),
                    ),
                )
        except Exception as e:
            log.error(f"ConversationDB save error: {e}")

    def save_fact(self, category: str, key: str, value: str):
        """Save or update a personal fact (upsert)."""
        if not value or not value.strip():
            return
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO user_facts
                       (category, fact_key, fact_value, learned_at)
                       VALUES (?, ?, ?, ?)""",
                    (
                        category.lower().strip(),
                        key.lower().strip(),
                        value.strip(),
                        datetime.now().isoformat(),
                    ),
                )
        except Exception as e:
            log.error(f"ConversationDB save_fact error: {e}")

    def track_preference(self, pref_type: str, value: str):
        """Increment frequency counter for a preference, or create it."""
        if not value or not value.strip():
            return
        try:
            with self._lock:
                existing = self._conn.execute(
                    "SELECT id FROM preferences WHERE pref_type=? AND pref_value=?",
                    (pref_type, value.strip()),
                ).fetchone()
                if existing:
                    self._conn.execute(
                        """UPDATE preferences
                           SET frequency=frequency+1, last_used=?
                           WHERE id=?""",
                        (datetime.now().isoformat(), existing["id"]),
                    )
                else:
                    self._conn.execute(
                        """INSERT INTO preferences
                           (pref_type, pref_value, last_used)
                           VALUES (?,?,?)""",
                        (pref_type, value.strip(), datetime.now().isoformat()),
                    )
        except Exception as e:
            log.error(f"ConversationDB track_preference error: {e}")

    # ── Recall ───────────────────────────────────────────────────

    def get_recent(self, limit: int = 10) -> list:
        """Get last N conversations (newest first)."""
        try:
            rows = self._conn.execute(
                """SELECT user_input, jarvis_reply, timestamp, intent
                   FROM conversations
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def search(self, query: str, limit: int = 8) -> list:
        """Full-text search over user_input and jarvis_reply."""
        try:
            rows = self._conn.execute(
                """SELECT user_input, jarvis_reply, timestamp
                   FROM conversations
                   WHERE user_input LIKE ? OR jarvis_reply LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_context_window(self, minutes: int = 45) -> str:
        """
        Return recent conversation as a formatted string for LLM context.
        Only goes back `minutes` minutes to keep context relevant.
        """
        try:
            since = (datetime.now() - timedelta(minutes=minutes)).isoformat()
            rows = self._conn.execute(
                """SELECT user_input, jarvis_reply
                   FROM conversations
                   WHERE timestamp >= ?
                   ORDER BY id ASC""",
                (since,),
            ).fetchall()
            if not rows:
                return ""
            lines = []
            for r in rows:
                lines.append(f"User: {r['user_input']}")
                if r["jarvis_reply"]:
                    lines.append(f"JARVIS: {r['jarvis_reply']}")
            return "\n".join(lines)
        except Exception:
            return ""

    def get_all_facts(self) -> dict:
        """Return all personal facts grouped by category."""
        try:
            rows = self._conn.execute(
                "SELECT category, fact_key, fact_value FROM user_facts ORDER BY category, fact_key"
            ).fetchall()
            result: dict = {}
            for r in rows:
                cat = r["category"]
                if cat not in result:
                    result[cat] = {}
                result[cat][r["fact_key"]] = r["fact_value"]
            return result
        except Exception:
            return {}

    def get_fact(self, category: str, key: str) -> str:
        """Get a single fact value."""
        try:
            row = self._conn.execute(
                "SELECT fact_value FROM user_facts WHERE category=? AND fact_key=?",
                (category.lower(), key.lower()),
            ).fetchone()
            return row["fact_value"] if row else ""
        except Exception:
            return ""

    def get_top_preferences(self, pref_type: str, limit: int = 5) -> list:
        """Get most frequent preferences of a given type."""
        try:
            rows = self._conn.execute(
                """SELECT pref_value, frequency
                   FROM preferences
                   WHERE pref_type=?
                   ORDER BY frequency DESC LIMIT ?""",
                (pref_type, limit),
            ).fetchall()
            return [(r["pref_value"], r["frequency"]) for r in rows]
        except Exception:
            return []

    # ── Statistics ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return conversation statistics."""
        try:
            total = self._conn.execute(
                "SELECT COUNT(*) as c FROM conversations"
            ).fetchone()["c"]
            today = self._conn.execute(
                "SELECT COUNT(*) as c FROM conversations WHERE DATE(timestamp)=DATE('now')"
            ).fetchone()["c"]
            facts = self._conn.execute(
                "SELECT COUNT(*) as c FROM user_facts"
            ).fetchone()["c"]
            sessions = self._conn.execute(
                "SELECT COUNT(DISTINCT session_id) as c FROM conversations WHERE session_id IS NOT NULL"
            ).fetchone()["c"]
            return {
                "total": total,
                "today": today,
                "facts": facts,
                "sessions": sessions,
            }
        except Exception:
            return {"total": 0, "today": 0, "facts": 0, "sessions": 0}

    def get_total_conversations(self) -> int:
        """Convenience method — returns total conversation count."""
        return self.get_stats().get("total", 0)

    # ── Maintenance ──────────────────────────────────────────────

    def close(self):
        """Close the database connection gracefully."""
        try:
            self._conn.close()
        except Exception:
            pass
