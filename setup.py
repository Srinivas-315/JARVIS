"""
JARVIS — setup.py
One-click setup script. Run this ONCE to install everything.
Usage: python setup.py
"""

import sys
import subprocess
import os
from pathlib import Path


def run(cmd, description):
    """Run a command and show status."""
    print(f"\n{'─' * 50}")
    print(f"⚙️  {description}...")
    print(f"CMD: {cmd}")
    print('─' * 50)
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 0:
        print(f"✅ {description} — Done!")
    else:
        print(f"⚠️  {description} — Had some issues (may still work)")
    return result.returncode == 0


def check_python():
    version = sys.version_info
    print(f"🐍 Python {version.major}.{version.minor}.{version.micro} detected")
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("❌ Python 3.9+ is required. Please upgrade.")
        sys.exit(1)
    print("✅ Python version OK")


def main():
    print("""
\033[94m
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
\033[0m
\033[92m  JARVIS Setup Wizard — Installing everything...\033[0m
""")

    check_python()

    # Step 1: Upgrade pip
    run("python -m pip install --upgrade pip", "Upgrading pip")

    # Step 2: Install core requirements phase by phase
    core_packages = [
        # Environment
        "python-dotenv",
        "colorama",

        # AI
        "google-generativeai",

        # Voice Output
        "pyttsx3",

        # Voice Input (Whisper)
        "openai-whisper",
        "sounddevice",
        "numpy",

        # System Control
        "pyautogui",
        "psutil",
        "pygetwindow",
        "pyperclip",
        "screen-brightness-control",
        "pycaw",
        "comtypes",

        # Internet & Browser
        "requests",
        "beautifulsoup4",
        "wikipedia",
        "pywhatkit",
        "playwright",

        # Notifications & Scheduler
        "plyer",
        "schedule",

        # Image & Vision
        "Pillow",
        "pdfplumber",

        # GUI
        "PyQt5",
    ]

    # Install in batches
    print("\n\n📦 Installing Python packages...\n")
    batch = " ".join(core_packages)
    run(f"pip install {batch}", "Installing all packages")

    # Step 3: Install Playwright browsers
    run("playwright install chromium", "Installing Playwright Chromium browser")

    # Step 4: Install OpenWakeWord (wake word, free)
    run("pip install openwakeword", "Installing OpenWakeWord (Hey Jarvis detection)")

    # Step 5: Install Whisper dependencies
    run("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu",
        "Installing PyTorch (for Whisper AI voice recognition)")

    # Step 6: Verify critical imports
    print("\n\n🔍 Verifying installation...\n")
    checks = [
        ("google.generativeai", "Gemini AI"),
        ("pyttsx3",             "Voice Output (pyttsx3)"),
        ("sounddevice",         "Microphone Input"),
        ("whisper",             "Whisper Voice Recognition"),
        ("PIL",                 "Image Processing"),
        ("psutil",              "System Control"),
        ("requests",            "Internet Requests"),
        ("plyer",               "Desktop Notifications"),
        ("schedule",            "Reminder Scheduler"),
    ]

    all_ok = True
    for module, name in checks:
        try:
            __import__(module)
            print(f"  ✅ {name}")
        except ImportError:
            print(f"  ❌ {name} — Run: pip install {module}")
            all_ok = False

    # Final message
    print("\n" + "═" * 55)
    if all_ok:
        print("""
\033[92m
🎉 JARVIS Setup Complete!

To start JARVIS:
    python main.py

To run a quick test (no mic needed):
    python main.py --test

To test voice only:
    python voice/speaker.py

To test Gemini AI only:
    python brain/gemini_handler.py
\033[0m""")
    else:
        print("""
\033[93m
⚠️  Setup completed with some warnings.
Some packages may need manual installation.
Try: pip install -r requirements.txt
\033[0m""")
    print("═" * 55)


if __name__ == "__main__":
    main()
