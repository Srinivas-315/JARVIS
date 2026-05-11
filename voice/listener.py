"""
JARVIS — voice/listener.py
Microphone capture + transcription.

Primary:  Google Speech Recognition (free, accurate with Indian English)
Fallback: Whisper offline (when no internet)
"""

import time
import numpy as np
import speech_recognition as sr
from utils.logger import log
import config

# Whisper as offline fallback
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


class Listener:
    """Voice input — Google Speech Recognition + Whisper fallback."""

    def __init__(self):
        self._recognizer = sr.Recognizer()
        self._mic = None
        self._whisper_model = None
        self._last_audio_np = None  # Raw audio as float32 numpy (16kHz) for ML modules

        # Tune recognizer for clear voice pickup
        self._recognizer.energy_threshold = 250      # Lower = picks up softer speech
        self._recognizer.dynamic_energy_threshold = True
        self._recognizer.pause_threshold = 0.8       # Faster response after speaking
        self._recognizer.non_speaking_duration = 0.5  # Less dead air before speech

        # Initialize microphone
        try:
            self._mic = sr.Microphone()
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
            log.info("Microphone initialized ✅")
        except Exception as e:
            log.error(f"Microphone error: {e}")
            log.error("Tip: Make sure mic is connected and not used by another app.")
            try:
                self._mic = sr.Microphone()   # Create anyway
            except Exception:
                self._mic = None

        # Load Whisper as offline fallback
        if WHISPER_AVAILABLE:
            try:
                model_name = config.WHISPER_MODEL
                log.info(f"Loading Whisper '{model_name}' model (offline fallback)...")
                self._whisper_model = whisper.load_model(model_name)
                log.info(f"Whisper '{model_name}' loaded ✅")
            except Exception as e:
                log.warning(f"Whisper load failed (not critical): {e}")

    def listen(self, timeout: int = 10) -> str:
        """
        Listen from microphone → transcribe → return text.
        Google Speech (online) → Whisper (offline fallback).

        Always creates a FRESH sr.Microphone() to avoid PyAudio
        cross-thread reuse crashes (PyAudio is not thread-safe).
        """
        log.info("🎤 Listening...")
        print("\033[92m🎤 Speak now...\033[0m", flush=True)

        # ── Wait for speaker to finish + extra silence buffer ────
        # Prevents JARVIS from hearing its own voice as a command
        try:
            wait_count = 0
            while getattr(self, '_speaker', None) and self._speaker.is_speaking:
                time.sleep(0.1)
                wait_count += 1
                if wait_count > 80:   # 8 second max wait
                    break
            # Extra buffer AFTER speech ends — mic/speaker need time to settle
            # Without this, JARVIS hears its own voice echo from the speakers
            if wait_count > 0:
                time.sleep(1.2)   # was 0.35s — now 1.2s after any speech
            else:
                time.sleep(0.5)   # minimum silence even when not speaking
        except Exception:
            time.sleep(0.5)

        try:
            # Always create a FRESH Microphone instance — never reuse across threads
            mic = sr.Microphone()
            with mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = self._recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=config.MAX_RECORDING
                )

            # Save raw audio as numpy float32 for ML modules (voice emotion, speaker ID)
            try:
                raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
                self._last_audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            except Exception:
                self._last_audio_np = None

            log.info("Transcribing...")

            # Get current speech language code from language handler
            _speech_lang = "en-IN"
            try:
                _jarvis = getattr(self, '_jarvis', None)
                _lh = getattr(_jarvis, 'lang', None) if _jarvis else None
                if _lh:
                    _speech_lang = _lh.speech_code
            except Exception:
                pass

            # Method 1: Google Speech Recognition (free, accurate)
            try:
                # Primary recognition in current language
                try:
                    text = self._recognizer.recognize_google(audio, language=_speech_lang)
                except sr.UnknownValueError:
                    text = ""

                # ── Dual recognition when in non-English mode ────────────
                # Always ALSO try English recognition so user can say
                # "speak in english" and escape back even from Telugu mode
                if _speech_lang != "en-IN":
                    try:
                        en_text = self._recognizer.recognize_google(audio, language="en-IN")
                        en_lower = en_text.lower().strip()
                        # If the English result has an escape/switch phrase, prefer it
                        _escape_phrases = [
                            "english", "speak in", "switch to", "change to",
                            "change voice", "which voice", "list voice",
                            "stop", "cancel", "open", "close", "time", "weather"
                        ]
                        if any(p in en_lower for p in _escape_phrases):
                            log.info(f"Dual-lang: English result preferred: '{en_text}'")
                            text = en_text
                    except (sr.UnknownValueError, sr.RequestError):
                        pass

                # If primary failed and English fallback not chosen, try en-IN
                if not text and _speech_lang != "en-IN":
                    try:
                        text = self._recognizer.recognize_google(audio, language="en-IN")
                    except (sr.UnknownValueError, sr.RequestError):
                        pass

                text = text.strip() if text else ""
                if text:
                    print(f"\033[93m👤 You said:\033[0m {text}")
                    log.info(f"Transcribed (Google, {_speech_lang}): '{text}'")
                return text

            except sr.UnknownValueError:
                log.warning("Couldn't understand — try speaking clearly.")
                return ""
            except sr.RequestError as e:
                log.warning(f"Google API error: {e}")
                # Method 2: Whisper offline fallback
                if self._whisper_model:
                    return self._transcribe_whisper(audio)
                return ""


        except sr.WaitTimeoutError:
            return ""
        except OSError as e:
            # PyAudio device error — wait and retry next cycle
            log.warning(f"Audio device error (will retry): {e}")
            time.sleep(1.0)
            return ""
        except Exception as e:
            log.error(f"Listen error: {e}")
            time.sleep(0.5)
            return ""


    def _transcribe_whisper(self, audio_data) -> str:
        """Fallback: transcribe with local Whisper model."""
        try:
            log.info("Using Whisper offline fallback...")
            raw = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
            audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

            result = self._whisper_model.transcribe(
                audio_np, language="en", fp16=False, verbose=False
            )
            text = result.get("text", "").strip()
            if text:
                print(f"\033[93m👤 You said:\033[0m {text}")
                log.info(f"Transcribed (Whisper): '{text}'")
            return text
        except Exception as e:
            log.error(f"Whisper error: {e}")
            return ""

    def listen_once_keyword(self, keywords: list, timeout: int = 5) -> bool:
        """Quick keyword detection for yes/no."""
        text = self.listen(timeout=timeout)
        return any(kw.lower() in text.lower() for kw in keywords)


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    listener = Listener()
    print("Say something...")
    result = listener.listen()
    print(f"Result: '{result}'")
