"""
JARVIS — memory/personal_memory.py
Zero-LLM personal fact storage and recall.
Works purely with JSON — no AI needed.

Stores: name, age, city, college, nickname, birthday, job, etc.
Triggered: "my name is X", "I studied at X", "remember I work at X"
Recalled:  "what's my name", "how old am I", "where do I study"
"""

import json
import re
from pathlib import Path

from utils.logger import log

# ─── Storage file ─────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent / "data"
_FACTS_FILE = _DATA_DIR / "personal_facts.json"

# Trailing phrases that should be stripped before pattern matching
# e.g. "I studied in NIT Delhi remember it" → "I studied in NIT Delhi"
_STRIP_SUFFIXES = re.compile(
    r"\s+(?:"
    r"remember (?:it|this|that|please|ok)"
    r"|save (?:it|this|that)"
    r"|note (?:it|this|that)"
    r"|keep (?:it|this|that)"
    r"|please"
    r"|ok\??"
    r"|right\??"
    r"|got it"
    r"|okay"
    r")\s*[.!?]?\s*$",
    re.IGNORECASE,
)


class PersonalMemory:
    """
    Stores and recalls personal facts about the user.
    100% file-based. No LLM involved — never fails.
    """

    # ── Learn patterns ─────────────────────────────────────────
    # Each tuple: (regex pattern, fact_key, group_index_for_value)
    LEARN_PATTERNS = [
        # ── Name ──────────────────────────────────────────────
        (r"my name is (\w+)", "name", 1),
        (r"call me (\w+)", "nickname", 1),
        (r"i am (\w+)[,.]?\s+remember", "name", 1),
        (r"remember (?:that )?my name is (\w+)", "name", 1),
        (r"remember me as (\w+)", "name", 1),
        (r"i go by (\w+)", "nickname", 1),
        (r"everyone calls me (\w+)", "nickname", 1),
        (r"people call me (\w+)", "nickname", 1),
        # ── Age ───────────────────────────────────────────────
        (r"i am (\d+) years old", "age", 1),
        (r"i'm (\d+) years old", "age", 1),
        (r"my age is (\d+)", "age", 1),
        (r"i turned (\d+)", "age", 1),
        (r"i am (\d+)", "age", 1),
        # ── City / Location ───────────────────────────────────
        (r"i (?:live|stay|am|reside) in ([a-z ,]+?)(?:\.|,|$)", "city", 1),
        (r"i am from ([a-z ,]+?)(?:\.|,|$)", "city", 1),
        (r"my city is ([a-z ,]+?)(?:\.|,|$)", "city", 1),
        (r"i belong to ([a-z ,]+?)(?:\.|,|$)", "city", 1),
        (
            r"(?:currently )?(?:living|staying|residing) in ([a-z ,]+?)(?:\.|,|$)",
            "city",
            1,
        ),
        # ── College / University (PRESENT + PAST tense) ──────
        (r"i (?:study|go|attend) (?:at|to|in) ([a-z0-9 ,]+?)(?:\.|,|$)", "college", 1),
        (
            r"i am (?:a student|studying|enrolled) (?:at|in) ([a-z0-9 ,]+?)(?:\.|,|$)",
            "college",
            1,
        ),
        (
            r"i (?:studied|was studying|have studied|had studied|used to study|went) (?:at|to|in) ([a-z0-9 ,]+?)(?:\.|,|$)",
            "college",
            1,
        ),
        (
            r"my (?:college|university|school|institution|institute) is ([a-z0-9 ,]+?)(?:\.|,|$)",
            "college",
            1,
        ),
        (
            r"(?:college|university|institute|institution): ([a-z0-9 ,]+?)(?:\.|,|$)",
            "college",
            1,
        ),
        (
            r"i (?:do|did) my (?:degree|b\.?tech|m\.?tech|bca|mca|mba|bsc|msc|be|me) (?:from|at|in) ([a-z0-9 ,]+?)(?:\.|,|$)",
            "college",
            1,
        ),
        (
            r"i am from ([a-z0-9 ,]*(?:nit|iit|bits|vit|srm|anna|mit|engineering|technology|university|college|institute)[a-z0-9 ,]*?)(?:\.|,|$)",
            "college",
            1,
        ),
        # ── Job / Profession ──────────────────────────────────
        (
            r"i (?:work|am working|worked) (?:at|for|in) ([a-z0-9 ,]+?)(?:\.|,|$)",
            "job",
            1,
        ),
        (
            r"i am (?:employed|a (?:software|senior|junior|lead|full stack|backend|frontend|data)) (?:at|in|engineer|developer|scientist|analyst|designer)[a-z ,]*?(?:at|in|for) ([a-z0-9 ,]+?)(?:\.|,|$)",
            "job",
            1,
        ),
        (r"my (?:job|work|company|employer) is ([a-z0-9 ,]+?)(?:\.|,|$)", "job", 1),
        (r"i am a ([a-z ]+?) (?:at|by profession)", "profession", 1),
        (r"my profession is ([a-z ]+?)(?:\.|,|$)", "profession", 1),
        (
            r"i am a ([a-z ]+?) (?:engineer|developer|designer|analyst|scientist|manager)(?:\.|,|$)",
            "profession",
            1,
        ),
        # ── Birthday ──────────────────────────────────────────
        (r"my birthday is ([a-z0-9 ,]+?)(?:\.|$)", "birthday", 1),
        (r"i was born on ([a-z0-9 ,]+?)(?:\.|$)", "birthday", 1),
        (r"i was born in ([a-z0-9 ,]+?)(?:\.|$)", "birthday", 1),
        (r"my date of birth is ([a-z0-9 /\-]+?)(?:\.|$)", "birthday", 1),
        # ── Hobby / Interests ─────────────────────────────────
        (
            r"i (?:like|love|enjoy|am into|am passionate about) ([a-z ,]+?)(?:\.|,|$)",
            "hobby",
            1,
        ),
        (r"my hobby is ([a-z ,]+?)(?:\.|,|$)", "hobby", 1),
        (r"my hobbies are ([a-z ,]+?)(?:\.|,|$)", "hobby", 1),
        (r"i am interested in ([a-z ,]+?)(?:\.|,|$)", "hobby", 1),
        # ── Dynamic generic facts ─────────────────────────────
        (r"(?:remember that )?my ([a-z ]+?) is ([a-z0-9 ,]+?)(?:\.|,|$)", "__dynamic__", 0),
        # ── Generic: "remember that I ..." ───────────────────
        (r"remember that (.+?)(?:\.|$)", "notes", 1),
        (r"note that (.+?)(?:\.|$)", "notes", 1),
    ]

    # ── Recall patterns ────────────────────────────────────────
    # Each tuple: (trigger phrases list, fact_key, spoken_template)
    RECALL_PATTERNS = [
        (
            [
                "what's my name",
                "what is my name",
                "my name",
                "do you know my name",
                "what am i called",
            ],
            "name",
            "Your name is {value}, sir.",
        ),
        (
            [
                "what do they call me",
                "my nickname",
                "what's my nickname",
                "what is my nickname",
            ],
            "nickname",
            "You go by {value}, sir.",
        ),
        (
            ["how old am i", "what's my age", "what is my age", "my age"],
            "age",
            "You are {value} years old, sir.",
        ),
        (
            [
                "where do i live",
                "where am i from",
                "my city",
                "what city",
                "where i live",
                "my location",
                "where do i stay",
            ],
            "city",
            "You live in {value}, sir.",
        ),
        (
            [
                "where do i study",
                "my college",
                "what college",
                "where i study",
                "my university",
                "which college",
                "what university",
                "my institution",
                "where did i study",
                "which university",
                "what school",
                "can you remember where i study",
            ],
            "college",
            "You study at {value}, sir.",
        ),
        (
            [
                "where do i work",
                "my job",
                "what do i do",
                "my profession",
                "where i work",
                "my company",
                "my employer",
                "my workplace",
            ],
            "job",
            "You work at {value}, sir.",
        ),
        (
            [
                "my birthday",
                "when is my birthday",
                "when was i born",
                "my date of birth",
                "my dob",
            ],
            "birthday",
            "Your birthday is {value}, sir.",
        ),
        (
            [
                "what do i like",
                "my hobby",
                "what are my hobbies",
                "my interests",
                "what am i into",
            ],
            "hobby",
            "You enjoy {value}, sir.",
        ),
        (
            [
                "what do you know about me",
                "what do u know about me",
                "what do you remember",
                "what do u remember",
                "tell me about me",
                "what have you stored",
                "what have u stored",
                "what have you saved",
                "what have u saved",
                "what have you learned about me",
                "what have u learned about me",
            ],
            "__all__",
            "",
        ),
        (
            [
                "forget my name",
                "forget everything about me",
                "clear my info",
                "delete my info",
                "forget about me",
            ],
            "__clear__",
            "",
        ),
    ]

    def __init__(self):
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._facts: dict = self._load()

    # ── Public API ─────────────────────────────────────────────

    def try_learn(self, text: str) -> str:
        """
        Try to extract and save a personal fact from text.
        Returns spoken confirmation or "" if no fact found.
        """
        text_lower = text.lower().strip()

        # ── Strip trailing "remember it / save this / ok" phrases ─
        # e.g. "I studied in NIT Delhi remember it" → "I studied in NIT Delhi"
        text_lower = _STRIP_SUFFIXES.sub("", text_lower).strip()

        # Must contain a "teaching" keyword to avoid false positives
        learn_keywords = [
            "my name is",
            "my age",
            "i am",
            "i'm",
            "i live",
            "i stay",
            "i study",
            "i studied",
            "was studying",
            "used to study",
            "i went to",
            "i work",
            "i am from",
            "remember",
            "call me",
            "i go by",
            "my city",
            "my college",
            "my university",
            "my job",
            "my birthday",
            "my hobby",
            "i like",
            "i love",
            "i enjoy",
            "i turned",
            "everyone calls",
            "people call",
            "my profession",
            "i attend",
            "i enrolled",
            "my institution",
        ]
        if not any(kw in text_lower for kw in learn_keywords) and not bool(re.search(r"\bmy\s+[a-z ]+\s(?:is|are)\b", text_lower)):
            return ""

        # ── Known acronyms that must stay uppercase ────────────
        _ACRONYMS = {
            "nit", "iit", "bits", "vit", "srm", "mit", "nus", "ucla",
            "iim", "iisc", "nift", "nid", "aiims", "sastra", "srmist",
            "usa", "uk", "uae", "ai", "ml", "cs", "it", "cse", "ece",
            "eee", "mba", "btech", "mtech", "phd", "bca", "mca",
        }

        def _smart_title(s: str) -> str:
            """Title-case but keep known acronyms uppercase."""
            return " ".join(
                w.upper() if w.lower() in _ACRONYMS else w.capitalize()
                for w in s.split()
            )

        for pattern, key, grp in self.LEARN_PATTERNS:
            m = re.search(pattern, text_lower)
            if m:
                if key == "__dynamic__":
                    dyn_key = m.group(1).strip().replace(" ", "_")
                    value = m.group(2).strip().rstrip(".,!")
                    if not value or len(value) < 2 or len(dyn_key) < 2:
                        continue
                    key = dyn_key
                else:
                    value = m.group(grp).strip().rstrip(".,!")
                    if not value or len(value) < 2:
                        continue

                # Capitalise properly (preserve acronyms)
                value = _smart_title(value)

                if key == "notes":
                    if "notes" not in self._facts:
                        self._facts["notes"] = []
                    elif not isinstance(self._facts["notes"], list):
                        self._facts["notes"] = [self._facts["notes"]]
                    self._facts["notes"].append(value)
                    self._save()
                    log.info(f"PersonalMemory: saved note: {value}")
                    return f"Got it, sir. I'll remember that {value}."

                old = self._facts.get(key)
                self._facts[key] = value
                self._save()

                if old and str(old).lower() != value.lower():
                    log.info(f"PersonalMemory: updated {key}: {old} → {value}")
                    return (
                        f"Got it, sir. I've updated your {key.replace('_', ' ')} from {old} to {value}."
                    )
                else:
                    log.info(f"PersonalMemory: saved {key}={value}")
                    return f"Got it, sir. I'll remember that your {key.replace('_', ' ')} is {value}."

        return ""


    def try_recall(self, text: str) -> str:
        """
        Try to answer a personal recall question from stored facts.
        Returns spoken answer or "" if not a recall question.
        """
        text_lower = text.lower().strip()

        for triggers, key, template in self.RECALL_PATTERNS:
            if not any(t in text_lower for t in triggers):
                continue
            
            # TEACH OVERRIDE: If it looks like teaching ("my X is Y", "remember..."),
            # yield to try_learn. BUT "what is my name" is a QUESTION — don't block it.
            # Rule: block only when "my <key> is" OR "i am" pattern is present (teaching)
            _is_teaching = (
                ("remember" in text_lower and not text_lower.startswith(("what", "tell", "do", "how", "who", "when", "where")))
                or bool(re.search(r"\bmy\s+\w+\s+is\b", text_lower))
                or bool(re.search(r"\bi(?:'m| am)\s+\w", text_lower))
            )
            if _is_teaching:
                return ""

            if key == "__clear__":
                # Do NOT clear memory here — return sentinel to trigger confirmation flow.
                # Actual clearing happens in main.py after user confirms with 'yes confirm delete'.
                return "MEMORY_CLEAR_REQUESTED"

            if key == "__all__":
                return self._recall_all()

            value = self._facts.get(key)
            if value:
                return template.format(value=value)
            else:
                return (
                    f"I don't have your {key} on record yet, sir. "
                    f"Just tell me and I'll remember."
                )

        # ── Dynamic Recall Fallback ──
        m_dyn = re.search(r"(?:what|when|where|who) (?:is|are|was|were) my ([a-z ]+?)(?:\?|\.|$)", text_lower)
        if not m_dyn:
            m_dyn = re.search(r"(?:what's|when's|where's|who's) my ([a-z ]+?)(?:\?|\.|$)", text_lower)
            
        if m_dyn:
            dyn_key = m_dyn.group(1).strip().replace(" ", "_")
            if dyn_key in self._facts:
                val = self._facts[dyn_key]
                return f"Your {dyn_key.replace('_', ' ')} is {val}, sir."

        return ""

    def get(self, key: str, fallback: str = "") -> str:
        """Get a stored fact by key."""
        return self._facts.get(key, fallback)

    def set(self, key: str, value: str):
        """Manually set a fact."""
        self._facts[key] = value
        self._save()

    def get_all(self) -> dict:
        """Return all stored facts."""
        return dict(self._facts)

    def get_summary(self) -> str:
        """
        Return a compact summary of all known facts for LLM context injection.
        e.g. "User's name: Srini. College: NIT Delhi. City: Chennai."
        """
        if not self._facts:
            return ""
        labels = {
            "name": "Name",
            "nickname": "Nickname",
            "age": "Age",
            "city": "City",
            "college": "College/University",
            "job": "Workplace",
            "profession": "Profession",
            "birthday": "Birthday",
            "hobby": "Hobbies",
            "note": "Note",
        }
        parts = []
        for key, val in self._facts.items():
            if key in labels:
                parts.append(f"{labels[key]}: {val}")
            elif key == "notes":
                if isinstance(val, list):
                    for n in val:
                        parts.append(f"Note: {n}")
                else:
                    parts.append(f"Note: {val}")
            else:
                parts.append(f"{key.replace('_', ' ').title()}: {val}")
        return ". ".join(parts) + "." if parts else ""

    # ── Internal ───────────────────────────────────────────────

    def _recall_all(self) -> str:
        if not self._facts:
            return "I don't know anything about you yet, sir. Tell me something!"
        parts = []
        labels = {
            "name": "name",
            "nickname": "nickname",
            "age": "age",
            "city": "city",
            "college": "college",
            "job": "workplace",
            "birthday": "birthday",
            "hobby": "hobby",
            "profession": "profession",
            "note": "note",
        }
        for key, val in self._facts.items():
            if key in labels:
                parts.append(f"{labels[key]}: {val}")
            elif key == "notes":
                if isinstance(val, list):
                    for n in val:
                        parts.append(f"note: {n}")
                else:
                    parts.append(f"note: {val}")
            else:
                parts.append(f"{key.replace('_', ' ')}: {val}")
        if not parts:
            return "I don't know anything about you yet, sir."
        return "Here's what I know about you, sir. " + ". ".join(parts) + "."

    def _load(self) -> dict:
        try:
            if _FACTS_FILE.exists():
                with open(_FACTS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"PersonalMemory load error: {e}")
        return {}

    def _save(self):
        try:
            with open(_FACTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._facts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"PersonalMemory save error: {e}")

    def clear(self):
        """Clear all stored personal facts."""
        self._facts.clear()
        self._save()
        log.info("PersonalMemory cleared successfully ✅")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    pm = PersonalMemory()
    # Test past-tense college
    print(
        pm.try_learn(
            "I studied in National Institution of Technology Delhi remember it"
        )
    )
    print(pm.try_learn("I am 21 years old"))
    print(pm.try_learn("I live in Chennai"))
    print(pm.try_recall("where do I study"))
    print(pm.try_recall("how old am I"))
    print(pm.try_recall("where do I live"))
    print(pm.try_recall("what do you know about me"))
    print(pm.get_summary())
