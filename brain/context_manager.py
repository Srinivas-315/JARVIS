"""
JARVIS — brain/context_manager.py
Conversation context memory — enables follow-up understanding.

Tracks the last N commands, their results, and active entities so
JARVIS can resolve pronouns and understand context like:
  "Play Believer" → "Make it louder" → knows "it" = music
  "Take a screenshot" → "Send that to Mom" → knows "that" = screenshot
"""

from collections import deque
from datetime import datetime
from utils.logger import log


class ConversationContext:
    """Tracks conversation state for context-aware command understanding."""

    def __init__(self, max_history: int = 8):
        self._history = deque(maxlen=max_history)
        self._last_action = None
        self._last_entities = {}
        self._last_skill = None
        self._active_media = None       # e.g. {"type": "music", "title": "Believer"}
        self._last_contact = None       # e.g. "Sarvani"
        self._last_app = None           # e.g. "chrome"
        self._last_file = None          # e.g. "report.pdf"
        self._pending_clarification = None  # For multi-turn follow-ups
        self._session_start = datetime.now()

    # ── Record Commands ──────────────────────────────────────────

    def add_user_input(self, text: str):
        """Record a new user command (before processing)."""
        self._history.append({
            "role": "user",
            "text": text,
            "timestamp": datetime.now(),
            "intent": None,
            "entities": {},
            "response": None,
        })

    def add_result(self, intent_result: dict, response: str):
        """
        Record the result of processing a command.

        Args:
            intent_result: {"action": "open_app", "entities": {"app": "chrome"}, ...}
            response: JARVIS's spoken response text
        """
        if not self._history:
            return

        entry = self._history[-1]
        entry["intent"] = intent_result.get("action", "unknown")
        entry["entities"] = intent_result.get("entities", {})
        entry["response"] = response

        # Update tracked entities
        action = intent_result.get("action", "")
        entities = intent_result.get("entities", {})

        self._last_action = action
        self._last_entities = entities
        self._last_skill = action

        # Track specific entity types for pronoun resolution
        if "app" in entities or "app_name" in entities:
            self._last_app = entities.get("app") or entities.get("app_name")

        if "contact" in entities:
            self._last_contact = entities.get("contact")

        if "file" in entities or "filename" in entities:
            self._last_file = entities.get("file") or entities.get("filename")

        if action in ("play_music", "media", "youtube"):
            song = entities.get("song") or entities.get("query") or entities.get("title")
            self._active_media = {"type": "music", "title": song}

        if action == "screenshot":
            self._last_file = "screenshot"

        log.debug(
            f"Context updated: action={action}, entities={entities}, "
            f"last_app={self._last_app}, last_contact={self._last_contact}"
        )

    # ── Pronoun Resolution ───────────────────────────────────────

    def resolve_pronouns(self, text: str) -> str:
        """
        Replace pronouns with actual entities from context.

        "Make it louder"     → "Make music louder"
        "Send that to Mom"   → "Send screenshot to Mom"
        "Close it"           → "Close chrome"
        "Message them again" → "Message Sarvani again"
        """
        if not self._history:
            return text

        text_lower = text.lower()
        resolved = text

        # Map pronouns to their resolution source
        pronoun_map = {
            # "it" / "this" / "that" → last thing acted on
            " it ": self._get_last_thing,
            " it.": self._get_last_thing,
            " it?": self._get_last_thing,
            " it!": self._get_last_thing,
            " this ": self._get_last_thing,
            " this.": self._get_last_thing,
            " that ": self._get_last_thing,
            " that.": self._get_last_thing,
            # "them" / "him" / "her" → last contact
            " them ": self._get_last_person,
            " them.": self._get_last_person,
            " him ": self._get_last_person,
            " her ": self._get_last_person,
        }

        for pronoun, resolver in pronoun_map.items():
            if pronoun in f" {text_lower} ":
                replacement = resolver()
                if replacement:
                    # Only replace if we have something meaningful
                    resolved = resolved.replace(
                        pronoun.strip(),
                        replacement,
                        1  # Only first occurrence
                    )
                    log.info(f"Context resolved: '{pronoun.strip()}' → '{replacement}'")
                    break  # One resolution per command

        return resolved

    def _get_last_thing(self) -> str:
        """Get the last thing user interacted with."""
        # Priority: active media > last app > last file
        if self._active_media and self._last_action in (
            "play_music", "media", "volume_control", "youtube"
        ):
            return self._active_media.get("title", "the music")

        if self._last_app and self._last_action in (
            "open_app", "close_app", "browser_search"
        ):
            return self._last_app

        if self._last_file:
            return self._last_file

        # Generic fallback from last entities
        for key in ("app", "app_name", "song", "query", "file", "filename"):
            if key in self._last_entities:
                return self._last_entities[key]

        return ""

    def _get_last_person(self) -> str:
        """Get last person mentioned."""
        return self._last_contact or ""

    # ── Context for AI Router ────────────────────────────────────

    def get_context_summary(self, max_entries: int = 3) -> str:
        """
        Get recent conversation context as text for the AI router.
        Injected into the routing prompt so AI understands follow-ups.
        """
        if not self._history:
            return ""

        recent = list(self._history)[-max_entries:]
        lines = ["Recent conversation:"]

        for entry in recent:
            user_text = entry.get("text", "")[:80]
            intent = entry.get("intent", "?")
            response = (entry.get("response") or "")[:60]
            lines.append(f"  User: {user_text}")
            if intent and intent != "?":
                lines.append(f"  → Action: {intent}")
            if response:
                lines.append(f"  → JARVIS: {response}")

        # Add active state
        state_parts = []
        if self._active_media:
            state_parts.append(f"Currently playing: {self._active_media.get('title', '?')}")
        if self._last_app:
            state_parts.append(f"Last app: {self._last_app}")
        if self._last_contact:
            state_parts.append(f"Last contact: {self._last_contact}")

        if state_parts:
            lines.append("Active state: " + ", ".join(state_parts))

        return "\n".join(lines)

    # ── Clarification State ──────────────────────────────────────

    def set_pending_clarification(self, clarification: dict):
        """
        Set a pending clarification for multi-turn interaction.

        Args:
            clarification: {
                "action": "send_whatsapp",
                "known_entities": {"message": "good morning"},
                "missing": ["contact"],
                "prompt": "Who should I send it to?"
            }
        """
        self._pending_clarification = clarification

    def get_pending_clarification(self) -> dict | None:
        """Get pending clarification if any."""
        return self._pending_clarification

    def clear_pending_clarification(self):
        """Clear pending clarification after it's resolved."""
        self._pending_clarification = None

    def has_pending_clarification(self) -> bool:
        """Check if there's a pending clarification."""
        return self._pending_clarification is not None

    # ── Utility ──────────────────────────────────────────────────

    def clear(self):
        """Reset all context."""
        self._history.clear()
        self._last_action = None
        self._last_entities = {}
        self._last_skill = None
        self._active_media = None
        self._last_contact = None
        self._last_app = None
        self._last_file = None
        self._pending_clarification = None

    def get_last_action(self) -> str | None:
        """Get the last action performed."""
        return self._last_action

    def get_last_entities(self) -> dict:
        """Get entities from the last command."""
        return self._last_entities.copy()

    @property
    def last_contact(self) -> str | None:
        return self._last_contact

    @property
    def last_app(self) -> str | None:
        return self._last_app

    @property
    def active_media(self) -> dict | None:
        return self._active_media


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    ctx = ConversationContext()

    # Simulate: "Play Believer"
    ctx.add_user_input("Play Believer by Imagine Dragons")
    ctx.add_result(
        {"action": "play_music", "entities": {"song": "Believer"}},
        "Playing Believer by Imagine Dragons"
    )

    # Now: "Make it louder" → should resolve "it"
    text = "Make it louder"
    resolved = ctx.resolve_pronouns(text)
    print(f"'{text}' → '{resolved}'")
    # Expected: "Make Believer louder"

    # Context summary for AI
    print("\n" + ctx.get_context_summary())
