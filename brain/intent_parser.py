"""
JARVIS — brain/intent_parser.py
Classifies user commands to route them to the right skill.
Uses ML model first (trained offline), falls back to keywords.

Features:
  - INTENTS expanded with synonyms
  - Adaptive per-intent confidence thresholds
  - Slot filling (extracts structured params)
  - Multi-intent detection for compound commands
  - User correction learning queue
"""

import pickle
from pathlib import Path

from utils.helpers import contains_any
from utils.logger import log

# ─── Load ML Model (once on startup) ────────────────────────
_ml_model = None
_model_path = Path(__file__).parent / "models" / "intent_classifier.pkl"

try:
    if _model_path.exists():
        with open(_model_path, "rb") as f:
            _ml_model = pickle.load(f)
        log.info(f"ML intent model loaded ({_model_path.stat().st_size // 1024} KB)")
except Exception as e:
    log.warning(f"ML model not loaded: {e}")


def predict_ml(text: str) -> tuple[str, float]:
    """Predict intent using the ML model. Returns (intent, confidence)."""
    if _ml_model is None:
        return "unknown", 0.0
    try:
        intent = _ml_model.predict([text])[0]
        confidence = _ml_model.predict_proba([text]).max()
        return intent, confidence
    except Exception:
        return "unknown", 0.0


# ─── Intent Categories (with synonyms) ───────────────────────
INTENTS = {
    "open_app": [
        "open",
        "launch",
        "start",
        "run",
        "execute",
        "fire up",
        "boot",
        "load",
        "bring up",
    ],
    "close_app": [
        "close",
        "kill",
        "exit",
        "quit",
        "shut",
        "terminate",
        "end",
        "force quit",
    ],
    "system_volume": [
        "volume",
        "louder",
        "quieter",
        "mute",
        "unmute",
        "sound",
        "turn up",
        "turn down",
        "increase volume",
        "decrease volume",
    ],
    "system_brightness": [
        "brightness",
        "brighter",
        "dimmer",
        "screen bright",
        "screen dim",
        "increase brightness",
        "decrease brightness",
    ],
    "screenshot": [
        "screenshot",
        "screen capture",
        "capture screen",
        "take a snap",
        "capture my screen",
        "snap my screen",
    ],
    "shutdown": [
        "shutdown",
        "shut down",
        "restart",
        "reboot",
        "sleep",
        "hibernate",
        "log off",
    ],
    "file_create": ["create file", "make file", "new file", "write file"],
    "file_open": ["open file", "read file", "show file"],
    "file_delete": ["delete file", "remove file", "trash file"],
    "weather": [
        "weather",
        "temperature",
        "rain",
        "sunny",
        "forecast",
        "humid",
        "outside temperature",
        "how hot",
        "how cold",
        "will it rain",
    ],
    "news": [
        "news",
        "headlines",
        "latest news",
        "what happened",
        "current events",
        "today's news",
        "breaking news",
    ],
    "youtube": ["play", "youtube", "video", "song", "music", "watch"],
    "shopping": [
        "amazon",
        "flipkart",
        "myntra",
        "buy",
        "purchase",
        "shop for",
        "compare price",
        "price comparison",
        "find on amazon",
        "find on flipkart",
        "search amazon",
        "search flipkart",
        "laptops under",
        "phones under",
        "search flights",
        "find flights",
        "book flight",
        "flight to",
        "find hotels",
        "search hotels",
        "hotel in",
        "hotels in",
        "makemytrip",
    ],
    "google_search": [
        "google",
        "search for",
        "search online",
        "look up",
        "find online",
        "find information",
        "search the web",
    ],
    "wikipedia": [
        "wikipedia",
        "what is",
        "who is",
        "tell me about",
        "explain",
        "define",
        "what does",
        "meaning of",
    ],
    "send_email": [
        "send email",
        "email to",
        "write email",
        "compose email",
        "draft email",
        "mail to",
    ],
    "read_email": ["read email", "check email", "my emails", "inbox"],
    "reminder": [
        "remind me",
        "set reminder",
        "set alarm",
        "alarm at",
        "reminder at",
        "alert me",
        "notify me",
        "upcoming reminders",
        "list reminders",
        "show reminders",
        "show my reminders",
        "my reminders",
        "what are my reminders",
        "pending reminders",
        "all reminders",
        "check reminders",
        "delete reminder",
        "cancel reminder",
        "snooze reminder",
    ],
    "timer": [
        "set timer",
        "timer for",
        "count down",
        "countdown",
        "start a timer",
    ],
    "whatsapp": [
        "whatsapp",
        "send message to",
        "text to",
        "message to",
        "text a message",
        "send a message",
        "send message",
        "sorry message to",
        "good morning to",
        "good night to",
        "heart emoji",
        "fire emoji",
        "emoji to",
        "summarize my chat",
        "summarise my chat",
        "whatsapp stats",
        "what did i send",
        "compose message",
        "translate and send",
    ],
    "vision_screen": [
        "what's on screen",
        "what is on my screen",
        "analyze screen",
        "look at my screen",
        "describe screen",
        "read my screen",
    ],
    "vision_image": [
        "what's in this image",
        "analyze image",
        "describe image",
        "what is this image",
        "look at this",
        # Camera / hand phrases (STT drops apostrophes — include both forms)
        "what is in my hand",
        "whats in my hand",
        "what's in my hand",
        "what am i holding",
        "what do i have",
        "what do i hold",
        "what is this",
        "whats this",
        "identify this",
        "what is that",
        "whats that",
        "recognize this",
        "scan this",
        "see this",
        "analyze this",
        "what am i showing",
        "tell me what this is",
        "look at this object",
        "check this out",
        "what do you think this is",
        "can you identify",
        "use camera",
        "take a look at this",
    ],
    "clipboard": ["copy", "paste", "clipboard", "what did i copy"],
    "time_date": [
        "what time",
        "current time",
        "what's the time",
        "what date",
        "today's date",
        "what day",
        "what year",
        "what time in",
        "time in",
        "time zone",
        "current time in",
        "what's the time in",
        "time right now in",
    ],
    "joke": ["tell me a joke", "joke", "funny", "make me laugh"],
    "reset": [
        "reset",
        "clear history",
        "forget everything",
        "start over",
        "new conversation",
    ],
    "stop": ["stop", "goodbye", "bye", "exit jarvis", "quit jarvis", "shut up"],
}

# ─── Adaptive confidence thresholds per intent ────────────────
INTENT_THRESHOLDS = {
    "open_app": 0.60,
    "close_app": 0.65,
    "shutdown": 0.80,  # very high — destructive!
    "file_delete": 0.75,  # destructive
    "send_email": 0.65,
    "whatsapp": 0.55,
    "weather": 0.50,
    "news": 0.50,
    "youtube": 0.45,
    "google_search": 0.45,
    "wikipedia": 0.45,
    "time_date": 0.60,
    "screenshot": 0.60,
    "system_volume": 0.55,
    "system_brightness": 0.55,
    "chat": 0.30,  # low bar — safest fallback
    "joke": 0.40,
    "reminder": 0.60,
    "timer": 0.60,
    "media": 0.50,
    "shopping": 0.55,
}

# ─── Multi-intent chain connectors ───────────────────────────
_CHAIN_CONNECTORS = [
    " and then ",
    " then ",
    " after that ",
    " also ",
    ", and ",
    " and ",
]


def parse_intent(text: str) -> tuple[str, str]:
    """
    Parse user input and determine intent.
    Priority: ML model (if confident) > specific keywords > generic keywords > chat
    """
    if not text:
        return "unknown", text

    text_lower = text.lower().strip()

    # ── STEP 1: ML Model prediction ──────────────────────────
    ml_intent, ml_conf = predict_ml(text)
    # Use adaptive per-intent threshold
    threshold = INTENT_THRESHOLDS.get(ml_intent, 0.50)
    if ml_conf >= threshold and ml_intent != "unknown":
        log.info(f"ML predicted: '{ml_intent}' ({ml_conf:.0%}, threshold={threshold})")

    # ── PRIORITY: WhatsApp Unread (BEFORE anything else) ─────────
    _wa_unread = ["check unread", "any unread", "unread", "any messages", "new messages", "what did i miss"]
    if any(w in text_lower for w in _wa_unread):
        log.info("Intent detected: 'check_unread' (priority)")
        return "check_unread", text

    # ── PRIORITY: Email / WhatsApp (BEFORE close_app eats contact names) ──
    # "send email to mom" — 'mom' would trigger close_app without this guard
    _email_prefixes = [
        "send email",
        "email to",
        "compose email",
        "draft email",
        "write email",
        "mail to",
    ]
    if any(text_lower.startswith(p) or p in text_lower for p in _email_prefixes):
        log.info("Intent detected: 'send_email' (priority)")
        return "send_email", text

    _wa_send_prefixes = [
        "whatsapp to",
        "send message to",
        "text to",
        "message to",
        "send whatsapp to",
        # Translate commands
        " in hindi",
        " in tamil",
        " in telugu",
        " in kannada",
        " in malayalam",
        " in french",
        " in spanish",
        " in arabic",
        " in japanese",
        " in english",
        # Emoji commands
        "emoji to",
        "send emoji",
        # Contact management
        "add contact",
        "save contact",
        "new contact",
        "list contacts",
        "my contacts",
        "show contacts",
    ]
    if any(p in text_lower for p in _wa_send_prefixes):
        log.info("Intent detected: 'whatsapp' (priority)")
        return "whatsapp", text

    # ── PRIORITY: Camera / Vision commands (BEFORE wikipedia/chat) ──
    # These short phrases get eaten by wikipedia "what is" — override here
    _cam_exact = {
        "what is this",
        "whats this",
        "what's this",
        "what is that",
        "whats that",
        "what's that",
        "what do you see",
        "what can you see",
        "what am i holding",
        "what is in my hand",
        "whats in my hand",
        "what's in my hand",
        "identify this",
        "recognize this",
        "scan this",
        "see this",
        "analyze this",
    }
    if text_lower in _cam_exact or any(
        t in text_lower
        for t in [
            "in my hand",
            "am i holding",
            "am i showing",
            "do i hold",
            "do i have in my hand",
        ]
    ):
        log.info("Intent detected: 'vision_image' (camera priority)")
        return "vision_image", text

    # Screen vision — must come before wikipedia eats "what is on my screen"
    if any(
        t in text_lower
        for t in ["on my screen", "on the screen", "on screen", "my screen"]
    ):
        log.info("Intent detected: 'vision_screen' (screen priority)")
        return "vision_screen", text

    # ── PRIORITY: Spotify / Media commands ───────────────────
    if "spotify" in text_lower:
        if "open" in text_lower:
            log.info("Intent detected: 'open_app' (spotify)")
            return "open_app", text
        else:
            log.info("Intent detected: 'media' (spotify)")
            return "media", text

    # General media: "play", "pause", "next song", "skip", "previous"
    media_words = [
        "pause",
        "resume",
        "next song",
        "skip song",
        "previous song",
        "previous track",
        "next track",
        "stop the music",
        "stop the song",
        "stop playing",
    ]
    if any(w in text_lower for w in media_words):
        log.info("Intent detected: 'media'")
        return "media", text

    # "play music" / "play some music" / "play [song]" -> media (Spotify)
    # But "play on youtube" / "play [X] on youtube" -> youtube
    if text_lower.startswith("play ") and "youtube" not in text_lower:
        log.info("Intent detected: 'media' (play command)")
        return "media", text

    # ── PRIORITY: Chrome with profile ───────────────────────
    if "chrome" in text_lower:
        if any(
            w in text_lower for w in ["close", "kill", "end", "quit", "exit", "stop"]
        ):
            log.info("Intent detected: 'close_app' (chrome)")
            return "close_app", text
        log.info("Intent detected: 'open_app' (chrome)")
        return "open_app", text

    # ── PRIORITY: WhatsApp messaging ──────────────────────────
    whatsapp_msg_keywords = [
        "message to",
        "text to",
        "text a message",
        "send message",
        "send a message",
        "whatsapp to",
        "whatsapp friend",
        "whatsapp mom",
        "whatsapp dad",
        "whatsapp sarvani",
        "sorry message to",
        "emoji to",
        "send emoji",
        "good morning to",
        "good night to",
        "summarize my chat",
        "summarise my chat",
        "what did i send",
        "whatsapp stats",
        "last seen",
        "add contact",
        "list contacts",
    ]
    if any(kw in text_lower for kw in whatsapp_msg_keywords):
        log.info("Intent detected: 'whatsapp'")
        return "whatsapp", text

    # "is NAME online" — contact status check
    import re as _re_ip

    if _re_ip.search(r"\bis\s+\w+\s+online\b", text_lower):
        log.info("Intent detected: 'whatsapp' (is X online)")
        return "whatsapp", text

    if "whatsapp" in text_lower and "open" in text_lower:
        log.info("Intent detected: 'open_app' (whatsapp)")
        return "open_app", text

    if "whatsapp" in text_lower:
        log.info("Intent detected: 'whatsapp'")
        return "whatsapp", text

    # ── PRIORITY: Search in current browser ───────────────────
    if text_lower.startswith("search"):
        try:
            import pygetwindow as gw

            active = gw.getActiveWindow()
            if active and any(
                b in active.title.lower()
                for b in ["chrome", "edge", "firefox", "brave"]
            ):
                log.info("Intent detected: 'browser_search' (active browser)")
                return "browser_search", text
        except Exception:
            pass

    # ── Fast keyword matching ──────────────────────────────
    for intent, keywords in INTENTS.items():
        if contains_any(text_lower, keywords):
            log.info(f"Intent detected: '{intent}'")
            return intent, text

    # ── ML Model fallback (if keywords missed it) ─────────────
    fallback_threshold = INTENT_THRESHOLDS.get(ml_intent, 0.35)
    if ml_conf >= max(0.35, fallback_threshold * 0.6) and ml_intent not in (
        "unknown",
        "chat",
    ):
        log.info(f"ML fallback: '{ml_intent}' ({ml_conf:.0%})")
        return ml_intent, text

    # ── Final fallback: send to Gemini AI ─────────────────────
    log.info("No intent matched - routing to Gemini chat")
    return "chat", text


def extract_app_name(text: str) -> str:
    """Extract application name from command like 'open chrome'."""
    text_lower = text.lower()
    triggers = [
        "fire up",
        "open",
        "launch",
        "start",
        "run",
        "execute",
        "close",
        "kill",
        "quit",
        "terminate",
    ]
    for trigger in sorted(triggers, key=len, reverse=True):
        if trigger in text_lower:
            parts = text_lower.split(trigger, 1)
            if len(parts) > 1:
                return parts[1].strip()
    return text


def extract_search_query(text: str) -> str:
    """
    Extract the meaningful search query from a command.
    Strips trigger/filler words from the whole string.

    Examples:
        'play arijit singh on youtube' → 'arijit singh'
        'search for python tutorials' → 'python tutorials'
        'google cricket score' → 'cricket score'
        'open youtube' → ''  (nothing left = ask user)
    """
    query = text.lower().strip()

    # Strip leading trigger words (order matters — longest first)
    _LEAD_TRIGGERS = [
        "search for", "search online for", "look up",
        "find online", "google search for", "google",
        "find", "search", "play", "watch", "open", "youtube",
    ]
    for trigger in sorted(_LEAD_TRIGGERS, key=len, reverse=True):
        if query.startswith(trigger):
            query = query[len(trigger):].strip()
            break

    # Strip trailing platform words
    _TRAIL_WORDS = [
        "on youtube", "on spotify", "on chrome", "in browser",
        "on google", "in chrome", "online", "youtube", "spotify",
    ]
    for trail in sorted(_TRAIL_WORDS, key=len, reverse=True):
        if query.endswith(trail):
            query = query[: -len(trail)].strip()

    # Strip ONLY fully vague words — not genre names like "lofi music", "rock music"
    _FULLY_VAGUE = {
        "some", "something", "any", "anything",
        "some music", "some songs", "random", "random music",
        "good music", "nice music", "music", "songs", "a song",
    }
    if query in _FULLY_VAGUE or not query:
        return ""

    return query



def extract_name_and_message(text: str) -> tuple[str, str]:
    """Extract (recipient, message) from 'send email to X saying Y'."""
    text_lower = text.lower()
    if " to " in text_lower and " saying " in text_lower:
        after_to = text_lower.split(" to ", 1)[1]
        name, _, message = after_to.partition(" saying ")
        return name.strip(), message.strip()
    elif " to " in text_lower:
        after_to = text_lower.split(" to ", 1)[1]
        return after_to.strip(), ""
    return "", text


# ─── Slot Filling ─────────────────────────────────────────────
def extract_slots(text: str, intent: str) -> dict:
    """
    Extract structured parameters from a command based on its intent.

    Returns dict like:
      {"intent": "send_email", "recipient": "Rahul", "body": "I'll be late"}
    """
    import re

    text_l = text.lower().strip()
    slots: dict = {"intent": intent, "raw": text}

    if intent in ("send_email", "whatsapp"):
        m = re.search(r"\bto\s+([\w\s]+?)\s+(?:saying|message|that|:)\s+(.+)", text_l)
        if m:
            slots["recipient"] = m.group(1).strip().title()
            slots["body"] = m.group(2).strip()
        else:
            m2 = re.search(r"\bto\s+([\w]+)", text_l)
            if m2:
                slots["recipient"] = m2.group(1).strip().title()
        m3 = re.search(r"\bsubject\b[:\s]+(.+?)(?:\bsaying\b|$)", text_l)
        if m3:
            slots["subject"] = m3.group(1).strip()

    elif intent in ("open_app", "close_app"):
        slots["app"] = extract_app_name(text)

    elif intent in ("youtube", "media"):
        slots["query"] = extract_search_query(text)
        if "spotify" in text_l:
            slots["platform"] = "spotify"
        elif "youtube" in text_l:
            slots["platform"] = "youtube"
        else:
            slots["platform"] = "spotify"

    elif intent == "reminder":
        m = re.search(r"(?:at|in)\s+([\d:apm\s]+?)(?:\s+to\s+(.+))?$", text_l)
        if m:
            slots["time"] = m.group(1).strip()
            slots["message"] = (m.group(2) or "").strip()

    elif intent == "timer":
        m = re.search(r"(\d+)\s*(second|minute|hour|min|sec|hr)", text_l)
        if m:
            slots["duration"] = m.group(1)
            slots["unit"] = m.group(2)

    elif intent in ("google_search", "wikipedia"):
        slots["query"] = extract_search_query(text)

    elif intent == "system_volume":
        m = re.search(r"(\d+)\s*(?:percent|%)?", text_l)
        if m:
            slots["level"] = int(m.group(1))
        elif any(w in text_l for w in ["up", "louder", "increase"]):
            slots["direction"] = "up"
        elif any(w in text_l for w in ["down", "quieter", "decrease"]):
            slots["direction"] = "down"
        elif "mute" in text_l:
            slots["direction"] = "mute"

    return slots


# ─── Multi-Intent Detection ───────────────────────────────────
def parse_multi_intent(text: str) -> list[tuple[str, str]]:
    """
    Detect multiple intents in a compound command.
    Example: "open chrome and search for laptops"
    Returns: [("open_app", "open chrome"), ("google_search", "search for laptops")]
    """
    text_l = text.lower().strip()
    parts = [text_l]
    for connector in _CHAIN_CONNECTORS:
        new_parts = []
        for part in parts:
            if connector in part:
                new_parts.extend(part.split(connector))
            else:
                new_parts.append(part)
        parts = new_parts

    parts = [p.strip() for p in parts if p.strip()]
    results = []
    for part in parts:
        intent, _ = parse_intent(part)
        if intent not in ("chat", "unknown"):
            results.append((intent, part))

    if len(results) <= 1:
        return [parse_intent(text)]

    log.info(f"Multi-intent detected: {[r[0] for r in results]}")
    return results


# ─── User Correction Learning ─────────────────────────────────
def save_intent_correction(text: str, wrong_intent: str, correct_intent: str):
    """
    User corrected an intent prediction.
    Saves to queue for next model retrain.
    Call when user says "No, I meant X" after a wrong action.
    """
    import json
    from datetime import datetime

    corrections_file = Path(__file__).parent.parent / "data" / "intent_corrections.json"
    corrections = []
    try:
        if corrections_file.exists():
            corrections = json.loads(corrections_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    corrections.append(
        {
            "text": text,
            "wrong": wrong_intent,
            "correct": correct_intent,
            "date": datetime.now().isoformat(),
        }
    )
    try:
        corrections_file.write_text(
            json.dumps(corrections, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info(f"Intent correction saved: '{wrong_intent}' -> '{correct_intent}'")
    except Exception as e:
        log.warning(f"Could not save intent correction: {e}")


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "open chrome",
        "what's the weather today",
        "play Bollywood songs on youtube",
        "send email to Rahul saying I'll be late",
        "take a screenshot",
        "tell me about black holes",
        "volume up",
        "what's on my screen",
        "tell me a joke",
        "open chrome and search for laptops",
        "remind me at 5pm to call mom",
    ]
    print("=" * 55)
    print("Single Intent + Slot Tests")
    print("=" * 55)
    for t in tests:
        intent, _ = parse_intent(t)
        slots = extract_slots(t, intent)
        print(f"  '{t}'")
        print(f"    intent={intent} | slots={slots}")

    print("\n" + "=" * 55)
    print("Multi-Intent Tests")
    print("=" * 55)
    for t in [
        "open chrome and search for laptops",
        "set a timer for 5 minutes then play music",
    ]:
        intents = parse_multi_intent(t)
        print(f"  '{t}' -> {intents}")
