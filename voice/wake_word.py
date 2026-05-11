"""
JARVIS — voice/wake_word.py
Wake word detection — "Hey Jarvis" activation.

PRIORITY:
  1. Local CNN model (ml/wake_word_model/) — <15ms, offline, trained on YOUR voice
  2. Google Speech Recognition fallback — needs internet, slower

When "jarvis" is detected, triggers the callback.
"""

import time
import threading
import speech_recognition as sr
from utils.logger import log

# Try to load neural wake word detector
try:
    from ml.wake_word_detector import NeuralWakeWordDetector
    _NEURAL_AVAILABLE = True
except ImportError:
    _NEURAL_AVAILABLE = False


class WakeWordDetector:
    """
    Always-on "Hey Jarvis" listener.
    Uses local CNN if trained, Google Speech Recognition as fallback.
    When wake word heard -> calls callback -> JARVIS activates.
    """

    WAKE_WORDS = ["jarvis", "hey jarvis", "hello jarvis", "jarves", "jarwis"]

    def __init__(self, callback=None):
        """callback -> function to call when 'Hey Jarvis' is detected."""
        self._callback    = callback
        self._running     = False
        self._thread      = None
        self._recognizer  = sr.Recognizer()
        self._mic         = None
        self._neural      = None  # CNN-based detector

        # Try to load neural wake word model
        if _NEURAL_AVAILABLE:
            try:
                self._neural = NeuralWakeWordDetector(threshold=0.85)
                if self._neural.is_ready:
                    log.info("Neural wake word detector ready (CNN, <15ms)")
                else:
                    log.info("Neural model not trained — using Google Speech fallback")
                    self._neural = None
            except Exception as e:
                log.debug(f"Neural wake word init error: {e}")
                self._neural = None

        # Tune for quick, low-CPU wake word detection (fallback)
        self._recognizer.energy_threshold = 400
        self._recognizer.dynamic_energy_threshold = True
        self._recognizer.pause_threshold = 0.5       # Short pause = end

        try:
            self._mic = sr.Microphone()
            log.info("Wake word mic ready")
        except Exception as e:
            log.error(f"Wake word mic error: {e}")

    def start(self):
        """Start listening for wake word in background thread."""
        # Use neural detector if available (CNN, <15ms, offline)
        if self._neural:
            self._neural.start(callback=self._callback)
            self._running = True
            log.info("Wake word active (CNN mode) - say 'Hey JARVIS' anytime!")
            return

        if not self._mic:
            log.warning("Wake word disabled - no microphone.")
            return

        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        log.info("Wake word active (Google Speech mode) - say 'Hey JARVIS' anytime!")

    def stop(self):
        """Stop the wake word detector."""
        self._running = False
        log.info("Wake word detector stopped.")

    @property
    def is_running(self):
        return self._running

    def _listen_loop(self):
        """Continuously listen in short bursts for wake word."""
        while self._running:
            try:
                with self._mic as source:
                    # Quick ambient noise adjustment
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.3)

                    # Listen for 3 seconds max (short burst = low CPU)
                    try:
                        audio = self._recognizer.listen(
                            source,
                            timeout=3,           # Wait max 3 sec for speech
                            phrase_time_limit=3   # Max 3 sec of speech
                        )
                    except sr.WaitTimeoutError:
                        continue  # No speech — loop again (very low CPU)

                # Quick recognition check
                try:
                    text = self._recognizer.recognize_google(
                        audio, language="en-IN"
                    ).lower().strip()

                    # Check if wake word is in the text
                    if any(wake in text for wake in self.WAKE_WORDS):
                        log.info(f"🚨 Wake word detected: '{text}'")
                        if self._callback:
                            self._callback()

                        # Pause briefly so main listener can take over
                        time.sleep(0.5)

                except sr.UnknownValueError:
                    pass  # Couldn't understand — ignore
                except sr.RequestError:
                    time.sleep(2)  # Network error — wait a bit

            except Exception as e:
                log.error(f"Wake word error: {e}")
                time.sleep(1)

    def pause(self):
        """Temporarily pause wake word detection (while JARVIS is active)."""
        self._running = False

    def resume(self):
        """Resume wake word detection after JARVIS finishes processing."""
        if not self._running and self._mic:
            self._running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    def on_wake():
        print("\n🚨 WAKE WORD DETECTED! Hey Jarvis heard!")
        print("JARVIS would now start listening for your command...")

    detector = WakeWordDetector(callback=on_wake)
    detector.start()

    print("Listening for 'Hey Jarvis'... (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        detector.stop()
        print("Stopped.")
