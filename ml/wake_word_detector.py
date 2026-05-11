"""
JARVIS — ml/wake_word_detector.py
Local CNN-based wake word detection — replaces Google Speech Recognition.

Processes raw audio in <15ms on CPU, no internet needed.
Detects "Hey JARVIS" with high accuracy while ignoring other speech.

Usage:
    from ml.wake_word_detector import NeuralWakeWordDetector
    detector = NeuralWakeWordDetector()
    detector.start(callback=on_wake)
"""

import os
import sys
import json
import time
import threading

# Ensure project root is in path (for direct execution)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
import torch.nn as nn
import torchaudio.transforms as T
import sounddevice as sd

from utils.logger import log

# Paths
ML_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(ML_DIR, "wake_word_model")
MODEL_PATH = os.path.join(MODEL_DIR, "wake_word_cnn.pth")
CONFIG_PATH = os.path.join(MODEL_DIR, "config.json")

# Default config (overridden by config.json if present)
DEFAULT_CONFIG = {
    "sample_rate": 16000,
    "duration": 1.5,
    "n_mels": 40,
    "n_fft": 512,
    "hop_length": 160,
}


class WakeWordCNN(nn.Module):
    """Tiny CNN for wake word detection — must match training architecture."""

    def __init__(self, n_mels=40, n_frames=151):
        super().__init__()

        self.features = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(2),

            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Dropout2d(0.3),
        )

        with torch.no_grad():
            dummy = torch.randn(1, 1, n_mels, n_frames)
            feat_size = self.features(dummy).view(1, -1).shape[1]

        self.classifier = nn.Sequential(
            nn.Linear(feat_size, 64),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(64, 2),
        )

    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x


class NeuralWakeWordDetector:
    """
    Always-on wake word detector using local CNN.
    Processes 1.5-second audio windows in <15ms.
    Falls back to keyword matching if model not trained.
    """

    def __init__(self, threshold: float = 0.85):
        """
        Args:
            threshold: Confidence threshold to trigger wake word (0-1).
                       Higher = fewer false positives, lower = more sensitive.
        """
        self._model = None
        self._config = DEFAULT_CONFIG.copy()
        self._threshold = threshold
        self._ready = False
        self._running = False
        self._thread = None
        self._callback = None
        self._mel_transform = None
        self._amplitude_to_db = None

        self._load_model()

    def _load_model(self):
        """Load the trained wake word CNN from disk."""
        if not os.path.exists(MODEL_PATH):
            log.info("Wake word CNN not found — run ml/train_wake_word.py first")
            return

        try:
            # Load config
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r") as f:
                    self._config.update(json.load(f))

            sr = self._config["sample_rate"]
            n_mels = self._config["n_mels"]
            n_frames = self._config.get("expected_frames", 151)

            # Initialize transforms
            self._mel_transform = T.MelSpectrogram(
                sample_rate=sr,
                n_fft=self._config["n_fft"],
                hop_length=self._config["hop_length"],
                n_mels=n_mels,
            )
            self._amplitude_to_db = T.AmplitudeToDB()

            # Load model
            self._model = WakeWordCNN(n_mels=n_mels, n_frames=n_frames)
            self._model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu", weights_only=True))
            self._model.eval()

            self._ready = True
            param_count = sum(p.numel() for p in self._model.parameters())
            model_size = os.path.getsize(MODEL_PATH) / 1024
            log.info(
                f"Wake word CNN loaded: {param_count:,} params, "
                f"{model_size:.0f}KB, threshold={self._threshold}"
            )

        except Exception as e:
            log.warning(f"Failed to load wake word CNN: {e}")
            self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, callback=None):
        """Start always-on wake word listening in background thread."""
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        method = "CNN" if self._ready else "fallback"
        log.info(f"Wake word detector started ({method})")

    def stop(self):
        """Stop the wake word detector."""
        self._running = False
        log.info("Wake word detector stopped")

    def pause(self):
        """Temporarily pause detection."""
        self._running = False

    def resume(self):
        """Resume detection."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()

    def detect(self, audio: np.ndarray) -> dict:
        """
        Run wake word detection on an audio array.

        Args:
            audio: 1D numpy array of audio samples (float32, 16kHz)

        Returns:
            {"detected": True/False, "confidence": 0.0-1.0, "latency_ms": float}
        """
        if not self._ready:
            return {"detected": False, "confidence": 0.0, "latency_ms": 0}

        try:
            start = time.time()

            # Convert to tensor
            waveform = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)

            # Pad/trim to expected length
            target_len = int(self._config["duration"] * self._config["sample_rate"])
            if waveform.shape[1] < target_len:
                waveform = torch.nn.functional.pad(waveform, (0, target_len - waveform.shape[1]))
            else:
                waveform = waveform[:, :target_len]

            # Compute mel-spectrogram
            mel = self._mel_transform(waveform)
            mel_db = self._amplitude_to_db(mel)

            # Inference
            with torch.no_grad():
                output = self._model(mel_db)
                probs = torch.softmax(output, dim=-1)
                confidence = probs[0, 1].item()  # Probability of wake word

            latency = (time.time() - start) * 1000
            detected = confidence >= self._threshold

            return {
                "detected": detected,
                "confidence": confidence,
                "latency_ms": latency,
            }

        except Exception as e:
            log.debug(f"Wake word detection error: {e}")
            return {"detected": False, "confidence": 0.0, "latency_ms": 0}

    def _listen_loop(self):
        """Continuously listen and check for wake word."""
        sr = self._config["sample_rate"]
        duration = self._config["duration"]
        chunk_samples = int(duration * sr)
        cooldown = 0  # Seconds to wait after detection

        while self._running:
            try:
                # Record audio chunk
                audio = sd.rec(chunk_samples, samplerate=sr, channels=1, dtype='float32')
                sd.wait()
                audio = audio.flatten()

                # Skip if mostly silence (energy threshold)
                energy = np.sqrt(np.mean(audio ** 2))
                if energy < 0.005:
                    continue

                # Run detection
                if self._ready:
                    result = self.detect(audio)
                    if result["detected"]:
                        log.info(
                            f"WAKE WORD DETECTED! confidence={result['confidence']:.1%}, "
                            f"latency={result['latency_ms']:.0f}ms"
                        )
                        if self._callback:
                            self._callback()
                        time.sleep(1.5)  # Cooldown to avoid double-triggers
                else:
                    # Fallback: simple keyword check via speech_recognition
                    self._fallback_detect(audio, sr)

            except Exception as e:
                log.debug(f"Wake word loop error: {e}")
                time.sleep(0.5)

    def _fallback_detect(self, audio: np.ndarray, sr: int):
        """Fallback wake word detection using speech_recognition."""
        try:
            import speech_recognition as speech_r
            import io
            import wave

            # Convert to WAV bytes
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes((audio * 32767).astype(np.int16).tobytes())
            buf.seek(0)

            recognizer = speech_r.Recognizer()
            audio_data = speech_r.AudioData(buf.read(), sr, 2)
            text = recognizer.recognize_google(audio_data, language="en-IN").lower()

            wake_words = ["jarvis", "hey jarvis", "hello jarvis"]
            if any(w in text for w in wake_words):
                log.info(f"WAKE WORD (fallback): '{text}'")
                if self._callback:
                    self._callback()
                time.sleep(1.5)

        except Exception:
            pass  # Speech not recognized — ignore


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Testing Neural Wake Word Detector...")
    detector = NeuralWakeWordDetector(threshold=0.85)

    if not detector.is_ready:
        print("Model not trained! Run these commands first:")
        print("  1. python ml/record_wake_word.py")
        print("  2. python ml/train_wake_word.py")
        print("\nFalling back to speech recognition mode.")

    def on_wake():
        print("\n*** WAKE WORD DETECTED! JARVIS ACTIVATED! ***\n")

    detector.start(callback=on_wake)
    print("Listening for 'Hey JARVIS'... (Ctrl+C to stop)\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        detector.stop()
        print("Stopped.")
