"""
JARVIS — ml/record_wake_word.py
Interactive tool to record wake word samples for training.

Guides you through recording "Hey JARVIS" 50 times.
Each recording is 1.5 seconds. Takes about 5 minutes total.

Usage:
    python ml/record_wake_word.py

It will:
    1. Record 50 "Hey JARVIS" samples → ml/wake_data/positive/
    2. Record 50 background noise samples → ml/wake_data/negative/
    3. Auto-augment to 1000+ samples for training
"""

import os
import sys
import time
import wave
import struct
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

# Paths
ML_DIR = os.path.dirname(os.path.abspath(__file__))
WAKE_DIR = os.path.join(ML_DIR, "wake_data")
POS_DIR = os.path.join(WAKE_DIR, "positive")
NEG_DIR = os.path.join(WAKE_DIR, "negative")
AUG_POS_DIR = os.path.join(WAKE_DIR, "augmented_positive")
AUG_NEG_DIR = os.path.join(WAKE_DIR, "augmented_negative")

SAMPLE_RATE = 16000
DURATION = 1.5  # seconds per sample
CHANNELS = 1


def record_audio(duration: float = DURATION, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Record audio from the microphone."""
    audio = sd.rec(int(duration * sr), samplerate=sr, channels=CHANNELS, dtype='float32')
    sd.wait()  # Wait until recording is finished
    return audio.flatten()


def save_wav(audio: np.ndarray, filepath: str, sr: int = SAMPLE_RATE):
    """Save audio as WAV file."""
    sf.write(filepath, audio, sr)


def augment_audio(audio: np.ndarray, sr: int = SAMPLE_RATE) -> list:
    """
    Generate augmented versions of an audio sample.
    Returns list of (augmented_audio, augmentation_name) tuples.
    """
    augmented = []

    # 1. Speed up (1.1x)
    try:
        indices = np.round(np.arange(0, len(audio), 1.1)).astype(int)
        indices = indices[indices < len(audio)]
        fast = audio[indices]
        # Pad to original length
        if len(fast) < len(audio):
            fast = np.pad(fast, (0, len(audio) - len(fast)), mode='constant')
        augmented.append((fast, "fast"))
    except Exception:
        pass

    # 2. Slow down (0.9x)
    try:
        indices = np.round(np.arange(0, len(audio), 0.9)).astype(int)
        indices = indices[indices < len(audio)]
        slow = audio[indices]
        slow = slow[:len(audio)]  # Trim
        augmented.append((slow, "slow"))
    except Exception:
        pass

    # 3. Add white noise (low level)
    noise = np.random.randn(len(audio)) * 0.005
    augmented.append((audio + noise, "noise_low"))

    # 4. Add white noise (medium)
    noise = np.random.randn(len(audio)) * 0.015
    augmented.append((audio + noise, "noise_med"))

    # 5. Pitch shift up (simple resampling trick)
    try:
        factor = 1.05
        indices = np.round(np.arange(0, len(audio), factor)).astype(int)
        indices = indices[indices < len(audio)]
        pitched_up = audio[indices]
        if len(pitched_up) < len(audio):
            pitched_up = np.pad(pitched_up, (0, len(audio) - len(pitched_up)), mode='constant')
        augmented.append((pitched_up, "pitch_up"))
    except Exception:
        pass

    # 6. Pitch shift down
    try:
        factor = 0.95
        indices = np.round(np.arange(0, len(audio), factor)).astype(int)
        indices = indices[indices < len(audio)]
        pitched_down = audio[indices]
        pitched_down = pitched_down[:len(audio)]
        augmented.append((pitched_down, "pitch_down"))
    except Exception:
        pass

    # 7. Volume up
    augmented.append((audio * 1.3, "vol_up"))

    # 8. Volume down
    augmented.append((audio * 0.7, "vol_down"))

    # 9. Add room reverb simulation (simple echo)
    try:
        delay_samples = int(0.02 * sr)  # 20ms echo
        reverb = np.zeros(len(audio))
        reverb[:len(audio)] = audio
        reverb[delay_samples:] += audio[:len(audio) - delay_samples] * 0.3
        augmented.append((reverb, "reverb"))
    except Exception:
        pass

    # 10. Random time shift
    shift = int(0.1 * sr)  # 100ms shift
    shifted = np.roll(audio, shift)
    augmented.append((shifted, "shift"))

    return augmented


def generate_negative_from_noise(duration: float = DURATION, sr: int = SAMPLE_RATE) -> list:
    """Generate various negative (non-wake-word) samples."""
    negatives = []

    # Pure silence
    negatives.append((np.zeros(int(duration * sr)), "silence"))

    # White noise
    negatives.append((np.random.randn(int(duration * sr)) * 0.01, "white_noise"))

    # Pink noise approximation
    samples = int(duration * sr)
    white = np.random.randn(samples)
    # Simple low-pass for pink-ish noise
    pink = np.convolve(white, np.ones(50)/50, mode='same') * 0.05
    negatives.append((pink, "pink_noise"))

    # Random speech-like frequencies
    t = np.linspace(0, duration, int(duration * sr))
    for freq in [100, 200, 300, 500]:
        tone = np.sin(2 * np.pi * freq * t) * 0.02
        negatives.append((tone, f"tone_{freq}"))

    return negatives


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 60)
    print("  JARVIS Wake Word Recorder")
    print("  Train JARVIS to recognize YOUR voice saying 'Hey JARVIS'")
    print("=" * 60)

    # Create directories
    for d in [POS_DIR, NEG_DIR, AUG_POS_DIR, AUG_NEG_DIR]:
        os.makedirs(d, exist_ok=True)

    # Check existing samples
    existing_pos = len([f for f in os.listdir(POS_DIR) if f.endswith('.wav')])
    existing_neg = len([f for f in os.listdir(NEG_DIR) if f.endswith('.wav')])
    print(f"\n  Existing samples: {existing_pos} positive, {existing_neg} negative")

    # ── PHASE 1: Record positive samples ──────────────────────
    target_pos = 50
    if existing_pos >= target_pos:
        print(f"\n  Already have {existing_pos} positive samples! Skipping recording.")
    else:
        remaining = target_pos - existing_pos
        print(f"\n  PHASE 1: Record 'Hey JARVIS' (need {remaining} more)")
        print("  -" * 30)
        print("  Instructions:")
        print("    - Say 'Hey JARVIS' naturally each time")
        print("    - Vary your tone: normal, loud, soft, fast, slow")
        print("    - Each recording is 1.5 seconds")
        print("    - Press ENTER to record, 'q' to quit\n")

        for i in range(existing_pos, target_pos):
            try:
                inp = input(f"  [{i+1}/{target_pos}] Press ENTER to record (q=quit): ").strip()
                if inp.lower() == 'q':
                    print(f"  Recorded {i - existing_pos} new samples.")
                    break

                print("    Recording... ", end="", flush=True)
                audio = record_audio()
                filepath = os.path.join(POS_DIR, f"hey_jarvis_{i:03d}.wav")
                save_wav(audio, filepath)
                print(f"SAVED! (peak: {np.max(np.abs(audio)):.3f})")

            except KeyboardInterrupt:
                print("\n  Stopped.")
                break

    # ── PHASE 2: Record negative samples ──────────────────────
    if existing_neg >= 30:
        print(f"\n  Already have {existing_neg} negative samples! Skipping.")
    else:
        remaining = 30 - existing_neg
        print(f"\n  PHASE 2: Record background noise / non-wake-words ({remaining})")
        print("  -" * 30)
        print("  Instructions:")
        print("    - Say random words that are NOT 'Hey JARVIS'")
        print("    - Try: 'hello', 'hey', 'what', clapping, typing, silence")
        print("    - This teaches the model what is NOT the wake word\n")

        for i in range(existing_neg, 30):
            try:
                inp = input(f"  [{i+1}/30] Press ENTER to record (q=quit): ").strip()
                if inp.lower() == 'q':
                    break

                print("    Recording... ", end="", flush=True)
                audio = record_audio()
                filepath = os.path.join(NEG_DIR, f"negative_{i:03d}.wav")
                save_wav(audio, filepath)
                print(f"SAVED!")

            except KeyboardInterrupt:
                break

    # ── PHASE 3: Auto-generate synthetic negatives ────────────
    print("\n  PHASE 3: Generating synthetic negative samples...")
    synth_negs = generate_negative_from_noise()
    for i, (audio, name) in enumerate(synth_negs):
        filepath = os.path.join(NEG_DIR, f"synthetic_{name}.wav")
        save_wav(audio.astype(np.float32), filepath)
    print(f"  Generated {len(synth_negs)} synthetic negatives.")

    # ── PHASE 4: Augment all samples ──────────────────────────
    print("\n  PHASE 4: Augmenting data (speed, pitch, noise, volume)...")

    pos_files = [f for f in os.listdir(POS_DIR) if f.endswith('.wav')]
    aug_count = 0
    for f in pos_files:
        try:
            audio, sr = sf.read(os.path.join(POS_DIR, f))
            augmented = augment_audio(audio, sr)
            for aug_audio, aug_name in augmented:
                aug_path = os.path.join(AUG_POS_DIR, f"{f[:-4]}_{aug_name}.wav")
                save_wav(aug_audio.astype(np.float32), aug_path)
                aug_count += 1
        except Exception as e:
            print(f"    Warning: Could not augment {f}: {e}")

    neg_files = [f for f in os.listdir(NEG_DIR) if f.endswith('.wav')]
    neg_aug_count = 0
    for f in neg_files:
        try:
            audio, sr = sf.read(os.path.join(NEG_DIR, f))
            augmented = augment_audio(audio, sr)[:5]  # Fewer augmentations for negatives
            for aug_audio, aug_name in augmented:
                aug_path = os.path.join(AUG_NEG_DIR, f"{f[:-4]}_{aug_name}.wav")
                save_wav(aug_audio.astype(np.float32), aug_path)
                neg_aug_count += 1
        except Exception as e:
            pass

    # ── Summary ───────────────────────────────────────────────
    total_pos = len(pos_files) + aug_count
    total_neg = len(neg_files) + neg_aug_count

    print(f"\n  " + "=" * 50)
    print(f"  RECORDING COMPLETE!")
    print(f"  " + "=" * 50)
    print(f"  Original positive:  {len(pos_files)}")
    print(f"  Augmented positive: {aug_count}")
    print(f"  Total positive:     {total_pos}")
    print(f"  Original negative:  {len(neg_files)}")
    print(f"  Augmented negative: {neg_aug_count}")
    print(f"  Total negative:     {total_neg}")
    print(f"\n  Next step: python ml/train_wake_word.py")


if __name__ == "__main__":
    main()
