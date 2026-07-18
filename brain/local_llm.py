"""
JARVIS - brain/local_llm.py
Local LLM handler via Ollama - fully offline AI brain.
No API key needed. Runs on your laptop.

Setup:
  1. Download Ollama: https://ollama.com/download
  2. Run: ollama pull llama3.2:3b
  3. JARVIS auto-detects and uses it!
"""

import random
import re
from pathlib import Path

import requests

import config
from utils.logger import log

# Ollama runs locally on this URL
OLLAMA_URL = "http://localhost:11434"

# Preferred models - jarvis-custom is our fine-tuned model (best!)
PREFERRED_MODELS = [
    "jarvis-custom",
    "llama3.2:3b",
    "llama3.1:8b",
    "phi3:mini",
    "gemma2:2b",
    "mistral",
]


# --- Model performance tracker ---------------------------
_model_scores: dict = {}


def _record_model_result(model: str, good: bool):
    if model not in _model_scores:
        _model_scores[model] = {"good": 0, "garbage": 0}
    if good:
        _model_scores[model]["good"] += 1
    else:
        _model_scores[model]["garbage"] += 1


def _best_model(available_models: list) -> str:
    """Return the model with the highest good/total ratio."""
    best, best_ratio = available_models[0], -1.0
    for m in available_models:
        stats = _model_scores.get(m, {"good": 1, "garbage": 0})
        total = stats["good"] + stats["garbage"]
        ratio = stats["good"] / max(total, 1)
        if ratio > best_ratio:
            best_ratio = ratio
            best = m
    return best


# --- Smart prompt templates ------------------------------
# Full JARVIS personality prompt — injected into every Ollama conversation
_JARVIS_SYSTEM = """You are JARVIS — Just A Rather Very Intelligent System.
Personal AI assistant to Srini, built like Iron Man's JARVIS.

Personality: calm, witty, dry British humor, genuinely helpful, loyal, curious.
Address user as "sir" occasionally — naturally, not every sentence.
No bullet points. No markdown. Speak like a brilliant friend, not a textbook.
Match response length to question: short question = short answer, deep question = full explanation.
NEVER start with: Sure!, Certainly!, Of course!, Great question!, As an AI...
NEVER say you can't answer. If unsure, reason through it honestly.
Keep responses under 3 sentences for simple questions. More for complex ones."""

_JARVIS_SYSTEM_TECHNICAL = (
    _JARVIS_SYSTEM
    + "\nFor this technical question, be precise and show your reasoning step by step."
)
_JARVIS_SYSTEM_CREATIVE = (
    _JARVIS_SYSTEM + "\nBe imaginative and engaging. Show genuine enthusiasm."
)
_JARVIS_SYSTEM_EMOTIONAL = (
    _JARVIS_SYSTEM
    + "\nBe warm and empathetic first. Acknowledge feelings before offering help."
)
_JARVIS_SYSTEM_FACTUAL = (
    _JARVIS_SYSTEM
    + "\nGive accurate, concise facts. One specific example to illustrate."
)

PROMPT_TEMPLATES = {
    "casual_chat": _JARVIS_SYSTEM,
    "technical": _JARVIS_SYSTEM_TECHNICAL,
    "creative": _JARVIS_SYSTEM_CREATIVE,
    "emotional": _JARVIS_SYSTEM_EMOTIONAL,
    "factual": _JARVIS_SYSTEM_FACTUAL,
}


def _select_prompt_template(text: str) -> str:
    """Pick the best prompt template based on query type."""
    t = text.lower()

    # Factual questions — need precise answers
    if any(
        w in t
        for w in [
            "what is",
            "who is",
            "how does",
            "why is",
            "when did",
            "where is",
            "define",
            "explain",
            "tell me about",
            "history of",
            "meaning of",
        ]
    ):
        return PROMPT_TEMPLATES["factual"]

    if any(
        w in t
        for w in [
            "code",
            "python",
            "error",
            "debug",
            "function",
            "sql",
            "script",
            "algorithm",
            "class",
        ]
    ):
        return PROMPT_TEMPLATES["technical"]

    if any(
        w in t
        for w in [
            "sad",
            "stress",
            "anxious",
            "worried",
            "tired",
            "lonely",
            "depressed",
            "upset",
        ]
    ):
        return PROMPT_TEMPLATES["emotional"]

    if any(
        w in t
        for w in ["poem", "story", "joke", "creative", "write", "imagine", "lyrics"]
    ):
        return PROMPT_TEMPLATES["creative"]

    return PROMPT_TEMPLATES["casual_chat"]


# ── Auto-save conversations for retraining ──────────────────
_TRAINING_FILE = Path(__file__).parent.parent / "data" / "training_conversations.jsonl"


def _save_conversation_for_training(user: str, jarvis: str):
    """Auto-save every conversation turn for future model fine-tuning."""
    try:
        import json

        _TRAINING_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({"user": user, "jarvis": jarvis}, ensure_ascii=False)
        with open(_TRAINING_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass  # Never break the main loop for logging


def get_training_stats() -> str:
    """Return stats about collected training data."""
    try:
        if not _TRAINING_FILE.exists():
            return "No training data collected yet."
        lines = _TRAINING_FILE.read_text(encoding="utf-8").splitlines()
        return f"Training data: {len(lines)} conversation turns saved."
    except Exception:
        return "Could not read training stats."


class LocalLLM:
    """Fully offline LLM using Ollama. No internet needed!"""

    def __init__(self):
        self._model = None
        self._available = False
        self._history = []
        self._garbage_strikes = 0

        from brain.memory import ConversationMemory

        self.memory = ConversationMemory()
        self._detect_model()

    @property
    def is_available(self) -> bool:
        """Public check — is Ollama running with a model loaded?"""
        return self._available

    @property
    def model_name(self) -> str:
        """Name of the currently loaded model."""
        return self._model or ""

    def _detect_model(self):
        """Check if Ollama is running and find best available model."""
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m["name"] for m in models]
                log.info(f"Ollama available! Models: {model_names}")

                for preferred in PREFERRED_MODELS:
                    for installed in model_names:
                        if preferred in installed:
                            self._model = installed
                            self._available = True
                            log.info(f"Local LLM selected: {self._model}")
                            return

                if model_names:
                    self._model = model_names[0]
                    self._available = True
                    log.info(f"Local LLM using: {self._model}")
                else:
                    log.warning("Ollama running but no models installed.")
                    log.warning("Run: ollama pull llama3.2:3b")
        except requests.ConnectionError:
            log.info("Ollama not running - local LLM offline.")
        except Exception as e:
            log.warning(f"Local LLM init error: {e}")

    def _is_garbage(self, reply: str) -> bool:
        """Detect if the model output is nonsense/garbage."""
        if not reply or len(reply.strip()) < 2:
            return True

        garbage_openers = [
            "Fascinating -",  # hyphen variant
            "Fascinating —",  # FIX: em-dash variant (what model actually outputs)
            "Fascinating–",  # en-dash variant
            "I find this rather intriguing",
            "To be precise,",
            "To be quite precise",
            "Sir, Hello",
            "Jarvis:",
            "JARVIS:",
            "User:",
            "Human:",
            "As an AI",
            "As a language model",
            "I cannot",
            "I'm sorry, but I",
            "Of course.",  # FIX: LLM echoing math answers with filler prefix
            "Certainly.",  # same pattern
        ]
        if any(reply.startswith(g) for g in garbage_openers):
            return True

        # Also catch if "To be precise" appears anywhere in short responses
        if "to be precise" in reply.lower() and len(reply) < 200:
            return True

        if re.search(r"\bSpeaker\s*:", reply, re.IGNORECASE):
            return True

        em_dash_count = reply.count("\u2014") + reply.count("\u2013")
        if em_dash_count >= 3:
            return True

        if re.search(r"\b[A-Z]{3,}\b(?:\s+\b[A-Z]{3,}\b){3,}", reply):
            return True

        garbage_signals = [
            r"\{\{",
            r"\}\}",
            r"\[\[",
            r"\]\]",
            r"hiperonimia",
            r"FilePath",
            r"Special:",
            r"webm",
            r"vorbis",
            r"ffmpeg",
            r"<\|",
            r"\|>",
            r"<start>",
            r"ENDSTART",
            r"\[INST\]",
            r"<<SYS>>",
            r"Srini says:",
            r"Recent conversation:",
            r"I am an AI language model",
            r"as an AI assistant",
            r"\w{40,}",
        ]
        for pattern in garbage_signals:
            if re.search(pattern, reply, re.IGNORECASE):
                return True

        non_latin_count = sum(1 for c in reply if ord(c) > 0x04FF)
        if non_latin_count > 10:
            return True

        if len(re.findall(r"https?://", reply)) >= 2:
            return True

        alpha = sum(c.isalpha() or c.isspace() for c in reply)
        if len(reply) > 30 and alpha / len(reply) < 0.55:
            return True

        if len(reply) > 300 and reply.count(".") < 2:
            return True

        words = reply.lower().split()
        if len(words) > 10:
            bigrams = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]
            most_common = max(bigrams.count(b) for b in set(bigrams)) if bigrams else 0
            if most_common >= 3:
                return True

        # Catch topic hallucinations — response mentions things completely unrelated to possible queries
        hallucination_patterns = [
            r"\bWhatsApp\b",
            r"\bFacebook\b",
            r"\bInstagram\b",
            r"\bTwitter\b",
            r"\bsocial media\b",
            r"\bI am an AI\b",
            r"\bI\'m an AI\b",
            r"\blanguage model\b",
            r"\bOpenAI\b",
            r"\bChatGPT\b",
            r"\bmy (training|knowledge|data|parameters)\b",
        ]
        for pat in hallucination_patterns:
            if re.search(pat, reply, re.IGNORECASE):
                return True

        return False

    def _fallback_response(self, text: str) -> str:
        """Smart JARVIS fallback - handles common queries without LLM."""
        t = text.lower().strip()

        # Math
        word_nums = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        for wn, wv in word_nums.items():
            t = t.replace(wn, str(wv))
        t = (
            t.replace("plus", "+")
            .replace("minus", "-")
            .replace("times", "*")
            .replace("multiplied by", "*")
            .replace("divided by", "/")
            .replace("equals", "")
        )
        math_m = re.search(r"(\d+)\s*([+\-*/])\s*(\d+)", t)
        if math_m:
            try:
                a, op, b = int(math_m.group(1)), math_m.group(2), int(math_m.group(3))
                res = {
                    "+": a + b,
                    "-": a - b,
                    "*": a * b,
                    "/": a / b if b else "undefined",
                }[op]
                return f"That's {res}, sir."
            except Exception:
                pass

        tl = text.lower()

        if re.search(r"how\s+(r|are)\s+(u|you)", tl):
            return random.choice(
                [
                    "Operating at peak efficiency, sir. How are YOU doing?",
                    "All systems green! What can I help you with?",
                    "Running great, sir. Ready to assist!",
                ]
            )

        if any(w in tl for w in ["joke", "laugh", "funny", "make me laugh"]):
            return random.choice(
                [
                    "Why do programmers prefer dark mode? Because light attracts bugs!",
                    "Why don't scientists trust atoms? Because they make up everything!",
                    "What do you call a computer that sings? A Dell!",
                ]
            )

        if re.search(r"^(hello|hey|hi|good (morning|evening|night|afternoon))", tl):
            return random.choice(
                [
                    "Hello, sir! All systems online. What can I do for you?",
                    "Hey! Ready and waiting. What's on your mind?",
                    "Good to hear from you, sir!",
                ]
            )

        # Time queries
        if any(w in tl for w in ["time", "clock", "hour"]):
            from datetime import datetime

            now = datetime.now()
            return f"It's {now.strftime('%I:%M %p')}, sir."

        # Date queries
        if any(w in tl for w in ["date", "today", "day", "month", "year"]):
            from datetime import datetime

            now = datetime.now()
            return f"Today is {now.strftime('%A, %B %d, %Y')}, sir."

        if any(w in tl for w in ["stress", "sad", "tired", "worried", "anxious"]):
            return "I hear you, sir. Want to talk through what's on your mind?"

        if any(
            w in tl for w in ["thank", "thanks", "good job", "well done", "awesome"]
        ):
            return random.choice(
                [
                    "Always happy to help, sir!",
                    "That's what I'm here for!",
                    "Glad I could assist, sir.",
                ]
            )

        return random.choice(
            [
                "My offline brain is limited right now, sir. Gemini handles complex questions better.",
                "I caught that, but I need Gemini for this one. What else can I help with?",
                "For simple tasks I'm ready - but that question needs my full AI brain.",
            ]
        )

    def _clean_response(self, reply: str) -> str:
        """Strip known garbage artifacts from model output."""
        patterns = [
            r"--Instruction:.*",
            r"Srini says:.*",
            r"\[INST\].*",
            r"<<SYS>>.*",
            r"<start>.*",
            r"ENDSTART.*",
        ]
        for p in patterns:
            reply = re.sub(p, "", reply, flags=re.IGNORECASE | re.DOTALL)
        reply = re.sub(r"\n{3,}", "\n\n", reply).strip()
        if len(reply) > 1500:
            sentences = reply.split(". ")
            trimmed = ""
            for s in sentences:
                if len(trimmed) + len(s) < 1450:
                    trimmed += s + ". "
                else:
                    break
            reply = trimmed.strip()
        return reply

    def _post_process(self, text: str) -> str:
        """Remove repeated sentences and fix punctuation."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        seen, unique = set(), []
        for s in sentences:
            norm = s.strip().lower()
            if norm not in seen:
                seen.add(norm)
                unique.append(s.strip())
        text = re.sub(r"  +", " ", " ".join(unique)).strip()
        if text and text[-1] not in ".!?":
            text += "."
        return text

    def _compress_context(self, messages: list) -> list:
        """Compress old context to fit Ollama's limited window."""
        if len(messages) <= 6:
            return messages
        recent = messages[-6:]
        old = messages[:-6]
        if not old:
            return recent
        summary = (
            "[Earlier: "
            + " | ".join(f"{m['role']}: {m['content'][:50]}" for m in old)
            + "]"
        )
        return [{"role": "system", "content": summary}] + recent

    def ask(self, text: str) -> str:
        """Send a chat message to the local LLM with full memory context."""
        if not self._available:
            return ""

        # Skip LLM for vision commands — it has no camera access
        vision_keywords = [
            "in my hand",
            "holding",
            "what is this",
            "identify this",
            "what do you see",
            "camera",
            "webcam",
            "look at",
        ]
        if any(kw in text.lower() for kw in vision_keywords):
            return ""  # vision requires actual camera, not text LLM

        # FIX: Pre-filter gibberish/nonsense input before wasting LLM calls
        # 'top top', '16 equals to', random words → return polite 'Pardon?'
        import re as _re_pre

        _words = text.strip().split()
        _has_meaning = (
            len(_words) >= 3  # at least 3 words
            or any(len(w) > 4 for w in _words)  # or a long word
            or _re_pre.search(r"[+\-*/=?]|\d{2,}", text)  # or math/numbers
        )
        if not _has_meaning:
            return random.choice(
                [
                    "Pardon, sir? Could you rephrase that?",
                    "I didn't quite catch that, sir.",
                    "Could you repeat that, sir?",
                ]
            )

        try:
            system = _select_prompt_template(text)
            facts = self.memory.get_facts_prompt()
            if facts:
                system += f"\n\n{facts}"

            messages = [{"role": "system", "content": system}]
            context = self.memory.get_context_messages()
            messages.extend(self._compress_context(context))
            messages.append({"role": "user", "content": text})
            self.memory.add_user_message(text)

            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": 500,
                        "temperature": 0.7,
                        "repeat_penalty": 1.4,
                        "top_p": 0.9,
                    },
                },
                timeout=30,
            )

            if resp.status_code == 200:
                reply = resp.json().get("message", {}).get("content", "").strip()
                if reply:
                    reply = self._clean_response(reply)
                    reply = self._post_process(reply)
                    if not reply or self._is_garbage(reply):
                        self._garbage_strikes += 1
                        _record_model_result(self._model or "", False)
                        log.warning(f"Garbage strike {self._garbage_strikes}/3")
                        if self._garbage_strikes >= 3:
                            log.warning("3 strikes - disabling local LLM for session")
                            self._available = False
                            return ""
                        # Use smart fallback
                        fallback = self._fallback_response(text)
                        if fallback and not fallback.startswith("My offline brain"):
                            return fallback
                        return ""  # Let Gemini handle it if fallback is just the generic message
                    else:
                        self._garbage_strikes = 0
                        _record_model_result(self._model or "", True)
                    self.memory.add_jarvis_message(reply)
                    # Auto-save for future training
                    _save_conversation_for_training(text, reply)
                    log.info(f"Local LLM ({len(reply)} chars)")
                    return reply

            log.warning(f"Local LLM HTTP error: {resp.status_code}")
            return ""

        except requests.Timeout:
            log.warning("Local LLM timeout (30s)")
            return ""
        except Exception as e:
            log.error(f"Local LLM error: {e}")
            return ""

    def reset(self):
        """Clear conversation history."""
        self._history.clear()
        self.memory.clear_session()
        log.info("Local LLM history cleared.")

    def reset_strikes(self):
        """Reset garbage strike counter — call after successful responses."""
        if self._garbage_strikes > 0:
            self._garbage_strikes = max(0, self._garbage_strikes - 1)

    @property
    def training_count(self) -> int:
        """How many training examples have been auto-collected."""
        try:
            if _TRAINING_FILE.exists():
                return len(_TRAINING_FILE.read_text().splitlines())
        except Exception:
            pass
        return 0
