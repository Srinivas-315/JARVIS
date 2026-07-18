"""
JARVIS — brain/smart_router.py
AI-Powered Intent Router — 3-tier classification system.

Priority:
  1. Instant commands (0ms)   — stop, mute, volume
  2. Offline DistilBERT (10ms) — local ML model, no internet
  3. Gemini API (100-200ms)    — entity extraction + complex cases
  4. Keyword fallback (0ms)    — old if/elif chain
"""

import json
import re
import time
from collections import OrderedDict

from brain.context_manager import ConversationContext
from brain.skill_registry import SKILL_REGISTRY, get_skill_descriptions_for_ai
from utils.logger import log

# Safety net: remap stale/old labels to current SKILL_REGISTRY keys
_LABEL_REMAP = {
    "google_search": "web_search",
    "browser_search": "web_search",
    "system_volume": "volume_control",
    "system_brightness": "brightness_control",
    "youtube": "youtube_search",
    "whatsapp": "send_whatsapp",
    "media": "play_music",
    "shutdown": "shutdown_system",
    "reminder": "set_reminder",
    "timer": "set_timer",
    "joke": "chat",
    "greeting": "chat",
    "wikipedia": "chat",
    "file_open": "file_operation",
    "file_create": "file_operation",
    "code_run": "write_code",
    "calendar": "calendar_event",
    "reset": "chat",
}

# ── Load offline ML model (if trained) ───────────────────────
try:
    from ml.intent_classifier import OfflineIntentClassifier
    _OFFLINE_MODEL = OfflineIntentClassifier(use_gpu=True)
except Exception as _e:
    log.info(f"Offline intent model not available: {_e}")
    _OFFLINE_MODEL = None

# Instant commands — skip AI for zero latency
INSTANT_COMMANDS = {
    "stop": {"action": "stop", "entities": {}},
    "cancel": {"action": "stop", "entities": {}},
    "shut up": {"action": "stop", "entities": {}},
    "be quiet": {"action": "stop", "entities": {}},
    "enough": {"action": "stop", "entities": {}},
    "silence": {"action": "stop", "entities": {}},
    "abort": {"action": "stop", "entities": {}},
    "halt": {"action": "stop", "entities": {}},
    "pause": {"action": "media_control", "entities": {"action": "pause"}},
    "resume": {"action": "media_control", "entities": {"action": "resume"}},
    "mute": {"action": "volume_control", "entities": {"direction": "mute"}},
    "unmute": {"action": "volume_control", "entities": {"direction": "unmute"}},
    "send": {"action": "send_typed", "entities": {}},
    "send it": {"action": "send_typed", "entities": {}},
    "enter": {"action": "send_typed", "entities": {}},
    "press enter": {"action": "send_typed", "entities": {}},
}

_VOL_UP = {"volume up", "louder", "turn up", "increase volume", "turn it up"}
_VOL_DOWN = {"volume down", "quieter", "turn down", "decrease volume", "turn it down"}


class SmartRouter:
    """AI-powered intent router using Gemini for classification."""

    def __init__(self, gemini_handler):
        self._gemini = gemini_handler
        self._offline = _OFFLINE_MODEL
        self._last_route_time = 0
        # Response cache — instant repeat commands
        self._cache = OrderedDict()
        self._cache_max = 100
        # Routing stats
        self._stats = {"instant": 0, "local_ml": 0, "cache": 0, "ai": 0, "keyword": 0}

    def _clean_message(self, text: str) -> str:
        """Sanitize incoming text from UI wrappers."""
        prefixes = ["⏳ Processing:", "📱 Telegram:"]
        for p in prefixes:
            if p in text:
                text = text.replace(p, "")
        
        text = text.strip()
        # Remove trailing ellipsis
        while text.endswith("..."):
            text = text[:-3].strip()
        while text.endswith(".."):
            text = text[:-2].strip()
            
        return text.strip()

    def route(self, text: str, context: ConversationContext, jarvis=None) -> dict:
        clean_text = self._clean_message(text)
        result = self._route_impl(clean_text, context, jarvis)
        print(f"ROUTER: {result}")
        return result

    def _route_impl(self, text: str, context: ConversationContext, jarvis=None) -> dict:
        """Classify user intent. Returns action + entities + confidence."""
        if not text or not text.strip():
            return {"action": "unknown", "entities": {}, "confidence": 0, "source": "empty"}

        text_lower = text.lower().strip()

        # STEP 1: Instant commands (zero latency)
        instant = self._check_instant(text_lower)
        if instant:
            self._stats["instant"] += 1
            log.info(f"SmartRouter: instant -> {instant['action']}")
            return instant

        # STEP 1.1.1: System Keyword Overrides (Calendar, Reminders, Tasks, Personality)
        system_override = self._detect_system_override(text_lower)
        if system_override:
            self._stats["keyword"] += 1
            log.info(f"SmartRouter: System Keyword Override -> {system_override['action']}")
            return system_override

        # STEP 1.2: WhatsApp Specific Keyword Overrides
        whatsapp_override = self._detect_whatsapp_override(text_lower)
        if whatsapp_override:
            self._stats["keyword"] += 1
            log.info(f"SmartRouter: WhatsApp Keyword Override -> {whatsapp_override['action']}")
            return whatsapp_override

        # STEP 1.3: Solve Problem Specific Keyword Overrides
        solve_override = self._detect_solve_override(text_lower)
        if solve_override:
            self._stats["keyword"] += 1
            log.info(f"SmartRouter: Solve Problem Keyword Override -> {solve_override['action']}")
            return solve_override

        # STEP 1.4: Knowledge Base / RAG Keyword Overrides
        kb_override = self._detect_knowledge_override(text_lower)
        if kb_override:
            self._stats["keyword"] += 1
            log.info(f"SmartRouter: Knowledge Base Override -> {kb_override['action']}")
            return kb_override

        # STEP 1.4.1: Email Keyword Overrides
        email_override = self._detect_email_override(text_lower)
        if email_override:
            self._stats["keyword"] += 1
            log.info(f"SmartRouter: Email Keyword Override -> {email_override['action']}")
            return email_override

        # STEP 1.5: Check response cache
        if text_lower in self._cache:
            cached = self._cache[text_lower].copy()
            cached["source"] = "cache"
            self._stats["cache"] += 1
            self._cache.move_to_end(text_lower)
            log.info(f"SmartRouter: CACHE -> {cached['action']} (0ms)")
            return cached

        # STEP 2: Resolve pronouns from context
        resolved = context.resolve_pronouns(text)
        if resolved != text:
            log.info(f"SmartRouter: resolved '{text}' -> '{resolved}'")
            text = resolved

        # STEP 3: Pending clarification
        if context.has_pending_clarification():
            return self._resolve_clarification(text, context)

        # STEP 4: LOCAL ML MODEL (offline, ~10ms, no API!)
        start = time.time()
        local_result = self._classify_offline(text)
        if local_result:
            self._last_route_time = (time.time() - start) * 1000
            conf = local_result["confidence"]

            # Penalize local ML confidence for questions if it predicts action-oriented intents
            # This prevents "Who founded whatsapp?" from being routed to open_app
            is_question = text_lower.startswith(("who ", "what ", "when ", "where ", "why ", "how ", "what's ", "whats ", "can you ", "could you ", "can u ", "could u ", "do you know "))
            if is_question and local_result["action"] in ("open_app", "send_whatsapp", "whatsapp_status"):
                conf = max(0.1, conf - 0.4)

            log.info(
                f"SmartRouter: LOCAL ML -> {local_result['action']} "
                f"({conf:.0%}) in {self._last_route_time:.0f}ms"
            )

            if conf >= 0.75:
                # High confidence — use local model, get entities via regex
                entities = self._extract_entities_fast(text, local_result["action"], jarvis=jarvis)
                
                # Validation: if regex failed to find mandatory entities, let Gemini try
                fallback_to_ai = False
                if local_result["action"] == "send_whatsapp" and not entities.get("contact"):
                    log.info("Local ML predicted send_whatsapp but regex failed to find contact. Falling back to Gemini.")
                    fallback_to_ai = True
                elif local_result["action"] == "open_app" and not entities.get("app_name"):
                    log.info("Local ML predicted open_app but regex failed to find app_name. Falling back to Gemini.")
                    fallback_to_ai = True
                    
                if not fallback_to_ai:
                    result = {
                        "action": local_result["action"],
                        "entities": entities,
                        "confidence": conf,
                        "source": "local_ml",
                    }
                    self._stats["local_ml"] += 1
                    self._cache_put(text_lower, result)
                    return result

        # STEP 5: Gemini API classification (for complex/ambiguous cases)
        start = time.time()
        result = self._classify_with_ai(text, context)
        self._last_route_time = (time.time() - start) * 1000

        if result and result.get("confidence", 0) >= 0.6:
            log.info(
                f"SmartRouter: GEMINI -> {result['action']} "
                f"({result.get('confidence',0):.0%}) in {self._last_route_time:.0f}ms"
            )
            result["source"] = "ai"
            self._stats["ai"] += 1
            self._cache_put(text_lower, result)
            return result

        # STEP 6: Keyword fallback
        log.info("SmartRouter: falling back to keywords")
        from brain.intent_parser import parse_intent, extract_slots
        intent, _ = parse_intent(text)
        slots = extract_slots(text, intent)
        result = {
            "action": intent,
            "entities": {k: v for k, v in slots.items() if k != "intent"},
            "confidence": 0.7,
            "source": "keyword_fallback",
        }
        self._stats["keyword"] += 1
        return result

    # ── Offline ML Classification ────────────────────────────────

    def _classify_offline(self, text: str) -> dict | None:
        """Classify using local DistilBERT model (~10ms, no internet)."""
        if not self._offline or not self._offline.is_ready:
            return None
        try:
            result = self._offline.classify(text, threshold=0.5)
            if result["intent"] != "unknown":
                # Apply label remap safety net
                action = _LABEL_REMAP.get(result["intent"], result["intent"])
                return {
                    "action": action,
                    "confidence": result["confidence"],
                    "latency_ms": result["latency_ms"],
                }
        except Exception as e:
            log.debug(f"Offline classifier error: {e}")
        return None

    def _extract_entities_fast(self, text: str, intent: str, jarvis=None) -> dict:
        """Quick entity extraction using regex (no API needed)."""
        entities = {}
        text_lower = text.lower().strip()

        if intent == "open_app" or intent == "close_app":
            # Extract app name — everything after open/close/launch/start/kill/quit
            for prefix in ["open ", "close ", "launch ", "start ", "kill ", "quit ",
                           "exit ", "run ", "fire up ", "bring up "]:
                if prefix in text_lower:
                    app = text_lower.split(prefix, 1)[-1].strip()
                    # Remove trailing pleasantries
                    for suffix in [" for me", " please", " now", " bro", " sir"]:
                        app = app.replace(suffix, "").strip()
                    if app:
                        entities["app_name"] = app
                    break

        elif intent == "play_music":
            for prefix in ["play ", "put on "]:
                if prefix in text_lower:
                    song = text_lower.split(prefix, 1)[-1].strip()
                    for suffix in [" on spotify", " on youtube", " please", " for me"]:
                        song = song.replace(suffix, "").strip()
                    if " by " in song:
                        parts = song.split(" by ", 1)
                        entities["song"] = parts[0].strip()
                        entities["artist"] = parts[1].strip()
                    else:
                        entities["song"] = song
                    break

        elif intent in ("web_search", "browser_search", "wikipedia", "youtube_search"):
            import re as _re
            m = _re.search(r"(?:search for|look up|what is|who is|who was|who founded|tell me about|explain)\s+(.*)", text_lower)
            if m:
                entities["query"] = m.group(1).strip()
            else:
                entities["query"] = text.strip()

        elif intent == "send_whatsapp":
            # Try to extract contact and message using improved regex
            import re as _re
            m_saying = _re.search(r"(?:send\s+(?:a\s+)?(?:message|text|whatsapp)\s+to|send\s+to|tell|message|whatsapp)\s+(.+?)\s+(?:saying|that)\s+(.+)", text_lower)
            if m_saying:
                entities["contact"] = m_saying.group(1).strip()
                entities["message"] = m_saying.group(2).strip()
            else:
                m_to = _re.search(r"(?:send|message|text|whatsapp|tell)\s+(.+?)\s+to\s+(.+)", text_lower)
                if m_to:
                    msg = m_to.group(1).strip()
                    contact = m_to.group(2).strip()
                    if msg not in ("a message", "message", "text", "a text", "messages", "whatsapp"):
                        entities["contact"] = contact
                        entities["message"] = msg
                    else:
                        entities["contact"] = contact
                        entities["message"] = ""

            # Fallback to the whatsapp skill's robust parser if contact is not extracted
            if not entities.get("contact") and jarvis and hasattr(jarvis, "whatsapp"):
                c, m = jarvis.whatsapp.parse_whatsapp_command(text)
                if c:
                    entities["contact"] = c
                    entities["message"] = m

        elif intent == "whatsapp_status":
            import re as _re
            for prefix in ["is ", "check status of ", "status of ", "when was ", "check "]:
                if prefix in text_lower:
                    contact = text_lower.split(prefix, 1)[-1].strip()
                    for suffix in [" online", " status", " last seen", " on whatsapp"]:
                        contact = contact.replace(suffix, "").strip()
                    entities["contact"] = contact
                    break
            if "contact" not in entities:
                m = _re.search(r"(\w+)\s+(?:online|last\s+seen|status)", text_lower)
                if m:
                    entities["contact"] = m.group(1).strip()

        elif intent == "whatsapp_schedule":
            import re as _re
            to_m = _re.search(r"to\s+(\w+)", text_lower)
            at_m = _re.search(r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text_lower)
            if to_m:
                entities["contact"] = to_m.group(1).strip()
            if at_m:
                entities["time"] = at_m.group(1).strip()
            msg_m = _re.search(r"to\s+\w+\s+(?:saying\s+)?(.+?)(?:\s+at\s+|$)", text_lower)
            if msg_m:
                entities["message"] = msg_m.group(1).strip()

        elif intent == "whatsapp_emoji":
            import re as _re
            m = _re.search(r"(?:send\s+(?:a\s+)?)?(.+?)\s+emoji\s+to\s+(\w+)", text_lower)
            if m:
                entities["emoji"] = m.group(1).strip()
                entities["contact"] = m.group(2).strip()
            else:
                m2 = _re.search(r"emoji\s+to\s+(\w+)", text_lower)
                if m2:
                    entities["contact"] = m2.group(1).strip()
                    entities["emoji"] = "heart"

        elif intent == "whatsapp_screenshot":
            for prefix in ["to ", "with "]:
                if prefix in text_lower:
                    entities["contact"] = text_lower.split(prefix, 1)[-1].replace("on whatsapp", "").strip()
                    break

        elif intent == "whatsapp_voice_note":
            import re as _re
            duration = 5
            dur_m = _re.search(r"(\d+)\s*seconds?", text_lower)
            if dur_m:
                duration = int(dur_m.group(1))
                cleaned_text = text_lower.replace(dur_m.group(0), "")
            else:
                cleaned_text = text_lower
                
            m = _re.search(r"(?:voice\s+note\s+to|voice\s+note\s+for|send\s+to|to|for)\s+(\w+)", cleaned_text)
            contact = m.group(1).strip() if m else ""
            if not contact:
                parts = cleaned_text.replace("send a voice note", "").replace("voice note", "").strip().split()
                if parts:
                    contact = parts[-1]
            entities["contact"] = contact
            entities["duration"] = duration

        elif intent == "whatsapp_group":
            import re as _re
            m = _re.search(r"group\s+(\w+)\s+(?:saying\s+)?(.+)", text_lower)
            if m:
                entities["group_name"] = m.group(1).strip()
                entities["message"] = m.group(2).strip()

        elif intent == "whatsapp_bulk":
            import re as _re
            m = _re.search(r"to\s+(.+?)\s+(?:saying\s+)?(.+)", text_lower)
            if m:
                entities["contacts"] = m.group(1).strip()
                entities["message"] = m.group(2).strip()

        elif intent == "whatsapp_translate":
            import re as _re
            to_lang = _re.search(r"to\s+(\w+)\s+and\s+send", text_lower)
            if to_lang:
                entities["language"] = to_lang.group(1).strip()
            to_contact = _re.search(r"send\s+to\s+(\w+)", text_lower)
            if to_contact:
                entities["contact"] = to_contact.group(1).strip()
            # extract message
            msg_m = _re.search(r"translate\s+(.+?)\s+to", text_lower)
            if msg_m:
                entities["message"] = msg_m.group(1).strip()

        elif intent == "web_search":
            for prefix in ["search for ", "search ", "google ", "look up ", "find "]:
                if prefix in text_lower:
                    entities["query"] = text_lower.split(prefix, 1)[-1].strip()
                    break

        elif intent == "youtube_search":
            for prefix in ["play ", "youtube ", "watch ", "search "]:
                if prefix in text_lower:
                    q = text_lower.split(prefix, 1)[-1].strip()
                    for suffix in [" on youtube", " video"]:
                        q = q.replace(suffix, "").strip()
                    entities["query"] = q
                    break

        elif intent == "weather":
            for prefix in ["weather in ", "weather at ", "temperature in "]:
                if prefix in text_lower:
                    entities["city"] = text_lower.split(prefix, 1)[-1].strip()
                    break

        elif intent == "set_reminder":
            for prefix in ["remind me to ", "reminder to ", "remind me about "]:
                if prefix in text_lower:
                    entities["message"] = text_lower.split(prefix, 1)[-1].strip()
                    break

        elif intent == "math_calculate":
            import re as _re
            nums = _re.findall(r"[\d.]+\s*[+\-*/x%]\s*[\d.]+", text_lower)
            if nums:
                entities["expression"] = nums[0]

        elif intent == "volume_control":
            import re as _re
            m = _re.search(r"(\d+)", text_lower)
            if m:
                entities["direction"] = "set"
                entities["level"] = int(m.group(1))
            elif any(w in text_lower for w in ["up", "louder", "increase", "raise"]):
                entities["direction"] = "up"
            elif any(w in text_lower for w in ["down", "quieter", "decrease", "lower"]):
                entities["direction"] = "down"

        elif intent == "brightness_control":
            if any(w in text_lower for w in ["up", "increase", "brighter", "more"]):
                entities["direction"] = "up"
            elif any(w in text_lower for w in ["down", "decrease", "dim", "less"]):
                entities["direction"] = "down"

        elif intent == "system_info":
            if "battery" in text_lower:
                entities["info_type"] = "battery"
            elif "cpu" in text_lower or "processor" in text_lower:
                entities["info_type"] = "cpu"
            elif "ram" in text_lower or "memory" in text_lower:
                entities["info_type"] = "ram"
            elif "network" in text_lower or "ip" in text_lower or "internet" in text_lower:
                entities["info_type"] = "network"
            else:
                entities["info_type"] = "health"

        elif intent == "media_control":
            if any(w in text_lower for w in ["pause", "stop"]):
                entities["action"] = "pause"
            elif any(w in text_lower for w in ["resume", "continue", "unpause", "play"]):
                entities["action"] = "resume"
            elif any(w in text_lower for w in ["next", "skip"]):
                entities["action"] = "next"
            elif any(w in text_lower for w in ["previous", "back", "last"]):
                entities["action"] = "previous"

        elif intent == "shutdown_system":
            if "restart" in text_lower or "reboot" in text_lower:
                entities["action"] = "restart"
            elif "sleep" in text_lower:
                entities["action"] = "sleep"
            else:
                entities["action"] = "shutdown"

        elif intent == "app_mode":
            for mode in ["work", "study", "movie", "gaming", "meeting", "focus", "relax"]:
                if mode in text_lower:
                    entities["mode"] = mode
                    break

        elif intent == "memory":
            import re as _re
            m = _re.search(r"my\s+(\w+)\s+is\s+(.+)", text_lower)
            if m:
                return {"fact_key": m.group(1).strip(), "fact_value": m.group(2).strip()}
            m2 = _re.search(r"remember\s+that\s+(.+)", text_lower)
            if m2:
                return {"fact": m2.group(1).strip()}
            return {"fact": text}

        elif intent == "solve_problem":
            entities = self._extract_solve_entities(text_lower)

        return entities

    def _check_instant(self, text_lower: str) -> dict | None:
        """Check for commands that must be instant."""
        if text_lower in INSTANT_COMMANDS:
            r = INSTANT_COMMANDS[text_lower].copy()
            r["confidence"] = 1.0
            r["source"] = "instant"
            return r
        if text_lower in _VOL_UP:
            return {"action": "volume_control", "entities": {"direction": "up"}, "confidence": 1.0, "source": "instant"}
        if text_lower in _VOL_DOWN:
            return {"action": "volume_control", "entities": {"direction": "down"}, "confidence": 1.0, "source": "instant"}
        vol_m = re.match(r"(?:set\s+)?volume\s+(?:to\s+)?(\d+)", text_lower)
        if vol_m:
            return {"action": "volume_control", "entities": {"direction": "set", "level": int(vol_m.group(1))}, "confidence": 1.0, "source": "instant"}

        # ── Cursor directional movement ──────────────────────────────
        _dir_pats = [
            (r"^move (?:mouse|cursor) (up|down|left|right)(?:\s+(\d+)(?:\s*(?:pixel|px|step)s?)?)?$", "direction"),
            (r"^(?:cursor|mouse) (up|down|left|right)(?:\s+(\d+)(?:\s*(?:pixel|px|step)s?)?)?$", "direction"),
        ]
        for pat, _ in _dir_pats:
            m = re.match(pat, text_lower)
            if m:
                direction = m.group(1)
                pixels = int(m.group(2)) if m.lastindex >= 2 and m.group(2) else 100
                return {"action": "move_cursor_direction", "entities": {"direction": direction, "pixels": pixels}, "confidence": 1.0, "source": "instant"}

        # ── Cursor to named element (OCR) ────────────────────────────
        # "move cursor to <element>", "go to <element>", "cursor to <element>",
        # "move mouse to <element>", "click on <element>"
        _elem_pats = [
            r"^move (?:cursor|mouse) to (?:the\s+)?(.+)$",
            r"^(?:cursor|mouse) to (?:the\s+)?(.+)$",
            r"^go to (?:the\s+)?(.+)$",
        ]
        for pat in _elem_pats:
            m = re.match(pat, text_lower)
            if m:
                elem = m.group(1).strip()
                # Skip navigation words that aren't element names
                if elem not in {"top", "bottom", "start", "end", "beginning"}:
                    return {"action": "move_cursor_to", "entities": {"element": elem}, "confidence": 1.0, "source": "instant"}

        # ── Click element by name ────────────────────────────────────
        _click_pats = [
            r"^click (?:on\s+)?(?:the\s+)?(.+)$",
            r"^press (?:the\s+)?(.+) button$",
        ]
        _skip_click = {"it", "here", "that", "this", "ok", "okay", "enter", "escape", "esc", "tab", "space", "backspace"}
        for pat in _click_pats:
            m = re.match(pat, text_lower)
            if m:
                elem = m.group(1).strip()
                if elem not in _skip_click and len(elem) > 1:
                    return {"action": "click_element", "entities": {"element": elem}, "confidence": 1.0, "source": "instant"}

        # ── Image Generation ──────────────────────────────────────────
        # IMPORTANT: Must NOT catch "generate a function/code/script" — those go to VS Code Writer.
        # Only trigger when visual/art words are present.
        _img_visual_words = {
            "image", "picture", "photo", "art", "artwork", "wallpaper",
            "illustration", "painting", "portrait", "drawing", "sketch",
            "render", "poster", "logo", "icon", "background", "scene",
        }
        _img_verbs = {"draw", "paint"}  # These always mean image even without a visual word
        _img_pats = [
            r"^(?:generate|create|make|draw|paint|design)\s+(?:an?\s+)?(?:image|picture|photo|art|artwork|wallpaper|illustration|painting|portrait|drawing|sketch|render|poster|logo|icon|background|scene)\s+(?:of\s+)?(.+)$",
            r"^(?:image|picture|photo|art)\s+of\s+(.+)$",
            r"^(?:draw|paint)\s+(?:me\s+)?(?:an?\s+)?(.+)$",
            r"^(?:generate|create|make)\s+(?:an?\s+)?(.+)\s+(?:image|picture|art|photo|artwork|wallpaper|illustration)$",
        ]
        for pat in _img_pats:
            m = re.match(pat, text_lower)
            if m:
                prompt = m.group(1).strip()
                # Block code-related prompts from leaking through
                _code_words = {"function", "code", "script", "program", "class", "method", "api", "bot", "app"}
                if prompt and len(prompt) > 2 and not any(cw in prompt.split() for cw in _code_words):
                    return {"action": "generate_image", "entities": {"prompt": prompt}, "confidence": 1.0, "source": "instant"}


        # ── Voice Switching — MUST run before ML model ────────────────
        # Catches: "switch to George", "change voice to Adam", "use Bella voice"
        # Without this, the ML model classifies these as open_app
        _VOICE_NAMES = {
            "george", "bella", "adam", "lewis", "michael", "nicole",
            "sarah", "sky", "emma", "isabella", "jarvis",
            "bm_george", "bm_lewis", "am_adam", "am_michael",
            "af_bella", "af_nicole", "af_sarah", "af_sky",
            "bf_emma", "bf_isabella",
            "edge_guy", "edge_jenny", "edge_ryan", "edge_aria",
            "edge_andrew", "edge_sonia", "edge guy", "edge jenny",
            "eleven_adam", "eleven_bella", "eleven_sarah", "eleven_george",
            "british", "female", "male", "american",
        }
        _VOICE_VERBS = [
            "change voice", "switch voice", "change your voice",
            "use voice", "set voice", "voice to",
            "change to", "switch to",
        ]
        _has_voice_name = any(v in text_lower for v in _VOICE_NAMES)
        _has_voice_verb = (
            "voice" in text_lower
            and any(v in text_lower for v in ["change", "switch", "use", "set", "make", "want"])
        ) or any(v in text_lower for v in _VOICE_VERBS)

        if _has_voice_name and _has_voice_verb:
            # Extract which voice name was mentioned
            found_voice = None
            # Sort by length desc so "bm_george" matches before "george"
            for alias in sorted(_VOICE_NAMES, key=len, reverse=True):
                if alias in text_lower:
                    found_voice = alias
                    break
            if found_voice:
                return {
                    "action": "change_voice",
                    "entities": {"voice_name": found_voice},
                    "confidence": 1.0,
                    "source": "instant",
                }

        return None

    def _detect_email_override(self, text_lower: str) -> dict | None:
        """Detect and route specific email commands with 100% accuracy using regex."""
        import re
        
        # 1. check unread emails
        if any(w in text_lower for w in ["check unread email", "check unread messages", "any unread email"]):
            return {"action": "email_check_unread", "entities": {"raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 2. search email for
        m = re.search(r"search email(?:s)? for (.+)", text_lower)
        if m:
            return {"action": "email_search", "entities": {"query": m.group(1).strip(), "raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 3. email stats
        if any(w in text_lower for w in ["email stats", "email statistics", "my email stats"]):
            return {"action": "email_stats", "entities": {"raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 4. undo email
        if any(w in text_lower for w in ["undo email", "undo last email", "unsend email"]):
            return {"action": "email_undo", "entities": {"raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 5. schedule email
        if "schedule email" in text_lower:
            m_to = re.search(r"to\s+(.+?)(?=\s+at|\s+saying|$)", text_lower)
            m_at = re.search(r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text_lower)
            m_saying = re.search(r"saying\s+(.+)", text_lower)
            
            recipient = m_to.group(1).strip() if m_to else ""
            time_str = m_at.group(1).strip() if m_at else ""
            body = m_saying.group(1).strip() if m_saying else ""
            return {"action": "email_schedule", "entities": {"recipient": recipient, "time": time_str, "body": body, "raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 6. reply to last email
        if "reply to last email" in text_lower or "reply to the last email" in text_lower:
            m_from = re.search(r"from\s+(\w+)", text_lower)
            sender = m_from.group(1).strip() if m_from else ""
            m_saying = re.search(r"saying\s+(.+)", text_lower)
            body = m_saying.group(1).strip() if m_saying else ""
            return {"action": "email_reply", "entities": {"sender": sender, "body": body, "raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 7. forward last email
        if "forward last email" in text_lower or "forward the last email" in text_lower:
            m_from = re.search(r"from\s+(\w+)", text_lower)
            sender = m_from.group(1).strip() if m_from else ""
            m_to = re.search(r"to\s+(\w+)", text_lower)
            recipient = m_to.group(1).strip() if m_to else ""
            m_saying = re.search(r"saying\s+(.+)", text_lower)
            body = m_saying.group(1).strip() if m_saying else ""
            return {"action": "email_forward", "entities": {"sender": sender, "recipient": recipient, "body": body, "raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 8. delete last email
        if any(w in text_lower for w in ["delete last email", "delete the last email"]):
            return {"action": "email_delete", "entities": {"raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 9. mark all read
        if any(w in text_lower for w in ["mark all email", "mark all as read", "mark emails as read"]):
            return {"action": "email_mark_read", "entities": {"raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 10. email brief
        if any(w in text_lower for w in ["email brief", "morning brief", "summarize my emails", "email summary"]):
            return {"action": "email_brief", "entities": {"raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        # 11. email compose ai (write an email)
        if "write an email" in text_lower or "compose an email" in text_lower:
            m_to = re.search(r"to\s+(.+?)(?=\s+about|\s+saying|$)", text_lower)
            m_about = re.search(r"(?:about|saying)\s+(.+)", text_lower)
            recipient = m_to.group(1).strip() if m_to else ""
            instruction = m_about.group(1).strip() if m_about else ""
            return {"action": "email_compose_ai", "entities": {"recipient": recipient, "instruction": instruction, "raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        return None

    def _detect_whatsapp_override(self, text_lower: str) -> dict | None:
        """Detect and route specific WhatsApp commands with 100% accuracy using regex."""
        import re

        # WhatsApp Drafts
        if "draft" in text_lower:
            if text_lower in ["show whatsapp drafts", "list whatsapp drafts"]:
                return {"action": "whatsapp_draft_list", "entities": {}, "confidence": 1.0, "source": "keyword_override"}
            if text_lower in ["clear whatsapp drafts", "clear drafts"]:
                return {"action": "whatsapp_draft_clear", "entities": {}, "confidence": 1.0, "source": "keyword_override"}
            
            _cmd_read_draft = re.match(r"read whatsapp draft (\d+)", text_lower)
            if _cmd_read_draft:
                return {"action": "whatsapp_draft_read", "entities": {"draft_id": int(_cmd_read_draft.group(1))}, "confidence": 1.0, "source": "keyword_override"}
            
            _cmd_send_draft = re.match(r"send whatsapp draft (\d+)", text_lower)
            if _cmd_send_draft:
                return {"action": "whatsapp_draft_send", "entities": {"draft_id": int(_cmd_send_draft.group(1))}, "confidence": 1.0, "source": "keyword_override"}
            
            _cmd_reject_draft = re.match(r"reject whatsapp draft (\d+)", text_lower)
            if _cmd_reject_draft:
                return {"action": "whatsapp_draft_reject", "entities": {"draft_id": int(_cmd_reject_draft.group(1))}, "confidence": 1.0, "source": "keyword_override"}

        # WhatsApp Monitor Status
        if text_lower in ["whatsapp monitor status", "whatsapp status monitor", "whatsapp listener status"]:
            return {"action": "whatsapp_monitor_status", "entities": {}, "confidence": 1.0, "source": "keyword_override"}
        if "whatsapp call monitor status" in text_lower:
            return {"action": "whatsapp_call_monitor_status", "entities": {}, "confidence": 1.0, "source": "keyword_override"}

        # Telegram Call Control Overrides
        if text_lower == "telegram status":
            return {"action": "telegram_status", "entities": {}, "confidence": 1.0, "source": "keyword_override"}

        if text_lower in ["call status", "whatsapp call status"]:
            return {"action": "whatsapp_call_status", "entities": {}, "confidence": 1.0, "source": "keyword_override"}

        if text_lower in ["lift", "accept call", "answer call", "answer"]:
            return {"action": "whatsapp_call_accept", "entities": {}, "confidence": 1.0, "source": "keyword_override"}

        if text_lower in ["decline", "reject call", "hang up", "reject"]:
            return {"action": "whatsapp_call_decline", "entities": {}, "confidence": 1.0, "source": "keyword_override"}


        # 1. whatsapp_undo
        if any(w in text_lower for w in ["undo my last", "delete the last message", "unsend message", "delete last message"]) and "whatsapp" in text_lower:
            return {"action": "whatsapp_undo", "entities": {}, "confidence": 1.0, "source": "keyword_override"}
        if text_lower in ["delete the last message", "undo last message", "delete last message"]:
            return {"action": "whatsapp_undo", "entities": {}, "confidence": 1.0, "source": "keyword_override"}

        # ── 2. WhatsApp UI Controls (MUST come BEFORE general emoji check!) ──
        # These catch "emoji panel", "sticker panel", "focus chat" etc.
        # BEFORE the general "emoji to <contact>" check can swallow them.

        # 2a. whatsapp_open_emoji_panel
        if any(w in text_lower for w in [
            "open emoji", "show emoji", "open emojis", "show emojis",
            "emoji panel", "emoji picker", "emoji keyboard",
            "emojis panel", "emojis picker",
        ]):
            return {
                "action": "whatsapp_open_emoji_panel",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 2b. whatsapp_open_sticker_panel
        if any(w in text_lower for w in [
            "open sticker", "show sticker", "open stickers", "show stickers",
            "sticker panel", "sticker picker", "sticker keyboard",
            "stickers panel", "stickers picker",
        ]):
            return {
                "action": "whatsapp_open_sticker_panel",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 2bb. whatsapp_send_sticker
        if any(s in text_lower for s in ["sticker", "stiker", "stricker", "striker"]) and any(w in text_lower for w in ["send", "to", "number", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "1", "2", "3", "4", "5", "6", "7", "8", "9"]):
            # Match index number/word
            idx_pattern = r"\b(?:number\s+)?(\d+|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\b"
            m_idx = re.search(idx_pattern, text_lower)
            if m_idx:
                idx_str = m_idx.group(1)
                # Check if there is a contact name after "to "
                contact = ""
                to_match = re.search(r"\bto\s+(\w+)", text_lower)
                if to_match:
                    contact = to_match.group(1).strip()
                # Check for "open sticker panel" or similar to avoid false match
                _panel_kws = [
                    "open sticker", "show sticker", "sticker panel", "sticker picker",
                    "open stricker", "show stricker", "stricker panel", "stricker picker",
                    "open striker", "show striker", "striker panel", "striker picker",
                    "open stiker", "show stiker", "stiker panel", "stiker picker"
                ]
                if not any(w in text_lower for w in _panel_kws):
                    return {
                        "action": "whatsapp_send_sticker",
                        "entities": {"contact": contact, "index": idx_str},
                        "confidence": 1.0,
                        "source": "keyword_override"
                    }

        # 2c. whatsapp_focus_chat_input
        if any(w in text_lower for w in [
            "focus chat", "focus input", "focus text box", "focus textbox",
            "move cursor to chat", "move cursor to input", "move cursor to text",
            "click chat box", "click input box", "click text box",
            "click on chat", "click on input", "click chatbox",
            "cursor to chat", "cursor to input", "cursor to text",
            "focus the chat", "focus the input",
        ]):
            return {
                "action": "whatsapp_focus_chat_input",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 3. whatsapp_emoji (send emoji TO someone)
        if "emoji to" in text_lower or re.search(r"\bemoji\b", text_lower):
            m = re.search(r"(?:send\s+(?:a\s+)?)?(.+?)\s+emoji\s+to\s+(\w+)", text_lower)
            if m:
                return {
                    "action": "whatsapp_emoji",
                    "entities": {"emoji": m.group(1).strip(), "contact": m.group(2).strip()},
                    "confidence": 1.0,
                    "source": "keyword_override"
                }
            else:
                m2 = re.search(r"emoji\s+to\s+(\w+)", text_lower)
                if m2:
                    return {
                        "action": "whatsapp_emoji",
                        "entities": {"emoji": "heart", "contact": m2.group(1).strip()},
                        "confidence": 1.0,
                        "source": "keyword_override"
                    }

        # 4. whatsapp_screenshot
        if "screenshot" in text_lower and any(w in text_lower for w in ["to ", "send ", "share ", "whatsapp "]):
            m = re.search(r"(?:screenshot|screen\s+capture)\s+(?:to|with|for)\s+(\w+)", text_lower)
            if not m:
                m = re.search(r"(?:send|share)\s+(?:a\s+)?(?:screenshot|screen\s+capture)\s+(?:to|with|for)\s+(\w+)", text_lower)
            if m:
                return {
                    "action": "whatsapp_screenshot",
                    "entities": {"contact": m.group(1).strip()},
                    "confidence": 1.0,
                    "source": "keyword_override"
                }

        # 5. whatsapp_voice_note
        if any(w in text_lower for w in ["voice note", "audio note", "voice message"]):
            duration = 5
            dur_m = re.search(r"(\d+)\s*seconds?", text_lower)
            if dur_m:
                duration = int(dur_m.group(1))
                cleaned = text_lower.replace(dur_m.group(0), "")
            else:
                cleaned = text_lower

            m = re.search(r"(?:voice\s+note\s+to|voice\s+note\s+for|send\s+to|to|for)\s+(\w+)", cleaned)
            contact = m.group(1).strip() if m else ""
            if not contact:
                parts = cleaned.replace("send a voice note", "").replace("voice note", "").strip().split()
                if parts:
                    contact = parts[-1]
            return {
                "action": "whatsapp_voice_note",
                "entities": {"contact": contact, "duration": duration},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 6. whatsapp_status
        if any(w in text_lower for w in ["online", "status of", "active", "last seen"]):
            m = re.search(r"(?:is|check|status|last\s+seen)\s+(?:of\s+)?(\w+)\s+(?:online|status|active|last\s+seen|on\s+whatsapp)", text_lower)
            if m:
                return {
                    "action": "whatsapp_status",
                    "entities": {"contact": m.group(1).strip()},
                    "confidence": 1.0,
                    "source": "keyword_override"
                }
            for w in ["online", "status", "active", "last seen"]:
                if w in text_lower:
                    parts = text_lower.replace(w, "").replace("is", "").replace("check", "").replace("of", "").replace("on", "").replace("whatsapp", "").strip().split()
                    if parts:
                        return {
                            "action": "whatsapp_status",
                            "entities": {"contact": parts[0]},
                            "confidence": 1.0,
                            "source": "keyword_override"
                        }

        # 7. whatsapp_schedule
        if "schedule" in text_lower and "whatsapp" in text_lower:
            to_m = re.search(r"to\s+(\w+)", text_lower)
            at_m = re.search(r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text_lower)
            msg_m = re.search(r"to\s+\w+\s+(?:saying\s+)?(.+?)(?:\s+at\s+|$)", text_lower)
            contact = to_m.group(1).strip() if to_m else ""
            time_str = at_m.group(1).strip() if at_m else ""
            message = msg_m.group(1).strip() if msg_m else ""
            return {
                "action": "whatsapp_schedule",
                "entities": {"contact": contact, "message": message, "time": time_str},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 8. send_whatsapp (improved entity extraction fallback)
        if text_lower.startswith(("send a message", "send message", "message to", "whatsapp to", "tell ")):
            m_saying = re.search(r"(?:send\s+(?:a\s+)?(?:message|text|whatsapp)\s+to|send\s+to|tell|message|whatsapp)\s+(.+?)\s+(?:saying|that)\s+(.+)", text_lower)
            if m_saying:
                return {
                    "action": "send_whatsapp",
                    "entities": {"contact": m_saying.group(1).strip(), "message": m_saying.group(2).strip()},
                    "confidence": 1.0,
                    "source": "keyword_override"
                }
            m_to = re.search(r"(?:send|message|text|whatsapp|tell)\s+(.+?)\s+to\s+(.+)", text_lower)
            if m_to:
                msg = m_to.group(1).strip()
                contact = m_to.group(2).strip()
                if msg not in ("a message", "message", "text", "a text", "messages", "whatsapp"):
                    return {
                        "action": "send_whatsapp",
                        "entities": {"contact": contact, "message": msg},
                        "confidence": 1.0,
                        "source": "keyword_override"
                    }
                else:
                    return {
                        "action": "send_whatsapp",
                        "entities": {"contact": contact, "message": ""},
                        "confidence": 1.0,
                        "source": "keyword_override"
                    }

        return None

    def _detect_solve_override(self, text_lower: str) -> dict | None:
        """Detect and route solve_problem commands with 100% accuracy using regex."""
        
        # 1. Paste Override
        if any(t in text_lower for t in ["paste it", "paste the solution", "paste solution", "paste the code", "paste code"]):
            return {
                "action": "paste_solution",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }
            
        # 2a. Explain from Screen Override
        explain_screen_triggers = [
            "explain the problem on my screen", 
            "explain the problem on the screen",
            "explain problem on screen",
            "explain the solution on my screen", 
            "explain the solution on the screen",
            "explain the code on my screen",
            "explain the code on the screen",
            "explain what's on my screen",
            "explain what's on the screen",
            "explain this screen",
            "explain screen"
        ]
        if any(t in text_lower for t in explain_screen_triggers):
            return {
                "action": "explain_from_screen",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 2b. Explain Override
        explain_triggers = [
            "explain", "explain it", "explain the approach", "explain the solution", 
            "explain this solution", "explain approach", "explain the code", 
            "explain this code", "explain the last solution", "explain your previous solution",
            "how does your previous solution work", "walk me through the solution",
            "how does the solution work", "explain the code you generated earlier"
        ]
        if any(t in text_lower for t in explain_triggers):
            return {
                "action": "explain_solution",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }
            
        # 2c. Explain Last Problem Override
        if any(t in text_lower for t in ["explain the last problem", "what was the last problem", "explain the problem", "explain previous problem"]):
            return {
                "action": "explain_last_problem",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }
            
        # 2d. Show Last Solution Override
        show_solution_triggers = [
            "show the last solution", "show last solution", "show solution", 
            "what was the solution", "show the code", "show me the last solution",
            "show your previous solution", "show me the code", "display the solution",
            "show the last code", "show me the last code", "what did you write",
            "show me your solution"
        ]
        if any(t in text_lower for t in show_solution_triggers):
            return {
                "action": "show_last_solution",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }
            
        # 2e. Get Complexity Override
        if any(t in text_lower for t in ["what was the complexity", "what is the complexity", "show complexity", "time complexity", "space complexity", "what's the complexity"]):
            return {
                "action": "get_complexity",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 3. Optimize Override
        if text_lower in ("optimize", "optimize it") or any(t in text_lower for t in ["optimize this", "optimize the code", "make this code better", "improve this code"]):
            return {
                "action": "optimize_code",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 4. Debug Override
        if text_lower in ("debug", "debug it", "fix it") or any(t in text_lower for t in ["debug this", "debug the code", "fix this code", "find the bug"]):
            return {
                "action": "debug_code",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override"
            }

        # 5. Solve Problem Override
        solve_triggers = [
            "solve this", "solve the problem", "solve this problem", "solve leetcode",
            "solve this question", "solve the question", "solve this code",
            "solve "
        ]
        
        is_solve = any(t in text_lower for t in solve_triggers) or text_lower.startswith("solve")
        
        # Exclude conversational patterns
        if is_solve:
            conversational_excludes = [
                "how to solve", "how do you solve", "help me solve"
            ]
            if any(exc in text_lower for exc in conversational_excludes):
                return None
                
            entities = self._extract_solve_entities(text_lower)
            return {
                "action": "solve_problem",
                "entities": entities,
                "confidence": 1.0,
                "source": "keyword_override"
            }
            
        return None

    def _detect_knowledge_override(self, text_lower: str) -> dict | None:
        """Detect and route Knowledge Base / RAG commands with keyword matching.

        Ensures commands like 'learn this file', 'search my documents',
        'how many documents do you know' work offline without Gemini.
        """
        import re

        # ── 1. knowledge_ingest: learn/ingest a file or folder ──
        if any(kw in text_lower for kw in [
            "learn this file", "learn file", "ingest file", "add file",
            "read file", "memorize file", "memorize this file",
            "learn folder", "learn my ", "ingest folder",
            "learn directory", "scan folder", "learn the ",
            "read folder", "scan my ",
        ]):
            raw = text_lower
            # Try to extract path after trigger
            path_match = re.search(
                r'(?:learn|ingest|add|read|memorize|scan)\s+'
                r'(?:this\s+)?(?:file|folder|my\s+\w+\s+folder|directory)\s*(.+)?',
                text_lower
            )
            raw_path = path_match.group(1).strip() if path_match and path_match.group(1) else ""
            return {
                "action": "knowledge_ingest",
                "entities": {"raw": raw, "file_path": raw_path, "folder_path": raw_path},
                "confidence": 1.0,
                "source": "keyword_override",
            }

        # ── 2. knowledge_search: search documents ──
        if any(kw in text_lower for kw in [
            "search my documents", "search documents", "search my files",
            "find in documents", "search knowledge", "look up in my",
            "find in my notes", "search my notes",
        ]):
            query_match = re.search(
                r'(?:search|find|look up).*?(?:for|about)\s+(.+)', text_lower
            )
            query = query_match.group(1).strip() if query_match else ""
            if not query:
                query_match2 = re.search(
                    r'(?:search|find|look up)\s+(.+)', text_lower
                )
                query = query_match2.group(1).strip() if query_match2 else text_lower
            return {
                "action": "knowledge_search",
                "entities": {"query": query, "raw": text_lower},
                "confidence": 1.0,
                "source": "keyword_override",
            }

        # ── 3. knowledge_ask: question about user's docs ──
        if any(kw in text_lower for kw in [
            "what do my ", "from my documents", "from my notes",
            "from my files", "in my documents", "according to my",
            "based on my ",
        ]):
            query_match = re.search(
                r'(?:what do my|from my|in my|according to my|based on my)'
                r'\s+\w+\s+(?:say|mention|note|explain|describe)\s+'
                r'(?:about\s+)?(.+)', text_lower
            )
            query = query_match.group(1).strip() if query_match else ""
            if not query:
                # Fallback: strip prefix
                query = re.sub(
                    r'^(?:what do my|from my|in my|according to my|based on my)\s+\w+\s+',
                    '', text_lower
                ).strip()
            return {
                "action": "knowledge_ask",
                "entities": {"query": query, "raw": text_lower},
                "confidence": 1.0,
                "source": "keyword_override",
            }

        # ── 4. knowledge_stats ──
        if any(kw in text_lower for kw in [
            "how many documents", "knowledge base stats",
            "what do you know about my documents",
            "what files have you learned", "kb stats", "document stats",
        ]):
            return {
                "action": "knowledge_stats",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override",
            }

        # ── 5. knowledge_clear ──
        if any(kw in text_lower for kw in [
            "forget all documents", "clear knowledge base",
            "reset knowledge base", "forget my documents",
            "clear documents", "forget documents",
        ]):
            return {
                "action": "knowledge_clear",
                "entities": {},
                "confidence": 1.0,
                "source": "keyword_override",
            }

        return None

    def _detect_system_override(self, text_lower: str) -> dict | None:
        """Detect and route Calendar, Reminders, Tasks, and Personality."""
        import re
        
        # 1. Calendar
        if any(w in text_lower for w in ["what is on my calendar", "what do i have today", "what's on my calendar", "my calendar today"]):
            return {"action": "calendar_event", "entities": {"raw": text_lower, "action": "view"}, "confidence": 1.0, "source": "keyword_override"}
            
        if any(w in text_lower for w in ["add event", "create event", "add to calendar", "schedule event", "add an event", "create an event"]):
            return {"action": "calendar_event", "entities": {"raw": text_lower, "action": "add"}, "confidence": 1.0, "source": "keyword_override"}
            
        # 2. Reminders
        if any(text_lower.startswith(w) for w in ["set reminder", "remind me to", "remind me about", "remind me at", "remind me in", "remind me ", "set a reminder"]):
            return {"action": "manage_reminders", "entities": {"raw": text_lower, "action": "set"}, "confidence": 1.0, "source": "keyword_override"}
            
        if any(w in text_lower for w in ["list reminders", "show reminders", "show my reminders", "what are my reminders", "my reminders", "what reminders do i have", "reminder list", "list of reminders"]):
            return {"action": "manage_reminders", "entities": {"raw": text_lower, "action": "list"}, "confidence": 1.0, "source": "keyword_override"}
            
        if any(w in text_lower for w in ["edit reminder", "change reminder", "update reminder"]):
            return {"action": "manage_reminders", "entities": {"raw": text_lower, "action": "edit"}, "confidence": 1.0, "source": "keyword_override"}
            
        if any(w in text_lower for w in ["delete reminder", "remove reminder", "cancel reminder"]):
            return {"action": "manage_reminders", "entities": {"raw": text_lower, "action": "delete"}, "confidence": 1.0, "source": "keyword_override"}

            
        # 3. Agent Tasks
        if "task" in text_lower:
            if any(w in text_lower for w in ["show", "list", "active", "status", "resume", "continue", "cancel", "stop", "my"]):
                return {"action": "agent_tasks", "entities": {"raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}
            
        # 4. Personality / Chat
        if text_lower in ["who are you", "who are you?", "what can you do", "what can you do?", "good morning jarvis", "hi jarvis", "hello jarvis", "good morning", "good evening", "good afternoon"]:
            return {"action": "chat", "entities": {"raw": text_lower}, "confidence": 1.0, "source": "keyword_override"}

        return None

    def _extract_solve_entities(self, text_lower: str) -> dict:
        """Helper to extract language and problem entities from a solve query."""
        entities = {"problem": "", "language": ""}
        import re
        
        # Look for language name preceded by in/on/using/with/to
        lang_pattern = r"\b(?:in|on|using|with|to)\s+(c\s*\+\+|cpp|c\s+plus\s+plus|cplusplus|python|java|javascript|js|go|golang|rust|c\s*#|csharp|c\s+sharp|typescript|ts|c)(?![a-zA-Z0-9_+#])"
        lang_match = re.search(lang_pattern, text_lower)
        
        # Fallback: look for standalone language name at the end of the query
        if not lang_match:
            lang_pattern_end = r"\b(c\s*\+\+|cpp|c\s+plus\s+plus|cplusplus|python|java|javascript|js|go|golang|rust|c\s*#|csharp|c\s+sharp|typescript|ts|c)(?![a-zA-Z0-9_+#])$"
            lang_match = re.search(lang_pattern_end, text_lower)
            
        if lang_match:
            raw_lang = lang_match.group(1).strip()
            # Normalize language name
            if raw_lang in ["c++", "cpp", "c plus plus", "cplusplus"]:
                entities["language"] = "C++"
            elif raw_lang in ["c#", "csharp", "c sharp"]:
                entities["language"] = "C#"
            elif raw_lang in ["python", "py"]:
                entities["language"] = "Python"
            elif raw_lang in ["java"]:
                entities["language"] = "Java"
            elif raw_lang in ["javascript", "js"]:
                entities["language"] = "JavaScript"
            elif raw_lang in ["typescript", "ts"]:
                entities["language"] = "TypeScript"
            elif raw_lang in ["go", "golang"]:
                entities["language"] = "Go"
            elif raw_lang in ["rust"]:
                entities["language"] = "Rust"
            elif raw_lang in ["c"]:
                entities["language"] = "C"
            else:
                entities["language"] = raw_lang.title()
                
            # Clean the language match from the string to help extract problem name
            cleaned = text_lower.replace(lang_match.group(0), "")
        else:
            cleaned = text_lower
            
        # 2. Extract problem name
        cleaned = cleaned.strip()
        problem = ""
        
        # Strip prefixes using regex (longest alternations first)
        prefix_pattern = r"^(?:solve\s+the\s+problem\s+on\s+my\s+screen\s+|solve\s+the\s+problem\s+on\s+screen\s+|solve\s+this\s+problem\s+|solve\s+the\s+problem\s+|solve\s+a\s+problem\s+|solve\s+the\s+|solve\s+a\s+|solve\s+|debug\s+|optimize\s+|explain\s+)(.+)$"
        match = re.match(prefix_pattern, cleaned)
        if match:
            problem = match.group(1).strip()
        else:
            problem = cleaned
            
        # Fallback if prefix is not at start but somewhere inside
        if not problem or problem == cleaned:
            for kw in ["solve", "debug", "optimize", "explain"]:
                if kw in cleaned:
                    parts = cleaned.split(kw, 1)
                    problem = parts[1].strip()
                    break
                    
        # Remove trailing pleasantries
        for suffix in [" for me", " please", " now", " bro", " sir"]:
            if problem.endswith(suffix):
                problem = problem[:-len(suffix)].strip()
                
        # Strip trailing "problem" or "question"
        if problem.lower().endswith(" problem"):
            problem = problem[:-8].strip()
        elif problem.lower().endswith(" question"):
            problem = problem[:-9].strip()
                
        # Clean up screen indicators
        screen_indicators = ["on the screen", "on my screen", "from screen", "from the screen", "on screen", "this", "this problem", "this code", "the code"]
        prob_lower = problem.lower()
        if any(ind in prob_lower for ind in screen_indicators) or prob_lower in ("", "problem", "code", "question", "leetcode"):
            problem = ""
            
        entities["problem"] = problem
        return entities

    def _classify_with_ai(self, text: str, context: ConversationContext) -> dict | None:
        """Send user text to Gemini for intent classification."""
        try:
            skill_list = get_skill_descriptions_for_ai()
            ctx = context.get_context_summary(max_entries=3)

            prompt = f"""You are JARVIS's intent classifier. Analyze the command and return JSON.

AVAILABLE ACTIONS:
{skill_list}

{f"CONTEXT:{chr(10)}{ctx}" if ctx else ""}

COMMAND: "{text}"

Return ONLY valid JSON:
{{"action": "<skill_name>", "entities": {{...}}, "confidence": <0.0-1.0>}}

Rules:
- Pick BEST action from the list. Extract ALL entities.
- WhatsApp: extract "contact" and "message" separately
- Apps: extract "app_name". Music: extract "song","artist"
- General questions → "chat". Ambiguous → confidence < 0.6
- Use context for pronouns (it, that, them)
JSON ONLY:"""

            response = self._ask_fast(prompt)
            if not response:
                return None
            return self._parse_ai_response(response)

        except Exception as e:
            log.warning(f"SmartRouter AI error: {e}")
            return None

    def _ask_fast(self, prompt: str) -> str | None:
        """Ultra-fast Gemini call for routing — minimal tokens, no history."""
        try:
            if hasattr(self._gemini, 'ask_quick'):
                return self._gemini.ask_quick(prompt, max_tokens=200)

            import requests
            key = self._gemini._active_key
            if not key:
                return None

            for model in ["gemini-2.0-flash-lite", "gemini-2.0-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
                body = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 200, "temperature": 0.1},
                }
                resp = requests.post(url, json=body, headers=headers, timeout=5)
                if resp.status_code == 200:
                    parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[-1].get("text", "").strip()
            return None
        except Exception as e:
            log.debug(f"SmartRouter fast ask failed: {e}")
            return None

    def _parse_ai_response(self, response: str) -> dict | None:
        """Parse JSON from AI response."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned)
            if json_match:
                cleaned = json_match.group(0)

            result = json.loads(cleaned)
            if "action" not in result:
                return None
            if "entities" not in result or not isinstance(result["entities"], dict):
                result["entities"] = {}
            if "confidence" not in result:
                result["confidence"] = 0.5
            result["confidence"] = float(result["confidence"])

            # Validate action is known
            if result["action"] not in SKILL_REGISTRY and result["action"] not in ("stop", "send_typed", "unknown"):
                for name in SKILL_REGISTRY:
                    if name in result["action"] or result["action"] in name:
                        result["action"] = name
                        break
                else:
                    result["action"] = "chat"
                    result["confidence"] = 0.5
            return result
        except (json.JSONDecodeError, ValueError) as e:
            log.debug(f"SmartRouter parse error: {e}")
            return None

    def _resolve_clarification(self, text: str, context: ConversationContext) -> dict:
        """Handle follow-up answers to clarification questions."""
        pending = context.get_pending_clarification()
        if not pending:
            return {"action": "unknown", "entities": {}, "confidence": 0, "source": "error"}

        known = pending.get("known_entities", {})
        missing = pending.get("missing", [])

        if missing:
            known[missing[0]] = text.strip()
            remaining = missing[1:]
            if remaining:
                context.set_pending_clarification({
                    "action": pending["action"],
                    "known_entities": known,
                    "missing": remaining,
                    "prompt": f"And the {remaining[0]}?",
                })
                return {"action": "_clarify", "entities": {"prompt": f"And the {remaining[0]}?"}, "confidence": 1.0, "source": "clarification"}

        context.clear_pending_clarification()
        return {"action": pending["action"], "entities": known, "confidence": 0.95, "source": "clarification_complete"}

    def _cache_put(self, key: str, result: dict):
        """Add to response cache with LRU eviction."""
        self._cache[key] = result
        if len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    @property
    def routing_stats(self) -> dict:
        """Return routing statistics."""
        return self._stats.copy()

    @property
    def last_route_time_ms(self) -> float:
        return self._last_route_time
