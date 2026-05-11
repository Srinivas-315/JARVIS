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

    def route(self, text: str, context: ConversationContext) -> dict:
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
            log.info(
                f"SmartRouter: LOCAL ML -> {local_result['action']} "
                f"({conf:.0%}) in {self._last_route_time:.0f}ms"
            )

            if conf >= 0.75:
                # High confidence — use local model, get entities via regex
                entities = self._extract_entities_fast(text, local_result["action"])
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
            "entities": {k: v for k, v in slots.items() if k not in ("intent", "raw")},
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

    def _extract_entities_fast(self, text: str, intent: str) -> dict:
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

        elif intent == "send_whatsapp":
            # Try to extract contact and message
            import re as _re
            m = _re.search(r"(?:send|message|text|whatsapp|tell)\s+(.+?)\s+(?:to|on whatsapp)\s+(.+)", text_lower)
            if m:
                entities["message"] = m.group(1).strip()
                entities["contact"] = m.group(2).replace("on whatsapp", "").strip()
            else:
                m2 = _re.search(r"(?:send|message|text|whatsapp|tell)\s+(.+?)\s+(?:saying|that)\s+(.+)", text_lower)
                if m2:
                    entities["contact"] = m2.group(1).strip()
                    entities["message"] = m2.group(2).strip()

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
        return None

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
                result["confidence"] = 0.8
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
