"""
JARVIS — memory/chat_history.py
Save and retrieve conversation history from SQLite.
"""

from memory.database import get_connection
from utils.logger import log


class ChatHistory:
    """Manages conversation history in SQLite."""

    def save(self, user_input: str, jarvis_reply: str, intent: str = "chat", session: str = "default"):
        """Save a conversation exchange."""
        try:
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO conversations 
                       (user_input, jarvis_reply, intent, session_id)
                       VALUES (?, ?, ?, ?)""",
                    (user_input, jarvis_reply, intent, session)
                )
                conn.commit()
        except Exception as e:
            log.error(f"Chat save error: {e}")

    def get_recent(self, limit: int = 10, session: str = None) -> list:
        """Get N most recent conversations."""
        try:
            with get_connection() as conn:
                if session:
                    rows = conn.execute(
                        """SELECT * FROM conversations WHERE session_id = ?
                           ORDER BY timestamp DESC LIMIT ?""",
                        (session, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM conversations ORDER BY timestamp DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            log.error(f"Chat retrieve error: {e}")
            return []

    def get_context_for_gemini(self, limit: int = 5) -> str:
        """Get recent history formatted for Gemini context injection."""
        history = self.get_recent(limit)
        if not history:
            return ""

        lines = []
        for h in reversed(history):  # Oldest first
            lines.append(f"User: {h['user_input']}")
            lines.append(f"JARVIS: {h['jarvis_reply']}")

        return "\n".join(lines)

    def search(self, query: str) -> list:
        """Search conversation history for a keyword."""
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    """SELECT * FROM conversations 
                       WHERE user_input LIKE ? OR jarvis_reply LIKE ?
                       ORDER BY timestamp DESC LIMIT 5""",
                    (f"%{query}%", f"%{query}%")
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            log.error(f"Chat search error: {e}")
            return []

    def clear(self):
        """Delete all conversation history."""
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM conversations")
                conn.commit()
            log.info("Conversation history cleared.")
        except Exception as e:
            log.error(f"Chat clear error: {e}")

    def count(self) -> int:
        """Return total number of saved conversations."""
        try:
            with get_connection() as conn:
                result = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
                return result[0] if result else 0
        except Exception:
            return 0
