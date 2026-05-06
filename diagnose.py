"""
JARVIS — diagnose.py
Run this to find ALL problems with your JARVIS installation.

Usage:
    python diagnose.py

It will check every component and tell you exactly what's broken.
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

PASS = "\033[92m  ✅ PASS\033[0m"
FAIL = "\033[91m  ❌ FAIL\033[0m"
WARN = "\033[93m  ⚠️  WARN\033[0m"

results = []

def check(name, fn):
    try:
        msg = fn()
        print(f"{PASS}  {name}: {msg or 'OK'}")
        results.append((name, True, msg))
    except Exception as e:
        print(f"{FAIL}  {name}: {e}")
        results.append((name, False, str(e)))

print()
print("=" * 55)
print("  JARVIS Diagnostic Tool")
print("=" * 55)
print()

# ── Python version ────────────────────────────────────────────
print("[ Python Environment ]")
check("Python version",
    lambda: f"{sys.version.split()[0]} — {'✅ OK' if sys.version_info >= (3,10) else '❌ Need 3.10+'}")

# ── Core imports ──────────────────────────────────────────────
print("\n[ Core Libraries ]")

def chk_import(mod, pkg=None):
    import importlib
    importlib.import_module(mod)
    m = importlib.import_module(mod)
    ver = getattr(m, '__version__', 'installed')
    return ver

check("numpy",          lambda: chk_import("numpy"))
check("torch",          lambda: chk_import("torch"))
check("cv2 (opencv)",   lambda: chk_import("cv2"))
check("cv2.face (LBPH)",lambda: __import__("cv2").face.LBPHFaceRecognizer_create() and "OK")
check("PIL (Pillow)",   lambda: chk_import("PIL", "Pillow"))
check("sounddevice",    lambda: chk_import("sounddevice"))
check("soundfile",      lambda: chk_import("soundfile"))
check("colorama",       lambda: chk_import("colorama"))
check("speech_recognition", lambda: chk_import("speech_recognition"))
check("whisper",        lambda: chk_import("whisper"))
check("sklearn",        lambda: chk_import("sklearn"))
check("psutil",         lambda: chk_import("psutil"))
check("pyperclip",      lambda: chk_import("pyperclip"))
check("PyQt5",          lambda: chk_import("PyQt5"))
check("google.generativeai", lambda: chk_import("google.generativeai"))
check("edge-tts",       lambda: chk_import("edge_tts"))
check("pythoncom",      lambda: chk_import("pythoncom"))

# ── Kokoro ────────────────────────────────────────────────────
print("\n[ Kokoro Voice Engine ]")
check("kokoro-onnx",    lambda: chk_import("kokoro"))

def chk_kokoro_models():
    model_dir = ROOT / "data" / "kokoro_models"
    files = list(model_dir.glob("*.onnx")) + list(model_dir.glob("*.bin"))
    if not files:
        raise Exception(f"No model files in {model_dir}")
    return f"{len(files)} model files found"
check("Kokoro model files", chk_kokoro_models)

# ── Data files ────────────────────────────────────────────────
print("\n[ Data & Config Files ]")

def chk_file(path, name):
    p = ROOT / path
    if not p.exists():
        raise Exception(f"Missing: {p}")
    size = p.stat().st_size
    return f"{size:,} bytes"

check("voice_config.json",    lambda: chk_file("data/voice_config.json", "voice config"))
check("language_config.json", lambda: chk_file("data/language_config.json", "language config"))
check("intent_classifier.pkl",lambda: chk_file("brain/models/intent_classifier.pkl", "intent model"))
check("training_data.py",     lambda: chk_file("brain/training_data.py", "training data"))

# ── API Keys ─────────────────────────────────────────────────
print("\n[ API Keys ]")
def chk_gemini_key():
    try:
        import config
        key = getattr(config, "GEMINI_API_KEY", None)
        if not key:
            raise Exception("GEMINI_API_KEY not set in config.py")
        return f"Key found: {key[:15]}..."
    except ImportError:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise Exception("No key in config.py or .env")
        return f"Key found in .env: {key[:15]}..."

check("Gemini API key", chk_gemini_key)

# ── Webcam ────────────────────────────────────────────────────
print("\n[ Hardware ]")
def chk_webcam():
    import cv2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise Exception("Webcam not accessible (index 0)")
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise Exception("Webcam opened but couldn't read a frame")
    return f"Webcam OK — frame shape: {frame.shape}"
check("Webcam",  chk_webcam)

def chk_mic():
    import speech_recognition as sr
    r  = sr.Recognizer()
    mics = sr.Microphone.list_microphone_names()
    if not mics:
        raise Exception("No microphones found")
    return f"{len(mics)} mic(s) found"
check("Microphone", chk_mic)

def chk_audio():
    import ctypes, tempfile, wave, struct, math
    # Create a tiny test WAV
    tmp = tempfile.mktemp(suffix=".wav")
    with wave.open(tmp, 'w') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(22050)
        frames = [struct.pack('<h', int(32767 * math.sin(2*math.pi*440*i/22050)))
                  for i in range(22050)]
        wf.writeframes(b''.join(frames))
    # Try MCI
    winmm = ctypes.windll.winmm
    alias = "diagnose_test"
    err = winmm.mciSendStringW(f'open "{tmp}" type waveaudio alias {alias}', None, 0, None)
    if err != 0:
        raise Exception(f"MCI open failed with error code {err}")
    winmm.mciSendStringW(f"play {alias} wait", None, 0, None)
    winmm.mciSendStringW(f"close {alias}", None, 0, None)
    import os; os.remove(tmp)
    return "Audio plays via MCI ✅"
check("Audio playback (MCI)", chk_audio)

# ── Crash log ─────────────────────────────────────────────────
print("\n[ Crash History ]")
def chk_crash_log():
    log = ROOT / "data" / "crash_log.txt"
    if not log.exists():
        return "No crashes recorded 🎉"
    text = log.read_text(encoding="utf-8", errors="ignore")
    crashes = text.count("CRASH at")
    last = text.split("CRASH at")[-1][:300] if crashes else ""
    print(f"\033[93m  Last crash preview:\n{last[:400]}\033[0m")
    return f"{crashes} crash(es) in log"
check("Crash log", chk_crash_log)

# ── Summary ──────────────────────────────────────────────────
print()
print("=" * 55)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"  Results: {passed} passed, {failed} failed")

if failed:
    print()
    print("\033[91m  ❌ Issues to fix:\033[0m")
    for name, ok, msg in results:
        if not ok:
            print(f"    • {name}: {msg}")
    print()
    print("  💡 Fix missing packages with:")
    print("     pip install opencv-contrib-python Pillow edge-tts sounddevice soundfile pythoncom")
else:
    print()
    print("\033[92m  ✅ All checks passed! JARVIS should work perfectly.\033[0m")
print("=" * 55)
print()
