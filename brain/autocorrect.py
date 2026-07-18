"""
JARVIS — brain/autocorrect.py
Smart auto-correction for misheard voice commands.
Fixes common speech recognition errors before processing.

Features:
  - Pre-compiled regex for O(1) phrase lookup
  - Word-level and phrase-level corrections
  - Hinglish + South Indian accent support
  - Context-aware correction (uses last command)
  - User-learning (auto-adds corrections after 3x same fix)
  - Confidence scoring (low-confidence → flag for user)
  - difflib fuzzy matching for typo recovery
"""

import difflib
import json
import re
from datetime import datetime
from pathlib import Path

from utils.logger import log

# ─── Storage for user-learned corrections ────────────────────
_DATA_DIR = Path(__file__).parent.parent / "data"
_LEARNED_FILE = _DATA_DIR / "learned_corrections.json"

# ─── Word-level fixes (SINGLE words only — not phrases!) ─────
WORD_FIXES = {
    # JARVIS variations
    "jarves": "jarvis",
    "jarwis": "jarvis",
    "javis": "jarvis",
    "jarvas": "jarvis",
    "jarvish": "jarvis",
    "travis": "jarvis",
    # App names (single words only)
    "crome": "chrome",
    "chrom": "chrome",
    "krom": "chrome",
    "spotty": "spotify",
    "calculater": "calculator",
    "calculador": "calculator",
    "telegrom": "telegram",
    "tellagram": "telegram",
    "discort": "discord",
    "youtoob": "youtube",
    "whatsapp": "whatsapp",
    # Commands
    "minimise": "minimize",
    "maximise": "maximize",
    "scrawl": "scroll",
    "schooll": "scroll",
    "clik": "click",
    "klik": "click",
    "pase": "paste",
    "copee": "copy",
    "volum": "volume",
    "volme": "volume",
    "brighness": "brightness",
    "brightnes": "brightness",
    "screanshot": "screenshot",
    "remine": "remind",
    "remined": "remind",
    "messege": "message",
    "masage": "message",
    "sarch": "search",
    "serch": "search",
    "wether": "weather",
    "wheather": "weather",
    "noose": "news",
    "newz": "news",
    "moosic": "music",
    "musique": "music",
    "plae": "play",
    "pley": "play",
    "opan": "open",
    "oppen": "open",
    "cloze": "close",
    "cloz": "close",
    # Hinglish → English
    "kya": "what",
    "haan": "yes",
    "nahi": "no",
    "aur": "and",
    "mera": "my",
    "meri": "my",
    # Additional Indian English voice fixes
    "jarwish": "jarvis",
    "jarves": "jarvis",
    "guromail": "gmail",
    "geemail": "gmail",
    "instergram": "instagram",
    "instagarm": "instagram",
    "nettflix": "netflix",
    "netflicks": "netflix",
    "amazone": "amazon",
    "amazom": "amazon",
    "flipkard": "flipkart",
    "flipkart": "flipkart",
    "valume": "volume",
    "volumm": "volume",
    "sceenshot": "screenshot",
    "screnshot": "screenshot",
    "remaind": "remind",
    "remaineder": "reminder",
    "calender": "calendar",
    "calander": "calendar",
    "schedual": "schedule",
    "shedule": "schedule",
    "tomorow": "tomorrow",
    "tommorow": "tomorrow",
    "yesturday": "yesterday",
    "yestarday": "yesterday",
    # Phonetic corrections for names
    "sherwani": "Sarvani",
    "sherwanis": "Sarvani",
    "sherwana": "Sarvani",
    "sarvana": "Sarvani",
    "sarwani": "Sarvani",
    "sharwana": "Sarvani",
    "sharvani": "Sarvani",
    "sarvoni": "Sarvani",
    "parthiv": "Pardhive",
    "pardhiv": "Pardhive",
    "padhive": "Pardhive",
    "prdhiv": "Pardhive",
    "hay": "hey",
    # WhatsApp UI control word fixes
    "emogi": "emoji",
    "imoji": "emoji",
    "immoji": "emoji",
    "stiker": "sticker",
    "stikr": "sticker",
    "stricker": "sticker",
    "striker": "sticker",
    "strikr": "sticker",
    "steaker": "sticker",
    "steker": "sticker",
    "curser": "cursor",
    "cursur": "cursor",
    "fokus": "focus",
    "chart": "chat",
    "charts": "chats",
}

# ─── Full phrase corrections ──────────────────────────────────
# (All multi-word entries MUST go here, NOT in WORD_FIXES)
PHRASE_FIXES = {
    # App names (multi-word misrecognitions)
    "open crome": "open chrome",
    "close crome": "close chrome",
    "what's app": "whatsapp",
    "whats up": "whatsapp",
    "what sup": "whatsapp",
    "prd hiv": "Pardhive",
    "spot fi": "spotify",
    "noted pad": "notepad",
    "not pad": "notepad",
    "vs cold": "vs code",
    "v s code": "vs code",
    "visual studio code": "vs code",
    "in stagram": "instagram",
    "insta gram": "instagram",
    "you tube": "youtube",
    # Commands
    "hey travis": "hey jarvis",
    "take a screen shot": "take a screenshot",
    "screen shot please": "screenshot please",
    "what's the whether": "what's the weather",
    "play moosic": "play music",
    "play musik": "play music",
    "scrawl down": "scroll down",
    "scrawl up": "scroll up",
    "minimum eyes": "minimize",
    "maximum eyes": "maximize",
    "minimum ice all": "minimize all",
    "minimum eyes all": "minimize all",
    "what time is": "what time is it",
    "what time it is": "what time is it",
    "screen shot": "screenshot",
    "spotify-fi": "spotify",
    "google crome": "google chrome",
    "open google crome": "open google chrome",
    "play on spotify": "play on spotify",
    "hey google": "hey jarvis",
    "ok google": "jarvis",
    "siri open": "open",
    "alexa open": "open",
    "what is the time": "what time is it",
    "tell me the time": "what time is it",
    "tell me the weather": "what is the weather",
    "switch off": "turn off",
    "switch on": "turn on",
    "focus chart": "focus chat",
    "focus chart input": "focus chat input",
    "chart input": "chat input",
    # WhatsApp UI control misrecognitions
    "mood cursor": "move cursor",
    "mood cursor to": "move cursor to",
    "mode cursor": "move cursor",
    "moved cursor": "move cursor",
    "moose cursor": "move cursor",
    "focus text box": "focus textbox",
    "focused text box": "focus textbox",
    "focused chat": "focus chat",
    "focus chart box": "focus chat box",
    "emogi panel": "emoji panel",
    "emoji penal": "emoji panel",
    "emogi": "emoji",
    "stiker panel": "sticker panel",
    "stiker": "sticker",
    "stiker picker": "sticker picker",
    "stricker panel": "sticker panel",
    "striker panel": "sticker panel",
    "stricker picker": "sticker picker",
    "striker picker": "sticker picker",
    "open immoji": "open emoji",
    "open imoji": "open emoji",
    "show immoji": "show emoji",
    "cursor to the chart": "cursor to chat",
    "cursor to the chat": "cursor to chat",
    "move cursor to the chat": "move cursor to chat",
    "move the cursor to chat": "move cursor to chat",
    "click on the chat": "click on chat",
    "click on the input": "click on input",
}

# ─── Hinglish Commands ────────────────────────────────────────
HINGLISH_FIXES = {
    "chalao": "play",
    "band karo": "close",
    "kholo": "open",
    "dekhao": "show",
    "sunao": "play",
    "rok": "stop",
    "roko": "stop",
    "band kar": "stop",
    "chalu kar": "open",
    "upar jao": "scroll up",
    "neeche jao": "scroll down",
    "awaaz badao": "volume up",
    "awaaz kam karo": "volume down",
    "mausam": "weather",
    "khabar": "news",
    "waqt": "time",
    "tasveer": "screenshot",
}

# ─── South Indian / Regional Accent Fixes ─────────────────────
ACCENT_FIXES = {
    # South Indian English patterns
    "wonly": "only",
    "prepone": "reschedule earlier",
    "revert back": "reply",
    "kindly do the needful": "please do this",
    # Telugu/Tamil fillers (remove)
    "na": "",
    "ra": "",
    "da": "",
    "yaar": "",
    "saar": "sir",
    "anna": "",
    "akka": "",
    # Common mishears
    "wifi": "wi-fi",
    "wify": "wi-fi",
    "pasword": "password",
    "passward": "password",
}

# ─── Pre-compile all phrases for O(1) speed ──────────────────
_ALL_PHRASES: dict[re.Pattern, str] = {}


def _build_compiled_patterns():
    """Build regex patterns once at import time — fast O(1) lookup."""
    global _ALL_PHRASES
    combined = {}
    combined.update(PHRASE_FIXES)
    combined.update(HINGLISH_FIXES)
    combined.update({k: v for k, v in ACCENT_FIXES.items() if " " in k})
    for wrong, right in combined.items():
        pattern = re.compile(r"\b" + re.escape(wrong) + r"\b", re.IGNORECASE)
        _ALL_PHRASES[pattern] = right


_build_compiled_patterns()

# ─── User-learned corrections store ──────────────────────────
_correction_log: dict[str, dict[str, int]] = {}  # {wrong: {right: count}}
_user_corrections: dict[str, str] = {}  # learned (>3x same fix)


def _load_user_corrections():
    """Load previously learned user-specific corrections from disk."""
    global _correction_log, _user_corrections
    try:
        if _LEARNED_FILE.exists():
            data = json.loads(_LEARNED_FILE.read_text(encoding="utf-8"))
            _correction_log = data.get("log", {})
            _user_corrections = data.get("learned", {})
            log.info(f"Loaded {len(_user_corrections)} user-learned corrections.")
    except Exception as e:
        log.warning(f"Could not load user corrections: {e}")


def _save_user_corrections():
    """Save learned corrections to disk."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _LEARNED_FILE.write_text(
            json.dumps(
                {"log": _correction_log, "learned": _user_corrections},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"Could not save user corrections: {e}")


def learn_from_correction(wrong: str, right: str):
    """
    User corrected JARVIS — track this.
    After 3 corrections of the same word → auto-add to permanent fixes.
    """
    wrong = wrong.lower().strip()
    right = right.lower().strip()
    if not wrong or not right or wrong == right:
        return

    if wrong not in _correction_log:
        _correction_log[wrong] = {}
    _correction_log[wrong][right] = _correction_log[wrong].get(right, 0) + 1

    # If corrected 3+ times, promote to permanent fix
    if _correction_log[wrong][right] >= 3:
        _user_corrections[wrong] = right
        log.info(f"User correction learned: '{wrong}' → '{right}'")

    _save_user_corrections()


_load_user_corrections()

# ─── Context tracker ─────────────────────────────────────────
_last_command: str = ""


def set_last_command(cmd: str):
    """Called by JARVIS after each command to keep context."""
    global _last_command
    _last_command = cmd.lower().strip()


# ─── Fuzzy matching ──────────────────────────────────────────
def _fuzzy_fix_word(word: str, vocabulary: list[str], cutoff: float = 0.82) -> str:
    """
    Use difflib to find closest match in vocabulary.
    Only replaces if similarity >= cutoff to avoid wrong fixes.
    """
    matches = difflib.get_close_matches(word, vocabulary, n=1, cutoff=cutoff)
    return matches[0] if matches else word


_VOCAB = list(set(list(WORD_FIXES.values()) + list(PHRASE_FIXES.values())))


# ═══════════════════════════════════════════════════════════════
# MAIN: autocorrect_with_confidence
# ═══════════════════════════════════════════════════════════════


def autocorrect_with_confidence(text: str, context: str = "") -> tuple[str, float]:
    """
    Smart autocorrect with confidence score.

    Returns:
        (corrected_text, confidence)
        confidence 1.0 = exact match found
        confidence 0.7 = fuzzy match applied
        confidence 1.0 = no change needed (also high confidence)

    Use the confidence to decide whether to ask user: "Did you mean X?"
    """
    if not text:
        return text, 1.0

    original = text
    corrected = text.lower().strip()
    confidence = 1.0
    ctx = context or _last_command

    # ── 1. User-learned corrections (highest priority — user-specific) ──
    for wrong, right in _user_corrections.items():
        if wrong in corrected:
            corrected = corrected.replace(wrong, right)
            log.info(f"User-learned fix: '{wrong}' → '{right}'")

    # ── 2. Context-aware fixes ────────────────────────────────
    # "play it again" → if last command had a song, resolve "it"
    if (
        ctx
        and "play it" in corrected
        and any(w in ctx for w in ["spotify", "play", "song", "music", "youtube"])
    ):
        # Extract what was playing from context
        if "play" in ctx:
            last_song = ctx.replace("play", "").strip().split("on")[0].strip()
            if last_song:
                corrected = corrected.replace("play it", f"play {last_song}")
                log.info(f"Context-aware fix: 'play it' → 'play {last_song}'")

    # ── 3. Pre-compiled phrase patterns (fast O(1)) ───────────
    for pattern, right in _ALL_PHRASES.items():
        new = pattern.sub(right, corrected)
        if new != corrected:
            corrected = new
            log.info(f"Phrase fix applied: → '{right}'")

    # ── 4. Word-level fixes ───────────────────────────────────
    words = corrected.split()
    fixed_words = []
    for word in words:
        clean = word.strip(".,!?;:'\"")
        # Exact fix
        if clean in WORD_FIXES:
            replacement = WORD_FIXES[clean]
            fixed_words.append(replacement if replacement else "")  # "" = remove filler
            log.info(f"Word fix: '{clean}' → '{replacement}'")
        # Accent fix (single-word entries)
        elif clean in ACCENT_FIXES and " " not in clean:
            replacement = ACCENT_FIXES[clean]
            if replacement:  # empty string = remove filler word
                fixed_words.append(replacement)
            # else: drop the word (filler)
        else:
            fixed_words.append(word)

    corrected = " ".join(w for w in fixed_words if w).strip()

    # ── 5. Fuzzy matching (last resort for unknowns) ──────────
    # Only apply if correction is very different from original
    if corrected == original.lower().strip():
        # Nothing was fixed — try fuzzy on the whole corrected text
        words2 = corrected.split()
        fuzzy_words = []
        for word in words2:
            clean = word.strip(".,!?")
            if len(clean) >= 4 and clean not in WORD_FIXES:
                fuzzy = _fuzzy_fix_word(clean, _VOCAB, cutoff=0.85)
                if fuzzy != clean:
                    fuzzy_words.append(fuzzy)
                    confidence = 0.75  # fuzzy fix → lower confidence
                    log.info(f"Fuzzy fix: '{clean}' → '{fuzzy}'")
                else:
                    fuzzy_words.append(word)
            else:
                fuzzy_words.append(word)
        corrected = " ".join(fuzzy_words).strip()

    # ── 6. Log if corrected ───────────────────────────────────
    if corrected != original.lower().strip():
        log.info(f"Autocorrected: '{original}' → '{corrected}' (conf={confidence:.2f})")

    return corrected, confidence


def autocorrect(text: str) -> str:
    """
    Simple autocorrect — returns corrected text only.
    Use autocorrect_with_confidence() when you need the confidence score.
    """
    corrected, _ = autocorrect_with_confidence(text)
    return corrected


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("open crome", ""),
        ("jarves play moosic", ""),
        ("take a screen shot", ""),
        ("scrawl down", ""),
        ("what's the whether today", ""),
        ("hey travis how are you", ""),
        ("minimise all", ""),
        ("send messege to banty", ""),
        ("chalao gaana", ""),  # Hinglish: play song
        ("band karo chrome", ""),  # Hinglish: close chrome
        ("wonly open chrome", ""),  # South Indian accent
        ("spot fi", ""),  # multi-word in old WORD_FIXES
        ("what's app message", ""),  # multi-word
        ("play it again", "play believer on spotify"),  # context-aware
    ]
    print("=" * 60)
    print("JARVIS Autocorrect Tests")
    print("=" * 60)
    for t, ctx in tests:
        corrected, conf = autocorrect_with_confidence(t, context=ctx)
        flag = " ⚠️ low conf" if conf < 0.8 else ""
        print(f"  '{t}' → '{corrected}' (conf={conf:.2f}){flag}")
