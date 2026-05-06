"""
JARVIS — jarvis/memory_system.py
Unified long-term memory — wires ConversationDatabase + PersonalMemory.

Every conversation is saved permanently.
Every personal fact is extracted and recalled.
Every AI call gets the full context injected.

Storage:
    data/conversations_full.db  ← ALL conversations, forever (SQLite)
    data/personal_facts.json    ← Personal facts (name, college, city…)
    data/jarvis_memory.json     ← Preferences, topics, corrections (JSON)
"""

import json
import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import config

# ── Storage paths ─────────────────────────────────────────────
_MEMORY_FILE = Path(__file__).parent.parent / "data" / "jarvis_memory.json"

# ── Phrases that trigger "remember that X" saves ─────────────
_REMEMBER_PHRASES = [
    "remember that",
    "remember,",
    "note that",
    "don't forget",
    "keep in mind",
    "i want you to know",
    "fyi,",
    "by the way,",
    "just so you know",
    "save this",
    "store this",
]


class MemorySystem:
    """
    JARVIS unified memory hub.

    Short-term : last 10 conversation turns in RAM (fast context)
    Long-term  : ConversationDatabase (SQLite, permanent, searchable)
    Facts      : PersonalMemory (JSON, name/city/college/…)
    Preferences: jarvis_memory.json (topics, prefs, corrections)
    """

    def __init__(self):
        _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        # In-RAM short-term deque (10 turns)
        self._short_term: deque = deque(maxlen=10)

        # JSON-backed preferences / topics / corrections
        self._data = self._load()

        # ── ConversationDatabase — permanent SQLite storage ───
        try:
            from memory.conversation_database import ConversationDatabase

            self.conv_db = ConversationDatabase()
        except Exception as _e:
            print(f"  [Memory] ConversationDatabase unavailable: {_e}")
            self.conv_db = None

        # ── PersonalMemory — personal facts JSON store ────────
        # Lazy reference: assigned from main.py after init to share
        # the same instance and avoid double-loading the JSON file.
        self._personal_mem = None

    # ── Personal memory reference ─────────────────────────────

    def set_personal_memory(self, personal_mem) -> None:
        """
        Wire the shared PersonalMemory instance.
        Called from main.py immediately after both objects are created.
        """
        self._personal_mem = personal_mem

    def _get_personal_mem(self):
        """Lazy-load PersonalMemory if not yet wired."""
        if self._personal_mem is None:
            try:
                from memory.personal_memory import PersonalMemory

                self._personal_mem = PersonalMemory()
            except Exception:
                pass
        return self._personal_mem

    # ── Persistence (JSON prefs/topics/corrections) ──────────

    def _load(self) -> dict:
        if _MEMORY_FILE.exists():
            try:
                with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "facts": [],
            "preferences": {},
            "topics": {},
            "corrections": [],
            "session_count": 0,
            "total_exchanges": 0,
        }

    def _save(self):
        try:
            with open(_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  [Memory] Save failed: {e}")

    # ── Short-term context ────────────────────────────────────

    def add_exchange(
        self,
        user_text: str,
        jarvis_response: str,
        intent: str = "chat",
        session_id: str | None = None,
    ):
        """
        Record one Q&A turn.
        Saves to:
          1. In-RAM short-term deque (instant context)
          2. ConversationDatabase (permanent SQLite)
        Also tracks topic frequency.
        """
        # 1. In-RAM
        self._short_term.append(("user", user_text))
        self._short_term.append(("jarvis", jarvis_response))
        self._data["total_exchanges"] = self._data.get("total_exchanges", 0) + 1

        # 2. Permanent SQLite
        if self.conv_db and user_text and user_text.strip():
            try:
                self.conv_db.save(
                    user_input=user_text,
                    jarvis_reply=jarvis_response or "",
                    intent=intent,
                    session_id=session_id,
                )
            except Exception as _e:
                print(f"  [Memory] conv_db.save error: {_e}")

        # 3. Track topic frequency (silent)
        self._track_topic(user_text)

        # Periodically persist topics
        total = self._data.get("total_exchanges", 0)
        if total % 10 == 0:
            self._save()

    def get_recent_context(self, n: int = 6) -> str:
        """Return last n turns as a formatted string."""
        items = list(self._short_term)[-(n * 2) :]
        lines = []
        for role, text in items:
            prefix = config.USER_NAME if role == "user" else "JARVIS"
            lines.append(f"{prefix}: {text}")
        return "\n".join(lines)

    # ── Learning from user input ──────────────────────────────

    def process_user_input(self, text: str) -> str | None:
        """
        Scan user input for explicit learning triggers only.
        ("remember that X", "note that X", preference tracking)

        NOTE: PersonalMemory.try_learn() (name, city, college, …) is
        handled exclusively in main._process_command_inner() so that the
        full name-sync pipeline (config / .env / prefs) always runs.
        This method must NOT call try_learn() — doing so creates a
        double-call that returns early and skips the name-sync logic.
        """
        text_lower = text.lower().strip()

        # ── "Remember that X" explicit saves ──────────────────
        for phrase in _REMEMBER_PHRASES:
            if phrase in text_lower:
                fact = re.sub(
                    r".*(remember that|remember,|note that|don't forget"
                    r"|keep in mind|i want you to know|fyi,|by the way,"
                    r"|just so you know|save this|store this)",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip(" .,!")
                if fact:
                    return self._save_fact(fact)
                break

        # ── Preference tracking (silent) ──────────────────────
        pref_match = re.search(
            r"i (?:prefer|like|love|enjoy|hate|dislike|always|usually) (.+)",
            text_lower,
        )
        if pref_match:
            pref = pref_match.group(1).strip(" .,!")
            self._save_preference(pref)

        # ── Topic frequency ───────────────────────────────────
        self._track_topic(text)

        return None

    # ── Context for LLM ──────────────────────────────────────

    def get_context_for_llm(self) -> str:
        """
        Build a compact memory context string for LLM prompts.
        Includes: personal facts + JSON preferences + short-term context.
        """
        parts = []

        # Personal facts from PersonalMemory
        pm = self._get_personal_mem()
        if pm:
            summary = pm.get_summary()
            if summary:
                parts.append(f"Personal facts about {config.USER_NAME}: {summary}")

        # Also check conv_db for any facts stored there
        if self.conv_db:
            db_facts = self.conv_db.get_all_facts()
            if db_facts:
                for category, items in db_facts.items():
                    for key, value in items.items():
                        # Avoid duplicates with PersonalMemory summary
                        if (
                            f"{key}: {value}".lower() not in parts[0].lower()
                            if parts
                            else True
                        ):
                            pass  # Already covered by pm.get_summary()

        # JSON preferences (last 3)
        prefs = list(self._data.get("preferences", {}).values())[-3:]
        if prefs:
            parts.append("Preferences: " + "; ".join(p["value"] for p in prefs))

        # JSON facts (last 5)
        json_facts = self._data.get("facts", [])[-5:]
        if json_facts:
            parts.append("Remembered: " + "; ".join(f["fact"] for f in json_facts))

        # Short-term recent conversation (last 4 turns)
        ctx = self.get_recent_context(4)
        if ctx:
            parts.append("Recent conversation:\n" + ctx)

        return "\n".join(parts)

    def get_personal_facts_summary(self) -> str:
        """
        Compact one-liner of personal facts for system-prompt injection.
        e.g. "User's name: Srini. College: NIT Delhi. City: Chennai."
        Injected into EVERY Gemini/LLM call so the AI always knows the user.
        """
        pm = self._get_personal_mem()
        if not pm:
            return ""

        summary = pm.get_summary()
        if not summary:
            return ""

        # Also include JSON-based remembered facts
        extra = []
        json_facts = self._data.get("facts", [])
        for f in json_facts[-3:]:
            extra.append(f["fact"])

        if extra:
            summary += " Also remember: " + "; ".join(extra) + "."

        return f"═══ WHAT I KNOW ABOUT {config.USER_NAME.upper()} ═══\n{summary}"

    # ── Recall / Search ──────────────────────────────────────

    def recall_all(self) -> str:
        """Produce a full summary of everything JARVIS remembers."""
        parts = []

        # Personal facts
        pm = self._get_personal_mem()
        if pm:
            all_facts = pm.get_all()
            if all_facts:
                parts.append("Personal info I have on file:")
                labels = {
                    "name": "Name",
                    "nickname": "Nickname",
                    "age": "Age",
                    "city": "City",
                    "college": "College",
                    "job": "Workplace",
                    "birthday": "Birthday",
                    "hobby": "Hobbies",
                    "profession": "Profession",
                    "note": "Note",
                }
                for key, label in labels.items():
                    if key in all_facts:
                        parts.append(f"  • {label}: {all_facts[key]}")

        # JSON-saved facts
        json_facts = self._data.get("facts", [])
        if json_facts:
            parts.append("\nThings you asked me to remember:")
            for f in json_facts[-10:]:
                parts.append(f"  • {f['fact']}")

        # Preferences
        prefs = self._data.get("preferences", {})
        if prefs:
            parts.append("\nYour preferences I've noted:")
            for v in list(prefs.values())[-5:]:
                parts.append(f"  • {v['value']}")

        # Top topics
        top_topics = sorted(
            self._data.get("topics", {}).items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]
        if top_topics:
            parts.append("\nTopics you bring up most:")
            for t, c in top_topics:
                parts.append(f"  • {t} ({c}×)")

        # Stats
        stats = self.get_memory_stats()
        parts.append(
            f"\nTotal conversations saved: {stats['total']} "
            f"({stats['today']} today, across {stats['sessions']} sessions)"
        )

        return "\n".join(parts) if parts else "My memory is blank so far, sir."

    def search_history(self, query: str) -> str:
        """
        Search ALL past conversations for a keyword.
        Returns a formatted string of matching exchanges.
        """
        if not self.conv_db:
            return "Conversation database is not available, sir."

        results = self.conv_db.search(query, limit=5)
        if not results:
            return f"I couldn't find any past conversations about '{query}', sir."

        lines = [f"Found {len(results)} conversation(s) about '{query}':\n"]
        for r in reversed(results):  # oldest first
            try:
                dt = datetime.fromisoformat(r["timestamp"])
                time_str = dt.strftime("%b %d at %I:%M %p")
            except Exception:
                time_str = r.get("timestamp", "")[:16]
            lines.append(f"[{time_str}]")
            lines.append(f"  You: {r['user_input']}")
            if r.get("jarvis_reply"):
                reply = r["jarvis_reply"]
                if len(reply) > 120:
                    reply = reply[:120] + "…"
                lines.append(f"  JARVIS: {reply}")
            lines.append("")

        return "\n".join(lines).strip()

    def get_memory_stats(self) -> dict:
        """Return conversation statistics dict."""
        if self.conv_db:
            return self.conv_db.get_stats()
        return {
            "total": self._data.get("total_exchanges", 0),
            "today": 0,
            "facts": len(self._data.get("facts", [])),
            "sessions": self._data.get("session_count", 0),
        }

    def get_stats_spoken(self) -> str:
        """Human-readable memory statistics string."""
        s = self.get_memory_stats()
        pm = self._get_personal_mem()
        fact_count = len(pm.get_all()) if pm else s.get("facts", 0)
        return (
            f"I've had {s['total']} conversations with you "
            f"({s['today']} today, across {s.get('sessions', 1)} sessions). "
            f"I have {fact_count} personal facts about you on file, sir."
        )

    # ── Long-term JSON fact saving ────────────────────────────

    @staticmethod
    def _score_importance(fact: str) -> float:
        """Score a fact's importance (0.0–1.0)."""
        f = fact.lower()
        if any(
            w in f
            for w in [
                "name",
                "birthday",
                "born",
                "live",
                "age",
                "family",
                "married",
                "job",
                "work",
                "study",
                "phone",
            ]
        ):
            return 1.0
        if any(
            w in f
            for w in [
                "like",
                "love",
                "prefer",
                "favourite",
                "favorite",
                "enjoy",
                "hate",
                "dislike",
            ]
        ):
            return 0.7
        if any(
            w in f
            for w in [
                "meeting",
                "tomorrow",
                "today",
                "later",
                "soon",
                "appointment",
                "call",
            ]
        ):
            return 0.4
        return 0.5

    @staticmethod
    def _classify_cluster(fact: str) -> str:
        """Assign fact to a semantic cluster."""
        f = fact.lower()
        if any(
            w in f
            for w in [
                "name",
                "birthday",
                "born",
                "live",
                "age",
                "family",
                "married",
                "phone",
                "email",
            ]
        ):
            return "personal"
        if any(
            w in f
            for w in [
                "like",
                "love",
                "prefer",
                "favorite",
                "favourite",
                "enjoy",
                "hate",
                "dislike",
                "music",
                "food",
                "color",
                "colour",
                "game",
                "sport",
            ]
        ):
            return "preferences"
        if any(
            w in f
            for w in [
                "work",
                "job",
                "office",
                "project",
                "meeting",
                "deadline",
                "boss",
                "client",
                "company",
                "study",
                "college",
                "university",
            ]
        ):
            return "work"
        if any(
            w in f
            for w in [
                "tomorrow",
                "today",
                "later",
                "soon",
                "appointment",
                "call",
                "reminder",
                "schedule",
            ]
        ):
            return "temporary"
        return "general"

    def _save_fact(self, fact: str, temporary: bool = False) -> str:
        """Save a manually-triggered fact to JSON long-term memory."""
        # Detect conflict
        conflict = self._detect_conflict(fact)
        if conflict:
            reply = (
                f"Sir, I have conflicting info: I knew '{conflict['fact']}', "
                f"but you're telling me '{fact}'. "
                f"Should I update it? (Say 'yes update' or 'keep old')"
            )
            self._data["facts"].append(
                {
                    "fact": fact,
                    "learned_at": datetime.now().isoformat(),
                    "confidence": 0.6,
                    "importance": self._score_importance(fact),
                    "cluster": self._classify_cluster(fact),
                    "expires_at": None,
                    "conflict_with": conflict["fact"],
                }
            )
            self._save()
            return reply

        # Avoid exact duplicates
        for existing in self._data["facts"]:
            if fact.lower() in existing["fact"].lower():
                return f'I already have that noted, sir: "{existing["fact"]}"'

        # TTL for temporary facts
        expires_at = None
        cluster = self._classify_cluster(fact)
        if cluster == "temporary" or temporary:
            expires_at = datetime.fromtimestamp(time.time() + 86400).isoformat()

        self._data["facts"].append(
            {
                "fact": fact,
                "learned_at": datetime.now().isoformat(),
                "confidence": 1.0,
                "importance": self._score_importance(fact),
                "cluster": cluster,
                "expires_at": expires_at,
            }
        )
        self._save()

        # Also save to conv_db for searchability
        if self.conv_db:
            self.conv_db.save_fact("manual", fact[:50], fact)

        return f"Noted and saved, sir. I'll remember that {fact}."

    def _save_preference(self, preference: str):
        """Track a user preference quietly."""
        key = preference[:40]
        self._data["preferences"][key] = {
            "value": preference,
            "updated_at": datetime.now().isoformat(),
        }
        self._save()

    def _track_topic(self, text: str):
        """Count how often topics are mentioned."""
        keywords = re.findall(r"\b[a-z]{4,}\b", text.lower())
        stop = {
            "what",
            "that",
            "this",
            "with",
            "from",
            "have",
            "will",
            "your",
            "jarvis",
            "please",
            "tell",
            "about",
            "know",
            "does",
            "when",
            "where",
            "just",
            "then",
            "also",
            "here",
            "like",
            "okay",
        }
        for word in keywords:
            if word not in stop:
                self._data["topics"][word] = self._data["topics"].get(word, 0) + 1
        total = self._data.get("total_exchanges", 0)
        if total % 20 == 0:
            self._save()

    def save_correction(self, wrong: str, correct: str):
        """Record when the user corrects JARVIS."""
        self._data["corrections"].append(
            {
                "wrong": wrong,
                "correct": correct,
                "learned_at": datetime.now().isoformat(),
            }
        )
        self._save()

    # ── Session management ────────────────────────────────────

    def increment_session(self):
        """Increment session counter at startup."""
        self._data["session_count"] = self._data.get("session_count", 0) + 1
        self._save()

    # ── Conflict detection ────────────────────────────────────

    def _detect_conflict(self, new_fact: str) -> dict | None:
        """
        Check if new_fact contradicts an existing high-importance fact.
        Only flags personal/work cluster facts with confidence > 0.8.
        """
        new_lower = new_fact.lower()
        new_cluster = self._classify_cluster(new_fact)
        new_importance = self._score_importance(new_fact)

        if new_importance < 0.7:
            return None

        for existing in self._data.get("facts", []):
            if existing.get("cluster") != new_cluster:
                continue
            if existing.get("confidence", 0) < 0.8:
                continue
            # Simple overlap check: same cluster, high confidence, different content
            ex_lower = existing["fact"].lower()
            if ex_lower == new_lower:
                return None  # Exact duplicate — not a conflict
            # Check for same key being set to different value
            # (heuristic: first 15 chars overlap but overall different)
            if (
                len(ex_lower) > 10
                and ex_lower[:15] == new_lower[:15]
                and ex_lower != new_lower
            ):
                return existing
        return None

    def expire_old_facts(self):
        """Remove temporary facts that have passed their TTL."""
        now = datetime.now()
        remaining = []
        removed = 0
        for f in self._data.get("facts", []):
            if f.get("expires_at"):
                try:
                    exp = datetime.fromisoformat(f["expires_at"])
                    if exp < now:
                        removed += 1
                        continue
                except Exception:
                    pass
            remaining.append(f)
        if removed:
            self._data["facts"] = remaining
            self._save()

    def get_cluster(self, cluster: str) -> list:
        """Get all facts belonging to a specific cluster."""
        return [f for f in self._data.get("facts", []) if f.get("cluster") == cluster]

    def generate_memory_timeline(self, days: int = 7) -> str:
        """
        Generate a readable memory timeline from ConversationDatabase.
        Shows a summary of what was discussed each day.
        """
        if not self.conv_db:
            return "Timeline unavailable — conversation database not initialised."

        try:
            from datetime import timedelta

            lines = [f"Memory timeline — last {days} days:\n"]
            for i in range(days - 1, -1, -1):
                day = (datetime.now() - timedelta(days=i)).date()
                day_str = day.isoformat()
                count = self.conv_db._conn.execute(
                    "SELECT COUNT(*) as c FROM conversations WHERE DATE(timestamp)=?",
                    (day_str,),
                ).fetchone()["c"]
                if count:
                    label = (
                        "Today"
                        if i == 0
                        else "Yesterday"
                        if i == 1
                        else day.strftime("%A, %b %d")
                    )
                    lines.append(f"  {label}: {count} conversation(s)")
            return (
                "\n".join(lines)
                if len(lines) > 1
                else "No conversation history yet, sir."
            )
        except Exception as _e:
            return f"Timeline error: {_e}"
