"""
JARVIS — ml/speaker_id.py
Speaker Recognition — identifies WHO is speaking.

Verifies if the speaker is Srini (the owner) or an unknown person.
Uses MFCC-based speaker embeddings — a voiceprint for your voice.

Two modes:
1. Enrollment: Records your voice to create a voiceprint
2. Verification: Checks if current speaker matches the voiceprint

Works OFFLINE, runs in <30ms on CPU.

Usage:
    from ml.speaker_id import SpeakerVerifier
    verifier = SpeakerVerifier()
    verifier.enroll()  # Record your voice once
    result = verifier.verify(audio)
    # → {"is_owner": True, "confidence": 0.92}
"""

import os
import sys
import json
import time
import numpy as np
import sounddevice as sd
import soundfile as sf

# Ensure project root is in path (for direct execution)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import torchaudio
    import torchaudio.transforms as T
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

from utils.logger import log

ML_DIR = os.path.dirname(os.path.abspath(__file__))
SPEAKER_DIR = os.path.join(ML_DIR, "speaker_data")
VOICEPRINT_PATH = os.path.join(SPEAKER_DIR, "voiceprint.npz")
CONFIG_PATH = os.path.join(SPEAKER_DIR, "speaker_config.json")

SAMPLE_RATE = 16000
N_MFCC = 40


class SpeakerVerifier:
    """
    Speaker verification using MFCC-based voiceprints.

    Creates a statistical model of the owner's voice using:
    - MFCC features (40 coefficients)
    - Mean + standard deviation of each coefficient
    - Cosine similarity for matching

    No neural network needed — works with signal processing!
    """

    def __init__(self, threshold: float = 0.75):
        """
        Args:
            threshold: Similarity threshold to accept as owner (0-1).
                       Higher = more strict, lower = more lenient.
        """
        self._threshold = threshold
        self._voiceprint = None  # (mean_mfcc, std_mfcc) of owner
        self._ready = False
        self._mfcc_transform = None

        if _TORCH_AVAILABLE:
            self._mfcc_transform = T.MFCC(
                sample_rate=SAMPLE_RATE,
                n_mfcc=N_MFCC,
                melkwargs={"n_fft": 512, "hop_length": 160, "n_mels": 64},
            )

        self._load_voiceprint()

    def _load_voiceprint(self):
        """Load saved voiceprint if available."""
        if os.path.exists(VOICEPRINT_PATH):
            try:
                data = np.load(VOICEPRINT_PATH)
                self._voiceprint = {
                    "mean": data["mean"],
                    "std": data["std"],
                    "samples_used": int(data.get("samples_used", 0)),
                }
                self._ready = True
                log.info(f"Voiceprint loaded ({self._voiceprint['samples_used']} samples)")
            except Exception as e:
                log.warning(f"Voiceprint load error: {e}")

        if not self._ready:
            log.info("Speaker ID: No voiceprint — run enrollment first")

    @property
    def is_ready(self) -> bool:
        return self._ready

    def enroll(self, num_samples: int = 10, duration: float = 3.0):
        """
        Interactive enrollment — records your voice to create a voiceprint.

        Args:
            num_samples: Number of voice samples to record
            duration: Duration of each sample in seconds
        """
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

        print("=" * 50)
        print("  JARVIS Speaker Enrollment")
        print("  Recording your voiceprint...")
        print("=" * 50)
        print(f"\n  I'll record {num_samples} samples of {duration}s each.")
        print("  Speak naturally — read anything, talk normally.\n")

        os.makedirs(SPEAKER_DIR, exist_ok=True)

        all_mfcc = []

        for i in range(num_samples):
            input(f"  [{i+1}/{num_samples}] Press ENTER, then speak for {duration}s: ")
            print("    Recording...", end="", flush=True)

            audio = sd.rec(
                int(duration * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype='float32'
            )
            sd.wait()
            audio = audio.flatten()
            print(" done!")

            # Save sample
            sample_path = os.path.join(SPEAKER_DIR, f"enrollment_{i:02d}.wav")
            sf.write(sample_path, audio, SAMPLE_RATE)

            # Extract MFCC
            mfcc = self._extract_mfcc(audio)
            if mfcc is not None:
                all_mfcc.append(mfcc)
                print(f"    Features extracted (shape: {mfcc.shape})")

        if len(all_mfcc) < 3:
            print("\n  ERROR: Not enough valid samples. Try again.")
            return False

        # Create voiceprint — mean and std of all MFCC features
        all_features = np.concatenate(all_mfcc, axis=1)  # (n_mfcc, total_frames)
        voiceprint_mean = np.mean(all_features, axis=1)
        voiceprint_std = np.std(all_features, axis=1)

        # Save
        np.savez(
            VOICEPRINT_PATH,
            mean=voiceprint_mean,
            std=voiceprint_std,
            samples_used=len(all_mfcc),
        )

        self._voiceprint = {
            "mean": voiceprint_mean,
            "std": voiceprint_std,
            "samples_used": len(all_mfcc),
        }
        self._ready = True

        print(f"\n  Voiceprint created from {len(all_mfcc)} samples!")
        print(f"  Saved to: {VOICEPRINT_PATH}")
        print(f"  JARVIS will now only respond to YOUR voice.")
        return True

    def verify(self, audio: np.ndarray, sr: int = SAMPLE_RATE) -> dict:
        """
        Verify if the speaker matches the enrolled voiceprint.

        Args:
            audio: 1D numpy array of audio (float32)
            sr: Sample rate

        Returns:
            {"is_owner": True/False, "similarity": 0.92, "threshold": 0.75, "latency_ms": 25}
        """
        if not self._ready:
            return {"is_owner": True, "similarity": 1.0,
                    "threshold": self._threshold, "note": "No voiceprint — allowing all"}

        start = time.time()

        # Extract MFCC from input
        mfcc = self._extract_mfcc(audio, sr)
        if mfcc is None:
            return {"is_owner": False, "similarity": 0.0, "threshold": self._threshold}

        # Compute mean MFCC of input
        input_mean = np.mean(mfcc, axis=1)

        # Cosine similarity between input and voiceprint
        similarity = self._cosine_similarity(input_mean, self._voiceprint["mean"])

        latency = (time.time() - start) * 1000
        is_owner = similarity >= self._threshold

        return {
            "is_owner": is_owner,
            "similarity": round(float(similarity), 4),
            "threshold": self._threshold,
            "latency_ms": round(latency, 1),
        }

    def _extract_mfcc(self, audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
        """Extract MFCC features from audio."""
        try:
            if _TORCH_AVAILABLE and self._mfcc_transform is not None:
                waveform = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)
                if sr != SAMPLE_RATE:
                    resampler = T.Resample(sr, SAMPLE_RATE)
                    waveform = resampler(waveform)
                mfcc = self._mfcc_transform(waveform)
                return mfcc.squeeze(0).numpy()  # (n_mfcc, time_frames)
            else:
                # Fallback: manual MFCC-like features using numpy
                return self._manual_mfcc(audio, sr)
        except Exception as e:
            log.debug(f"MFCC extraction error: {e}")
            return None

    def _manual_mfcc(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Simple spectral features as MFCC fallback."""
        frame_size = int(0.025 * sr)  # 25ms frames
        hop_size = int(0.010 * sr)    # 10ms hop
        num_frames = (len(audio) - frame_size) // hop_size + 1

        features = []
        for i in range(num_frames):
            frame = audio[i * hop_size:i * hop_size + frame_size]
            # Simple spectral features
            fft = np.abs(np.fft.rfft(frame * np.hamming(len(frame))))
            # Log power in frequency bands
            n_bands = N_MFCC
            band_size = len(fft) // n_bands
            band_energies = []
            for b in range(n_bands):
                band = fft[b * band_size:(b + 1) * band_size]
                band_energies.append(np.log(np.mean(band ** 2) + 1e-10))
            features.append(band_energies)

        return np.array(features).T  # (n_mfcc, time_frames)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    verifier = SpeakerVerifier()

    if not verifier.is_ready:
        print("No voiceprint found. Starting enrollment...\n")
        verifier.enroll(num_samples=5, duration=3.0)
        print()

    if verifier.is_ready:
        print("Speaker Verification Test")
        print("Speak and I'll check if it's you!\n")

        for i in range(3):
            input(f"[{i+1}/3] Press ENTER and speak for 2 seconds: ")
            print("  Recording...", end="", flush=True)
            audio = sd.rec(int(2 * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                          channels=1, dtype='float32')
            sd.wait()
            audio = audio.flatten()
            print(" done!")

            result = verifier.verify(audio)
            status = "OWNER" if result["is_owner"] else "UNKNOWN"
            sim = result["similarity"]
            ms = result["latency_ms"]
            print(f"  Result: {status} (similarity: {sim:.1%}, {ms:.0f}ms)\n")
