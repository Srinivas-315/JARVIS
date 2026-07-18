"""
JARVIS — brain/free_api_handler.py
Free AI API Handler - Groq, OpenRouter, HuggingFace, Google AI Studio (No quotas!)

This module provides unlimited free AI responses without API quotas.
Falls back between Groq → OpenRouter → HuggingFace → Google AI Studio.

Setup:
  1. Groq API Key: https://console.groq.com/ (free account)
  2. HuggingFace Token: https://huggingface.co/settings/tokens
  3. Google AI Studio: https://aistudio.google.com/app/apikey

Environment variables:
  GROQ_API_KEY=gsk_xxxxx
  HUGGINGFACE_TOKEN=hf_xxxxx
  GOOGLE_AI_STUDIO_KEY=AIza_xxxxx (alternative to GEMINI_API_KEY)
"""

import json
import os
import time
from datetime import datetime
from typing import Optional

import requests
from dotenv import load_dotenv

from utils.logger import log

# Load environment variables
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_ENV_PATH)

# ══════════════════════════════════════════════════════════════
# API Keys & Endpoints
# ══════════════════════════════════════════════════════════════

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "")
GOOGLE_AI_STUDIO_KEY = os.getenv("GOOGLE_AI_STUDIO_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
HUGGINGFACE_ENDPOINT = "https://router.huggingface.co/v1/chat/completions"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Default timeout (seconds)
REQUEST_TIMEOUT = 30

# Rate limiting trackers
_groq_last_call = 0
_hf_last_call = 0
_or_last_call = 0
_groq_calls_minute = 0


# ══════════════════════════════════════════════════════════════
# Rate Limiting Functions
# ══════════════════════════════════════════════════════════════


def _check_groq_rate_limit():
    """Groq has 30 requests/minute limit. Enforce it."""
    global _groq_last_call, _groq_calls_minute

    current_time = time.time()

    # Reset counter every minute
    if current_time - _groq_last_call > 60:
        _groq_calls_minute = 0

    if _groq_calls_minute >= 30:
        wait_time = 60 - (current_time - _groq_last_call)
        if wait_time > 0:
            log.warning(f"Groq rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time + 1)
            _groq_calls_minute = 0

    _groq_calls_minute += 1
    _groq_last_call = current_time


def _check_hf_rate_limit():
    """HuggingFace has gentle rate limiting. Add small delay between calls."""
    global _hf_last_call

    current_time = time.time()
    time_since_last = current_time - _hf_last_call

    # Enforce minimum 1 second between requests to be respectful
    if time_since_last < 1.0:
        time.sleep(1.0 - time_since_last)

    _hf_last_call = time.time()


# ══════════════════════════════════════════════════════════════
# Groq API Handler (FASTEST - 0.5-1s response)
# ══════════════════════════════════════════════════════════════


class GroqHandler:
    """Ultra-fast Groq API - free tier with 30 req/min"""

    @staticmethod
    def is_available() -> bool:
        """Check if Groq API key is configured."""
        return bool(GROQ_API_KEY and GROQ_API_KEY.strip())

    @staticmethod
    def ask(
        prompt: str, system_prompt: str = "", model: str = "llama-3.3-70b-versatile"
    ) -> Optional[str]:
        """
        Send request to Groq API.

        Args:
            prompt: User message
            system_prompt: System instruction/personality
            model: Model name (llama-3.2-3b-preview, mixtral-8x7b-32768, etc)

        Returns:
            Response text or None if failed
        """
        if not GroqHandler.is_available():
            return None

        try:
            _check_groq_rate_limit()

            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            }

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.7,
                "top_p": 0.9,
            }

            response = requests.post(
                GROQ_ENDPOINT, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if content:
                    log.debug(f"✅ Groq response: {len(content)} chars")
                    return content
            else:
                log.warning(f"Groq error {response.status_code}: {response.text[:100]}")
                return None

        except requests.Timeout:
            log.warning("Groq request timeout")
            return None
        except Exception as e:
            log.warning(f"Groq error: {e}")
            return None


# ══════════════════════════════════════════════════════════════
# HuggingFace Inference API Handler (FREE - unlimited)
# ══════════════════════════════════════════════════════════════


class HuggingFaceHandler:
    """Free HuggingFace Inference API - unlimited with rate limiting"""

    @staticmethod
    def is_available() -> bool:
        """Check if HuggingFace token is configured."""
        return bool(HUGGINGFACE_TOKEN and HUGGINGFACE_TOKEN.strip())

    @staticmethod
    def ask(
        prompt: str,
        system_prompt: str = "",
        model: str = "meta-llama/Llama-3.2-3B-Instruct",
    ) -> Optional[str]:
        """
        Send request to HuggingFace Inference API.

        Args:
            prompt: User message
            system_prompt: System instruction/personality
            model: HuggingFace model ID

        Returns:
            Response text or None if failed
        """
        if not HuggingFaceHandler.is_available():
            return None

        try:
            _check_hf_rate_limit()

            headers = {
                "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
                "Content-Type": "application/json",
            }

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.7,
            }

            response = requests.post(
                HUGGINGFACE_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if content:
                    log.debug(f"✅ HuggingFace response: {len(content)} chars")
                    return content
            else:
                log.warning(
                    f"HuggingFace error {response.status_code}: {response.text[:100]}"
                )
                return None

        except requests.Timeout:
            log.warning("HuggingFace request timeout")
            return None
        except Exception as e:
            log.warning(f"HuggingFace error: {e}")
            return None


# ══════════════════════════════════════════════════════════════
# OpenRouter API Handler (FREE models + paid models)
# ══════════════════════════════════════════════════════════════


def _check_openrouter_rate_limit():
    """OpenRouter has gentle rate limits. Enforce 1s gap."""
    global _or_last_call

    current_time = time.time()
    time_since_last = current_time - _or_last_call

    if time_since_last < 1.0:
        time.sleep(1.0 - time_since_last)

    _or_last_call = time.time()


class OpenRouterHandler:
    """OpenRouter API - access to many free models via one API key"""

    # Free models on OpenRouter (no credit card needed — updated Apr 2026)
    FREE_MODELS = [
        "google/gemma-4-31b-it:free",                  # Google Gemma 4 31B — best free!
        "openai/gpt-oss-120b:free",                    # OpenAI GPT-OSS 120B — huge
        "qwen/qwen3-next-80b-a3b-instruct:free",       # Qwen 3 Next 80B — smart
        "nvidia/nemotron-3-super-120b-a12b:free",       # NVIDIA Nemotron 120B
        "google/gemma-3-4b-it:free",                    # Google Gemma 3 4B — fast fallback
    ]

    @staticmethod
    def is_available() -> bool:
        """Check if OpenRouter API key is configured."""
        return bool(OPENROUTER_API_KEY and OPENROUTER_API_KEY.strip())

    @staticmethod
    def ask(
        prompt: str, system_prompt: str = "", model: str = None
    ) -> Optional[str]:
        """
        Send request to OpenRouter API.

        Tries free models in order. If one fails, tries the next.

        Args:
            prompt: User message
            system_prompt: System instruction/personality
            model: Specific model (None = try free models in order)

        Returns:
            Response text or None if failed
        """
        if not OpenRouterHandler.is_available():
            return None

        models_to_try = [model] if model else OpenRouterHandler.FREE_MODELS

        for m in models_to_try:
            try:
                _check_openrouter_rate_limit()

                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/jarvis-assistant",
                    "X-Title": "JARVIS AI Assistant",
                }

                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": m,
                    "messages": messages,
                    "max_tokens": 1000,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }

                response = requests.post(
                    OPENROUTER_ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if content:
                        log.debug(
                            f"✅ OpenRouter ({m.split('/')[-1]}) response: "
                            f"{len(content)} chars"
                        )
                        return content
                elif response.status_code == 429:
                    log.warning(f"OpenRouter rate limited on {m}, trying next...")
                    continue
                else:
                    log.warning(
                        f"OpenRouter error {response.status_code} on {m}: "
                        f"{response.text[:100]}"
                    )
                    continue

            except requests.Timeout:
                log.warning(f"OpenRouter timeout on {m}")
                continue
            except Exception as e:
                log.warning(f"OpenRouter error on {m}: {e}")
                continue

        return None



# ══════════════════════════════════════════════════════════════
# Google AI Studio Handler (FREE - higher limits than Gemini API)
# ══════════════════════════════════════════════════════════════


class GoogleAIStudioHandler:
    """Google's free AI Studio API - 1500 requests/day"""

    @staticmethod
    def is_available() -> bool:
        """Check if Google AI Studio key is configured."""
        return bool(GOOGLE_AI_STUDIO_KEY and GOOGLE_AI_STUDIO_KEY.strip())

    @staticmethod
    def ask(prompt: str, system_prompt: str = "") -> Optional[str]:
        """
        Send request to Google AI Studio (Gemini 2.0 Flash).

        Args:
            prompt: User message
            system_prompt: System instruction/personality

        Returns:
            Response text or None if failed
        """
        if not GoogleAIStudioHandler.is_available():
            return None

        try:
            import google.generativeai as genai

            genai.configure(api_key=GOOGLE_AI_STUDIO_KEY)

            model = genai.GenerativeModel("gemini-2.0-flash")

            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\nUser: {prompt}"

            response = model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_output_tokens": 1000,
                },
            )

            if response and response.text:
                content = response.text.strip()
                log.debug(f"✅ Google AI Studio response: {len(content)} chars")
                return content

        except ImportError:
            log.warning("google-generativeai not installed")
        except Exception as e:
            log.warning(f"Google AI Studio error: {e}")

        return None


# ══════════════════════════════════════════════════════════════
# Multi-API Fallback Handler
# ══════════════════════════════════════════════════════════════


class FreeAPIHandler:
    """
    Smart fallback between free APIs.
    Priority: Groq (fastest) → HuggingFace → Google AI Studio
    """

    def __init__(self):
        self._api_stats = {
            "groq": {"success": 0, "fail": 0},
            "openrouter": {"success": 0, "fail": 0},
            "huggingface": {"success": 0, "fail": 0},
            "google": {"success": 0, "fail": 0},
        }
        self._available_apis = self._detect_available_apis()

    def _detect_available_apis(self) -> list:
        """Detect which APIs are configured."""
        available = []

        if GroqHandler.is_available():
            available.append("groq")
            log.info("✅ Groq API available (Llama 3.3 70B, 30 req/min)")
        else:
            log.info("❌ Groq API not configured")

        if OpenRouterHandler.is_available():
            available.append("openrouter")
            log.info("✅ OpenRouter API available (Gemma 2, Llama 3.1, Mistral)")
        else:
            log.info("❌ OpenRouter API not configured")

        if HuggingFaceHandler.is_available():
            available.append("huggingface")
            log.info("✅ HuggingFace API available (unlimited)")
        else:
            log.info("❌ HuggingFace API not configured")

        if GoogleAIStudioHandler.is_available():
            available.append("google")
            log.info("✅ Google AI Studio available (1500/day)")
        else:
            log.info("❌ Google AI Studio not configured")

        return available

    def is_available(self) -> bool:
        """Check if at least one free API is configured."""
        return len(self._available_apis) > 0

    def ask(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """
        Try free APIs in priority order: Groq → HuggingFace → Google.

        Args:
            prompt: User message
            system_prompt: System instruction

        Returns:
            Response from first successful API, or None
        """
        if not self._available_apis:
            return None

        # Priority order: Groq (fastest) → OpenRouter (smart) → HuggingFace → Google
        api_order = ["groq", "openrouter", "huggingface", "google"]

        for api_name in api_order:
            if api_name not in self._available_apis:
                continue

            log.debug(f"Trying {api_name}...")
            response = None

            try:
                if api_name == "groq":
                    response = GroqHandler.ask(prompt, system_prompt)
                elif api_name == "openrouter":
                    response = OpenRouterHandler.ask(prompt, system_prompt)
                elif api_name == "huggingface":
                    response = HuggingFaceHandler.ask(prompt, system_prompt)
                elif api_name == "google":
                    response = GoogleAIStudioHandler.ask(prompt, system_prompt)

                if response:
                    self._api_stats[api_name]["success"] += 1
                    log.info(f"✅ Response via {api_name}")
                    return response
                else:
                    self._api_stats[api_name]["fail"] += 1

            except Exception as e:
                log.warning(f"{api_name} failed: {e}")
                self._api_stats[api_name]["fail"] += 1

        log.warning("All free APIs failed or not configured")
        return None

    def get_stats(self) -> dict:
        """Get API usage statistics."""
        return self._api_stats

    def get_available_apis(self) -> list:
        """Get list of available APIs."""
        return self._available_apis


# ══════════════════════════════════════════════════════════════
# Conversation Auto-Learning System
# ══════════════════════════════════════════════════════════════


class ConversationLogger:
    """
    Auto-log conversations for future model retraining.
    Saves to data/free_api_conversations.jsonl
    """

    def __init__(self, log_file: str = "data/free_api_conversations.jsonl"):
        self.log_file = log_file
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    def log_conversation(self, user_input: str, jarvis_response: str, api_used: str):
        """Log a conversation turn."""
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "user": user_input,
                "jarvis": jarvis_response,
                "api": api_used,
                "length": len(jarvis_response),
            }

            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        except Exception as e:
            log.warning(f"Failed to log conversation: {e}")

    def get_conversation_count(self) -> int:
        """Get total logged conversations."""
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except:
            return 0

    def should_retrain(self, threshold: int = 500) -> bool:
        """Check if we have enough conversations to retrain."""
        return self.get_conversation_count() >= threshold

    def export_for_training(self) -> str:
        """Export conversations in training format."""
        conversations = []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        conversations.append(entry)
                    except:
                        pass
        except:
            pass

        return json.dumps(conversations, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════
# Testing & Validation
# ══════════════════════════════════════════════════════════════


def test_free_apis():
    """Test all configured free APIs."""
    print("\n🧪 Testing Free APIs...\n")

    handler = FreeAPIHandler()

    test_prompt = "What is 2+2? Answer in one sentence."
    system = "You are a helpful AI assistant."

    print(f"Available APIs: {handler.get_available_apis()}")
    print(f"\nTesting with prompt: '{test_prompt}'\n")

    # Test Groq
    if GroqHandler.is_available():
        print("🔵 Testing Groq...")
        start = time.time()
        response = GroqHandler.ask(test_prompt, system)
        elapsed = time.time() - start
        print(f"   Response: {response}")
        print(f"   Time: {elapsed:.2f}s\n")

    # Test HuggingFace
    if HuggingFaceHandler.is_available():
        print("🟣 Testing HuggingFace...")
        start = time.time()
        response = HuggingFaceHandler.ask(test_prompt, system)
        elapsed = time.time() - start
        print(f"   Response: {response}")
        print(f"   Time: {elapsed:.2f}s\n")

    # Test Google AI Studio
    if GoogleAIStudioHandler.is_available():
        print("🔴 Testing Google AI Studio...")
        start = time.time()
        response = GoogleAIStudioHandler.ask(test_prompt, system)
        elapsed = time.time() - start
        print(f"   Response: {response}")
        print(f"   Time: {elapsed:.2f}s\n")

    # Test fallback handler
    print("🟢 Testing Fallback Handler...")
    start = time.time()
    response = handler.ask(test_prompt, system)
    elapsed = time.time() - start
    print(f"   Response: {response}")
    print(f"   Time: {elapsed:.2f}s")
    print(f"   Stats: {handler.get_stats()}\n")


if __name__ == "__main__":
    test_free_apis()
