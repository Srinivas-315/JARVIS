# skills/wolfram.py — WolframAlpha integration for JARVIS
"""
Answers factual/computational questions via WolframAlpha Short Answers API.

Free tier: 2,000 queries/month
Sign up at: https://developer.wolframalpha.com/
Set WOLFRAM_APP_ID in .env

Examples of what Wolfram handles perfectly:
  "what is 15 percent of 230"
  "speed of light in km/s"
  "how many days until Christmas"
  "distance from earth to moon"
  "square root of 144"
  "capital of France"
  "population of India"
  "convert 100 fahrenheit to celsius"
  "what is the atomic number of gold"
"""

import logging
import os
import urllib.parse
import urllib.request

log = logging.getLogger("JARVIS")

# Wolfram Simple Answer API (returns plain text — perfect for voice)
_WOLFRAM_API = "https://api.wolframalpha.com/v1/result"
# Wolfram Spoken Results API (returns natural language — even better for TTS)
_WOLFRAM_SPOKEN = "https://api.wolframalpha.com/v1/spoken"


def ask_wolfram(query: str) -> str:
    """
    Query WolframAlpha and return a clean spoken-style answer.
    Returns empty string if no API key or query fails.
    """
    app_id = os.getenv("WOLFRAM_APP_ID", "").strip()
    if not app_id:
        log.warning("WOLFRAM_APP_ID not set in .env")
        return ""

    try:
        # Use spoken results API — returns natural language like "about 384,400 kilometers"
        params = urllib.parse.urlencode(
            {
                "i": query,
                "appid": app_id,
                "units": "metric",
            }
        )
        url = f"{_WOLFRAM_SPOKEN}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                answer = resp.read().decode("utf-8").strip()
                log.info(f"Wolfram: '{query}' → '{answer[:60]}'")
                return answer
            elif resp.status == 501:
                # Wolfram couldn't understand — return empty so Gemini handles it
                return ""
    except urllib.error.HTTPError as e:
        if e.code == 501:
            return ""  # "Input could not be interpreted"
        log.warning(f"Wolfram HTTP {e.code} for: {query}")
    except Exception as e:
        log.warning(f"Wolfram error: {e}")
    return ""


def is_wolfram_query(text: str) -> bool:
    """
    Heuristic: should this question go to WolframAlpha?
    True for factual/computational questions, False for opinions/tasks.
    """
    text_lower = text.lower().strip()

    # Hard triggers — almost certainly Wolfram territory
    hard_triggers = [
        "what is ",
        "what's ",
        "whats ",
        "how much ",
        "how many ",
        "how far ",
        "how tall ",
        "how big ",
        "how heavy ",
        "how long ",
        "convert ",
        "calculate ",
        "compute ",
        "square root",
        "cube root",
        "factorial",
        "percent of",
        "% of",
        "distance from",
        "distance between",
        "population of",
        "capital of",
        "speed of",
        "weight of",
        "temperature of",
        "atomic number",
        "molecular weight",
        "when was ",
        "who invented",
        "who discovered",
        "define ",
        "definition of",
        "solve ",
        "integrate ",
        "derivative of",
        "circumference",
        "area of",
        "volume of",
    ]

    # Skip if it's clearly a task for JARVIS
    task_keywords = [
        "open ",
        "play ",
        "send ",
        "message ",
        "remind ",
        "set alarm",
        "search for",
        "look up",
        "whatsapp",
        "turn on",
        "turn off",
        "volume",
        "brightness",
        "weather",
        "news",
        "translate",
        "summarize",
        # Camera / vision commands — must NEVER go to Wolfram
        "in my hand",
        "in my hands",
        "am i holding",
        "what do i have",
        "what do i hold",
        "what is this",
        "whats this",
        "what's this",
        "what am i showing",
        "what am i holding",
        "look at",
        "camera",
        "screen",
        "holding",
        "showing",
        "identify this",
        "recognize this",
        "scan this",
        "analyze this",
        "see this",
        "look through",
        "use camera",
        "take a look",
        "what can you see",
        "look around",
        "what is that",
        "whats that",
        "what's that",
    ]
    if any(text_lower.startswith(t) or t in text_lower for t in task_keywords):
        return False

    # Skip conversational questions
    conversational = [
        "how are you",
        "how do you",
        "what do you think",
        "tell me about yourself",
        "what can you do",
        "who are you",
        "your name",
    ]
    if any(c in text_lower for c in conversational):
        return False

    return any(text_lower.startswith(t) or t in text_lower for t in hard_triggers)


class WolframSkill:
    """JARVIS wrapper around WolframAlpha."""

    def query(self, text: str) -> str:
        """
        Try WolframAlpha first. If it can't answer, return '' so
        the caller can fall back to Gemini.
        """
        # Strip common question prefixes for cleaner Wolfram query
        cleaned = text
        for prefix in [
            "jarvis ",
            "hey jarvis ",
            "ok jarvis ",
            "please ",
            "can you ",
            "could you ",
        ]:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()

        answer = ask_wolfram(cleaned)
        if answer:
            # Clean up Wolfram's sometimes verbose preamble
            # e.g. "Wolfram Alpha says: " prefix (doesn't happen but just in case)
            for noise in ["wolfram alpha says:", "according to wolfram alpha,"]:
                if answer.lower().startswith(noise):
                    answer = answer[len(noise) :].strip()
            return answer
        return ""

    def query_with_fallback(self, text: str, gemini_fn) -> str:
        """
        Try Wolfram first, fall back to Gemini if Wolfram can't answer.
        gemini_fn is a callable that takes the query text.
        """
        wolfram_answer = self.query(text)
        if wolfram_answer:
            log.info("Answered via WolframAlpha")
            return wolfram_answer
        log.info("Wolfram couldn't answer — falling back to Gemini")
        return gemini_fn(text)
