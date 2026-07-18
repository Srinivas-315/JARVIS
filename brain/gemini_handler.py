"""
JARVIS — brain/gemini_handler.py
Handles all AI conversations using Google Gemini REST API directly.
Supports both old (AIzaSy) and new (AQ.) API key formats.

Features:
  - Response caching (1 hour, MD5-keyed)
  - Smart model router (coding/chat/creative → best model)
  - Auto-retry with exponential backoff (2s, 4s, 8s)
  - Context compression (after 20 messages, summarize oldest)
  - Personality switching (formal/casual/funny)
  - API cost tracker (daily token count, 80% quota warning)
  - Free API fallback (Groq, OpenRouter, HuggingFace, Google AI Studio - unlimited!)
  - Conversation auto-learning (learns from your patterns monthly)
  - Memory leak fix: trim BEFORE appending
"""

import hashlib
import os
import time
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

import config

# Conversation auto-learning (learns from patterns, retrains monthly)
from brain.conversation_learner import ConversationLearner

# Free APIs (Groq, HuggingFace, Google AI Studio - unlimited!)
from brain.free_api_handler import FreeAPIHandler

# Local LLM — offline AI brain (Ollama)
from brain.local_llm import LocalLLM

# Memory — load past conversations across sessions
from memory.chat_history import ChatHistory
from memory.user_prefs import UserPrefs
from utils.logger import log
from utils.safe_api import safe_json_extract

load_dotenv()

_OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()


# ─── Personality presets ─────────────────────────────────────
PERSONALITIES = {
    "formal": (
        "You are JARVIS — a highly professional, precise AI assistant. "
        "Speak formally, be concise, address the user as 'sir'. "
        "Never use slang or colloquialisms."
    ),
    "casual": (
        "You are JARVIS — a friendly, conversational AI buddy. "
        "Be warm, use casual language, feel free to be slightly humorous."
    ),
    "funny": (
        "You are JARVIS — a witty, sarcastic, but helpful AI. "
        "Add clever quips. Keep responses snappy. Be entertaining."
    ),
    "default": None,  # use config.JARVIS_SYSTEM_PROMPT
}

# ─── Model routing by task type ──────────────────────────────
MODEL_ROUTING = {
    "coding": "gemini-2.5-flash",  # slowest but smartest for code
    "creative": "gemini-2.0-flash",  # balanced for creative tasks
    "chat": "gemini-2.0-flash-lite",  # fastest for casual chat
    "default": "gemini-2.0-flash",  # standard
}

# OpenAI model routing (fallback)
OPENAI_MODEL_ROUTING = {
    "coding": "gpt-4o",  # Best for code & complex reasoning
    "default": "gpt-4o-mini",  # Fast & cheap for everything else
}

# ─── Response cache ──────────────────────────────────────────
_CACHE: dict[str, tuple[str, float]] = {}  # hash → (response, timestamp)
_CACHE_TTL = 3600  # 1 hour

# ─── API cost tracker ────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent / "data"
_USAGE_FILE = _DATA_DIR / "api_usage.json"
_DAILY_QUOTA = 1_500_000  # rough Gemini free tier token limit/day


def _load_usage() -> dict:
    try:
        if _USAGE_FILE.exists():
            import json

            return json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_usage(usage: dict):
    try:
        import json

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _USAGE_FILE.write_text(
            json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


class GeminiHandler:
    """
    Manages Gemini AI conversations using direct REST API.
    Auto-detects the correct auth method for your key type.
    """

    # Models to try (in order of preference)
    MODELS = [
        "gemini-2.0-flash",  # ← FAST! 2-3 sec response
        "gemini-2.0-flash-lite",  # Even faster fallback
        "gemini-2.5-flash",  # Slower (thinking model) - last resort
        "gemini-flash-latest",  # Alias fallback
    ]

    # API endpoints to try
    ENDPOINTS = [
        # New format (AQ. keys) — header-based auth, v1beta
        {
            "base": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            "use_header": True,
        },
        # Old format (AIzaSy keys) — query param, v1
        {
            "base": "https://generativelanguage.googleapis.com/v1/models/{model}:generateContent",
            "use_header": False,
        },
        # Old format v1beta
        {
            "base": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            "use_header": False,
        },
    ]

    def __init__(self):
        self._history = []
        self._working_model = None
        self._working_endpoint = None
        self._active_key = None
        self._keys = []
        self._personality = "default"
        self._usage = _load_usage()
        self._mem_sys = None  # Wired from main.py via set_memory_system()

        # Load persistent memory
        self._chat_history = ChatHistory()
        self._user_prefs = UserPrefs()
        self._load_past_memory()

        # Local LLM (Ollama) — try offline first!
        self._local_llm = LocalLLM()
        if self._local_llm.is_available:
            log.info(
                f"Local LLM ready: {self._local_llm.model_name} — no API needed! ✅"
            )

        # Free API Handler (Groq, HuggingFace, Google AI Studio - unlimited!)
        self._free_api = FreeAPIHandler()
        if self._free_api.is_available():
            available = self._free_api.get_available_apis()
            log.info(f"Free APIs available: {available} ✅")
        else:
            log.info("No free APIs configured (optional)")

        # Conversation Auto-Learner (learns patterns, retrains monthly)
        self._learner = ConversationLearner()
        total_convs = self._learner.db.get_total_conversations()
        log.info(f"Conversation learner initialized ({total_convs} past conversations)")

        self._init()

    # ── Personality ──────────────────────────────────────────
    def set_memory_system(self, mem_sys) -> None:
        """
        Wire a MemorySystem instance so every AI prompt automatically
        includes the user's personal facts (name, college, city, etc.).
        Called once from main.py after both objects are initialised.
        """
        self._mem_sys = mem_sys
        log.info(
            "✅ Memory system linked to GeminiHandler — context will be injected in every prompt."
        )

    def set_calendar(self, calendar_instance) -> None:
        self._calendar = calendar_instance

    def set_reminder(self, reminder_instance) -> None:
        self._reminder = reminder_instance

    def set_emotion_engine(self, emotion_engine) -> None:
        self._emotion_engine = emotion_engine

    def set_rag_engine(self, rag_engine) -> None:
        self._rag_engine = rag_engine

    def _build_unified_context(self) -> str:
        """
        Builds the unified context (Memory, Calendar, Reminders, Emotion, etc.)
        used by ProactiveAssistant and other modules.
        """
        context = []
        if getattr(self, '_mem_sys', None):
            try:
                facts = self._mem_sys.get_personal_facts_summary()
                if facts:
                    context.append(f"[MEMORY]\n{facts}")
            except Exception: pass
            
        if getattr(self, '_calendar', None):
            try:
                cal = self._calendar.get_today()
                if "Nothing scheduled" not in cal:
                    context.append(f"[CALENDAR]\n{cal}")
            except Exception: pass
            
        if getattr(self, '_reminder', None):
            try:
                rem = self._reminder.list_reminders()
                if "no upcoming reminders" not in rem:
                    context.append(f"[REMINDERS]\n{rem}")
            except Exception: pass
            
        if getattr(self, '_emotion_engine', None):
            try:
                emo = self._emotion_engine.get_state()
                context.append(f"[EMOTION STATE]\n{emo}")
            except Exception: pass
            
        return "\n\n".join(context)

    def set_personality(self, mode: str) -> str:
        """
        Switch JARVIS personality on the fly.
        mode: 'formal' | 'casual' | 'funny' | 'default'
        Returns confirmation string.
        """
        mode = mode.lower().strip()
        if mode not in PERSONALITIES:
            return f"Unknown personality '{mode}'. Options: {', '.join(PERSONALITIES.keys())}"
        self._personality = mode
        log.info(f"Personality switched to: {mode}")
        msgs = {
            "formal": "Understood, sir. Switching to formal communication protocol.",
            "casual": "Sure thing! I'll keep it chill from now on.",
            "funny": "Oh, so you want the fun version? Challenge accepted, sir. 😏",
            "default": "Reverting to standard JARVIS personality, sir.",
        }
        return msgs.get(mode, "Personality updated.")

    def _get_system_prompt(self) -> str:
        """
        Return the system prompt based on current personality.
        Injects personal facts from MemorySystem so the AI always
        knows who it's talking to — across ALL restarts.
        """
        custom = PERSONALITIES.get(self._personality)
        base = custom or config.JARVIS_SYSTEM_PROMPT

        # ── Inject user preferences from UserPrefs (SQLite) ───
        prefs = self._user_prefs.get_all()
        if prefs:
            pref_context = []
            if prefs.get("name"):
                pref_context.append(f"User's name: {prefs['name']}")
            if prefs.get("city"):
                pref_context.append(f"User's city: {prefs['city']}")
            if pref_context:
                base += "\n\nCurrent user context:\n" + "\n".join(
                    f"  - {p}" for p in pref_context
                )

        # ── Inject personal facts from MemorySystem ───────────
        # This is the KEY fix: every AI call now knows name, college,
        # city, job, birthday, hobbies — whatever the user has told JARVIS.
        if self._mem_sys is not None:
            try:
                facts_summary = self._mem_sys.get_personal_facts_summary()
                if facts_summary:
                    base += f"\n\n{facts_summary}"
            except Exception:
                pass

        # ── Inject Personal Assistant Schedule ───────────────
        try:
            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %I:%M %p (%A)")
            base += f"\n\n[SYSTEM TIME]\nCurrent Datetime: {current_time}\n"
            
            cal_today = ""
            if getattr(self, '_calendar', None) is not None:
                raw_cal = self._calendar.get_today()
                if "Nothing scheduled" not in raw_cal:
                    cal_lines = raw_cal.split('\n')
                    cal_today = '\n'.join(cal_lines[:6]) # Title + max 5 items
                    if len(cal_lines) > 6:
                        cal_today += '\n  • ... (and more)'

            reminders = ""
            if getattr(self, '_reminder', None) is not None:
                raw_rem = self._reminder.list_reminders()
                if "no upcoming reminders" not in raw_rem:
                    rem_lines = raw_rem.split('\n')
                    reminders = '\n'.join(rem_lines[:6]) # Title + max 5 items
                    if len(rem_lines) > 6:
                        reminders += '\n• ... (and more)'

            if cal_today or reminders:
                base += "\n=== PERSONAL ASSISTANT SCHEDULE ==="
                if cal_today:
                    base += f"\n[CALENDAR]\n{cal_today}"
                if reminders:
                    base += f"\n[REMINDERS]\n{reminders}"
                base += "\n"
        except Exception as e:
            from utils.logger import log
            log.error(f"Error building Personal Assistant Layer context: {e}")

        return base

    # ── Smart model router ───────────────────────────────────
    def _route_model(self, prompt: str) -> str:
        """Pick the best Gemini model based on query type."""
        p = prompt.lower()
        if any(
            w in p
            for w in [
                "code",
                "python",
                "javascript",
                "debug",
                "error",
                "function",
                "class",
                "sql",
                "algorithm",
                "script",
            ]
        ):
            task = "coding"
        elif any(
            w in p
            for w in [
                "write",
                "poem",
                "story",
                "creative",
                "design",
                "imagine",
                "compose",
                "lyrics",
            ]
        ):
            task = "creative"
        elif any(
            w in p
            for w in [
                "hello",
                "how are",
                "what do you think",
                "tell me",
                "explain",
                "chat",
                "talk",
            ]
        ):
            task = "chat"
        else:
            task = "default"

        preferred = MODEL_ROUTING.get(task, MODEL_ROUTING["default"])
        # Verify preferred model is in our available list
        if self._working_model and preferred == self._working_model:
            return preferred
        # Fall back to whatever is working
        return self._working_model or preferred

    def _should_use_local(self, prompt: str) -> bool:
        """
        Decide whether local LLM or Gemini is better for this query.
        Local LLM: conversational, simple facts, greetings, opinions
        Gemini: complex reasoning, latest info, technical depth, coding
        """
        p = prompt.lower()

        # Always use Gemini for these (need accuracy/recency)
        gemini_preferred = [
            "code",
            "python",
            "javascript",
            "debug",
            "error",
            "script",
            "algorithm",
            "sql",
            "function",
            "class",
            "syntax",
            "latest",
            "current",
            "today",
            "recent",
            "news",
            "price",
            "stock",
            "bitcoin",
            "weather",
            "translate",
            "translation",
        ]
        if any(w in p for w in gemini_preferred):
            return False  # Use Gemini

        # Local LLM is great for these
        local_preferred = [
            "hello",
            "hi",
            "hey",
            "how are",
            "how's it",
            "what do you think",
            "tell me about yourself",
            "joke",
            "funny",
            "laugh",
            "i feel",
            "i'm tired",
            "i'm stressed",
            "i'm bored",
            "what time",
            "what day",
            "remind me",
            "thank you",
            "thanks",
            "good job",
            "what can you do",
            "who are you",
        ]
        if any(w in p for w in local_preferred):
            return True  # Use local

        # Default: try local first (it's free and fast)
        return True

    # ── Response caching ─────────────────────────────────────
    def _cache_key(self, prompt: str) -> str:
        return hashlib.md5(prompt.encode()).hexdigest()

    def _get_cached(self, prompt: str) -> str | None:
        key = self._cache_key(prompt)
        if key in _CACHE:
            response, ts = _CACHE[key]
            if time.time() - ts < _CACHE_TTL:
                log.info("Cache hit! Returning cached response.")
                return response
            else:
                del _CACHE[key]  # expired
        return None

    def _set_cache(self, prompt: str, response: str):
        key = self._cache_key(prompt)
        _CACHE[key] = (response, time.time())
        # Keep cache small — max 100 entries
        if len(_CACHE) > 100:
            oldest = sorted(_CACHE.items(), key=lambda x: x[1][1])
            for k, _ in oldest[:20]:
                del _CACHE[k]

    # ── Fast intent routing (SmartRouter) ────────────────────
    def ask_quick(self, prompt: str, max_tokens: int = 200) -> str | None:
        """
        Ultra-fast Gemini call for intent routing.
        No history, no personality, no caching — just raw classification.
        Used by SmartRouter for ~100-200ms intent classification.
        """
        key = self._active_key
        if not key:
            return None
        try:
            # Use the fastest model
            model = "gemini-2.0-flash-lite"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.1,
                },
            }
            resp = requests.post(url, json=body, headers=headers, timeout=5)
            if resp.status_code == 200:
                parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[-1].get("text", "").strip()
            # Fallback to flash
            if resp.status_code in (404, 429):
                model = "gemini-2.0-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                resp = requests.post(url, json=body, headers=headers, timeout=5)
                if resp.status_code == 200:
                    parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[-1].get("text", "").strip()
        except Exception as e:
            log.debug(f"ask_quick failed: {e}")
        return None

    # ── API cost tracker ─────────────────────────────────────
    def _track_usage(self, prompt: str, response: str):
        today = str(date.today())
        tokens = _estimate_tokens(prompt) + _estimate_tokens(response)
        if today not in self._usage:
            self._usage[today] = {"tokens": 0, "calls": 0}
        self._usage[today]["tokens"] += tokens
        self._usage[today]["calls"] += 1
        # Warn at 80% quota
        used = self._usage[today]["tokens"]
        if used > _DAILY_QUOTA * 0.8:
            log.warning(
                f"⚠️  API usage at {used / _DAILY_QUOTA * 100:.0f}% of daily quota!"
            )
        _save_usage(self._usage)

    def _is_quality_response(self, reply: str, prompt: str) -> bool:
        """
        Score the quality of a local LLM response.
        Returns True if the response is good enough to use.
        False = fall through to Gemini for a better answer.
        """
        if not reply or len(reply.strip()) < 5:
            return False

        # Too short for a non-trivial question
        prompt_lower = prompt.lower()
        is_complex = any(
            w in prompt_lower
            for w in [
                "explain",
                "how does",
                "why",
                "what is",
                "tell me about",
                "describe",
                "difference between",
                "compare",
                "analyze",
            ]
        )
        if is_complex and len(reply) < 30:
            return False

        # Contains generic non-answers
        non_answers = [
            "i don't know",
            "i'm not sure",
            "i cannot",
            "i can't",
            "i don't have access",
            "i don't have information",
            "as an ai",
            "as a language model",
            "my training",
            "i don't have the ability",
        ]
        reply_lower = reply.lower()
        if any(phrase in reply_lower for phrase in non_answers):
            return False

        # Response length makes sense for question complexity
        word_count = len(reply.split())
        if word_count > 150 and not is_complex:
            return False  # Over-explained a simple question

        # Repetition check — same sentence appearing multiple times
        sentences = reply.split(". ")
        if len(sentences) > 2:
            normalized = [s.strip().lower() for s in sentences]
            if len(set(normalized)) < len(normalized) * 0.7:
                return False  # Too much repetition

        return True

    def get_daily_usage(self) -> str:
        """Return today's API usage as a human-readable string."""
        today = str(date.today())
        data = self._usage.get(today, {"tokens": 0, "calls": 0})
        pct = data["tokens"] / _DAILY_QUOTA * 100
        return (
            f"Today's API usage: {data['calls']} calls, "
            f"~{data['tokens']:,} tokens ({pct:.1f}% of daily quota)"
        )

    # ── Context compression ───────────────────────────────────
    def _compress_history_if_needed(self):
        """
        After 20 messages, summarize the oldest 10 to save tokens.
        Keeps last 10 in full detail.
        """
        if len(self._history) < 20:
            return
        to_compress = self._history[:10]
        recent = self._history[10:]

        summary_parts = []
        for h in to_compress:
            user_short = h["user"][:60]
            jarvis_short = h["jarvis"][:60]
            summary_parts.append(f"[{user_short} → {jarvis_short}]")

        compressed = {
            "user": "<<SUMMARY of older conversation>>",
            "jarvis": " | ".join(summary_parts),
        }
        self._history = [compressed] + recent
        log.info("Context compressed: 20 messages → 1 summary + 10 recent")

    # ── Memory ───────────────────────────────────────────────
    def _load_past_memory(self):
        """Load recent conversations from SQLite so JARVIS remembers across restarts."""
        try:
            past = self._chat_history.get_recent(limit=5)
            if past:
                for h in reversed(past):  # Oldest first
                    self._history.append(
                        {
                            "user": h.get("user_input", ""),
                            "jarvis": h.get("jarvis_reply", ""),
                        }
                    )
                log.info(f"Loaded {len(past)} past conversations from memory ✅")
        except Exception as e:
            log.warning(f"Could not load past memory: {e}")

    # ── Request builder ──────────────────────────────────────
    def _build_request_with_key(
        self, endpoint_cfg: dict, model: str, text: str, key: str
    ):
        """Build URL and headers using a specific API key."""
        base = endpoint_cfg["base"].format(model=model)
        if endpoint_cfg["use_header"]:
            url = base
            headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        else:
            url = f"{base}?key={key}"
            headers = {"Content-Type": "application/json"}
        body = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"maxOutputTokens": 500},
        }
        return url, headers, body

    def _build_request(self, endpoint_cfg: dict, model: str, text: str):
        """Build URL and headers using the active key."""
        key = self._active_key or (
            self._keys[0] if self._keys else getattr(config, "GEMINI_API_KEY", "")
        )
        return self._build_request_with_key(endpoint_cfg, model, text, key)

    def _init(self):
        """Try all API keys quietly — show ONE summary line, not 20 warnings."""
        raw_keys = [os.getenv("GEMINI_API_KEY", "").strip()]
        for i in range(2, 21):  # supports up to GEMINI_API_KEY_20
            k = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
            if k:
                raw_keys.append(k)
        self._keys = [k for k in raw_keys if k]

        if not self._keys:
            log.warning("No GEMINI_API_KEY set — running on local LLM only.")
            return

        log.info(f"🔑 Checking {len(self._keys)} API keys...")

        for key in self._keys:
            for endpoint in self.ENDPOINTS:
                for model in self.MODELS:
                    try:
                        url, headers, body = self._build_request_with_key(
                            endpoint, model, "Hi", key
                        )
                        resp = requests.post(
                            url, json=body, headers=headers, timeout=10
                        )
                        if resp.status_code == 200:
                            self._working_model = model
                            self._working_endpoint = endpoint
                            self._active_key = key
                            log.info(f"✅ Gemini ready: {model}")
                            return
                        elif resp.status_code == 429:
                            break  # quota hit — try next key silently
                    except Exception:
                        continue
                else:
                    continue
                break

        log.warning("⚠️  All Gemini keys at quota — local LLM mode active.")

    # ── Core ask with retry + caching ────────────────────────
    def ask(self, prompt: str, context: str = "") -> str:
        """Send a message and get a response. Tries: Local LLM → Cache → Gemini → Free APIs → OpenAI."""

        import time

        start_time = time.time()
        api_used = "unknown"

        # ── STEP 1: Try local LLM — pass full JARVIS personality ────
        if self._local_llm.is_available:
            system = self._get_system_prompt()
            history = self._build_history_context()
            rich_prompt = system
            if history:
                rich_prompt += f"\n\nConversation so far:\n{history}\n"
            rich_prompt += f"\nUser: {prompt}\nJARVIS:"
            local_reply = self._local_llm.ask(rich_prompt)
            if local_reply and self._is_quality_response(local_reply, prompt):
                # Good response from local LLM
                if len(self._history) >= 20:
                    self._history = self._history[-19:]
                self._history.append({"user": prompt, "jarvis": local_reply})
                # Save to chat history for memory
                try:
                    self._chat_history.save(user_input=prompt, jarvis_reply=local_reply)
                except Exception:
                    pass
                # Log to auto-learner (learns patterns for monthly retraining)
                try:
                    response_time = int((time.time() - start_time) * 1000)
                    self._learner.log_conversation(
                        prompt,
                        local_reply,
                        quality_score=0.95,
                        api_used="local_llm",
                        response_time_ms=response_time,
                    )
                except Exception:
                    pass
                return local_reply
            elif local_reply:
                log.info("Local LLM response quality insufficient, trying Gemini...")
            else:
                log.info("Local LLM returned empty, trying Gemini...")

        # ── STEP 2: Check cache ────────────────────────────────
        cached = self._get_cached(prompt)
        if cached:
            return cached

        # ── STEP 3 + 4: Gemini API (only if working model exists) ──
        answer = None
        if self._working_model:
            # Route to best model for this query
            model = self._route_model(prompt)
            system = self._get_system_prompt()

            # Inject user preferences for personalization
            prefs = self._user_prefs.get_all()
            if prefs:
                pref_lines = [f"  {k}: {v}" for k, v in prefs.items() if v]
                system += "\nUser preferences:\n" + "\n".join(pref_lines) + "\n"

            # Compress history if needed
            self._compress_history_if_needed()
            history = self._build_history_context()

            full_text = f"{system}\n\n"
            if history:
                full_text += f"Conversation so far:\n{history}\n\n"
            if context:
                full_text += f"Context: {context}\n\n"
            full_text += f"User: {prompt}\nJARVIS:"

            # ── STEP 4: Retry with exponential backoff ─────────────
            answer = self._ask_with_retry(full_text, model)

            if answer:
                self._set_cache(prompt, answer)
                self._track_usage(full_text, answer)
                if len(self._history) >= 20:
                    self._history = self._history[-19:]
                self._history.append({"user": prompt, "jarvis": answer})
                try:
                    self._chat_history.save(user_input=prompt, jarvis_reply=answer)
                except Exception:
                    pass
                api_used = "gemini"
                # Log to auto-learner
                try:
                    response_time = int((time.time() - start_time) * 1000)
                    self._learner.log_conversation(
                        prompt,
                        answer,
                        quality_score=0.9,
                        api_used=api_used,
                        response_time_ms=response_time,
                    )
                except Exception:
                    pass
                return answer
        else:
            log.info("Gemini quota exhausted, jumping to free APIs (Groq/OpenRouter)...")

        # ── STEP 5: Try Free APIs (Groq → HuggingFace → Google AI Studio) ───────
        log.info(
            "Gemini quota/failed, trying free APIs (Groq, HuggingFace, Google AI Studio)..."
        )
        if self._free_api.is_available():
            free_answer = self._free_api.ask(prompt, system)
            if free_answer:
                if len(self._history) >= 20:
                    self._history = self._history[-19:]
                self._history.append({"user": prompt, "jarvis": free_answer})
                try:
                    self._chat_history.save(user_input=prompt, jarvis_reply=free_answer)
                except Exception:
                    pass
                api_used = "free_api"
                # Log to auto-learner
                try:
                    response_time = int((time.time() - start_time) * 1000)
                    self._learner.log_conversation(
                        prompt,
                        free_answer,
                        quality_score=0.85,
                        api_used=api_used,
                        response_time_ms=response_time,
                    )
                except Exception:
                    pass
                log.info(f"✅ Response via {api_used}")
                return free_answer

        # ── STEP 6: ChatGPT fallback (when all else fails) ───────────
        openai_answer = self._ask_openai(prompt, context)
        if openai_answer:
            if len(self._history) >= 20:
                self._history = self._history[-19:]
            self._history.append({"user": prompt, "jarvis": openai_answer})
            try:
                self._chat_history.save(user_input=prompt, jarvis_reply=openai_answer)
            except Exception:
                pass
            api_used = "openai"
            # Log to auto-learner
            try:
                response_time = int((time.time() - start_time) * 1000)
                self._learner.log_conversation(
                    prompt,
                    openai_answer,
                    quality_score=0.95,
                    api_used=api_used,
                    response_time_ms=response_time,
                )
            except Exception:
                pass
            return openai_answer

        return (
            "I'm at my AI capacity right now, sir — all AI services are temporarily unavailable. "
            "I can still handle system commands, weather, news, reminders, and file management. "
            "Please try again in a moment."
        )

    def _ask_with_retry(self, full_text: str, model: str, max_retries: int = 3) -> str:
        """
        Send request to Gemini with exponential backoff retry.
        Delays: 2s → 4s → 8s
        """
        for attempt in range(max_retries):
            try:
                url, headers, _ = self._build_request(
                    self._working_endpoint, model, full_text
                )
                body = {
                    "contents": [{"parts": [{"text": full_text}]}],
                    "generationConfig": {
                        "temperature": config.TEMPERATURE,
                        "maxOutputTokens": config.MAX_TOKENS,
                    },
                }
                log.info(f"Asking Gemini (attempt {attempt + 1}/{max_retries})...")
                resp = requests.post(url, json=body, headers=headers, timeout=15)

                if resp.status_code == 200:
                    data = resp.json()
                    parts = safe_json_extract(
                        data, "candidates", 0, "content", "parts", default=[]
                    )
                    if not parts:
                        log.error("Gemini response missing parts field")
                        continue
                    answer = next(
                        (
                            p["text"]
                            for p in reversed(parts)
                            if "text" in p and not p.get("thought", False)
                        ),
                        parts[-1].get("text", "") if parts else "",
                    ).strip()
                    log.info("Gemini responded ✅")
                    return answer

                elif resp.status_code == 429:
                    log.warning("Rate limited (429). Not retrying.")
                    return "I've hit my daily API limit. I'll be back to full AI mode tomorrow!"

                else:
                    log.warning(
                        f"Gemini HTTP {resp.status_code} on attempt {attempt + 1}"
                    )

            except requests.Timeout:
                log.warning(f"Gemini timeout on attempt {attempt + 1}")
            except Exception as e:
                log.error(f"Gemini error on attempt {attempt + 1}: {e}")

            # Exponential backoff: 2, 4, 8 seconds
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                log.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        log.error("All Gemini retry attempts failed.")
        return ""

    # ── Streaming response (speak as sentences arrive) ────────
    def ask_streaming(self, prompt: str, context: str = "", on_sentence=None) -> str:
        """
        Stream Gemini response sentence-by-sentence.
        Calls on_sentence(sentence) for each complete sentence so JARVIS
        can speak it immediately while the rest is still generating.

        Falls back to normal ask() if streaming isn't available.
        Returns the full concatenated response.

        Args:
            prompt: User's message
            context: Optional RAG/vector context
            on_sentence: Callback(str) called for each sentence chunk
        """
        # If no Gemini key or no callback, fall back to normal ask
        if not self._working_model or not self._active_key or not on_sentence:
            return self.ask(prompt, context)

        # Build the full prompt (same as normal ask)
        system = self._get_system_prompt()
        prefs = self._user_prefs.get_all()
        if prefs:
            pref_lines = [f"  {k}: {v}" for k, v in prefs.items() if v]
            system += "\nUser preferences:\n" + "\n".join(pref_lines) + "\n"

        self._compress_history_if_needed()
        history = self._build_history_context()

        full_text = f"{system}\n\n"
        if history:
            full_text += f"Conversation so far:\n{history}\n\n"
        if context:
            full_text += f"Context: {context}\n\n"
        full_text += f"User: {prompt}\nJARVIS:"

        # Use Gemini streaming endpoint
        model = self._route_model(prompt)
        key = self._active_key

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
            headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
            body = {
                "contents": [{"parts": [{"text": full_text}]}],
                "generationConfig": {
                    "temperature": config.TEMPERATURE,
                    "maxOutputTokens": config.MAX_TOKENS,
                },
            }

            log.info(f"Streaming from Gemini ({model})...")
            resp = requests.post(url, json=body, headers=headers, timeout=30, stream=True)

            if resp.status_code != 200:
                log.warning(f"Streaming failed ({resp.status_code}), falling back to normal ask")
                return self.ask(prompt, context)

            import json as _json

            full_response = ""
            sentence_buffer = ""
            sentences_sent = 0

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]  # Remove "data: " prefix
                if data_str.strip() == "[DONE]":
                    break

                try:
                    chunk = _json.loads(data_str)
                    parts = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    for part in parts:
                        text_chunk = part.get("text", "")
                        if not text_chunk:
                            continue
                        full_response += text_chunk
                        sentence_buffer += text_chunk

                        # Check for complete sentences (., !, ?)
                        while True:
                            # Find the earliest sentence-ending punctuation
                            end_idx = -1
                            for punct in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
                                idx = sentence_buffer.find(punct)
                                if idx != -1 and (end_idx == -1 or idx < end_idx):
                                    end_idx = idx + len(punct)

                            if end_idx == -1:
                                break

                            sentence = sentence_buffer[:end_idx].strip()
                            sentence_buffer = sentence_buffer[end_idx:]

                            if sentence and len(sentence) > 3:
                                sentences_sent += 1
                                try:
                                    on_sentence(sentence)
                                except Exception:
                                    pass
                except Exception:
                    continue

            # Flush remaining buffer
            remaining = sentence_buffer.strip()
            if remaining and len(remaining) > 3:
                try:
                    on_sentence(remaining)
                except Exception:
                    pass

            log.info(f"Streaming complete: {sentences_sent + 1} sentences, {len(full_response)} chars")

            # Save to history & cache (same as normal ask)
            if full_response:
                self._set_cache(prompt, full_response)
                self._track_usage(full_text, full_response)
                if len(self._history) >= 20:
                    self._history = self._history[-19:]
                self._history.append({"user": prompt, "jarvis": full_response})
                try:
                    self._chat_history.save(user_input=prompt, jarvis_reply=full_response)
                except Exception:
                    pass

            return full_response

        except Exception as e:
            log.warning(f"Streaming error: {e}, falling back to normal ask")
            return self.ask(prompt, context)


    def ask_quick(self, prompt: str) -> str:
        """One-shot question without history."""
        if not self._working_model:
            # Try OpenAI directly for quick ask
            return self._ask_openai(prompt) or ""
        try:
            url, headers, body = self._build_request(
                self._working_endpoint, self._working_model, prompt
            )
            body["generationConfig"] = {"maxOutputTokens": 500}
            resp = requests.post(url, json=body, headers=headers, timeout=10)
            if resp.status_code == 200:
                parts = safe_json_extract(
                    resp.json(), "candidates", 0, "content", "parts", default=[]
                )
                if not parts:
                    log.error("Gemini quick response missing parts field")
                    return ""
                return next(
                    (
                        p["text"]
                        for p in reversed(parts)
                        if "text" in p and not p.get("thought", False)
                    ),
                    parts[-1].get("text", "") if parts else "",
                ).strip()
        except Exception as e:
            log.error(f"Quick ask error: {e}")
        return self._ask_openai(prompt) or ""

    def _ask_openai(self, prompt: str, context: str = "") -> str:
        """
        ChatGPT fallback — used when Gemini quota is hit or fails.
        Uses gpt-4o-mini (fast + cheap) for chat, gpt-4o for coding.
        """
        key = _OPENAI_KEY
        if not key or key == "PASTE_YOUR_SK_KEY_HERE" or not key.startswith("sk-"):
            return ""
        try:
            system = self._get_system_prompt()
            history = self._build_history_context()

            # Pick model based on task
            p_lower = prompt.lower()
            is_code = any(
                w in p_lower
                for w in [
                    "code",
                    "python",
                    "debug",
                    "function",
                    "sql",
                    "script",
                    "algorithm",
                    "error",
                    "class",
                ]
            )
            model = "gpt-4o" if is_code else "gpt-4o-mini"

            messages = [{"role": "system", "content": system}]
            if history:
                # Inject history as alternating user/assistant messages
                for h in self._history[-10:]:
                    messages.append({"role": "user", "content": h["user"]})
                    messages.append({"role": "assistant", "content": h["jarvis"]})
            if context:
                messages.append({"role": "user", "content": f"Context: {context}"})
            messages.append({"role": "user", "content": prompt})

            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": config.MAX_TOKENS,
                    "temperature": config.TEMPERATURE,
                },
                timeout=20,
            )
            if resp.status_code == 200:
                answer = (
                    resp.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                log.info(f"ChatGPT ({model}) responded ✅")
                return answer
            elif resp.status_code == 429:
                log.warning("OpenAI rate limited (429)")
            elif resp.status_code == 401:
                log.error("OpenAI: Invalid API key")
            else:
                log.warning(f"OpenAI HTTP {resp.status_code}")
        except Exception as e:
            log.error(f"OpenAI error: {e}")
        return ""

    def _build_history_context(self) -> str:
        """Build conversation history context, prioritizing recent and relevant turns."""
        if not self._history:
            return ""

        # Use last 8 turns (16 entries = 8 Q&A pairs)
        recent = self._history[-8:]

        lines = []
        for h in recent:
            user_text = h.get("user", "")[:200]  # Cap at 200 chars per turn
            jarvis_text = h.get("jarvis", "")[:200]
            if user_text and jarvis_text:
                lines.append(f"User: {user_text}")
                lines.append(f"JARVIS: {jarvis_text}")

        return "\n".join(lines)

    def reset_conversation(self):
        self._history = []
        log.info("Conversation reset.")

    def get_history(self) -> list:
        return self._history.copy()

    def export_conversations_for_training(self, output_path: str = None) -> str:
        """
        Export all saved conversations as training data for Ollama fine-tuning.
        Format: JSONL with {user, jarvis} pairs.
        """
        import json
        from pathlib import Path as _Path

        if not output_path:
            output_path = str(
                _Path(__file__).parent.parent / "data" / "gemini_training.jsonl"
            )

        try:
            recent = self._chat_history.get_recent(limit=200)
            if not recent:
                return "No conversations to export yet."

            saved = 0
            with open(output_path, "w", encoding="utf-8") as f:
                for h in recent:
                    user = h.get("user_input", "").strip()
                    jarvis = h.get("jarvis_reply", "").strip()
                    if user and jarvis and len(user) > 3 and len(jarvis) > 3:
                        entry = json.dumps(
                            {"user": user, "jarvis": jarvis}, ensure_ascii=False
                        )
                        f.write(entry + "\n")
                        saved += 1

            return f"Exported {saved} conversations to {output_path}, sir."
        except Exception as e:
            return f"Export failed: {str(e)[:60]}"

    def get_conversation_stats(self) -> str:
        """Get stats about JARVIS's conversation history."""
        try:
            total = self._chat_history.count()
            history_len = len(self._history)
            model = self._working_model or "none (local LLM only)"
            local_available = self._local_llm.is_available
            local_model = (
                self._local_llm.model_name if local_available else "not running"
            )

            return (
                f"Conversation stats:\n"
                f"  Total saved: {total} exchanges\n"
                f"  Current session: {history_len} turns\n"
                f"  Gemini model: {model}\n"
                f"  Local AI: {local_model}\n"
                f"  Training data: {self._local_llm.training_count} turns collected"
            )
        except Exception as e:
            return f"Stats unavailable: {str(e)[:60]}"

    def get_model(self) -> str:
        return self._working_model or "none"

    @property
    def is_at_quota(self) -> bool:
        """True when all Gemini keys are exhausted and local LLM is the only fallback."""
        return self._working_model is None and not self._local_llm.is_available

    @property
    def has_ai(self) -> bool:
        """True if any AI (Gemini or local LLM) is available."""
        return bool(self._working_model) or self._local_llm.is_available


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    g = GeminiHandler()
    print(f"\nWorking model: {g.get_model()}")
    print(g.get_daily_usage())
    if g.get_model() != "none":
        resp = g.ask("Introduce yourself as JARVIS in 2 sentences.")
        print(f"Response: {resp}")
    else:
        print("❌ No working model. Please check your API key.")
