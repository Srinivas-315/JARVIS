"""
JARVIS — voice/voice_cloner.py
AI Voice System using Kokoro-ONNX (lightweight, fast, offline).

This gives JARVIS a premium AI voice — much better than Windows default.
Runs 100% offline after first model download (~80MB, takes ~1 min).

AVAILABLE VOICES:
  Female: af_heart, af_bella, af_sarah, af_sky, bf_emma, bf_isabella
  Male:   am_adam, am_michael, bm_george, bm_lewis

STANDALONE — does NOT touch main.py yet.
When you want to activate inside JARVIS, just ask!
"""

import os
import sys
import time
import wave
import threading
import urllib.request
from pathlib import Path

# ── Safe logger — works both inside JARVIS and standalone ─────
class _SafeLog:
    def info(self, m):    print(f"  [INFO]  {m}")
    def warning(self, m): print(f"  [WARN]  {m}")
    def error(self, m):   print(f"  [ERROR] {m}")

try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import log
except Exception:
    log = _SafeLog()

# ── Paths ─────────────────────────────────────────────────────
_ROOT      = Path(__file__).parent.parent          # JARVIS root
MODEL_DIR  = _ROOT / "data" / "kokoro_models"     # Store models here
OUTPUT_DIR = _ROOT / "data" / "voice_output"      # Generated audio here

# Default voice
DEFAULT_VOICE = "af"   # Default warm female voice

# All available voices (EXACT names from voices.bin)
VOICES = {
    # Female (American)
    "af":          "Female — Default warm voice (best for JARVIS)",
    "af_bella":    "Female — Bella",
    "af_nicole":   "Female — Nicole",
    "af_sarah":    "Female — Sarah",
    "af_sky":      "Female — Sky",
    # Female (British)
    "bf_emma":     "Female — Emma (British)",
    "bf_isabella": "Female — Isabella (British)",
    # Male (American)
    "am_adam":     "Male — Adam",
    "am_michael":  "Male — Michael",
    # Male (British)
    "bm_george":   "Male — George (British) — closest to Iron Man JARVIS",
    "bm_lewis":    "Male — Lewis (British)",
}

# Model download URLs (GitHub releases)
MODEL_FILES = {
    "kokoro-v0_19.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx",
    "voices.bin":        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin",
}

# ── Check kokoro-onnx ─────────────────────────────────────────
try:
    from kokoro_onnx import Kokoro as _Kokoro
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

# ── Check soundfile ───────────────────────────────────────────
try:
    import soundfile as _sf
    import numpy as _np
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
#  VOICE ENGINE
# ═══════════════════════════════════════════════════════════════

class VoiceCloner:
    """
    JARVIS AI Voice using Kokoro-ONNX.
    High-quality, fully offline TTS with 10 voice options.
    """

    def __init__(self):
        self._kokoro      = None      # Loaded Kokoro model
        self._voice       = DEFAULT_VOICE
        self._speed       = 1.0
        self._lock        = threading.Lock()

        # Create folders
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Properties ──────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._kokoro is not None

    @property
    def current_voice(self) -> str:
        return self._voice

    # ═══════════════════════════════════════════════════════════
    #  MODEL DOWNLOAD
    # ═══════════════════════════════════════════════════════════

    def download_models(self) -> bool:
        """
        Download Kokoro model files (~80MB total).
        Only needed once — saved to JARVIS/data/kokoro_models/
        """
        all_ok = True

        for filename, url in MODEL_FILES.items():
            target = MODEL_DIR / filename

            # Skip if already downloaded
            if target.exists() and target.stat().st_size > 1_000_000:
                print(f"  ✅ {filename} already downloaded.")
                continue

            print(f"\n  ⏳ Downloading {filename}...")
            print(f"     From: {url}")
            print(f"     To:   {target}")

            try:
                # Show download progress
                def _progress(block_num, block_size, total_size):
                    if total_size > 0:
                        done  = block_num * block_size
                        pct   = min(100, done * 100 // total_size)
                        mb    = done / 1_048_576
                        total = total_size / 1_048_576
                        bar   = "█" * (pct // 5) + "░" * (20 - pct // 5)
                        print(f"  [{bar}] {pct:3d}%  {mb:.1f}/{total:.1f} MB", end="\r")

                urllib.request.urlretrieve(url, str(target), reporthook=_progress)
                print(f"\n  ✅ {filename} downloaded! ({target.stat().st_size / 1_048_576:.1f} MB)")

            except Exception as e:
                print(f"\n  ❌ Download failed: {e}")
                print(f"     Check internet connection and try again.")
                all_ok = False

        return all_ok

    def models_exist(self) -> bool:
        """Check if model files are already downloaded."""
        for filename in MODEL_FILES:
            path = MODEL_DIR / filename
            if not path.exists() or path.stat().st_size < 1_000_000:
                return False
        return True

    # ═══════════════════════════════════════════════════════════
    #  LOAD MODEL
    # ═══════════════════════════════════════════════════════════

    def load_model(self) -> bool:
        """Load Kokoro model into memory (fast, ~2 seconds)."""
        if not KOKORO_AVAILABLE:
            print("  ❌ kokoro-onnx not installed.")
            print("  Run:  pip install kokoro-onnx soundfile")
            return False

        if not SOUNDFILE_AVAILABLE:
            print("  ❌ soundfile not installed.")
            print("  Run:  pip install soundfile")
            return False

        if self._kokoro is not None:
            print("  ✅ Model already loaded.")
            return True

        # Check model files exist
        if not self.models_exist():
            print("  ❌ Model files not found.")
            print("  Download them first (option 1 in the menu).")
            return False

        onnx_path  = str(MODEL_DIR / "kokoro-v0_19.onnx")
        voices_path = str(MODEL_DIR / "voices.bin")

        print("  ⏳ Loading Kokoro model...", end="", flush=True)
        try:
            self._kokoro = _Kokoro(onnx_path, voices_path)
            print(" ✅ Ready!")
            log.info("Kokoro model loaded.")
            return True

        except Exception as e:
            print(f"\n  ❌ Load failed: {e}")
            log.error(f"Kokoro load error: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    #  SPEAK
    # ═══════════════════════════════════════════════════════════

    def speak(self, text: str, voice: str = None, speed: float = None,
              play: bool = True) -> str:
        """
        Speak text using the AI voice.

        text:  What to say
        voice: Voice name (see VOICES dict). Uses default if None.
        speed: Speaking speed. 1.0 = normal, 1.2 = faster, 0.9 = slower
        play:  True = auto-play audio
        Returns: path to WAV file
        """
        if not self._kokoro:
            print("  ❌ Model not loaded. Call load_model() first.")
            return ""

        text = text.strip()
        if not text:
            return ""

        voice = voice or self._voice
        speed = speed or self._speed

        # Validate voice
        if voice not in VOICES:
            print(f"  ⚠️  Unknown voice '{voice}'. Using '{DEFAULT_VOICE}'.")
            voice = DEFAULT_VOICE

        # Output path — unique per text
        out_name    = f"jarvis_{abs(hash(text + voice)) % 999999:06d}.wav"
        output_path = str((OUTPUT_DIR / out_name).resolve())

        print(f"  🎙️  Speaking as [{voice}]: \"{text[:55]}{'...' if len(text)>55 else ''}\"")

        try:
            with self._lock:
                # Generate audio samples
                samples, sample_rate = self._kokoro.create(
                    text,
                    voice  = voice,
                    speed  = speed,
                    lang   = "en-us"
                )

                # Save to WAV using soundfile
                _sf.write(output_path, samples, sample_rate)

            log.info(f"Audio generated: {out_name}")

            if play:
                self._play(output_path)

            return output_path

        except Exception as e:
            print(f"  ❌ Generation error: {e}")
            # Common fixes
            if "voice" in str(e).lower():
                print(f"  Fix: Try a different voice. Available: {', '.join(list(VOICES.keys())[:4])}")
            log.error(f"Speak error: {e}")
            return ""

    def speak_async(self, text: str, voice: str = None) -> None:
        """Non-blocking speak — returns immediately, speaks in background."""
        t = threading.Thread(
            target=self.speak,
            args=(text, voice, None, True),
            daemon=True
        )
        t.start()

    # ═══════════════════════════════════════════════════════════
    #  VOICE SETTINGS
    # ═══════════════════════════════════════════════════════════

    def set_voice(self, voice: str) -> bool:
        """Set the default voice for JARVIS."""
        if voice not in VOICES:
            print(f"  ❌ Unknown voice: {voice}")
            print(f"  Available: {', '.join(VOICES.keys())}")
            return False
        self._voice = voice
        print(f"  ✅ Voice set to: {voice} — {VOICES[voice]}")
        return True

    def set_speed(self, speed: float) -> None:
        """Set speaking speed. 1.0 = normal, 1.2 = faster."""
        self._speed = max(0.5, min(2.0, speed))
        print(f"  ✅ Speed set to: {self._speed}x")

    # ═══════════════════════════════════════════════════════════
    #  AUDIO PLAYBACK
    # ═══════════════════════════════════════════════════════════

    def _play(self, filepath: str) -> None:
        """Play WAV — tries winsound first (built-in), then pygame."""

        # Method 1: winsound — Windows built-in, zero deps, handles spaces in path
        try:
            import winsound
            winsound.PlaySound(filepath, winsound.SND_FILENAME)
            return
        except Exception:
            pass

        # Method 2: pygame
        try:
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

        # Method 3: OS open (plays in default media player)
        try:
            os.startfile(filepath)
        except Exception as e:
            print(f"  ⚠️  Could not auto-play. Open manually: {filepath}")

    # ═══════════════════════════════════════════════════════════
    #  STATUS
    # ═══════════════════════════════════════════════════════════

    def status(self) -> None:
        print()
        print("  ┌─── Voice Cloner Status ──────────────────┐")
        items = [
            ("kokoro-onnx installed", KOKORO_AVAILABLE),
            ("soundfile installed",   SOUNDFILE_AVAILABLE),
            ("Model files on disk",   self.models_exist()),
            ("Model loaded",          self._kokoro is not None),
            ("Ready to speak",        self.is_ready),
        ]
        for label, ok in items:
            icon = "✅" if ok else "❌"
            print(f"  │  {icon}  {label:<30}  │")

        print(f"  │  🎙️  Current voice: {self._voice:<22}  │")
        print(f"  │  ⚡  Speed: {self._speed}x{' ' * 34}│")
        print("  └──────────────────────────────────────────┘")
        print()


# ═══════════════════════════════════════════════════════════════
#  INTERACTIVE MENU
# ═══════════════════════════════════════════════════════════════

def main():
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║   🎙️   JARVIS AI Voice — Kokoro Setup   ║")
    print("  ╚══════════════════════════════════════════╝")

    # Check requirements
    if not KOKORO_AVAILABLE or not SOUNDFILE_AVAILABLE:
        print()
        missing = []
        if not KOKORO_AVAILABLE:   missing.append("kokoro-onnx")
        if not SOUNDFILE_AVAILABLE: missing.append("soundfile")
        print(f"  ❌ Missing packages: {', '.join(missing)}")
        print(f"  Run:  pip install {' '.join(missing)}")
        print()
        return

    cloner = VoiceCloner()
    cloner.status()

    while True:
        print("  ─── Menu ────────────────────────────────")
        print("  1. Download model files (~80MB)")
        print("  2. Load model into memory")
        print("  3. Test — speak a sentence")
        print("  4. Browse & preview all voices")
        print("  5. Change speed")
        print("  6. Full setup (1 → 2 → 3)")
        print("  7. Show status")
        print("  0. Exit")
        print("  ─────────────────────────────────────────")

        choice = input("  Choice: ").strip()
        print()

        # ── 1. Download ─────────────────────────────────────
        if choice == "1":
            if cloner.models_exist():
                print("  ✅ Model files already downloaded! Skip to option 2.")
            else:
                cloner.download_models()

        # ── 2. Load ─────────────────────────────────────────
        elif choice == "2":
            cloner.load_model()

        # ── 3. Test ─────────────────────────────────────────
        elif choice == "3":
            if not cloner.is_ready:
                print("  ❌ Complete steps 1 and 2 first.")
            else:
                text = input("  What should JARVIS say?\n  > ").strip()
                if text:
                    cloner.speak(text)

        # ── 4. Browse voices ─────────────────────────────────
        elif choice == "4":
            if not cloner.is_ready:
                print("  ❌ Load the model first (option 2).")
            else:
                print("  Available voices:\n")
                voice_list = list(VOICES.items())
                for i, (name, desc) in enumerate(voice_list, 1):
                    current = " ← current" if name == cloner.current_voice else ""
                    print(f"  {i:2d}. {name:<15} — {desc}{current}")

                print()
                sel = input("  Pick a number to preview (or press Enter to skip): ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(voice_list):
                    chosen_voice = voice_list[int(sel) - 1][0]
                    test = f"Hello! I am JARVIS, speaking in the {chosen_voice} voice. How do I sound?"
                    print(f"\n  Previewing {chosen_voice}...")
                    cloner.speak(test, voice=chosen_voice)
                    print()
                    confirm = input("  Set this as JARVIS voice? (y/n): ").strip().lower()
                    if confirm == "y":
                        cloner.set_voice(chosen_voice)

        # ── 5. Speed ─────────────────────────────────────────
        elif choice == "5":
            print("  Speed options:  0.8 = slow | 1.0 = normal | 1.2 = fast | 1.5 = very fast")
            val = input("  Enter speed (0.5 to 2.0): ").strip()
            try:
                cloner.set_speed(float(val))
            except ValueError:
                print("  ❌ Invalid number.")

        # ── 6. Full setup ────────────────────────────────────
        elif choice == "6":
            print("  === FULL AUTO SETUP ===\n")

            # Step 1: Download
            print("  STEP 1/3 — Download model files")
            if cloner.models_exist():
                print("  ✅ Already downloaded!")
            elif not cloner.download_models():
                print("  ❌ Download failed. Check internet and retry.")
                continue

            # Step 2: Load
            print("\n  STEP 2/3 — Load model")
            if not cloner.load_model():
                print("  ❌ Load failed.")
                continue

            # Step 3: Test
            print("\n  STEP 3/3 — Test")
            test = ("Hello! I am JARVIS, your personal AI assistant. "
                    "Voice setup is complete and I am ready to help you!")
            out = cloner.speak(test)
            if out:
                print("\n  ✅ Voice system working perfectly!")
                print()
                print("  Next: Choose your preferred voice (option 4)")
                print("  Then: I can connect this to JARVIS — just ask!")
            else:
                print("\n  ⚠️  Something went wrong. Check errors above.")

        # ── 7. Status ────────────────────────────────────────
        elif choice == "7":
            cloner.status()

        # ── 0. Exit ──────────────────────────────────────────
        elif choice == "0":
            print("  Bye!")
            break

        else:
            print("  ❌ Enter a number from 0-7.")

        print()


if __name__ == "__main__":
    main()
