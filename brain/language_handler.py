"""
JARVIS — brain/language_handler.py
Multilingual support: English, Hindi, Telugu, Tamil, Kannada.

Voice commands:
  "Speak in Hindi"          → switches to Hindi voice + recognition
  "Telugu lo maat ladu"     → switches to Telugu
  "Speak in Tamil"          → switches to Tamil
  "Switch to English"       → back to English (George)
  "What language"           → tells current language
  "Auto detect language"    → auto-detects from your speech

Languages supported:
  English  (en) — George British voice (Kokoro)
  Hindi    (hi) — Microsoft Madhur Neural (edge-tts)
  Telugu   (te) — Microsoft Mohan Neural (edge-tts)
  Tamil    (ta) — Microsoft Valluvar Neural (edge-tts)
  Kannada  (kn) — Microsoft Gagan Neural (edge-tts)
"""

import os
import json
import asyncio
import tempfile
from pathlib import Path
from utils.logger import log

# ── Paths ─────────────────────────────────────────────────────
_ROOT       = Path(__file__).parent.parent
_LANG_FILE  = _ROOT / "data" / "language_config.json"
_AUDIO_DIR  = _ROOT / "data" / "voice_output"

# ══════════════════════════════════════════════════════════════
# LANGUAGE DEFINITIONS
# ══════════════════════════════════════════════════════════════

LANGUAGES = {
    "english": {
        "code":         "en",
        "speech_code":  "en-IN",          # For speech recognition
        "edge_voice":   None,             # Uses Kokoro (George)
        "kokoro_voice": "bm_george",
        "name":         "English",
        "greet":        "Hello! Switched to English.",
        "flag":         "🇬🇧",
    },
    "hindi": {
        "code":         "hi",
        "speech_code":  "hi-IN",
        "edge_voice":   "hi-IN-MadhurNeural",   # Male Hindi voice
        "kokoro_voice": None,
        "name":         "Hindi",
        "greet":        "नमस्ते! मैं अब हिंदी में बात करूंगा।",
        "flag":         "🇮🇳",
    },
    "telugu": {
        "code":         "te",
        "speech_code":  "te-IN",
        "edge_voice":   "te-IN-MohanNeural",    # Male Telugu voice
        "kokoro_voice": None,
        "name":         "Telugu",
        "greet":        "నమస్కారం! నేను ఇప్పుడు తెలుగులో మాట్లాడతాను.",
        "flag":         "🌟",
    },
    "tamil": {
        "code":         "ta",
        "speech_code":  "ta-IN",
        "edge_voice":   "ta-IN-ValluvarNeural",  # Male Tamil voice
        "kokoro_voice": None,
        "name":         "Tamil",
        "greet":        "வணக்கம்! நான் இப்போது தமிழில் பேசுவேன்.",
        "flag":         "🌺",
    },
    "kannada": {
        "code":         "kn",
        "speech_code":  "kn-IN",
        "edge_voice":   "kn-IN-GaganNeural",    # Male Kannada voice
        "kokoro_voice": None,
        "name":         "Kannada",
        "greet":        "ನಮಸ್ಕಾರ! ನಾನು ಈಗ ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ.",
        "flag":         "🌸",
    },
}

# ── Language trigger phrases ──────────────────────────────────
LANG_TRIGGERS = {
    # English — always keep these (escape hatch from any language)
    "speak in english":      "english",
    "switch to english":     "english",
    "english mode":          "english",
    "use english":           "english",
    "back to english":       "english",
    "change to english":     "english",
    "english please":        "english",
    "english lo maat ladu":  "english",
    "talk in english":       "english",
    "speak english":         "english",

    # Hindi — require explicit context, no bare 'hindi'
    "speak in hindi":        "hindi",
    "switch to hindi":       "hindi",
    "hindi mein bolo":       "hindi",
    "hindi mode":            "hindi",
    "use hindi":             "hindi",
    "hindi me baat karo":    "hindi",
    "talk in hindi":         "hindi",
    "change to hindi":       "hindi",

    # Telugu — require explicit context, no bare 'telugu'
    "speak in telugu":       "telugu",
    "switch to telugu":      "telugu",
    "telugu lo maat ladu":   "telugu",
    "telugu mode":           "telugu",
    "use telugu":            "telugu",
    "talk in telugu":        "telugu",
    "change to telugu":      "telugu",
    "telugu lo baat karo":   "telugu",

    # Tamil — require explicit context
    "speak in tamil":        "tamil",
    "switch to tamil":       "tamil",
    "tamil mode":            "tamil",
    "use tamil":             "tamil",
    "talk in tamil":         "tamil",
    "change to tamil":       "tamil",

    # Kannada — require explicit context
    "speak in kannada":      "kannada",
    "switch to kannada":     "kannada",
    "kannada mode":          "kannada",
    "use kannada":           "kannada",
    "talk in kannada":       "kannada",
    "change to kannada":     "kannada",
}

# ── Emergency escape words (work in ANY language/script) ──────
# These are checked separately so 'english' spoken in Telugu mode
# still switches back even if Google returns garbled text
ENGLISH_ESCAPE = [
    "english", "switch english", "back english", "go english",
]


class LanguageHandler:
    """
    Manages JARVIS language switching.
    Detects language triggers, switches voice + recognition.
    """

    def __init__(self):
        self._current   = "english"
        self._audio_dir = _AUDIO_DIR
        self._audio_dir.mkdir(parents=True, exist_ok=True)

        # Check edge-tts
        try:
            import edge_tts
            self._edge_available = True
        except ImportError:
            self._edge_available = False
            log.warning("edge-tts not installed. Run: pip install edge-tts")

        # Check langdetect
        try:
            from langdetect import detect
            self._detect_fn = detect
            self._detect_available = True
        except ImportError:
            self._detect_available = False

        self._load()
        log.info(f"Language handler ready | Current: {self.current_name}")

    # ═══════════════════════════════════════════════════════════
    # PROPERTIES
    # ═══════════════════════════════════════════════════════════

    @property
    def current(self) -> dict:
        return LANGUAGES[self._current]

    @property
    def current_name(self) -> str:
        return LANGUAGES[self._current]["name"]

    @property
    def current_code(self) -> str:
        return LANGUAGES[self._current]["code"]

    @property
    def speech_code(self) -> str:
        """Language code for speech recognition."""
        return LANGUAGES[self._current]["speech_code"]

    @property
    def is_english(self) -> bool:
        return self._current == "english"

    # ═══════════════════════════════════════════════════════════
    # DETECT LANGUAGE SWITCH COMMAND
    # ═══════════════════════════════════════════════════════════

    def detect_switch(self, text: str) -> str | None:
        """
        Check if text is a language-switch command.
        Returns language name if switching, None otherwise.

        When stuck in a non-English mode, also checks for bare
        'english' word as an emergency escape hatch.
        """
        t = text.lower().strip()

        # Full-phrase triggers (exact substring match)
        for trigger, lang in LANG_TRIGGERS.items():
            if trigger in t:
                # Safety: don't re-trigger same language unnecessarily
                # (prevents 'telugu' in a sentence from looping)
                if lang == self._current and lang != "english":
                    continue
                return lang

        # Emergency English escape — if we're stuck in non-English
        # and user says anything containing 'english', come back
        if not self.is_english:
            for escape in ENGLISH_ESCAPE:
                if escape in t:
                    return "english"

        return None

    def switch_to(self, lang_name: str) -> str:
        """Switch to a language. Returns greeting message."""
        lang_name = lang_name.lower()
        if lang_name not in LANGUAGES:
            available = ", ".join(LANGUAGES.keys())
            return f"Unknown language. Available: {available}"

        self._current = lang_name
        self._save()
        lang = LANGUAGES[lang_name]
        log.info(f"Language switched to: {lang['name']}")
        return lang["greet"]

    # ═══════════════════════════════════════════════════════════
    # AUTO LANGUAGE DETECTION
    # ═══════════════════════════════════════════════════════════

    def detect_language(self, text: str) -> str:
        """
        Auto-detect language from text.
        Returns: 'english', 'hindi', 'telugu', etc.
        """
        if not self._detect_available or not text:
            return self._current

        try:
            code = self._detect_fn(text)
            # Map langdetect code → our language name
            code_map = {
                "en": "english",
                "hi": "hindi",
                "te": "telugu",
                "ta": "tamil",
                "kn": "kannada",
            }
            detected = code_map.get(code, "english")
            return detected
        except Exception:
            return self._current

    # ═══════════════════════════════════════════════════════════
    # SPEAK IN ANY LANGUAGE (edge-tts)
    # ═══════════════════════════════════════════════════════════

    def speak_edge(self, text: str, language: str = None) -> str:
        """
        Generate speech using edge-tts for non-English languages.
        Returns: path to generated MP3 file.
        """
        if not self._edge_available:
            return ""

        lang = language or self._current
        lang_config = LANGUAGES.get(lang, LANGUAGES["english"])
        voice = lang_config.get("edge_voice")

        if not voice:
            return ""  # Use Kokoro for English

        out_path = str(self._audio_dir / f"jarvis_{lang}_{abs(hash(text)) % 99999}.mp3")

        try:
            asyncio.run(self._generate_edge_audio(text, voice, out_path))
            log.info(f"Edge-TTS generated: {lang} | {out_path}")
            return out_path
        except RuntimeError:
            # asyncio already running (in GUI thread)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self._generate_edge_audio(text, voice, out_path)
                )
                future.result(timeout=30)
            return out_path
        except Exception as e:
            log.error(f"Edge-TTS error: {e}")
            return ""

    async def _generate_edge_audio(self, text: str, voice: str, output: str):
        """Async edge-tts generation."""
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output)

    def play_audio(self, filepath: str):
        """Play MP3/WAV file."""
        import time
        try:
            # MP3 → pygame
            import pygame
            pygame.mixer.pre_init(44100, -16, 1, 512)
            pygame.mixer.init()
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            pygame.mixer.quit()
            return
        except Exception:
            pass
        try:
            os.startfile(filepath)
            time.sleep(2)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # TRANSLATE VIA GEMINI
    # ═══════════════════════════════════════════════════════════

    def make_prompt_multilingual(self, text: str, target_lang: str = None) -> str:
        """
        Wrap a prompt so Gemini responds in the correct language.
        """
        lang = target_lang or self._current
        if lang == "english":
            return text

        lang_name = LANGUAGES[lang]["name"]
        return (
            f"[IMPORTANT: Reply ONLY in {lang_name}. "
            f"Do not use English at all in your response.]\n\n"
            f"{text}"
        )

    # ═══════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════

    def status(self) -> str:
        lang = LANGUAGES[self._current]
        engine = "Kokoro (George)" if self.is_english else f"Edge-TTS ({lang['edge_voice']})"
        return (
            f"Current language: {lang['flag']} {lang['name']}\n"
            f"Voice engine: {engine}\n"
            f"Speech recognition: {lang['speech_code']}"
        )

    def list_languages(self) -> str:
        lines = ["Available languages:"]
        for name, info in LANGUAGES.items():
            current = " ← current" if name == self._current else ""
            lines.append(f"  {info['flag']}  {info['name']}{current}")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════

    def _save(self):
        try:
            _LANG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_LANG_FILE, "w", encoding="utf-8") as f:
                json.dump({"language": self._current}, f)
        except Exception as e:
            log.warning(f"Could not save language config: {e}")

    def _load(self):
        try:
            if _LANG_FILE.exists():
                with open(_LANG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                lang = cfg.get("language", "english")
                if lang in LANGUAGES:
                    self._current = lang
        except Exception:
            self._current = "english"


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    lh = LanguageHandler()
    print(lh.status())
    print()
    print(lh.list_languages())
    print()

    # Test language detection
    tests = [
        "नमस्ते, मेरा नाम श्रीनि है",
        "నమస్కారం, నా పేరు శ్రీని",
        "வணக்கம், என் பெயர் ஸ்ரீனி",
        "Hello, my name is Srini",
    ]
    print("Language detection test:")
    for t in tests:
        detected = lh.detect_language(t)
        print(f"  '{t[:30]}...' → {detected}")
