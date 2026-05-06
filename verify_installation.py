#!/usr/bin/env python3
"""
JARVIS — verify_installation.py
Quick installation verification for unlimited free AI system.

Checks:
  ✅ All new modules importable
  ✅ Dependencies installed
  ✅ Configuration valid
  ✅ Optional APIs configured
  ✅ Database initialized

Run: python verify_installation.py
"""

import os
import sys
from pathlib import Path

# Add root to path
sys.path.insert(0, str(Path(__file__).parent))


def check_imports():
    """Check if all new modules can be imported."""
    print("\n" + "=" * 70)
    print("CHECKING IMPORTS")
    print("=" * 70)

    modules_to_check = [
        ("brain.free_api_handler", "Free API Handler"),
        ("brain.conversation_learner", "Conversation Learner"),
        ("brain.local_llm", "Local LLM (Ollama)"),
        ("brain.gemini_handler", "Gemini Handler"),
        ("utils.logger", "Logger"),
    ]

    results = []
    for module_name, display_name in modules_to_check:
        try:
            __import__(module_name)
            print(f"  ✅ {display_name:30} — OK")
            results.append(True)
        except ImportError as e:
            print(f"  ❌ {display_name:30} — FAILED: {e}")
            results.append(False)
        except Exception as e:
            print(f"  ⚠️  {display_name:30} — ERROR: {e}")
            results.append(False)

    return all(results)


def check_dependencies():
    """Check if required packages are installed."""
    print("\n" + "=" * 70)
    print("CHECKING DEPENDENCIES")
    print("=" * 70)

    dependencies = [
        ("requests", "HTTP requests"),
        ("dotenv", "Environment variables"),
        ("google.generativeai", "Google Generative AI (optional)"),
        ("groq", "Groq API (optional)"),
        ("huggingface_hub", "HuggingFace Hub (optional)"),
        ("sqlite3", "SQLite (built-in)"),
    ]

    results = []
    for package_name, display_name in dependencies:
        try:
            __import__(package_name)
            is_optional = "(optional)" in display_name
            symbol = "⚠️ " if is_optional else "✅"
            print(f"  {symbol} {display_name:40} — OK")
            results.append(True)
        except ImportError:
            is_optional = "(optional)" in display_name
            symbol = "⚠️ " if is_optional else "❌"
            print(f"  {symbol} {display_name:40} — NOT INSTALLED")
            results.append(is_optional)  # Pass if optional
        except Exception as e:
            print(f"  ⚠️  {display_name:40} — ERROR: {e}")
            results.append(False)

    return all(results)


def check_files():
    """Check if configuration and data files exist."""
    print("\n" + "=" * 70)
    print("CHECKING FILES")
    print("=" * 70)

    files_to_check = [
        (".env", "Environment configuration", False),
        ("config.py", "Main configuration", True),
        ("main.py", "Main JARVIS script", True),
        ("Modelfile", "Ollama model file", False),
        ("FREE_AI_SETUP.txt", "Setup guide", True),
        ("UPGRADE_COMPLETE.md", "Upgrade documentation", True),
        ("test_free_api_system.py", "Test suite", True),
        ("brain/free_api_handler.py", "Free API handler", True),
        ("brain/conversation_learner.py", "Conversation learner", True),
        ("brain/gemini_handler.py", "Gemini handler", True),
        ("data/", "Data directory", False),
    ]

    results = []
    for file_name, display_name, required in files_to_check:
        path = Path(file_name)
        exists = path.exists()

        if exists:
            print(f"  ✅ {display_name:40} — EXISTS")
            results.append(True)
        elif required:
            print(f"  ❌ {display_name:40} — MISSING (required)")
            results.append(False)
        else:
            print(f"  ⚠️  {display_name:40} — NOT FOUND (optional)")
            results.append(True)

    return all(results)


def check_configuration():
    """Check if .env is properly configured."""
    print("\n" + "=" * 70)
    print("CHECKING CONFIGURATION")
    print("=" * 70)

    env_path = Path(".env")

    if not env_path.exists():
        print("  ⚠️  .env file not found (optional)")
        print("     Create one using: cp .env.example .env")
        print("     Or manually add API keys")
        return True

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)

        # Check for API keys
        api_keys = {
            "GEMINI_API_KEY": "Gemini API (optional)",
            "GROQ_API_KEY": "Groq API (optional)",
            "HUGGINGFACE_TOKEN": "HuggingFace token (optional)",
            "GOOGLE_AI_STUDIO_KEY": "Google AI Studio (optional)",
            "USER_NAME": "User name (optional)",
            "USER_CITY": "User city (optional)",
        }

        configured = []
        not_configured = []

        for key, display_name in api_keys.items():
            value = os.getenv(key, "").strip()
            if value:
                print(f"  ✅ {display_name:40} — CONFIGURED")
                configured.append(key)
            else:
                is_optional = "(optional)" in display_name
                symbol = "⚠️ " if is_optional else "❌"
                print(f"  {symbol} {display_name:40} — NOT SET")
                not_configured.append(key)

        print(
            f"\n  Summary: {len(configured)} configured, {len(not_configured)} not set"
        )
        print("  Note: Optional APIs can be added later for more features")

        return True

    except Exception as e:
        print(f"  ❌ Error reading .env: {e}")
        return False


def check_database():
    """Check if conversation database is initialized."""
    print("\n" + "=" * 70)
    print("CHECKING DATABASE")
    print("=" * 70)

    try:
        from brain.conversation_learner import ConversationDatabase

        db = ConversationDatabase()
        count = db.get_total_conversations()

        print(f"  ✅ Conversation database initialized")
        print(f"     Total conversations logged: {count}")

        return True

    except Exception as e:
        print(f"  ⚠️  Could not initialize database: {e}")
        print("     It will be created on first use")
        return True


def check_ollama():
    """Check if Ollama is running and has models."""
    print("\n" + "=" * 70)
    print("CHECKING OLLAMA (Optional)")
    print("=" * 70)

    try:
        import requests

        resp = requests.get("http://localhost:11434/api/tags", timeout=2)

        if resp.status_code == 200:
            models = resp.json().get("models", [])
            if models:
                print(f"  ✅ Ollama is running!")
                print(f"     Models installed: {len(models)}")
                for model in models[:3]:
                    print(f"       - {model['name']}")
                if len(models) > 3:
                    print(f"       ... and {len(models) - 3} more")
                return True
            else:
                print("  ⚠️  Ollama is running but no models installed")
                print("     Run: ollama pull llama3.2:3b")
                return True
        else:
            print("  ⚠️  Ollama returned error status")
            return False

    except requests.ConnectionError:
        print("  ⚠️  Ollama not running")
        print("     Download: https://ollama.com/download")
        print("     Run: ollama serve")
        return True

    except Exception as e:
        print(f"  ⚠️  Could not check Ollama: {e}")
        return True


def check_free_apis():
    """Check which free APIs are configured."""
    print("\n" + "=" * 70)
    print("CHECKING FREE APIs")
    print("=" * 70)

    try:
        from brain.free_api_handler import FreeAPIHandler

        handler = FreeAPIHandler()
        available = handler.get_available_apis()

        if available:
            print(f"  ✅ Free APIs configured: {', '.join(available)}")
            for api_name in available:
                stats = handler.get_stats()[api_name]
                print(f"     - {api_name}: {stats}")
            return True
        else:
            print("  ⚠️  No free APIs configured (optional)")
            print("     See FREE_AI_SETUP.txt for setup instructions")
            return True

    except Exception as e:
        print(f"  ⚠️  Could not check free APIs: {e}")
        return True


def print_summary(results):
    """Print verification summary."""
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    checks = [
        "Imports",
        "Dependencies",
        "Files",
        "Configuration",
        "Database",
        "Ollama (Optional)",
        "Free APIs (Optional)",
    ]

    passed = sum(results)
    total = len(results)

    for check_name, result in zip(checks, results):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  — {check_name}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if results[0] and results[1] and results[2]:
        print("\n✅ JARVIS is ready to use!")
        print("\nNext steps:")
        print("  1. python main.py")
        print("  2. Say 'Hello JARVIS'")
        print("  3. Enjoy unlimited AI!")

        if not any(results[3:]):
            print("\nOptional: Configure APIs for more features:")
            print("  See FREE_AI_SETUP.txt for instructions")

    else:
        print("\n❌ Some required checks failed")
        print("   Please fix the issues above and try again")

    print("\n" + "=" * 70)


def main():
    """Run all verification checks."""
    print("\n" + "=" * 70)
    print("JARVIS INSTALLATION VERIFICATION")
    print("=" * 70)

    results = [
        check_imports(),
        check_dependencies(),
        check_files(),
        check_configuration(),
        check_database(),
        check_ollama(),
        check_free_apis(),
    ]

    print_summary(results)

    # Exit code
    if all(results[:3]):  # If core checks pass
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
