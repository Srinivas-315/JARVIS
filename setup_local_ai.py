"""
JARVIS — setup_local_ai.py
One-command setup for fully offline AI.

Run: python setup_local_ai.py

This script:
  1. Checks if Ollama is installed
  2. Downloads the best model for your hardware
  3. Creates the JARVIS custom personality
  4. Tests the model
  5. Updates config to use it
"""

import subprocess
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent

# ─── Colors ──────────────────────────────────────────────────
G = "\033[92m"  # Green
Y = "\033[93m"  # Yellow
R = "\033[91m"  # Red
B = "\033[94m"  # Blue
W = "\033[0m"  # Reset
BOLD = "\033[1m"


def print_header():
    print(f"""
{B}{BOLD}
╔══════════════════════════════════════════════════════╗
║       JARVIS — Local AI Setup                        ║
║       Making JARVIS work 100% offline                ║
╚══════════════════════════════════════════════════════╝
{W}""")


def check_ollama() -> bool:
    """Check if Ollama is installed and running."""
    try:
        result = subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print(f"{G}✅ Ollama installed: {result.stdout.strip()}{W}")
            return True
    except FileNotFoundError:
        pass
    except Exception:
        pass
    print(f"{R}❌ Ollama not installed.{W}")
    print(f"{Y}   Install from: https://ollama.com/download{W}")
    print(f"{Y}   Then run this script again.{W}")
    return False


def start_ollama() -> bool:
    """Start Ollama server if not running."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            print(f"{G}✅ Ollama server is running{W}")
            return True
    except Exception:
        pass
    print(f"{Y}⚡ Starting Ollama server...{W}")
    try:
        subprocess.Popen(
            ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        # Check again
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=3)
            if resp.status_code == 200:
                print(f"{G}✅ Ollama server started{W}")
                return True
        except Exception:
            pass
    except Exception as e:
        print(f"{R}❌ Could not start Ollama: {e}{W}")
    return False


def get_installed_models() -> list:
    """Get list of installed Ollama models."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    return []


def detect_ram_gb() -> float:
    """Detect system RAM in GB."""
    try:
        import psutil

        return psutil.virtual_memory().total / (1024**3)
    except Exception:
        return 8.0  # Assume 8GB


def recommend_model() -> str:
    """Recommend best model based on system specs."""
    ram = detect_ram_gb()
    print(f"{B}   System RAM: {ram:.1f} GB{W}")
    if ram >= 16:
        return "llama3.2:3b"  # Best for conversation
    elif ram >= 8:
        return "phi3:mini"  # Good balance
    else:
        return "phi3:mini"  # Smallest viable model


def pull_model(model_name: str) -> bool:
    """Pull an Ollama model."""
    print(f"\n{Y}📥 Downloading {model_name}...{W}")
    print(f"{Y}   (This is a one-time download — may take 5-15 minutes){W}\n")
    try:
        result = subprocess.run(
            ["ollama", "pull", model_name],
            timeout=1800,  # 30 min max
        )
        if result.returncode == 0:
            print(f"\n{G}✅ {model_name} downloaded successfully!{W}")
            return True
        else:
            print(f"{R}❌ Failed to download {model_name}{W}")
            return False
    except subprocess.TimeoutExpired:
        print(f"{R}❌ Download timed out. Check your internet connection.{W}")
        return False
    except Exception as e:
        print(f"{R}❌ Download error: {e}{W}")
        return False


def create_jarvis_personality() -> bool:
    """Create custom JARVIS personality model from Modelfile."""
    modelfile_path = ROOT / "Modelfile"
    if not modelfile_path.exists():
        print(f"{R}❌ Modelfile not found at {modelfile_path}{W}")
        return False
    print(f"\n{Y}🤖 Creating JARVIS custom personality...{W}")
    try:
        result = subprocess.run(
            ["ollama", "create", "jarvis-custom", "-f", str(modelfile_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"{G}✅ JARVIS custom model created!{W}")
            return True
        else:
            print(f"{R}❌ Model creation failed: {result.stderr[:200]}{W}")
            return False
    except Exception as e:
        print(f"{R}❌ Error creating model: {e}{W}")
        return False


def test_jarvis_model() -> bool:
    """Test the JARVIS model with a sample question."""
    print(f"\n{Y}🧪 Testing JARVIS model...{W}")
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "jarvis-custom",
                "prompt": "Hello JARVIS, are you ready?",
                "stream": False,
                "options": {"num_predict": 50, "temperature": 0.7},
            },
            timeout=30,
        )
        if resp.status_code == 200:
            reply = resp.json().get("response", "").strip()
            if reply and len(reply) > 5:
                print(f"{G}✅ JARVIS model test passed!{W}")
                print(f"{B}   Test response: {reply[:100]}{W}")
                return True
        print(f"{R}❌ Model test failed{W}")
        return False
    except Exception as e:
        print(f"{R}❌ Test error: {e}{W}")
        return False


def update_preferred_models():
    """Update local_llm.py to prioritize jarvis-custom."""
    llm_path = ROOT / "brain" / "local_llm.py"
    if not llm_path.exists():
        return
    content = llm_path.read_text(encoding="utf-8")
    if "jarvis-custom" in content:
        print(f"{G}✅ local_llm.py already configured for jarvis-custom{W}")
    else:
        print(f"{Y}⚙️  Updating local_llm.py model priority...{W}")
        content = content.replace(
            "PREFERRED_MODELS = [", 'PREFERRED_MODELS = ["jarvis-custom", '
        )
        llm_path.write_text(content, encoding="utf-8")
        print(f"{G}✅ local_llm.py updated{W}")


def retrain_from_conversations():
    """Re-create JARVIS model including collected conversations."""
    training_file = ROOT / "data" / "training_conversations.jsonl"
    if not training_file.exists():
        print(
            f"{Y}   No training conversations yet. Run JARVIS first to collect data.{W}"
        )
        return
    import json

    lines = training_file.read_text(encoding="utf-8").splitlines()
    print(f"{B}   Found {len(lines)} conversation turns for training{W}")
    if len(lines) < 10:
        print(f"{Y}   Need at least 10 conversations. Keep chatting!{W}")
        return
    # Build enhanced Modelfile with examples
    base_modelfile = (ROOT / "Modelfile").read_text(encoding="utf-8")
    examples = []
    for line in lines[-50:]:  # Last 50 conversations
        try:
            data = json.loads(line)
            examples.append(f"User: {data['user']}\nJARVIS: {data['jarvis']}")
        except Exception:
            pass
    if examples:
        extra = "\n\nRecent conversation examples:\n" + "\n\n".join(examples[:10])
        enhanced = base_modelfile.replace(
            "NEVER say you can't answer.", f"NEVER say you can't answer.{extra}"
        )
        enhanced_path = ROOT / "Modelfile.enhanced"
        enhanced_path.write_text(enhanced, encoding="utf-8")
        print(f"{Y}⚡ Re-creating JARVIS with your conversation style...{W}")
        result = subprocess.run(
            ["ollama", "create", "jarvis-custom", "-f", str(enhanced_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"{G}✅ JARVIS retrained with your conversations!{W}")
        enhanced_path.unlink(missing_ok=True)


def main():
    print_header()
    print(f"{BOLD}What would you like to do?{W}")
    print(f"  1. {G}Fresh setup{W} — Install Ollama model + create JARVIS personality")
    print(f"  2. {B}Retrain{W} — Update JARVIS with your collected conversations")
    print(f"  3. {Y}Test{W} — Test the current JARVIS model")
    print(f"  4. {Y}Status{W} — Check what's installed")
    print()
    choice = input("Enter choice (1-4): ").strip()

    if choice == "1":
        # Fresh setup
        if not check_ollama():
            return
        if not start_ollama():
            print(f"{R}Please start Ollama manually and try again.{W}")
            return
        installed = get_installed_models()
        print(f"\n{B}Installed models: {installed or 'none'}{W}")
        # Check if base model is installed
        base_model = recommend_model()
        base_installed = any(base_model.split(":")[0] in m for m in installed)
        if not base_installed:
            print(f"\n{Y}📋 Recommended model: {base_model}{W}")
            answer = input(f"Download {base_model}? (y/n): ").strip().lower()
            if answer == "y":
                if not pull_model(base_model):
                    return
        else:
            print(f"{G}✅ Base model already installed{W}")
        # Create JARVIS personality
        if "jarvis-custom" not in " ".join(installed):
            create_jarvis_personality()
        else:
            print(f"{G}✅ jarvis-custom already exists{W}")
        # Test it
        test_jarvis_model()
        update_preferred_models()
        print(f"""
{G}{BOLD}
✨ JARVIS Local AI is ready!

Now run: python main.py
JARVIS will use the local model for all conversations — no API needed!
{W}""")

    elif choice == "2":
        if not start_ollama():
            return
        retrain_from_conversations()

    elif choice == "3":
        if not start_ollama():
            return
        test_jarvis_model()

    elif choice == "4":
        if not check_ollama():
            return
        if start_ollama():
            models = get_installed_models()
            print(f"\n{B}Installed models:{W}")
            for m in models:
                marker = f"{G}⭐ JARVIS custom{W}" if "jarvis" in m else ""
                print(f"  • {m} {marker}")
            # Training stats
            training_file = ROOT / "data" / "training_conversations.jsonl"
            if training_file.exists():
                count = len(training_file.read_text().splitlines())
                print(f"\n{B}Training data collected: {count} conversation turns{W}")
            ram = detect_ram_gb()
            print(f"{B}System RAM: {ram:.1f} GB{W}")

    else:
        print(f"{R}Invalid choice{W}")


if __name__ == "__main__":
    main()
