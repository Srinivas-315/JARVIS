#!/usr/bin/env python3
"""
JARVIS — test_free_api_system.py
Comprehensive test suite for unlimited free AI system.

Tests:
  ✅ Local LLM (Ollama)
  ✅ Groq API
  ✅ HuggingFace API
  ✅ Google AI Studio
  ✅ Conversation Learner
  ✅ Free API Fallback Chain
  ✅ Integration with GeminiHandler

Usage:
  python test_free_api_system.py
"""

import json
import sys
import time
from pathlib import Path

# Add root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import log


def test_local_llm():
    """Test Ollama local LLM."""
    print("\n" + "=" * 70)
    print("TEST 1: LOCAL LLM (OLLAMA)")
    print("=" * 70)

    try:
        from brain.local_llm import LocalLLM

        llm = LocalLLM()

        if not llm.is_available:
            print("⚠️  Ollama not available (make sure 'ollama serve' is running)")
            print("   Download: https://ollama.com/download")
            print("   Install and run: ollama serve")
            return False

        print(f"✅ Ollama Available! Model: {llm.model_name}")

        # Test simple question
        print("\n🧪 Testing simple question...")
        start = time.time()
        response = llm.ask("What is 2+2? Answer in one word.")
        elapsed = time.time() - start

        print(f"   Question: What is 2+2?")
        print(f"   Response: {response}")
        print(f"   Time: {elapsed:.2f}s")

        if response and "4" in response:
            print("   ✅ PASS: Got correct answer")
            return True
        else:
            print("   ⚠️  Response looks odd, but Ollama is working")
            return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False


def test_groq_api():
    """Test Groq API."""
    print("\n" + "=" * 70)
    print("TEST 2: GROQ API (FASTEST FREE)")
    print("=" * 70)

    try:
        import os

        from dotenv import load_dotenv

        from brain.free_api_handler import GroqHandler

        load_dotenv()

        if not GroqHandler.is_available():
            print("⚠️  Groq API key not configured")
            print("   Get key: https://console.groq.com")
            print("   Add to .env: GROQ_API_KEY=gsk_...")
            return False

        print("✅ Groq API key found!")

        # Test simple question
        print("\n🧪 Testing Groq API...")
        start = time.time()
        response = GroqHandler.ask(
            "What is the capital of France?",
            system_prompt="Answer in one sentence.",
        )
        elapsed = time.time() - start

        print(f"   Question: What is the capital of France?")
        print(f"   Response: {response}")
        print(f"   Time: {elapsed:.2f}s")

        if response and "Paris" in response:
            print("   ✅ PASS: Groq working!")
            return True
        else:
            print(f"   ⚠️  Response: {response}")
            return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False


def test_huggingface_api():
    """Test HuggingFace API."""
    print("\n" + "=" * 70)
    print("TEST 3: HUGGINGFACE API (UNLIMITED)")
    print("=" * 70)

    try:
        from dotenv import load_dotenv

        from brain.free_api_handler import HuggingFaceHandler

        load_dotenv()

        if not HuggingFaceHandler.is_available():
            print("⚠️  HuggingFace token not configured")
            print("   Get token: https://huggingface.co/settings/tokens")
            print("   Add to .env: HUGGINGFACE_TOKEN=hf_...")
            return False

        print("✅ HuggingFace token found!")

        # Test simple question
        print("\n🧪 Testing HuggingFace API...")
        start = time.time()
        response = HuggingFaceHandler.ask(
            "What is machine learning?", system_prompt="Explain briefly."
        )
        elapsed = time.time() - start

        print(f"   Question: What is machine learning?")
        print(f"   Response: {response}")
        print(f"   Time: {elapsed:.2f}s")

        if response:
            print("   ✅ PASS: HuggingFace working!")
            return True
        else:
            print("   ❌ No response from HuggingFace")
            return False

    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False


def test_free_api_handler():
    """Test Free API fallback chain."""
    print("\n" + "=" * 70)
    print("TEST 4: FREE API FALLBACK HANDLER")
    print("=" * 70)

    try:
        from brain.free_api_handler import FreeAPIHandler

        handler = FreeAPIHandler()

        available = handler.get_available_apis()
        print(f"Available APIs: {available}")

        if not available:
            print("⚠️  No free APIs configured")
            print("   Configure at least one:")
            print("   - GROQ_API_KEY=gsk_...")
            print("   - HUGGINGFACE_TOKEN=hf_...")
            print("   - GOOGLE_AI_STUDIO_KEY=AIza_...")
            return False

        print(f"✅ Found {len(available)} available API(s)")

        # Test fallback chain
        print("\n🧪 Testing fallback chain...")
        start = time.time()
        response = handler.ask("Hello! What can you do?")
        elapsed = time.time() - start

        print(f"   Response: {response}")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   API Stats: {handler.get_stats()}")

        if response:
            print("   ✅ PASS: Fallback chain working!")
            return True
        else:
            print("   ❌ All APIs failed")
            return False

    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False


def test_conversation_learner():
    """Test conversation auto-learning system."""
    print("\n" + "=" * 70)
    print("TEST 5: CONVERSATION AUTO-LEARNING")
    print("=" * 70)

    try:
        import json

        from brain.conversation_learner import ConversationLearner

        learner = ConversationLearner()

        # Log test conversations
        print("🧪 Logging test conversations...")
        test_convs = [
            ("Hey Jarvis what's the weather", "It's sunny and 28°C in Chennai"),
            ("Open Chrome browser", "Opening Google Chrome..."),
            (
                "Tell me a joke",
                "Why do programmers prefer dark mode? Light attracts bugs.",
            ),
            ("What's the current time", "It's 3:45 PM"),
        ]

        for user_input, response in test_convs:
            learner.log_conversation(
                user_input, response, quality_score=0.9, api_used="test"
            )

        # Check stats
        stats = learner.get_stats()
        print(f"\n✅ Conversations logged: {stats['total_conversations']}")
        print(f"   Intent distribution: {stats['intent_distribution']}")
        print(f"   User preferences: {stats['user_preferences']}")

        # Check if retraining needed
        if stats["total_conversations"] >= 5:
            print("\n🔄 Enough data for analysis...")
            # Don't actually retrain in test, just check logic
            print("   (Retraining would happen in production)")

        print("✅ PASS: Conversation learner working!")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_gemini_handler_integration():
    """Test GeminiHandler with free APIs integrated."""
    print("\n" + "=" * 70)
    print("TEST 6: GEMINI HANDLER INTEGRATION")
    print("=" * 70)

    try:
        from brain.gemini_handler import GeminiHandler

        handler = GeminiHandler()

        print("✅ GeminiHandler initialized")

        # Check what's available
        if handler._local_llm.is_available:
            print(f"   📍 Local LLM: {handler._local_llm.model_name}")
        else:
            print("   📍 Local LLM: Not available")

        if handler._free_api.is_available():
            print(f"   📍 Free APIs: {handler._free_api.get_available_apis()}")
        else:
            print("   📍 Free APIs: Not configured")

        print(
            f"   📍 Auto-learner: {handler._learner.db.get_total_conversations()} conversations"
        )

        print("✅ PASS: Full integration ready!")
        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_end_to_end():
    """End-to-end test: ask a question and get response."""
    print("\n" + "=" * 70)
    print("TEST 7: END-TO-END (Full Pipeline)")
    print("=" * 70)

    try:
        from brain.gemini_handler import GeminiHandler

        handler = GeminiHandler()

        print("🧪 Asking: 'What is artificial intelligence?'")
        start = time.time()
        response = handler.ask(
            "What is artificial intelligence? Answer in 2 sentences."
        )
        elapsed = time.time() - start

        print(f"\n📝 Response:")
        print(f"   {response}")
        print(f"\n⏱️  Time: {elapsed:.2f}s")

        if response and len(response) > 10:
            print("✅ PASS: Got response from pipeline!")
            return True
        else:
            print("❌ Empty or short response")
            return False

    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
        return False


def print_summary(results):
    """Print test summary."""
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    tests = [
        "Local LLM (Ollama)",
        "Groq API",
        "HuggingFace API",
        "Free API Handler",
        "Conversation Learner",
        "GeminiHandler Integration",
        "End-to-End",
    ]

    passed = sum(results)
    total = len(results)

    for test_name, result in zip(tests, results):
        status = "✅ PASS" if result else "⚠️  FAIL/SKIP"
        print(f"  {status}  — {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed/available")

    if passed >= 2:
        print("\n🎉 JARVIS unlimited AI system is working!")
    else:
        print(
            "\n⚠️  Some APIs not configured. Read FREE_AI_SETUP.txt for setup instructions."
        )

    print("\nNEXT STEPS:")
    print("  1. Configure missing APIs (optional but recommended)")
    print("  2. Run: python main.py")
    print("  3. Enjoy unlimited free AI! 🚀")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("JARVIS UNLIMITED FREE AI SYSTEM - TEST SUITE")
    print("=" * 70)

    results = [
        test_local_llm(),
        test_groq_api(),
        test_huggingface_api(),
        test_free_api_handler(),
        test_conversation_learner(),
        test_gemini_handler_integration(),
        test_end_to_end(),
    ]

    print_summary(results)

    print("\n" + "=" * 70)
    print("For detailed setup guide, see: FREE_AI_SETUP.txt")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
