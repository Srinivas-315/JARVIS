"""
JARVIS — memory/user_prefs.py
Persistent user preferences stored in SQLite.
"""

from memory.database import get_connection
from utils.logger import log
import config


class UserPrefs:
    """Manages persistent user preferences."""

    # ─── Default preferences ─────────────────────────────────
    DEFAULTS = {
        "name":          config.USER_NAME,
        "city":          config.USER_CITY,
        "voice_rate":    str(config.VOICE_RATE),
        "whisper_model": config.WHISPER_MODEL,
        "news_category": "general",
        "greeting_done": "false",
    }

    def __init__(self):
        self._load_defaults()

    def _load_defaults(self):
        """Load defaults if not already in DB."""
        defaults = {
            "name":          config.USER_NAME,
            "city":          config.USER_CITY,
            "voice_rate":    str(config.VOICE_RATE),
            "whisper_model": config.WHISPER_MODEL,
            "news_category": "general",
            "greeting_done": "false",
        }
        for key, value in defaults.items():
            if self.get(key) is None:
                self.set(key, value)

    def get(self, key: str, fallback=None):
        """Get a preference value."""
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM preferences WHERE key = ?", (key,)
                ).fetchone()
                return row["value"] if row else fallback
        except Exception as e:
            log.error(f"Prefs get error: {e}")
            return fallback

    def set(self, key: str, value: str):
        """Set a preference value (upsert)."""
        try:
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO preferences (key, value, updated_at)
                       VALUES (?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                    (key, str(value))
                )
                conn.commit()
        except Exception as e:
            log.error(f"Prefs set error: {e}")

    def get_all(self) -> dict:
        """Return all preferences as a dictionary."""
        try:
            with get_connection() as conn:
                rows = conn.execute("SELECT key, value FROM preferences").fetchall()
                return {row["key"]: row["value"] for row in rows}
        except Exception as e:
            log.error(f"Prefs get all error: {e}")
            return {}

    def reset(self):
        """Reset all preferences to defaults."""
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM preferences")
                conn.commit()
            self._load_defaults()
            log.info("Preferences reset to defaults.")
        except Exception as e:
            log.error(f"Prefs reset error: {e}")

    # ─── Convenience properties ──────────────────────────────
    @property
    def name(self) -> str:
        return self.get("name", config.USER_NAME)

    @property
    def city(self) -> str:
        return self.get("city", config.USER_CITY)

    @name.setter
    def name(self, value: str):
        self.set("name", value)

    @city.setter
    def city(self, value: str):
        self.set("city", value)
