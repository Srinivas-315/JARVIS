"""
JARVIS — voice/speaker.py
Smart Speaker — uses Kokoro AI voice (bm_george by default).
Falls back to pyttsx3 if Kokoro is not ready.

Voice change commands (say to JARVIS):
  "Change voice to George"     → bm_george (British male)
  "Change voice to female"     → af (default female)
  "Change voice to Adam"       → am_adam (American male)
  "Switch to British voice"    → bm_george
  "Change voice to Bella"      → af_bella
  "Speak faster" / "Speak slower"
"""

import json
import re
import threading
import time
from pathlib import Path

import config
from utils.helpers import clean_text, speak_friendly
from utils.logger import log

# ── Max sentences JARVIS speaks aloud (rest shown in GUI only) ─
MAX_SPEAK_SENTENCES = 3  # Speak only first 3 sentences
MAX_SPEAK_CHARS = 220  # Hard cap — keeps responses snappy

# ── Voice config path ─────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_CONFIG_FILE = _ROOT / "data" / "voice_config.json"
_MODEL_DIR = _ROOT / "data" / "kokoro_models"

# ── Kokoro voice names (for voice change commands) ────────────
KOKORO_VOICE_ALIASES = {
    # By full name
    "bm_george": "bm_george",
    "george": "bm_george",
    "bm_lewis": "bm_lewis",
    "lewis": "bm_lewis",
    "am_adam": "am_adam",
    "adam": "am_adam",
    "am_michael": "am_michael",
    "michael": "am_michael",
    "af_bella": "af_bella",
    "bella": "af_bella",
    "af_nicole": "af_nicole",
    "nicole": "af_nicole",
    "af_sarah": "af_sarah",
    "sarah": "af_sarah",
    "af_sky": "af_sky",
    "sky": "af_sky",
    "bf_emma": "bf_emma",
    "emma": "bf_emma",
    "bf_isabella": "bf_isabella",
    "isabella": "bf_isabella",
    "af": "af",
    # By gender/accent shortcuts
    "male": "bm_george",
    "british": "bm_george",
    "british male": "bm_george",
    "female": "af",
    "american": "am_adam",
    "british female": "bf_emma",
}

# ── pyttsx3 fallback voice map ────────────────────────────────
PYTTSX3_MAP = {
    "david": 0,
    "zira": 1,
    "male": 0,
    "female": 1,
}


class Speaker:
    """
    JARVIS voice output.
    Uses Kokoro AI voice (bm_george) with pyttsx3 as fallback.
    """

    def __init__(self):
        self._rate = config.VOICE_RATE
        self._volume = config.VOICE_VOLUME
        self._speaking = False
        self._interrupted = False
        self._lock = threading.Lock()

        # pyttsx3 fallback engine
        self._engine = None
        self._voice_index = 0

        # Kokoro engine
        self._kokoro = None
        self._kokoro_voice = "bm_george"
        self._kokoro_speed = 1.25  # Slightly faster than default
        self._use_kokoro = False

        # WAV cache — repeated phrases play instantly (no re-generation)
        self._wav_cache: dict[str, str] = {}
        self._cache_max = 30  # Max cached WAV files

        # Language handler (set by main.py after init)
        self.language_handler = None

        # Load config and initialize
        self._load_config()
        self._init_kokoro()

        if not self._use_kokoro:
            self._init_pyttsx3_fallback()

    # ═══════════════════════════════════════════════════════════
    # INIT
    # ═══════════════════════════════════════════════════════════

    def _load_config(self):
        """Load voice preferences from voice_config.json."""
        try:
            if _CONFIG_FILE.exists():
                with open(_CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                self._kokoro_voice = cfg.get("voice", "bm_george")
                self._kokoro_speed = float(cfg.get("speed", 1.0))
                log.info(
                    f"Voice config loaded: {self._kokoro_voice} @ {self._kokoro_speed}x"
                )
        except Exception as e:
            log.warning(f"Could not load voice_config.json: {e}")

    def _save_config(self):
        """Save current voice preferences to disk."""
        try:
            _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_CONFIG_FILE, "w") as f:
                json.dump(
                    {
                        "voice": self._kokoro_voice,
                        "speed": self._kokoro_speed,
                        "engine": "kokoro" if self._use_kokoro else "pyttsx3",
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            log.warning(f"Could not save voice config: {e}")

    def _init_kokoro(self):
        """Try to initialize Kokoro AI voice engine."""
        # Check model files exist
        onnx = _MODEL_DIR / "kokoro-v0_19.onnx"
        vbin = _MODEL_DIR / "voices.bin"
        if not onnx.exists() or not vbin.exists():
            log.info("Kokoro models not found — using pyttsx3 fallback.")
            return

        try:
            import soundfile as _sf
            from kokoro_onnx import Kokoro as _Kokoro

            self._sf = _sf

            log.info("Loading Kokoro AI voice (bm_george)...")
            self._kokoro = _Kokoro(str(onnx), str(vbin))
            self._use_kokoro = True
            log.info(f"✅ Kokoro ready | Voice: {self._kokoro_voice}")

        except ImportError:
            log.warning("kokoro-onnx or soundfile not installed — using pyttsx3.")
        except Exception as e:
            log.warning(f"Kokoro init failed ({e}) — using pyttsx3 fallback.")

    def _init_pyttsx3_fallback(self):
        """Test pyttsx3 fallback engine."""
        try:
            import pyttsx3

            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            engine.stop()
            del engine
            voice_name = voices[self._voice_index].name if voices else "default"
            log.info(f"pyttsx3 fallback ready | Voice: {voice_name}")
        except Exception as e:
            log.error(f"pyttsx3 also failed: {e}")

    # ═══════════════════════════════════════════════════════════
    # SPEAK
    # ═══════════════════════════════════════════════════════════

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def speak(self, text: str):
        """Speak a text string out loud."""
        if not text or not text.strip():
            return

        clean = clean_text(text)
        clean = speak_friendly(clean)
        if not clean:
            return

        # Always print FULL response to console/GUI
        try:
            print(f"\n\033[94m🤖 JARVIS:\033[0m {clean}\n")
        except UnicodeEncodeError:
            print(f"\n\033[94mJARVIS:\033[0m {clean}\n")

        # Trim for speaking — keeps audio short and snappy
        speak_text = self._trim_for_speaking(clean)

        self._interrupted = False

        # Route to correct TTS engine based on current language
        if self.language_handler and not self.language_handler.is_english:
            # Indian language — use edge-tts
            self._say_edge(speak_text)
        elif self._use_kokoro:
            self._say_kokoro(speak_text)
        else:
            self._say_pyttsx3(speak_text)

    def _trim_for_speaking(self, text: str) -> str:
        """
        Trim text to MAX_SPEAK_SENTENCES for speaking.
        Full text still shows in GUI — only audio is trimmed.
        This is the biggest speed improvement.
        """
        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        # Take first N sentences
        spoken = " ".join(sentences[:MAX_SPEAK_SENTENCES])
        # Hard char cap
        if len(spoken) > MAX_SPEAK_CHARS:
            spoken = spoken[:MAX_SPEAK_CHARS].rsplit(" ", 1)[0] + "."
        return spoken or text[:MAX_SPEAK_CHARS]

    def _normalize_for_kokoro(self, text: str) -> str:
        """
        Normalize text before sending to Kokoro TTS.
        Fixes 'phonemizer words count mismatch' warnings caused by:
        - Abbreviations (CPU, RAM, KB/s)
        - Numbers and symbols (₹, %, °C)
        - Punctuation clusters (..., --)
        - ALL-CAPS words that phonemizer can't handle
        """
        import re as _re

        t = text

        # Expand common abbreviations phonemizer struggles with
        _abbrevs = [
            (r"\bCPU\b", "C P U"),
            (r"\bRAM\b", "RAM"),
            (r"\bGPU\b", "G P U"),
            (r"\bGHz\b", "gigahertz"),
            (r"\bMHz\b", "megahertz"),
            (r"\bGB\b", "gigabytes"),
            (r"\bMB\b", "megabytes"),
            (r"\bKB\b", "kilobytes"),
            (r"\bTB\b", "terabytes"),
            (r"\bKB/s\b", "kilobytes per second"),
            (r"\bMB/s\b", "megabytes per second"),
            (r"\bIP\b", "I P"),
            (r"\bURL\b", "U R L"),
            (r"\bAPI\b", "A P I"),
            (r"\bAI\b", "A I"),
            (r"\bUI\b", "U I"),
            (r"\bHUD\b", "H U D"),
            (r"\bOCR\b", "O C R"),
            (r"\bTTS\b", "T T S"),
            (r"\bLLM\b", "L L M"),
            (r"\bSQL\b", "sequel"),
            (r"\bHTTP\b", "H T T P"),
            (r"\bHTTPS\b", "H T T P S"),
            (r"\bWiFi\b", "wifi"),
            (r"\bWi-Fi\b", "wifi"),
            (r"\bOK\b", "okay"),
        ]
        for pattern, replacement in _abbrevs:
            t = _re.sub(pattern, replacement, t, flags=_re.IGNORECASE)

        # Symbols → words
        t = t.replace("₹", " rupees ")
        t = t.replace("$", " dollars ")
        t = t.replace("%", " percent ")
        t = t.replace("°C", " degrees Celsius ")
        t = t.replace("°F", " degrees Fahrenheit ")
        t = t.replace("&", " and ")
        t = t.replace("@", " at ")
        t = t.replace("#", " number ")
        t = t.replace("→", " to ")
        t = t.replace("←", " from ")
        t = t.replace("…", "...")
        t = t.replace("–", "-")
        t = t.replace("—", ",")

        # Expand numbers with units (e.g. "16GB", "2.5GHz", "50000")
        t = _re.sub(r"(\d+)\s*GB", r"\1 gigabytes", t)
        t = _re.sub(r"(\d+)\s*MB", r"\1 megabytes", t)
        t = _re.sub(r"(\d+)\s*KB", r"\1 kilobytes", t)
        t = _re.sub(r"(\d+)\s*TB", r"\1 terabytes", t)
        t = _re.sub(r"(\d+)\s*GHz", r"\1 gigahertz", t)
        t = _re.sub(r"(\d+)\s*MHz", r"\1 megahertz", t)
        t = _re.sub(r"(\d+)\s*ms\b", r"\1 milliseconds", t)
        t = _re.sub(r"(\d+)\s*fps\b", r"\1 frames per second", t)

        # Remove markdown leftovers
        t = _re.sub(r"\*{1,3}", "", t)
        t = _re.sub(r"_{1,2}", "", t)
        t = _re.sub(r"`+", "", t)
        t = _re.sub(r"#+\s*", "", t)

        # Collapse repeated punctuation (... → pause, -- → comma)
        t = _re.sub(r"\.{2,}", ".", t)
        t = _re.sub(r"-{2,}", ",", t)
        t = _re.sub(r"!{2,}", "!", t)
        t = _re.sub(r"\?{2,}", "?", t)

        # Strip lone special characters that confuse phonemizer
        t = _re.sub(r'(?<!\w)[^\w\s.,!?\'"-](?!\w)', " ", t)

        # Collapse whitespace
        t = _re.sub(r"\s+", " ", t).strip()

        return t

    def _say_kokoro(self, text: str):
        """Speak using Kokoro AI voice with WAV caching."""
        with self._lock:
            self._speaking = True

        # Normalize text to avoid phonemizer word-count mismatch warnings
        text = self._normalize_for_kokoro(text)

        try:
            out_dir = _ROOT / "data" / "voice_output"
            out_dir.mkdir(parents=True, exist_ok=True)

            # Check WAV cache first — instant playback!
            cache_key = (
                f"{self._kokoro_voice}_{self._kokoro_speed}_{hash(text) % 999999}"
            )
            if cache_key in self._wav_cache:
                cached_path = self._wav_cache[cache_key]
                if Path(cached_path).exists():
                    log.info("Playing cached WAV (instant!)")
                    if not self._interrupted:
                        self._play_wav(cached_path)
                    return

            # Generate new audio — MUST include voice name in filename
            # so George's WAV is NEVER replayed when Bella is selected
            voice_tag = self._kokoro_voice.replace("/", "_")
            out_path = str(
                out_dir / f"jarvis_{voice_tag}_{abs(hash(text)) % 999999:06d}.wav"
            )
            samples, sample_rate = self._kokoro.create(
                text, voice=self._kokoro_voice, speed=self._kokoro_speed, lang="en-us"
            )
            self._sf.write(out_path, samples, sample_rate)

            # Save to cache
            if len(self._wav_cache) >= self._cache_max:
                # Remove oldest entry
                oldest = next(iter(self._wav_cache))
                del self._wav_cache[oldest]
            self._wav_cache[cache_key] = out_path

            if not self._interrupted:
                self._play_wav(out_path)

        except Exception as e:
            log.error(f"Kokoro speak error: {e}")
            self._say_pyttsx3(text)
        finally:
            with self._lock:
                self._speaking = False

    def _say_edge(self, text: str):
        """Speak using edge-tts for Indian languages. Falls back to Kokoro if edge-tts fails."""
        with self._lock:
            self._speaking = True
        try:
            if not self.language_handler:
                self._say_kokoro(text)
                return

            out_path = self.language_handler.speak_edge(text)
            if out_path and Path(out_path).exists():
                if not self._interrupted:
                    # edge-tts outputs MP3 — use MP3 player, not WAV
                    self._play_mp3(out_path)
            else:
                # edge-tts failed — fall back to Kokoro (NOT pyttsx3)
                log.warning("edge-tts failed — using Kokoro fallback")
                self._say_kokoro(text)
        except Exception as e:
            log.error(f"edge-tts speak error: {e}")
            self._say_kokoro(text)  # Kokoro fallback
        finally:
            with self._lock:
                self._speaking = False

    def _play_mp3(self, filepath: str):
        """Play MP3 file. Used by edge-tts language voices."""
        filepath = str(Path(filepath).resolve())

        # Method 1: pygame.mixer — best MP3 support
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(44100, -16, 1, 512)
                pygame.mixer.init()
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._interrupted:
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.05)
            return
        except Exception as e:
            log.warning(f"pygame MP3 playback failed: {e}")

        # Method 2: Windows MCI with mpegvideo type (handles MP3)
        try:
            import ctypes

            winmm = ctypes.windll.winmm
            alias = f"mp3_{int(time.time() * 1000) % 99999}"
            err = winmm.mciSendStringW(
                f'open "{filepath}" type mpegvideo alias {alias}', None, 0, None
            )
            if err == 0:
                winmm.mciSendStringW(f"play {alias} wait", None, 0, None)
                winmm.mciSendStringW(f"close {alias}", None, 0, None)
                return
        except Exception as e:
            log.warning(f"MCI MP3 playback failed: {e}")

        # Method 3: os.startfile — last resort
        try:
            import os

            os.startfile(filepath)
            time.sleep(3)
        except Exception as e:
            log.error(f"All MP3 playback methods failed: {e}")

    def _say_pyttsx3(self, text: str):
        """Speak using pyttsx3 (fallback). Thread-safe with CoInitialize."""
        # Initialize COM for this thread (required by Windows SAPI)
        _coinit_done = False
        try:
            import pythoncom

            pythoncom.CoInitialize()
            _coinit_done = True
        except Exception:
            pass

        try:
            import pyttsx3
        except ImportError:
            log.error("pyttsx3 not installed!")
            return

        with self._lock:
            self._speaking = True
            self._interrupted = False

        try:
            self._engine = pyttsx3.init()
            voices = self._engine.getProperty("voices")
            if voices and self._voice_index < len(voices):
                self._engine.setProperty("voice", voices[self._voice_index].id)
            self._engine.setProperty("rate", self._rate)
            self._engine.setProperty("volume", self._volume)
            self._engine.say(text)
            self._engine.runAndWait()
        except RuntimeError:
            pass  # Interrupted — expected
        except Exception as e:
            log.error(f"pyttsx3 error: {e}")
        finally:
            with self._lock:
                self._speaking = False
            try:
                if self._engine:
                    self._engine.stop()
                    del self._engine
                    self._engine = None
            except Exception:
                pass
            # Clean up COM for this thread
            if _coinit_done:
                try:
                    import pythoncom

                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _play_wav(self, filepath: str):
        """
        Play WAV using Windows MCI (winmm.dll).
        Thread-safe. Uses Windows default audio device.
        """
        filepath = str(Path(filepath).resolve())

        # Method 1: Windows MCI via ctypes — works from ANY thread
        try:
            import ctypes
            import time as _t

            winmm = ctypes.windll.winmm
            # Unique alias per call prevents conflicts between concurrent calls
            alias = f"jv{int(_t.time() * 1000) % 99999}"
            err = winmm.mciSendStringW(
                f'open "{filepath}" type waveaudio alias {alias}', None, 0, None
            )
            if err == 0:
                winmm.mciSendStringW(f"play {alias} wait", None, 0, None)
                winmm.mciSendStringW(f"close {alias}", None, 0, None)
                return
        except Exception as e:
            log.warning(f"MCI playback failed: {e}")

        # Method 2: sounddevice with Microsoft Sound Mapper (device=3)
        try:
            import sounddevice as sd
            import soundfile as sf

            data, samplerate = sf.read(filepath, dtype="float32")
            sd.play(data, samplerate, device=3)
            sd.wait()
            return
        except Exception:
            pass

        # Method 3: PowerShell — last resort
        try:
            import subprocess

            subprocess.run(
                [
                    "powershell",
                    "-c",
                    f"(New-Object Media.SoundPlayer '{filepath}').PlaySync()",
                ],
                timeout=30,
                capture_output=True,
            )
        except Exception as e:
            log.error(f"All playback methods failed: {e}")

    def stop(self):
        """Stop speaking immediately."""
        self._interrupted = True
        with self._lock:
            self._speaking = False
        try:
            if self._engine:
                self._engine.stop()
        except Exception:
            pass
        log.info("Speech interrupted!")

    # ═══════════════════════════════════════════════════════════
    # VOICE CHANGE (called from main.py by voice command)
    # ═══════════════════════════════════════════════════════════

    def set_voice(self, name: str) -> str:
        """
        Change JARVIS voice by name.
        Saves to voice_config.json so it persists across restarts.
        """
        name_lower = name.lower().strip()

        if self._use_kokoro:
            kokoro_name = KOKORO_VOICE_ALIASES.get(name_lower)
            if not kokoro_name:
                available = "george, adam, michael, lewis, bella, nicole, sarah, sky, emma, isabella"
                return f"I don't know that voice. Try: {available}"

            old_voice = self._kokoro_voice
            self._kokoro_voice = kokoro_name

            # 1. Clear in-memory cache dict
            self._wav_cache.clear()

            # 2. Delete ALL old WAV files from disk so stale audio can't replay
            try:
                out_dir = _ROOT / "data" / "voice_output"
                for f in out_dir.glob("jarvis_*.wav"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
                log.info(f"Cleared voice WAV cache from disk")
            except Exception as e:
                log.warning(f"Could not clear WAV cache files: {e}")

            self._save_config()
            log.info(f"Voice changed: {old_voice} → {kokoro_name}")
            return f"Switched to {kokoro_name}. How does this sound?"

        else:
            idx = PYTTSX3_MAP.get(name_lower)
            if idx is None:
                return f"Unknown voice '{name}'. Say: David or Zira"
            self._voice_index = idx
            self._save_config()
            return f"Voice changed to {name}!"

    def find_voice_in_text(self, text: str) -> str | None:
        """
        Scan any sentence for a known voice name.
        Returns the alias if found, None if not.

        Examples:
          "change to George"       → "george"
          "use Bella voice"        → "bella"
          "I want Adam"            → "adam"
          "switch to bm_lewis"     → "bm_lewis"
        """
        t = text.lower()
        # Sort by length descending so "bm_george" matches before "george"
        for alias in sorted(KOKORO_VOICE_ALIASES.keys(), key=len, reverse=True):
            if alias in t:
                return alias
        return None

    def set_rate(self, rate: int):
        """Set speaking speed."""
        self._rate = max(100, min(300, rate))
        if self._use_kokoro:
            # Convert pyttsx3 rate to Kokoro speed
            # pyttsx3 default ~150, Kokoro default 1.0
            self._kokoro_speed = round(rate / 150.0, 2)
            self._save_config()
        log.info(f"Rate set: {self._rate} | Kokoro speed: {self._kokoro_speed}")

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))

    def list_voices(self) -> list:
        """Return available voices."""
        if self._use_kokoro:
            return list(set(KOKORO_VOICE_ALIASES.values()))
        try:
            import pyttsx3

            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            engine.stop()
            del engine
            return [v.name for v in voices] if voices else []
        except Exception:
            return []

    def current_voice_name(self) -> str:
        """Return current voice name."""
        if self._use_kokoro:
            return f"{self._kokoro_voice} (Kokoro AI)"
        return "pyttsx3 default"


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    speaker = Speaker()
    print(f"Engine: {'Kokoro' if speaker._use_kokoro else 'pyttsx3'}")
    print(f"Voice:  {speaker.current_voice_name()}")
    speaker.speak("Hello! I am JARVIS speaking in the George voice. How do I sound?")
