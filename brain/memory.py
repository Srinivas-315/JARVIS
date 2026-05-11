"""
JARVIS — brain/memory.py
Conversation Memory — JARVIS remembers context and personal facts.

Two types:
1. Short-term: Last 10 messages (RAM) — "play that song again"
2. Long-term: Personal facts (disk) — "my favorite color is blue"
"""

import json
import os
import re
from datetime import datetime
from utils.logger import log

# Vector memory for RAG (lazy-loaded)
try:
    from brain.vector_memory import VectorMemory
    _VECTOR_MEMORY = VectorMemory()
except Exception as _e:
    log.info(f"VectorMemory not available: {_e}")
    _VECTOR_MEMORY = None

# Where long-term memory is stored
MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
FACTS_FILE = os.path.join(MEMORY_DIR, "user_memory.json")


class ConversationMemory:
    """Manages short-term context and long-term personal facts."""

    def __init__(self, max_short_term: int = 10):
        self._short_term = []  # Recent messages [{role, content, time}]
        self._max = max_short_term
        self._facts = {}       # Long-term personal facts
        self._load_facts()

    # ═══════════════════════════════════════════════════════════
    # SHORT-TERM MEMORY (current session context)
    # ═══════════════════════════════════════════════════════════

    def add_user_message(self, text: str, intent: str = ""):
        """Remember what the user said."""
        self._short_term.append({
            "role": "user",
            "content": text,
            "time": datetime.now().isoformat()
        })
        # Keep only last N messages
        if len(self._short_term) > self._max * 2:
            self._short_term = self._short_term[-self._max * 2:]

        # Store in vector memory for RAG
        if _VECTOR_MEMORY and _VECTOR_MEMORY.is_ready:
            _VECTOR_MEMORY.store(text, role="user", intent=intent)

        # Check if user shared a personal fact
        self._detect_and_save_fact(text)

    def add_jarvis_message(self, text: str, intent: str = ""):
        """Remember what JARVIS said."""
        self._short_term.append({
            "role": "assistant",
            "content": text,
            "time": datetime.now().isoformat()
        })
        if len(self._short_term) > self._max * 2:
            self._short_term = self._short_term[-self._max * 2:]

        # Store in vector memory for RAG
        if _VECTOR_MEMORY and _VECTOR_MEMORY.is_ready:
            _VECTOR_MEMORY.store(text, role="assistant", intent=intent)

    def get_context_messages(self) -> list:
        """Get recent messages for LLM context."""
        return [{"role": m["role"], "content": m["content"]}
                for m in self._short_term[-self._max:]]

    def get_last_topic(self) -> str:
        """Get the last thing discussed (for 'play that again' type queries)."""
        for msg in reversed(self._short_term):
            if msg["role"] == "user":
                return msg["content"]
        return ""

    def get_summary(self) -> str:
        """Get a brief summary of recent conversation for context."""
        if not self._short_term:
            return ""
        recent = self._short_term[-6:]
        lines = []
        for m in recent:
            role = "User" if m["role"] == "user" else "JARVIS"
            lines.append(f"{role}: {m['content'][:80]}")
        return "\n".join(lines)

    def get_relevant_history(self, query: str, top_k: int = 5) -> str:
        """Search vector memory for relevant past conversations (RAG)."""
        if _VECTOR_MEMORY and _VECTOR_MEMORY.is_ready:
            return _VECTOR_MEMORY.get_context_for_prompt(query, top_k=top_k)
        return ""

    def get_memory_stats(self) -> dict:
        """Get combined memory statistics."""
        stats = {
            "short_term_msgs": len(self._short_term),
            "long_term_facts": len(self._facts),
        }
        if _VECTOR_MEMORY and _VECTOR_MEMORY.is_ready:
            stats["vector_memory"] = _VECTOR_MEMORY.get_stats()
        return stats

    # ═══════════════════════════════════════════════════════════
    # LONG-TERM MEMORY (personal facts — saved to disk)
    # ═══════════════════════════════════════════════════════════

    def _detect_and_save_fact(self, text: str):
        """Detect if user shared a personal fact and save it."""
        t = text.lower().strip()

        # Patterns that indicate personal facts
        patterns = {
            r"my (?:favourite|favorite) (?:color|colour) is (\w+)": "favorite_color",
            r"my name is (\w+)": "name",
            r"my (?:favourite|favorite) song is (.+)": "favorite_song",
            r"my (?:favourite|favorite) movie is (.+)": "favorite_movie",
            r"my (?:favourite|favorite) food is (.+)": "favorite_food",
            r"my birthday is (.+)": "birthday",
            r"i live in (\w+)": "city",
            r"i am (\d+) years old": "age",
            r"i'm (\d+) years old": "age",
            r"i study (\w+)": "studies",
            r"i work (?:at|in) (.+)": "workplace",
            r"my (?:favourite|favorite) (?:game|video game) is (.+)": "favorite_game",
            r"my (?:favourite|favorite) artist is (.+)": "favorite_artist",
            r"my (?:favourite|favorite) singer is (.+)": "favorite_singer",
            r"i like (.+?) music": "music_preference",
            r"my pet(?:'s)? name is (\w+)": "pet_name",
            r"call me (\w+)": "nickname",
            r"remember that (.+)": "custom_memory",
        }

        for pattern, key in patterns.items():
            match = re.search(pattern, t)
            if match:
                value = match.group(1).strip()
                if key == "custom_memory":
                    # Save custom memories with timestamp
                    if "custom" not in self._facts:
                        self._facts["custom"] = []
                    self._facts["custom"].append({
                        "fact": value,
                        "date": datetime.now().isoformat()
                    })
                else:
                    self._facts[key] = value

                self._save_facts()
                log.info(f"Memory saved: {key} = '{value}'")
                return True
        return False

    def get_facts_prompt(self) -> str:
        """Get personal facts formatted for LLM context."""
        if not self._facts:
            return ""

        lines = ["Things I know about the user:"]
        for key, value in self._facts.items():
            if key == "custom":
                for mem in value[-5:]:  # Last 5 custom memories
                    lines.append(f"- User said to remember: {mem['fact']}")
            else:
                clean_key = key.replace("_", " ").title()
                lines.append(f"- {clean_key}: {value}")

        return "\n".join(lines)

    def get_fact(self, key: str) -> str:
        """Get a specific fact about the user."""
        return self._facts.get(key, "")

    def forget(self, key: str = None):
        """Forget a specific fact or everything."""
        if key:
            self._facts.pop(key, None)
        else:
            self._facts.clear()
        self._save_facts()
        log.info(f"Memory cleared: {'all' if not key else key}")

    def _load_facts(self):
        """Load personal facts from disk."""
        try:
            if os.path.exists(FACTS_FILE):
                with open(FACTS_FILE, "r", encoding="utf-8") as f:
                    self._facts = json.load(f)
                log.info(f"Loaded {len(self._facts)} personal facts from memory.")
        except Exception as e:
            log.warning(f"Could not load memory: {e}")
            self._facts = {}

    def _save_facts(self):
        """Save personal facts to disk."""
        try:
            os.makedirs(MEMORY_DIR, exist_ok=True)
            with open(FACTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._facts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Could not save memory: {e}")

    def clear_session(self):
        """Clear short-term memory (keep long-term)."""
        self._short_term.clear()
        log.info("Session memory cleared.")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    mem = ConversationMemory()

    # Test short-term
    mem.add_user_message("Play Believer on Spotify")
    mem.add_jarvis_message("Playing now.")
    mem.add_user_message("Play that song again")
    print("Last topic:", mem.get_last_topic())
    print("Context:", mem.get_summary())

    # Test long-term
    mem.add_user_message("My favorite color is blue")
    mem.add_user_message("Remember that I have a meeting tomorrow at 10am")
    print("Facts:", mem.get_facts_prompt())
    print("Color:", mem.get_fact("favorite_color"))
