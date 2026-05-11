"""
JARVIS — ml/voice_emotion.py
Voice Emotion Detection using MFCC features + CNN.

Analyzes voice tone, pitch, speed to detect mood:
  happy, sad, angry, neutral, stressed

Uses torchaudio for feature extraction — no external APIs needed.
Runs in <20ms on CPU.

Usage:
    from ml.voice_emotion import VoiceEmotionDetector
    detector = VoiceEmotionDetector()
    result = detector.detect(audio_array)
    # → {"emotion": "happy", "confidence": 0.85}
"""

import os
import sys
import json
import time

# Ensure project root is in path (for direct execution)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
import torch.nn as nn
import torchaudio
import torchaudio.transforms as T

from utils.logger import log

ML_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(ML_DIR, "emotion_model")
MODEL_PATH = os.path.join(MODEL_DIR, "voice_emotion_cnn.pth")

SAMPLE_RATE = 16000
N_MFCC = 40
EMOTIONS = ["neutral", "happy", "sad", "angry", "stressed"]


class VoiceEmotionCNN(nn.Module):
    """
    CNN for emotion detection from MFCC features.
    Input: (batch, 1, n_mfcc, time_frames)
    Output: (batch, 5) emotion logits
    """

    def __init__(self, n_mfcc=N_MFCC, n_emotions=5):
        super().__init__()

        self.features = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2),

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)),
            nn.Dropout2d(0.3),
        )

        self.classifier = nn.Sequential(
            nn.Linear(128 * 4 * 4, 128),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(128, n_emotions),
        )

    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x


class VoiceEmotionDetector:
    """
    Detects emotion from voice audio using MFCC features + CNN.

    Works in two modes:
    1. Trained mode: Uses the custom CNN (if trained)
    2. Rule-based mode: Uses acoustic features (pitch, energy, speed)
       as fallback when CNN not trained
    """

    def __init__(self):
        self._model = None
        self._ready = False
        self._mfcc_transform = T.MFCC(
            sample_rate=SAMPLE_RATE,
            n_mfcc=N_MFCC,
            melkwargs={"n_fft": 512, "hop_length": 160, "n_mels": 64},
        )

        self._load_model()

    def _load_model(self):
        """Load trained emotion model if available."""
        if os.path.exists(MODEL_PATH):
            try:
                self._model = VoiceEmotionCNN()
                self._model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu", weights_only=True))
                self._model.eval()
                self._ready = True
                log.info("Voice emotion CNN loaded")
            except Exception as e:
                log.debug(f"Voice emotion model error: {e}")

        if not self._ready:
            log.info("Voice emotion: using rule-based analysis (CNN not trained)")

    @property
    def is_ready(self) -> bool:
        """True if CNN model is loaded, False uses rule-based."""
        return self._ready

    def detect(self, audio: np.ndarray, sr: int = SAMPLE_RATE) -> dict:
        """
        Detect emotion from audio.

        Args:
            audio: 1D numpy array of audio samples (float32)
            sr: Sample rate

        Returns:
            {"emotion": "happy", "confidence": 0.85, "all_scores": {...}, "method": "cnn"|"rules"}
        """
        start = time.time()

        if self._ready:
            result = self._detect_cnn(audio, sr)
        else:
            result = self._detect_rules(audio, sr)

        result["latency_ms"] = (time.time() - start) * 1000
        return result

    def _detect_cnn(self, audio: np.ndarray, sr: int) -> dict:
        """CNN-based emotion detection."""
        try:
            waveform = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)

            # Resample if needed
            if sr != SAMPLE_RATE:
                resampler = T.Resample(sr, SAMPLE_RATE)
                waveform = resampler(waveform)

            # Extract MFCC
            mfcc = self._mfcc_transform(waveform).unsqueeze(0)  # Add batch dim

            with torch.no_grad():
                output = self._model(mfcc)
                probs = torch.softmax(output, dim=-1)
                pred_id = torch.argmax(probs, dim=-1).item()
                confidence = probs[0][pred_id].item()

            all_scores = {EMOTIONS[i]: probs[0][i].item() for i in range(len(EMOTIONS))}

            return {
                "emotion": EMOTIONS[pred_id],
                "confidence": confidence,
                "all_scores": all_scores,
                "method": "cnn",
            }
        except Exception as e:
            log.debug(f"CNN emotion error: {e}")
            return self._detect_rules(audio, sr)

    def _detect_rules(self, audio: np.ndarray, sr: int) -> dict:
        """
        Rule-based emotion detection using acoustic features.
        This works WITHOUT training — uses signal processing.
        """
        try:
            # Feature 1: Energy (RMS)
            rms = np.sqrt(np.mean(audio ** 2))

            # Feature 2: Zero crossing rate (how "noisy" the voice is)
            zcr = np.mean(np.abs(np.diff(np.sign(audio)))) / 2

            # Feature 3: Pitch estimation (autocorrelation method)
            pitch = self._estimate_pitch(audio, sr)

            # Feature 4: Speaking rate (energy envelope changes)
            envelope = np.abs(audio)
            # Smooth the envelope
            kernel_size = int(0.02 * sr)
            if kernel_size > 0:
                kernel = np.ones(kernel_size) / kernel_size
                envelope = np.convolve(envelope, kernel, mode='same')
            # Count peaks (syllable-like segments)
            threshold = np.mean(envelope) * 1.5
            peaks = np.sum(np.diff((envelope > threshold).astype(int)) > 0)
            duration = len(audio) / sr
            speaking_rate = peaks / max(duration, 0.1)

            # Feature 5: Spectral centroid (brightness)
            fft = np.abs(np.fft.rfft(audio))
            freqs = np.fft.rfftfreq(len(audio), 1.0 / sr)
            centroid = np.sum(freqs * fft) / max(np.sum(fft), 1e-10)

            # ── Relative emotion detection ──────────────────────
            # Instead of fixed thresholds, we use deviation from
            # the speaker's baseline (set from first sample)
            scores = {e: 0.0 for e in EMOTIONS}

            # Store baseline from first call
            if not hasattr(self, '_baseline'):
                self._baseline = {
                    "pitch": pitch, "rms": rms, "zcr": zcr,
                    "rate": speaking_rate, "centroid": centroid,
                }

            b = self._baseline
            # How much each feature deviates from baseline
            pitch_dev = (pitch - b["pitch"]) / max(b["pitch"], 1)
            energy_dev = (rms - b["rms"]) / max(b["rms"], 0.001)
            zcr_dev = (zcr - b["zcr"]) / max(b["zcr"], 0.001)
            rate_dev = (speaking_rate - b["rate"]) / max(b["rate"], 0.1)

            # Neutral: close to baseline
            neutral_score = max(0, 1.0 - abs(pitch_dev) - abs(energy_dev) * 0.5)
            scores["neutral"] = max(0.1, neutral_score * 0.7)

            # Happy: pitch UP, energy UP, rate UP
            if pitch_dev > 0.1 and energy_dev > 0.1:
                scores["happy"] = 0.3 + min(0.5, pitch_dev + energy_dev * 0.5)

            # Sad: pitch DOWN, energy DOWN, rate DOWN
            if pitch_dev < -0.1 and energy_dev < -0.1:
                scores["sad"] = 0.3 + min(0.5, abs(pitch_dev) + abs(energy_dev) * 0.5)

            # Angry: energy WAY UP, zcr UP, centroid UP
            if energy_dev > 0.3 and zcr_dev > 0.2:
                scores["angry"] = 0.3 + min(0.5, energy_dev * 0.8 + zcr_dev * 0.3)

            # Stressed: pitch UP, energy UP, rate UP significantly
            if pitch_dev > 0.15 and energy_dev > 0.2 and rate_dev > 0.3:
                scores["stressed"] = 0.3 + min(0.5, pitch_dev * 0.5 + energy_dev * 0.5)

            # Normalize
            total = sum(scores.values())
            if total > 0:
                scores = {k: round(v / total, 3) for k, v in scores.items()}

            best_emotion = max(scores, key=scores.get)

            return {
                "emotion": best_emotion,
                "confidence": scores[best_emotion],
                "all_scores": scores,
                "method": "rules",
                "features": {
                    "pitch_hz": round(pitch, 1),
                    "energy_rms": round(rms, 4),
                    "zcr": round(zcr, 4),
                    "speaking_rate": round(speaking_rate, 1),
                    "spectral_centroid": round(centroid, 1),
                },
            }
        except Exception as e:
            log.debug(f"Rule-based emotion error: {e}")
            return {"emotion": "neutral", "confidence": 0.5, "all_scores": {}, "method": "error"}

    def _estimate_pitch(self, audio: np.ndarray, sr: int) -> float:
        """Estimate fundamental frequency using autocorrelation."""
        try:
            # Autocorrelation
            corr = np.correlate(audio, audio, mode='full')
            corr = corr[len(corr) // 2:]

            # Find first peak after initial decline
            min_lag = int(sr / 500)  # Max 500 Hz
            max_lag = int(sr / 50)   # Min 50 Hz

            if max_lag > len(corr):
                max_lag = len(corr) - 1

            segment = corr[min_lag:max_lag]
            if len(segment) == 0:
                return 150.0

            peak_idx = np.argmax(segment) + min_lag
            if peak_idx > 0:
                return sr / peak_idx
            return 150.0
        except Exception:
            return 150.0


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import sounddevice as sd
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Voice Emotion Detector -- Test")
    print("How it works: Sample 1 = YOUR BASELINE (speak normally)")
    print("Then change your voice to see different emotions!\n")
    print("  Try: speak LOUDLY for angry, QUIETLY for sad,")
    print("       FAST+HIGH for happy, NORMALLY for neutral\n")

    detector = VoiceEmotionDetector()

    prompts = [
        "Speak NORMALLY (this sets your baseline)",
        "Try speaking HAPPILY (high pitch, excited)",
        "Try speaking SADLY (quiet, slow, low voice)",
        "Try speaking ANGRILY (loud, sharp, fast)",
        "Speak however you want!",
    ]

    for i in range(5):
        input(f"[{i+1}/5] {prompts[i]} - Press ENTER: ")
        for sec in [3, 2, 1]:
            print(f"  {sec}...", end=" ", flush=True)
            time.sleep(0.5)
        print("SPEAK NOW!", flush=True)
        audio = sd.rec(int(2 * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
        sd.wait()
        audio = audio.flatten()

        result = detector.detect(audio)
        emotion = result["emotion"].upper()
        conf = result["confidence"]
        print(f"\n  >> {emotion} ({conf:.0%})")
        if "all_scores" in result:
            for emo, score in sorted(result["all_scores"].items(), key=lambda x: -x[1]):
                bar = "#" * int(score * 30)
                print(f"     {emo:10s} {bar} {score:.0%}")
        if "features" in result:
            f = result["features"]
            print(f"     [pitch={f['pitch_hz']}Hz energy={f['energy_rms']:.3f} speed={f['speaking_rate']}/s]")
        print()
